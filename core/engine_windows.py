"""
core/engine_windows.py — پیاده‌سازی ویندوز (پشتیبانی: "partial")

روی ویندوز، مانیتور مود واقعی فقط از طریق WlanHelper.exe که همراه Npcap
میاد امکان‌پذیره، و اون‌هم فقط روی کارت‌ها/درایورهایی که از OID مربوطه
پشتیبانی کنن (اغلب چیپ‌ست‌های Atheros/بعضی Realtek با درایور مناسب؛
خیلی از لپ‌تاپ‌های امروزی اصلاً ساپورت نمی‌کنن). این پیاده‌سازی روی همچین
سیستم‌هایی fallback و best-effort محسوب می‌شه، نه یک تضمین.

مرجع: مستندات Npcap درباره‌ی WlanHelper.
"""

import os
import re
import subprocess
import threading

from .base_engine import BaseEngine, EngineError, channels_for_band
from .capture_display import LiveDisplayReader
from .platform_utils import (
    find_tshark, find_wlan_helper, is_admin,
    list_tshark_interfaces, looks_like_wireless, subprocess_creationflags,
)
from .process_utils import terminate_process, process_is_alive, ensure_process_started


def _run(cmd, check=False):
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        creationflags=subprocess_creationflags(),
    )
    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise EngineError(f"{' '.join(cmd)} -> {err}")
    return result


