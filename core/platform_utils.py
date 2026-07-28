"""
core/platform_utils.py — تشخیص سیستم‌عامل و پیدا کردن ابزارهای لازم روی هرکدوم
"""

import platform
import shutil
import glob
import os


def current_platform() -> str:
    system = platform.system().lower()
    if system.startswith("linux"):
        return "linux"
    if system.startswith("windows"):
        return "windows"
    if system.startswith("darwin"):
        return "macos"
    return "unknown"


def find_tshark() -> str:
    """مسیر tshark رو پیدا می‌کنه (روی ویندوز معمولاً کنار Wireshark نصب می‌شه)."""
    found = shutil.which("tshark")
    if found:
        return found
    if current_platform() == "windows":
        candidates = glob.glob(r"C:\Program Files\Wireshark\tshark.exe") + \
                     glob.glob(r"C:\Program Files (x86)\Wireshark\tshark.exe")
        if candidates:
            return candidates[0]
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
    else:
        return os.geteuid() == 0
