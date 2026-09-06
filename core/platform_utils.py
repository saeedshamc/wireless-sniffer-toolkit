"""
core/platform_utils.py — تشخیص سیستم‌عامل و پیدا کردن ابزارهای لازم روی هرکدوم
"""

import glob
import os
import platform
import shutil
import subprocess


def current_platform() -> str:
    system = platform.system().lower()
    if system.startswith("linux"):
        return "linux"
    if system.startswith("windows"):
        return "windows"
    if system.startswith("darwin"):
        return "macos"
    return "unknown"


def _wireshark_dir_candidates() -> list:
    plat = current_platform()
    if plat == "windows":
        return [
            r"C:\Program Files\Wireshark",
            r"C:\Program Files (x86)\Wireshark",
        ]
    if plat == "macos":
        return [
            "/Applications/Wireshark.app/Contents/MacOS",
            "/usr/local/bin",
            "/opt/homebrew/bin",
        ]
    return ["/usr/bin", "/usr/local/bin"]


def find_tshark() -> str:
    """مسیر tshark رو پیدا می‌کنه (روی ویندوز معمولاً کنار Wireshark نصب می‌شه)."""
    found = shutil.which("tshark")
    if found:
        return found
    name = "tshark.exe" if current_platform() == "windows" else "tshark"
    for directory in _wireshark_dir_candidates():
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate
    return ""


def find_mergecap() -> str:
    """مسیر mergecap برای ترکیب فایل‌های کپچر (عمدتاً مک)."""
    found = shutil.which("mergecap")
    if found:
        return found
    name = "mergecap.exe" if current_platform() == "windows" else "mergecap"
    for directory in _wireshark_dir_candidates():
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate
    return ""


def find_wlan_helper() -> str:
    """
    WlanHelper.exe بخشی از Npcap هست که امکان تلاش برای فعال‌سازی مانیتور مود
    و تنظیم کانال رو (روی درایورهایی که ازش پشتیبانی کنن) روی ویندوز می‌ده.
    """
    candidates = glob.glob(r"C:\Windows\System32\Npcap\WlanHelper.exe") + \
                 glob.glob(r"C:\Program Files\Npcap\WlanHelper.exe")
    for c in candidates:
        if os.path.exists(c):
            return c
    return shutil.which("WlanHelper.exe") or ""


def find_airport_binary() -> str:
    """
    باینری airport روی مک — فقط روی نسخه‌های قدیمی‌تر macOS و چیپ‌های Broadcom
    قدیمی موجوده؛ روی مک‌های اپل‌سیلیکون و نسخه‌های جدید macOS معمولاً حذف شده.
    """
    path = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
    return path if os.path.exists(path) else ""


def is_admin() -> bool:
    plat = current_platform()
    if plat == "windows":
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def parse_tshark_interfaces_output(stdout: str) -> list:
    """
    پارس متن خروجی `tshark -D` به لیست dictها.
    کلیدها: index, name, description, display
    """
    interfaces = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # قالب: "1. eth0" یا '1. \Device\NPF_{GUID} (Wi-Fi)'
        try:
            num_part, rest = line.split(".", 1)
            index = int(num_part.strip())
        except ValueError:
            continue
        rest = rest.strip()
        description = ""
        name = rest
        if rest.endswith(")") and "(" in rest:
            name, desc = rest.rsplit("(", 1)
            name = name.strip()
            description = desc.rstrip(")").strip()
        interfaces.append({
            "index": index,
            "name": name,
            "description": description,
            "display": f"{description} [{name}]" if description else name,
        })
    return interfaces


def list_tshark_interfaces(tshark_path: str) -> list:
    """لیست اینترفیس‌ها از خروجی `tshark -D`."""
    if not tshark_path:
        return []
    try:
        result = subprocess.run(
            [tshark_path, "-D"],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess_creationflags(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_tshark_interfaces_output(result.stdout or "")


def looks_like_wireless(description: str, name: str = "") -> bool:
    """حدس می‌زند اینترفیس وای‌فای است (برای فیلتر لیست روی ویندوز/مک)."""
    blob = f"{description} {name}".lower()
    keywords = (
        "wi-fi", "wifi", "wireless", "wlan", "802.11", "airport",
        "atheros", "ralink", "realtek", "mediatek", "broadcom",
    )
    return any(k in blob for k in keywords)


def subprocess_creationflags() -> int:
    """روی ویندوز از باز شدن پنجرهٔ کنسول برای subprocess جلوگیری می‌کنه."""
    if current_platform() == "windows":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


# سازگاری با importهای قبلی داخل پکیج
_subprocess_no_window = subprocess_creationflags
