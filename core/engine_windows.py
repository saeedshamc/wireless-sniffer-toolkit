"""
core/engine_windows.py — پیاده‌سازی ویندوز (پشتیبانی: "partial")

روی ویندوز، مانیتور مود واقعی فقط از طریق WlanHelper.exe که همراه Npcap
میاد امکان‌پذیره، و اون‌هم فقط روی کارت‌ها/درایورهایی که از OID مربوطه
پشتیبانی کنن (اغلب چیپ‌ست‌های Atheros/بعضی Realtek با درایور مناسب؛
خیلی از لپ‌تاپ‌های امروزی اصلاً ساپورت نمی‌کنن). این پیاده‌سازی روی همچین
سیستم‌هایی fallback و best-effort محسوب می‌شه، نه یک تضمین.

مرجع: مستندات Npcap درباره‌ی WlanHelper.
"""

import re
import subprocess
import threading

from .base_engine import BaseEngine, EngineError, channels_for_band
from .capture_display import LiveDisplayReader
from .platform_utils import find_tshark, find_wlan_helper, is_admin


def _run(cmd, check=False):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise EngineError(f"{' '.join(cmd)} -> {result.stderr.strip()}")
    return result


class WindowsEngine(BaseEngine):
    support_level = "partial"
    caveats = [
        "مانیتور مود روی ویندوز فقط با WlanHelper.exe (بخشی از Npcap) و فقط روی درایورهای خاص کار می‌کنه.",
        "اکثر کارت‌های وای‌فای داخلی لپ‌تاپ‌های امروزی روی ویندوز این قابلیت رو پشتیبانی نمی‌کنن.",
        "این بخش به‌صورت best-effort نوشته شده و لازمه روی سخت‌افزار واقعی خودتون تست/تنظیم بشه.",
    ]

    def __init__(self, on_log=None):
        super().__init__(on_log)
        self._stop_event = threading.Event()
        self._hopper_thread = None
        self._capture_proc = None
        self._display_reader = None
        self.tshark_path = find_tshark()
        self.wlan_helper = find_wlan_helper()

    def check_ready(self) -> list:
        problems = []
        if not is_admin():
            problems.append("این برنامه باید با Run as Administrator اجرا بشه.")
        if not self.tshark_path:
            problems.append("tshark پیدا نشد (Wireshark رو نصب کنید).")
        if not self.wlan_helper:
            problems.append("WlanHelper.exe پیدا نشد — مطمئن شید Npcap با گزینه‌ی "
                             "«Support raw 802.11 traffic» نصب شده.")
        return problems

    def list_interfaces(self) -> list:
        """اسم اینترفیس‌های وای‌فای رو با کمک WlanHelper لیست می‌کنه."""
        if not self.wlan_helper:
            return []
        result = _run([self.wlan_helper])
        # خروجی WlanHelper به‌طور معمول اسم/GUID اینترفیس‌ها رو در هر خط می‌ده
        return re.findall(r"\{[0-9A-Fa-f-]{36}\}", result.stdout) or []

    def _enable_monitor_mode(self, iface: str):
        self._log(f"تلاش برای مانیتور مود روی {iface} با WlanHelper ...")
        _run([self.wlan_helper, iface, "mode", "monitor"], check=True)

    def _disable_monitor_mode(self, iface: str):
        try:
            _run([self.wlan_helper, iface, "mode", "managed"])
        except EngineError as e:
            self._log(f"هشدار در بازگردانی حالت: {e}")

    def _channel_hopper(self, iface: str, channels: list, dwell: float):
        idx = 0
        while not self._stop_event.is_set():
            ch = channels[idx % len(channels)]
            _run([self.wlan_helper, iface, "channel", str(ch)])
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
        self._enable_monitor_mode(iface)
        self.state.monitor_iface = iface

        self._stop_event.clear()
        self._hopper_thread = threading.Thread(
            target=self._channel_hopper, args=(iface, channels, dwell), daemon=True
        )
        self._hopper_thread.start()

        self._log(f"شروع ذخیره کپچر -> {output_path}")
        self._capture_proc = subprocess.Popen(
            [self.tshark_path, "-i", iface, "-w", output_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        self._display_reader = LiveDisplayReader(self.tshark_path, iface)
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
            self._disable_monitor_mode(self.state.monitor_iface)
        self.state.running = False
        self._log("متوقف شد.")
