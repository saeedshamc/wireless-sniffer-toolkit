"""
core/capture_display.py — یک پردازش جدا و سبک از tshark رو اجرا می‌کنه که
فقط فیلدهای لازم (بدون نوشتن فایل) رو استریم می‌کنه، تا GUI بتونه به‌صورت
زنده تعداد بسته‌ها و شبکه‌های (SSID) دیده‌شده رو نشون بده.

این کاملاً جدا از پردازش اصلی tshark هست که فایل pcapng رو ذخیره می‌کنه —
گرفتن چند session کپچر هم‌زمان روی یک اینترفیس مانیتور مشکلی نداره.
"""

import subprocess
import threading


class LiveDisplayReader:
    def __init__(self, tshark_path: str, iface: str, on_update=None):
        self.tshark_path = tshark_path
        self.iface = iface
        self.on_update = on_update or (lambda: None)
        self._proc = None
        self._thread = None
        self._stop = False

        self.lock = threading.Lock()
        self.total_packets = 0
        # bssid -> {"ssid": str, "last_signal": int|None, "count": int}
        self.networks = {}

    def start(self):
        cmd = [
            self.tshark_path, "-i", self.iface, "-l", "-n",
            "-T", "fields",
            "-e", "wlan.bssid",
            "-e", "wlan.ssid",
            "-e", "radiotap.dbm_antsignal",
            "-Y", "wlan.fc.type_subtype==0x08 || wlan.fc.type_subtype==0x05 || wlan.fc.type_subtype==0x04",
        ]
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1
        )
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        for line in self._proc.stdout:
            if self._stop:
                break
            self._handle_line(line.rstrip("\n"))
        return

    def _handle_line(self, line: str):
        parts = line.split("\t")
        with self.lock:
            self.total_packets += 1
            if len(parts) >= 1 and parts[0]:
                bssid = parts[0]
                ssid = parts[1] if len(parts) >= 2 and parts[1] else "(پنهان/بدون نام)"
                signal = None
                if len(parts) >= 3 and parts[2]:
                    try:
                        signal = int(parts[2].split(",")[0])
                    except ValueError:
                        signal = None
                entry = self.networks.setdefault(bssid, {"ssid": ssid, "last_signal": signal, "count": 0})
                entry["ssid"] = ssid or entry["ssid"]
                if signal is not None:
                    entry["last_signal"] = signal
                entry["count"] += 1
        self.on_update()

    def snapshot(self):
        with self.lock:
            return self.total_packets, dict(self.networks)

    def stop(self):
        self._stop = True
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