class WindowsEngine(BaseEngine):
    support_level = "partial"
    caveats = [
        "مانیتور مود روی ویندوز فقط با WlanHelper.exe (بخشی از Npcap) و فقط روی درایورهای خاص کار می‌کنه.",
        "اکثر کارت‌های وای‌فای داخلی لپ‌تاپ‌های امروزی روی ویندوز این قابلیت رو پشتیبانی نمی‌کنن.",
        "این بخش به‌صورت best-effort نوشته شده و لازمه روی سخت‌افزار واقعی خودتون تست/تنظیم بشه.",
        "برای کپچر، اینترفیس باید از لیست tshark انتخاب بشه؛ WlanHelper با نام دوستانهٔ کارت کار می‌کنه.",
    ]

    def __init__(self, on_log=None):
        super().__init__(on_log)
        self._stop_event = threading.Event()
        self._hopper_thread = None
        self._capture_proc = None
        self._display_reader = None
        self._iface_map = {}  # display label -> {tshark_name, wlan_name}
        self.tshark_path = find_tshark()
        self.wlan_helper = find_wlan_helper()

    def check_ready(self) -> list:
        problems = []
        if not is_admin():
            problems.append("این برنامه باید با Run as Administrator اجرا بشه.")
        if not self.tshark_path:
            problems.append("tshark پیدا نشد (Wireshark رو نصب کنید).")
        if not self.wlan_helper:
            problems.append(
                "WlanHelper.exe پیدا نشد — مطمئن شید Npcap با گزینه‌ی "
                "«Support raw 802.11 traffic» نصب شده."
            )
        return problems

    def list_interfaces(self) -> list:
        """
        لیست اینترفیس‌ها از tshark -D (برای کپچر ضروری است).
        برای WlanHelper، نام دوستانه (description) یا GUID استخراج می‌شود.
        """
        self._iface_map.clear()
        labels = []

        tshark_ifaces = list_tshark_interfaces(self.tshark_path)
        wireless = []
        others = []
        for info in tshark_ifaces:
            label = info["display"]
            wlan_name = info["description"] or info["name"]
            guid_match = re.search(r"\{[0-9A-Fa-f-]{36}\}", info["name"])
            guid = guid_match.group(0) if guid_match else ""
            meta = {
                "tshark": info["name"],
                "wlan": wlan_name,
                "guid": guid,
                "index": str(info["index"]),
            }
            if looks_like_wireless(info["description"], info["name"]):
                wireless.append((label, meta))
            else:
                others.append((label, meta))

        chosen = wireless or others
        for label, meta in chosen:
            self._iface_map[label] = meta
            labels.append(label)

        if labels:
            return labels

        # fallback: فقط WlanHelper
        if self.wlan_helper:
            result = _run([self.wlan_helper])
            guids = re.findall(r"\{[0-9A-Fa-f-]{36}\}", result.stdout or "")
            for g in guids:
                label = g
                self._iface_map[label] = {
                    "tshark": g,
                    "wlan": g,
                    "guid": g,
                    "index": g,
                }
                labels.append(label)
        return labels

    def _resolve_iface(self, selection: str) -> tuple:
        """برمی‌گرداند (tshark_iface, wlan_helper_iface)."""
        mapped = self._iface_map.get(selection)
        if mapped:
            wlan = mapped["wlan"] or mapped["guid"] or mapped["tshark"]
            # tshark روی ویندوز هم با ایندکس و هم با نام دستگاه کار می‌کنه
            tshark = mapped["tshark"] or mapped["index"]
            return tshark, wlan
        return selection, selection

    def _enable_monitor_mode(self, wlan_iface: str):
        self._log(f"تلاش برای مانیتور مود روی {wlan_iface} با WlanHelper ...")
        # اول با نام دوستانه، بعد با GUID در صورت شکست
        attempts = [wlan_iface]
        mapped_guid = None
        for meta in self._iface_map.values():
            if meta["wlan"] == wlan_iface or meta["tshark"] == wlan_iface:
                mapped_guid = meta.get("guid")
                break
        if mapped_guid and mapped_guid not in attempts:
            attempts.append(mapped_guid)

        last_err = None
        for name in attempts:
            result = _run([self.wlan_helper, name, "mode", "monitor"])
            if result.returncode == 0:
                self._log(f"مانیتور مود فعال شد ({name}).")
                return name
            last_err = (result.stderr or result.stdout or "").strip()
            self._log(f"WlanHelper mode monitor روی «{name}» ناموفق: {last_err}")

        raise EngineError(
            "فعال‌سازی مانیتور مود ناموفق بود. درایور/کارت احتمالاً OID مانیتور مود را "
            f"پشتیبانی نمی‌کند. جزئیات: {last_err or 'نامشخص'}"
        )

    def _disable_monitor_mode(self, wlan_iface: str):
        result = _run([self.wlan_helper, wlan_iface, "mode", "managed"])
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            self._log(f"هشدار در بازگردانی حالت managed: {err or 'نامشخص'}")

    def _channel_hopper(self, wlan_iface: str, channels: list, dwell: float):
        idx = 0
        while not self._stop_event.is_set():
            ch = channels[idx % len(channels)]
            result = _run([self.wlan_helper, wlan_iface, "channel", str(ch)])
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

        tshark_iface, wlan_iface = self._resolve_iface(iface)
        channels = channels_for_band(band)
        self.state.original_iface = wlan_iface

        active_wlan = self._enable_monitor_mode(wlan_iface)
        self.state.monitor_iface = active_wlan

        self._stop_event.clear()
        self._hopper_thread = threading.Thread(
            target=self._channel_hopper, args=(active_wlan, channels, dwell), daemon=True
        )
        self._hopper_thread.start()

        self._log(f"شروع ذخیره کپچر روی «{tshark_iface}» -> {output_path}")
        try:
            self._capture_proc = subprocess.Popen(
                [self.tshark_path, "-i", tshark_iface, "-w", output_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                creationflags=subprocess_creationflags(),
            )
        except OSError as e:
            self._stop_event.set()
            self._disable_monitor_mode(active_wlan)
            raise EngineError(f"اجرای tshark ناموفق: {e}") from e

        early_err = ensure_process_started(self._capture_proc)
        if early_err:
            self._stop_event.set()
            terminate_process(self._capture_proc)
            self._capture_proc = None
            self._disable_monitor_mode(active_wlan)
            raise EngineError(f"tshark بلافاصله خارج شد: {early_err[:300]}")

        self._display_reader = LiveDisplayReader(
            self.tshark_path, tshark_iface, on_error=self._log
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
            self._disable_monitor_mode(self.state.monitor_iface)

        self._current_channel = None
        self.state.monitor_iface = ""
        self.state.running = False
        self._log("متوقف شد.")
