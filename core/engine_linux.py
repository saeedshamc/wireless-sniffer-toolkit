"""
core/engine_linux.py — پیاده‌سازی کامل روی لینوکس (پشتیبانی کامل: "full")
"""

import os
import re
import shutil
import subprocess
import threading

from .base_engine import BaseEngine, EngineError, channels_for_band
from .capture_display import LiveDisplayReader
from .platform_utils import find_tshark, is_admin
from .process_utils import terminate_process, process_is_alive, ensure_process_started


def _run(cmd, check=False):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise EngineError(f"{' '.join(cmd)} -> {err}")
    return result


class LinuxEngine(BaseEngine):
    support_level = "full"
    caveats = [
        "فقط روی کارت‌هایی که مانیتور مود رو ساپورت کنن کار می‌کنه (اکثر Atheros، بعضی Realtek/MediaTek).",
        "کارت‌های Intel معمولاً مانیتور مود واقعی رو پشتیبانی نمی‌کنن.",
        "برای مانیتور مود، NetworkManager ممکنه موقتاً اینترفیس رو مدیریت نکنه؛ بعد از توقف سعی می‌شه برگرده.",
    ]

    def __init__(self, on_log=None):
        super().__init__(on_log)
        self._stop_event = threading.Event()
        self._hopper_thread = None
        self._capture_proc = None
        self._display_reader = None
        self._used_airmon = False
        self._nm_stopped = False
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
        ifaces = re.findall(r"Interface\s+(\S+)", result.stdout or "")
        return sorted(set(ifaces))

    def _discover_monitor_iface(self, before: set, preferred: str) -> str:
        after = set(self.list_interfaces())
        created = after - before
        if preferred in after:
            return preferred
        if created:
            return sorted(created)[0]
        # بعضی درایورها اسم رو عوض نمی‌کنن
        return preferred if preferred in after else (sorted(after)[0] if after else preferred)

    def _enable_monitor_mode(self, iface: str) -> str:
        before = set(self.list_interfaces())
        self._used_airmon = False
        self._nm_stopped = False

        if shutil.which("airmon-ng"):
            # به‌جای check kill کامل، فقط NetworkManager رو موقتاً متوقف می‌کنیم
            # تا پروسهٔ کاربر (مثل مرورگر) بی‌دلیل کشته نشه.
            nm = shutil.which("systemctl")
            if nm:
                status = _run(["systemctl", "is-active", "NetworkManager"])
                if (status.stdout or "").strip() == "active":
                    _run(["systemctl", "stop", "NetworkManager"])
                    self._nm_stopped = True
                    self._log("NetworkManager موقتاً متوقف شد.")
            before = set(self.list_interfaces())
            result = _run(["airmon-ng", "start", iface])
            self._used_airmon = True
            # airmon معمولاً iface + "mon" می‌سازه؛ ولی همیشه نه
            preferred = f"{iface}mon"
            mon = self._discover_monitor_iface(before, preferred)
            if mon not in self.list_interfaces():
                # پیام خطا از airmon
                detail = (result.stderr or result.stdout or "").strip()
                raise EngineError(
                    f"مانیتور مود روی {iface} فعال نشد. "
                    f"chipset احتمالاً پشتیبانی نمی‌کنه. {detail[:200]}"
                )
            return mon

        _run(["ip", "link", "set", iface, "down"], check=True)
        _run(["iw", iface, "set", "monitor", "none"], check=True)
        _run(["ip", "link", "set", iface, "up"], check=True)
        return iface

    def _disable_monitor_mode(self, mon_iface: str, original_iface: str):
        try:
            if self._used_airmon and shutil.which("airmon-ng") and mon_iface != original_iface:
                _run(["airmon-ng", "stop", mon_iface])
            else:
                _run(["ip", "link", "set", mon_iface, "down"])
                _run(["iw", mon_iface, "set", "type", "managed"])
                _run(["ip", "link", "set", mon_iface, "up"])
        finally:
            if self._nm_stopped and shutil.which("systemctl"):
                _run(["systemctl", "start", "NetworkManager"])
                self._log("NetworkManager دوباره راه‌اندازی شد.")
                self._nm_stopped = False

    def _channel_hopper(self, iface: str, channels: list, dwell: float):
        idx = 0
        while not self._stop_event.is_set():
            ch = channels[idx % len(channels)]
            result = _run(["iw", "dev", iface, "set", "channel", str(ch)])
            if result.returncode == 0:
                self._current_channel = ch
            idx += 1
            self._stop_event.wait(dwell)

    def start(self, iface: str, output_path: str, band: str, dwell: float):
        if self.state.running:
            raise EngineError("سشن قبلی هنوز فعاله.")
        problems = self.check_ready()
        if problems:
            raise EngineError(" | ".join(problems))
        if not iface:
            raise EngineError("اینترفیس مشخص نشده.")

        out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
        if not os.path.isdir(out_dir):
            raise EngineError(f"پوشهٔ خروجی وجود ندارد: {out_dir}")

        channels = channels_for_band(band)
        self.state.original_iface = iface
        self._log(f"فعال‌سازی مانیتور مود روی {iface} ...")
        try:
            mon_iface = self._enable_monitor_mode(iface)
        except EngineError:
            if self._nm_stopped and shutil.which("systemctl"):
                _run(["systemctl", "start", "NetworkManager"])
                self._nm_stopped = False
            raise

        self.state.monitor_iface = mon_iface
        self._log(f"اینترفیس مانیتور: {mon_iface}")

        self._stop_event.clear()
        self._hopper_thread = threading.Thread(
            target=self._channel_hopper, args=(mon_iface, channels, dwell), daemon=True
        )
        self._hopper_thread.start()

        self._log(f"شروع ذخیره کپچر -> {output_path}")
        try:
            self._capture_proc = subprocess.Popen(
                [self.tshark_path, "-i", mon_iface, "-w", output_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
        except OSError as e:
            self._stop_event.set()
            self._disable_monitor_mode(mon_iface, iface)
            raise EngineError(f"اجرای tshark ناموفق: {e}") from e

        early_err = ensure_process_started(self._capture_proc)
        if early_err:
            self._stop_event.set()
            terminate_process(self._capture_proc)
            self._capture_proc = None
            self._disable_monitor_mode(mon_iface, iface)
            raise EngineError(f"tshark بلافاصله خارج شد: {early_err[:300]}")

        self._display_reader = LiveDisplayReader(
            self.tshark_path, mon_iface, on_error=self._log
        )
        self._display_reader.start()

        self.state.running = True

    def get_live_stats(self):
        if self._display_reader:
            return self._display_reader.snapshot()
        return 0, {}

    def is_capture_alive(self) -> bool:
        return process_is_alive(self._capture_proc)

    def stop(self):
        if not self.state.running:
            return
        self._log("در حال توقف ...")
        self._stop_event.set()
        if self._hopper_thread and self._hopper_thread.is_alive():
            self._hopper_thread.join(timeout=2.0)
        self._hopper_thread = None

        terminate_process(self._capture_proc)
        self._capture_proc = None

        if self._display_reader:
            self._display_reader.stop()
            self._display_reader = None

        if self.state.monitor_iface:
            self._log("برگردوندن اینترفیس به حالت managed ...")
            try:
                self._disable_monitor_mode(self.state.monitor_iface, self.state.original_iface)
            except EngineError as e:
                self._log(f"هشدار: {e}")

        self._current_channel = None
        self.state.monitor_iface = ""
        self.state.running = False
        self._log("متوقف شد.")
