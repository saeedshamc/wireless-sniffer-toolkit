"""
core/capture_display.py — پارس زنده خروجی tshark برای APها، کلاینت‌ها و آمار کانال.
"""

from __future__ import annotations

import collections
import subprocess
import threading
import time
from typing import Optional

from .oui_lookup import vendor_from_bssid
from .platform_utils import subprocess_creationflags

# فیلدها به ترتیب:
# 0 bssid, 1 ssid, 2 signal, 3 channel, 4 sa, 5 da, 6 type_subtype,
# 7 rsn_ver, 8 wpa_ie, 9 ht_bw, 10 vht_bw
FIELD_COUNT = 11


def infer_encryption(rsn: str, wpa: str) -> str:
    rsn = (rsn or "").strip()
    wpa = (wpa or "").strip()
    if rsn:
        # RSN موجود: WPA2 یا WPA3 — بدون AKM دقیق، WPA2 می‌گذاریم مگر نشانهٔ SAE
        # tshark گاهی akm را جدا می‌دهد؛ اگر فقط version باشد WPA2
        return "WPA2/WPA3"
    if wpa:
        return "WPA"
    return "Open/Unknown"


def infer_width(ht_bw: str, vht_bw: str) -> str:
    vht = (vht_bw or "").strip()
    ht = (ht_bw or "").strip()
    if vht:
        # 0=20, 1=40, 2=80, 3=160 تقریبی
        mapping = {"0": "20", "1": "40", "2": "80", "3": "160"}
        return mapping.get(vht.split(",")[0].strip(), f"{vht}MHz")
    if ht in ("1", "true", "True"):
        return "40"
    if ht in ("0", "false", "False"):
        return "20"
    return "-"


def parse_live_fields_line(line: str) -> Optional[dict]:
    if not line or not line.strip():
        return None
    parts = line.rstrip("\n").split("\t")
    while len(parts) < FIELD_COUNT:
        parts.append("")

    bssid = (parts[0] or "").lower()
    sa = (parts[4] or "").lower()
    da = (parts[5] or "").lower()
    ssid = parts[1] if parts[1] else "(پنهان/بدون نام)"

    signal = None
    if parts[2]:
        try:
            signal = int(float(parts[2].split(",")[0].strip()))
        except ValueError:
            signal = None
    channel = None
    if parts[3]:
        try:
            channel = int(parts[3].split(",")[0].strip())
        except ValueError:
            channel = None

    subtype = ""
    if parts[6]:
        subtype = parts[6].split(",")[0].strip()

    enc = infer_encryption(parts[7], parts[8])
    width = infer_width(parts[9], parts[10])

    return {
        "bssid": bssid,
        "ssid": ssid,
        "signal": signal,
        "channel": channel,
        "sa": sa,
        "da": da,
        "subtype": subtype,
        "encryption": enc,
        "width": width,
    }


def _is_mgmt_beacon_like(subtype: str) -> bool:
    # 0x08 beacon, 0x05 probe resp, 0x04 probe req — tshark ممکن است عدد دهدهی بدهد
    try:
        val = int(subtype, 0) if subtype else -1
    except ValueError:
        return False
    return val in (4, 5, 8)


def _is_broadcast(mac: str) -> bool:
    return mac in ("", "ff:ff:ff:ff:ff:ff")


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
        self.networks = {}
        self.clients = {}
        # channel -> {"count": int, "best_signal": int|None}
        self.channel_stats = {}
        # bssid -> deque of (ts, signal)
        self.signal_history = {}

    def start(self):
        cmd = [
            self.tshark_path, "-i", self.iface, "-l", "-n",
            "-T", "fields",
            "-e", "wlan.bssid",
            "-e", "wlan.ssid",
            "-e", "radiotap.dbm_antsignal",
            "-e", "wlan_radio.channel",
            "-e", "wlan.sa",
            "-e", "wlan.da",
            "-e", "wlan.fc.type_subtype",
            "-e", "wlan.rsn.version",
            "-e", "wlan.wfa.ie.wpa",
            "-e", "wlan.ht.bandwidth",
            "-e", "wlan.vht.bandwidth",
            "-Y", "wlan",
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
        now = time.time()
        with self.lock:
            self.total_packets += 1
            bssid = parsed["bssid"]
            signal = parsed["signal"]
            channel = parsed["channel"]

            if channel is not None:
                st = self.channel_stats.setdefault(
                    channel, {"count": 0, "best_signal": None}
                )
                st["count"] += 1
                if signal is not None and (
                    st["best_signal"] is None or signal > st["best_signal"]
                ):
                    st["best_signal"] = signal

            # AP از beacon/probe یا هر فریمی که bssid دارد
            if bssid and bssid != "ff:ff:ff:ff:ff:ff":
                ssid = parsed["ssid"]
                entry = self.networks.setdefault(
                    bssid,
                    {
                        "ssid": ssid,
                        "last_signal": signal,
                        "count": 0,
                        "channel": channel,
                        "encryption": parsed["encryption"],
                        "width": parsed["width"],
                        "vendor": vendor_from_bssid(bssid),
                    },
                )
                if ssid and ssid != "(پنهان/بدون نام)":
                    entry["ssid"] = ssid
                if signal is not None:
                    entry["last_signal"] = signal
                    hist = self.signal_history.setdefault(
                        bssid, collections.deque(maxlen=120)
                    )
                    hist.append((now, signal))
                if channel is not None:
                    entry["channel"] = channel
                if parsed["encryption"] and parsed["encryption"] != "Open/Unknown":
                    entry["encryption"] = parsed["encryption"]
                elif entry.get("encryption") in (None, "", "Open/Unknown"):
                    entry["encryption"] = parsed["encryption"]
                if parsed["width"] and parsed["width"] != "-":
                    entry["width"] = parsed["width"]
                entry["vendor"] = vendor_from_bssid(bssid)
                entry["count"] += 1

            # Client: sa که خودش bssid نیست و broadcast نیست
            sa = parsed["sa"]
            if sa and not _is_broadcast(sa) and sa != bssid:
                # فقط اگر شبیه stations باشد (نه فقط beacon بدون sa مفید)
                if not _is_mgmt_beacon_like(parsed["subtype"]) or sa:
                    client = self.clients.setdefault(
                        sa,
                        {
                            "station": sa,
                            "ap_bssid": bssid or "",
                            "ssid": "",
                            "last_signal": signal,
                            "count": 0,
                            "vendor": vendor_from_bssid(sa),
                        },
                    )
                    if bssid:
                        client["ap_bssid"] = bssid
                        ap = self.networks.get(bssid)
                        if ap:
                            client["ssid"] = ap.get("ssid", "")
                    if signal is not None:
                        client["last_signal"] = signal
                    client["count"] += 1
                    client["vendor"] = vendor_from_bssid(sa)
        self.on_update()

    def reset(self):
        with self.lock:
            self.total_packets = 0
            self.networks.clear()
            self.clients.clear()
            self.channel_stats.clear()
            self.signal_history.clear()

    def snapshot(self):
        with self.lock:
            return (
                self.total_packets,
                {k: dict(v) for k, v in self.networks.items()},
            )

    def snapshot_full(self):
        with self.lock:
            return {
                "total": self.total_packets,
                "networks": {k: dict(v) for k, v in self.networks.items()},
                "clients": {k: dict(v) for k, v in self.clients.items()},
                "channels": {k: dict(v) for k, v in self.channel_stats.items()},
                "signal_history": {
                    k: list(v) for k, v in self.signal_history.items()
                },
            }

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
