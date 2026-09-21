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

from .base_engine import BaseEngine, EngineError, channels_for_band
from .platform_utils import find_tshark, find_airport_binary, find_mergecap, is_admin
from .process_utils import terminate_process


def _run(cmd, check=False, timeout=None):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise EngineError(f"{' '.join(cmd)} -> {err}")
    return result


class MacOSEngine(BaseEngine):
    caveats = [
        "ابزار airport فقط روی مک‌های قدیمی‌تر (اینتلی/Broadcom) موجوده و روی مک‌های "
        "اپل‌سیلیکون و نسخه‌های جدید macOS معمولاً وجود نداره.",
        "channel hopping با فراخوانی مکرر airport شبیه‌سازی می‌شه، نه واقعاً همزمان.",
        "آمار زنده SSID روی این موتور در دسترس نیست (کپچر ناپیوسته).",
        "این بخش تست‌نشده روی سخت‌افزار واقعیه؛ اگه airport نبود، از یک آداپتور USB خارجی سازگار استفاده کنید.",
    ]

    def __init__(self, on_log=None):
        super().__init__(on_log)
        self._stop_event = threading.Event()
        self._worker_thread = None
        self.tshark_path = find_tshark()
        self.airport_path = find_airport_binary()
        self.mergecap_path = find_mergecap()
        self._tmp_dir = None
        self._final_output = None
        self._channels_seen = 0
        self._airport_proc = None
        if self.airport_path:
            self.support_level = "experimental"
        else:
            self.support_level = "unsupported"
            self.caveats = [
                "airport روی این مک پیدا نشد — مانیتور مود native پشتیبانی نمی‌شود.",
                "از آداپتور USB خارجی سازگار + لینوکس/ابزار مخصوص، یا مک قدیمی‌تر استفاده کنید.",
            ]

    def check_ready(self) -> list:
        problems = []
        if not is_admin():
            problems.append("این برنامه باید با sudo اجرا بشه.")
        if not self.airport_path:
            problems.append(
                "ابزار airport روی این مک پیدا نشد — این مک احتمالاً از "
                "مانیتور مود پشتیبانی نمی‌کنه."
            )
        if not self.mergecap_path and not self.tshark_path:
            problems.append(
                "mergecap/Wireshark پیدا نشد (برای ترکیب کپچرهای هر کانال لازمه)."
            )
        return problems

    def list_interfaces(self) -> list:
        # ترجیح: فقط اینترفیس‌های وای‌فای واقعی از networksetup
        if shutil.which("networksetup"):
            result = _run(["networksetup", "-listallhardwareports"])
            wifi = []
            lines = (result.stdout or "").splitlines()
            current_port = ""
            for line in lines:
                if line.startswith("Hardware Port:"):
                    current_port = line.split(":", 1)[1].strip().lower()
                elif line.startswith("Device:") and current_port:
                    dev = line.split(":", 1)[1].strip()
                    if any(k in current_port for k in ("wi-fi", "wifi", "airport")):
                        wifi.append(dev)
                    current_port = ""
            if wifi:
                return wifi

        result = _run(["ifconfig", "-l"])
        return [i for i in (result.stdout or "").split() if i.startswith("en")]

    def _hop_and_capture(self, iface: str, channels: list, dwell: float):
        idx = 0
        while not self._stop_event.is_set():
            if self._channel_mode == "fixed" and self._fixed_channel is not None:
                ch = int(self._fixed_channel)
            else:
                ch = channels[idx % len(channels)]
            self._current_channel = ch
            tmp_file = os.path.join(self._tmp_dir, f"ch{ch}_{idx:05d}.cap")
            self._log(f"کپچر کانال {ch} برای {dwell} ثانیه ...")
            before = set(glob.glob("/tmp/airportSniff*.cap"))
            try:
                proc = subprocess.Popen(
                    [self.airport_path, iface, "sniff", str(ch)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self._airport_proc = proc
                self._stop_event.wait(dwell)
                terminate_process(proc, timeout=3)
                self._airport_proc = None
                after = set(glob.glob("/tmp/airportSniff*.cap"))
                new_caps = sorted(after - before, key=os.path.getmtime)
                if not new_caps:
                    all_caps = sorted(glob.glob("/tmp/airportSniff*.cap"), key=os.path.getmtime)
                    new_caps = all_caps[-1:] if all_caps else []
                if new_caps:
                    shutil.move(new_caps[-1], tmp_file)
                    self._channels_seen += 1
            except Exception as e:
                self._airport_proc = None
                self._log(f"خطا در کانال {ch}: {e}")
            idx += 1
            if self._channel_mode == "fixed":
                # روی کانال ثابت هم حلقه می‌زند تا سشن ادامه داشته باشد
                pass

    def start(
        self,
        iface: str,
        output_path: str,
        band: str,
        dwell: float,
        channel_mode: str = "hop",
        fixed_channel=None,
    ):
        if self.state.running:
            raise EngineError("سشن قبلی هنوز فعاله.")
        if self.support_level == "unsupported":
            raise EngineError(
                "مانیتور مود روی این مک پشتیبانی نمی‌شود (airport موجود نیست)."
            )
        problems = self.check_ready()
        if problems:
            raise EngineError(" | ".join(problems))
        if not iface:
            raise EngineError("اینترفیس مشخص نشده.")

        out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
        if not os.path.isdir(out_dir):
            raise EngineError(f"پوشهٔ خروجی وجود ندارد: {out_dir}")

        channels = channels_for_band(band)
        self._channel_mode = channel_mode or "hop"
        self._fixed_channel = fixed_channel
        self.state.original_iface = iface
        self.state.monitor_iface = iface
        self.state.output_path = output_path
        self._final_output = output_path
        self._tmp_dir = tempfile.mkdtemp(prefix="wifi_monitor_mac_")
        self._channels_seen = 0

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._hop_and_capture, args=(iface, channels, dwell), daemon=True
        )
        self._worker_thread.start()
        self.state.running = True
        self._log("کپچر ناپیوستهٔ کانال‌ها شروع شد (experimental).")

    def get_live_stats(self):
        # آمار دقیق بسته نداریم؛ تعداد فایل‌های کانال دیده‌شده را به عنوان پروکسی می‌دهیم
        return self._channels_seen, {}

    def is_capture_alive(self) -> bool:
        if not self.state.running:
            return False
        if self._worker_thread and self._worker_thread.is_alive():
            return True
        return False

    def stop(self):
        if not self.state.running:
            return
        self._log("در حال توقف و ترکیب فایل‌های کپچر ...")
        self._stop_event.set()
        terminate_process(self._airport_proc, timeout=3)
        self._airport_proc = None
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        self._worker_thread = None

        cap_files = sorted(glob.glob(os.path.join(self._tmp_dir or "", "*.cap")))
        merge_tool = self.mergecap_path or find_mergecap()
        try:
            if cap_files and merge_tool:
                _run([merge_tool, "-w", self._final_output] + cap_files, check=True)
                self._log(f"کپچر ترکیبی ذخیره شد در: {self._final_output}")
            elif cap_files:
                shutil.copy(cap_files[-1], self._final_output)
                self._log(
                    f"فقط آخرین کانال ذخیره شد (mergecap موجود نبود): {self._final_output}"
                )
            else:
                self._log("هیچ فایل کپچری تولید نشد.")
        except EngineError as e:
            self._log(f"خطا در ترکیب فایل‌ها: {e}")
        finally:
            if self._tmp_dir:
                shutil.rmtree(self._tmp_dir, ignore_errors=True)
            self._tmp_dir = None

        self._current_channel = None
        self.state.monitor_iface = ""
        self.state.running = False
        self._log("متوقف شد.")
