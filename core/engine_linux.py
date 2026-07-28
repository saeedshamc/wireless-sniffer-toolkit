"""
core/engine_linux.py — پیاده‌سازی کامل روی لینوکس (پشتیبانی کامل: "full")
"""

import re
import shutil
import subprocess
import threading

from .base_engine import BaseEngine, EngineError, channels_for_band
from .capture_display import LiveDisplayReader
from .platform_utils import find_tshark, is_admin


def _run(cmd, check=False):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise EngineError(f"{' '.join(cmd)} -> {result.stderr.strip()}")
    return result


class LinuxEngine(BaseEngine):
    support_level = "full"
    caveats = [
        "فقط روی کارت‌هایی که مانیتور مود رو ساپورت کنن کار می‌کنه (اکثر Atheros، بعضی Realtek/MediaTek).",
        "کارت‌های Intel معمولاً مانیتور مود واقعی رو پشتیبانی نمی‌کنن.",
    ]

    def __init__(self, on_log=None):
        super().__init__(on_log)
        self._stop_event = threading.Event()
        self._hopper_thread = None
        self._capture_proc = None
        self._display_reader = None
        self.tshark_path = find_tshark()

    def check_ready(self) -> list:
        problems = []
        if not is_admin():
            problems.append("این برنامه باید با sudo/root اجرا بشه.")
        for tool in ("iw", "ip"):
            if shutil.which(tool) is None:
                problems.append(f"ابزار «{tool}» نصب نیست.")
        if not self.tshark_path:
            problems.append("tshark پیدا نشد (apt install tshark).")
        return problems

    def list_interfaces(self) -> list:
        result = _run(["iw", "dev"])
        return re.findall(r"Interface\s+(\S+)", result.stdout)

    def _enable_monitor_mode(self, iface: str) -> str:
        if shutil.which("airmon-ng"):
            _run(["airmon-ng", "check", "kill"])
            _run(["airmon-ng", "start", iface])
            mon_iface = f"{iface}mon"
            check = _run(["iw", "dev"])
            return mon_iface if mon_iface in check.stdout else iface
        _run(["ip", "link", "set", iface, "down"])
        _run(["iw", iface, "set", "monitor", "none"])
        _run(["ip", "link", "set", iface, "up"])
        return iface

    def _disable_monitor_mode(self, mon_iface: str, original_iface: str):
        if shutil.which("airmon-ng") and mon_iface != original_iface:
            _run(["airmon-ng", "stop", mon_iface])
        else:
            _run(["ip", "link", "set", mon_iface, "down"])
            _run(["iw", mon_iface, "set", "type", "managed"])
            _run(["ip", "link", "set", mon_iface, "up"])

    def _channel_hopper(self, iface: str, channels: list, dwell: float):
        idx = 0
        while not self._stop_event.is_set():
            ch = channels[idx % len(channels)]
            _run(["iw", "dev", iface, "set", "channel", str(ch)])
            self._current_channel = ch
            idx += 1
            self._stop_event.wait(dwell)

    def start(self, iface: str, output_path: str, band: str, dwell: float):
        if self.state.running:
            raise EngineError("سشن قبلی هنوز فعاله.")
        problems = self.check_ready()
        if problems:
            raise EngineError(" | ".join(problems))

        channels = channels_for_band(band)
        self.state.original_iface = iface
        self._log(f"فعال‌سازی مانیتور مود روی {iface} ...")
        mon_iface = self._enable_monitor_mode(iface)
        self.state.monitor_iface = mon_iface
        self._log(f"اینترفیس مانیتور: {mon_iface}")

        self._stop_event.clear()
        self._hopper_thread = threading.Thread(
            target=self._channel_hopper, args=(mon_iface, channels, dwell), daemon=True
        )
        self._hopper_thread.start()

        self._log(f"شروع ذخیره کپچر -> {output_path}")
        self._capture_proc = subprocess.Popen(
            [self.tshark_path, "-i", mon_iface, "-w", output_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        self._display_reader = LiveDisplayReader(self.tshark_path, mon_iface)
        self._display_reader.start()

        self.state.running = True

    def get_live_stats(self):
        if self._display_reader:
            return self._display_reader.snapshot()
        return 0, {}

    def stop(self):
        if not self.state.running:
            return
        self._log("در حال توقف ...")
        self._stop_event.set()
        if self._capture_proc:
            self._capture_proc.terminate()
            try:
                self._capture_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._capture_proc.kill()
        if self._display_reader:
            self._display_reader.stop()
        if self.state.monitor_iface:
            self._log("برگردوندن اینترفیس به حالت managed ...")
            try:
                self._disable_monitor_mode(self.state.monitor_iface, self.state.original_iface)
            except EngineError as e:
                self._log(f"هشدار: {e}")
        self.state.running = False
        self._log("متوقف شد.")
