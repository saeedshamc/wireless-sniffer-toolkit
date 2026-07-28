"""
core/engine_macos.py — پیاده‌سازی macOS (پشتیبانی: "experimental")

ابزار native برای این کار روی مک، باینری قدیمی `airport` هست که:
  - فقط روی macOS نسخه‌های قدیمی‌تر و چیپ‌های Wi-Fi قدیمی‌تر (عمدتاً Broadcom)
    وجود داره؛ روی مک‌های اپل‌سیلیکون و نسخه‌های جدید macOS اصلاً پیدا نمی‌شه.
  - در هر اجرا فقط روی یک کانال «sniff» می‌کنه و تا وقتی که کشته نشه ادامه
    می‌ده — یعنی خودش channel hopping بلد نیست.

برای شبیه‌سازی channel hopping، این پیاده‌سازی به‌ازای هر کانال، `airport`
رو برای مدت dwell اجرا و متوقف می‌کنه، کپچر هر کانال رو در یک فایل موقت
ذخیره می‌کنه و در پایان همه رو با mergecap (همراه Wireshark) به یک فایل
واحد ترکیب می‌کنه.

این موتور را «experimental» در نظر بگیرید — روی مک‌های مدرن به احتمال زیاد
اصلاً کار نخواهد کرد و اگر airport موجود نباشه، برنامه صادقانه اعلام می‌کنه.
"""

import glob
import os
import shutil
import subprocess
import tempfile
import threading
import time

from .base_engine import BaseEngine, EngineError, channels_for_band
from .platform_utils import find_tshark, find_airport_binary, is_admin


def _run(cmd, check=False, timeout=None):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        raise EngineError(f"{' '.join(cmd)} -> {result.stderr.strip()}")
    return result


class MacOSEngine(BaseEngine):
    support_level = "experimental"
    caveats = [
        "ابزار airport فقط روی مک‌های قدیمی‌تر (اینتلی/Broadcom) موجوده و روی مک‌های "
        "اپل‌سیلیکون و نسخه‌های جدید macOS معمولاً وجود نداره.",
        "channel hopping با فراخوانی مکرر airport شبیه‌سازی می‌شه، نه واقعاً همزمان.",
        "این بخش تست‌نشده روی سخت‌افزار واقعیه؛ اگه airport نبود، از یک ابزار مانیتورینگ "
        "جایگزین مثل Wireshark به‌همراه یک آداپتور USB خارجی سازگار استفاده کنید.",
    ]

    def __init__(self, on_log=None):
        super().__init__(on_log)
        self._stop_event = threading.Event()
        self._worker_thread = None
        self.tshark_path = find_tshark()
        self.airport_path = find_airport_binary()
        self._tmp_dir = None
        self._final_output = None

    def check_ready(self) -> list:
        problems = []
        if not is_admin():
            problems.append("این برنامه باید با sudo اجرا بشه.")
        if not self.airport_path:
            problems.append("ابزار airport روی این مک پیدا نشد — این مک احتمالاً از "
                             "مانیتور مود پشتیبانی نمی‌کنه.")
        if not shutil.which("mergecap") and not self.tshark_path:
            problems.append("mergecap/Wireshark پیدا نشد (برای ترکیب کپچرهای هر کانال لازمه).")
        return problems

    def list_interfaces(self) -> list:
        result = _run(["ifconfig", "-l"])
        return [i for i in result.stdout.split() if i.startswith("en")]

    def _hop_and_capture(self, iface: str, channels: list, dwell: float):
        idx = 0
        while not self._stop_event.is_set():
            ch = channels[idx % len(channels)]
            self._current_channel = ch
            tmp_file = os.path.join(self._tmp_dir, f"ch{ch}_{idx}.cap")
            self._log(f"کپچر کانال {ch} برای {dwell} ثانیه ...")
            try:
                proc = subprocess.Popen(
                    [self.airport_path, iface, "sniff", str(ch)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                self._stop_event.wait(dwell)
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                # airport خروجی رو خودش در /tmp/airportSniffXXXXXX.cap می‌نویسه
                default_caps = sorted(glob.glob("/tmp/airportSniff*.cap"), key=os.path.getmtime)
                if default_caps:
                    shutil.move(default_caps[-1], tmp_file)
            except Exception as e:
                self._log(f"خطا در کانال {ch}: {e}")
            idx += 1

    def start(self, iface: str, output_path: str, band: str, dwell: float):
        if self.state.running:
            raise EngineError("سشن قبلی هنوز فعاله.")
        problems = self.check_ready()
        if problems:
            raise EngineError(" | ".join(problems))

        channels = channels_for_band(band)
        self.state.original_iface = iface
        self.state.monitor_iface = iface
        self._final_output = output_path
        self._tmp_dir = tempfile.mkdtemp(prefix="wifi_monitor_mac_")

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._hop_and_capture, args=(iface, channels, dwell), daemon=True
        )
        self._worker_thread.start()
        self.state.running = True

    def get_live_stats(self):
        # روی مک به‌دلیل ماهیت غیرپیوسته‌ی کپچر، آمار زنده‌ی دقیق در دسترس نیست.
        return 0, {}

    def stop(self):
        if not self.state.running:
            return
        self._log("در حال توقف و ترکیب فایل‌های کپچر ...")
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

        cap_files = sorted(glob.glob(os.path.join(self._tmp_dir, "*.cap")))
        merge_tool = shutil.which("mergecap")
        try:
            if cap_files and merge_tool:
                _run([merge_tool, "-w", self._final_output] + cap_files, check=True)
                self._log(f"کپچر ترکیبی ذخیره شد در: {self._final_output}")
            elif cap_files:
                shutil.copy(cap_files[-1], self._final_output)
                self._log(f"فقط آخرین کانال ذخیره شد (mergecap موجود نبود): {self._final_output}")
            else:
                self._log("هیچ فایل کپچری تولید نشد.")
        finally:
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

        self.state.running = False
        self._log("متوقف شد.")
