"""
core/capture_display.py — یک پردازش جدا و سبک از tshark رو اجرا می‌کنه که
فقط فیلدهای لازم (بدون نوشتن فایل) رو استریم می‌کنه، تا GUI بتونه به‌صورت
زنده تعداد بسته‌ها و شبکه‌های (SSID) دیده‌شده رو نشون بده.

این کاملاً جدا از پردازش اصلی tshark هست که فایل pcapng رو ذخیره می‌کنه —
گرفتن چند session کپچر هم‌زمان روی یک اینترفیس مانیتور مشکلی نداره.
"""

import subprocess
import threading

from .platform_utils import subprocess_creationflags


def parse_live_fields_line(line: str):
    """
    یک خط fields خروجی tshark را پارس می‌کند.
    برمی‌گرداند: None یا dict با bssid/ssid/signal/channel
    """
    if not line or not line.strip():
        return None
    parts = line.rstrip("\n").split("\t")
    if not parts or not parts[0]:
        return None

    bssid = parts[0].lower()
    ssid = parts[1] if len(parts) >= 2 and parts[1] else "(پنهان/بدون نام)"
    signal = None
    if len(parts) >= 3 and parts[2]:
        try:
            signal = int(float(parts[2].split(",")[0].strip()))
        except ValueError:
            signal = None
    channel = None
    if len(parts) >= 4 and parts[3]:
        try:
            channel = int(parts[3].split(",")[0].strip())
        except ValueError:
            channel = None
    return {
        "bssid": bssid,
        "ssid": ssid,
        "signal": signal,
        "channel": channel,
    }


class LiveDisplayReader:
    def __init__(self, tshark_path: str, iface: str, on_update=None, on_error=None):
        self.tshark_path = tshark_path
        self.iface = iface
        self.on_update = on_update or (lambda: None)
        self.on_error = on_error or (lambda msg: None)
        self._proc = None
        self._thread = None
        self._stop = False

        self.lock = threading.Lock()
        self.total_packets = 0
        # bssid -> {"ssid": str, "last_signal": int|None, "count": int, "channel": int|None}
        self.networks = {}

    def start(self):
        cmd = [
            self.tshark_path, "-i", self.iface, "-l", "-n",
            "-T", "fields",
            "-e", "wlan.bssid",
            "-e", "wlan.ssid",
            "-e", "radiotap.dbm_antsignal",
            "-e", "wlan_radio.channel",
            "-Y", "wlan.fc.type_subtype==0x08 || wlan.fc.type_subtype==0x05 || wlan.fc.type_subtype==0x04",
        ]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=subprocess_creationflags(),
            )
        except OSError as e:
            self.on_error(f"اجرای tshark برای نمایش زنده ناموفق: {e}")
            return

        self._stop = False
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def is_alive(self) -> bool:
        return bool(self._proc and self._proc.poll() is None)

    def _read_loop(self):
        assert self._proc is not None
        try:
            for line in self._proc.stdout:
                if self._stop:
                    break
                self._handle_line(line.rstrip("\n"))
        except Exception as e:
            if not self._stop:
                self.on_error(f"خطا در خواندن خروجی tshark: {e}")
        finally:
            # اگر tshark زود خارج شد، stderr رو برای دیباگ نگه می‌داریم
            if self._proc and self._proc.poll() not in (None, 0) and not self._stop:
                err = ""
                try:
                    err = (self._proc.stderr.read() or "").strip()
                except Exception:
                    pass
                if err:
                    self.on_error(f"tshark نمایش زنده خارج شد: {err[:300]}")

    def _handle_line(self, line: str):
        parsed = parse_live_fields_line(line)
        if not parsed:
            return
        with self.lock:
            self.total_packets += 1
            bssid = parsed["bssid"]
            ssid = parsed["ssid"]
            signal = parsed["signal"]
            channel = parsed["channel"]
            entry = self.networks.setdefault(
                bssid,
                {"ssid": ssid, "last_signal": signal, "count": 0, "channel": channel},
            )
            if ssid and ssid != "(پنهان/بدون نام)":
                entry["ssid"] = ssid
            if signal is not None:
                entry["last_signal"] = signal
            if channel is not None:
                entry["channel"] = channel
            entry["count"] += 1
        self.on_update()

    def reset(self):
        with self.lock:
            self.total_packets = 0
            self.networks.clear()

    def snapshot(self):
        with self.lock:
            return self.total_packets, {k: dict(v) for k, v in self.networks.items()}

    def stop(self):
        self._stop = True
        if self._proc:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=2)
            except Exception:
                pass
            self._proc = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
