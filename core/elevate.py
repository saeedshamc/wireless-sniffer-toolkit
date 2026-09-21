"""درخواست ارتقای دسترسی Administrator روی ویندوز."""

from __future__ import annotations

import os
import sys

from .platform_utils import current_platform, is_admin


def ensure_windows_admin(argv=None) -> bool:
    """
    اگر روی ویندوز و غیر Admin باشیم، UAC می‌خواهد و True برمی‌گرداند
    یعنی باید فرآیند فعلی خارج شود. در غیر این صورت False.
    """
    if current_platform() != "windows":
        return False
    if is_admin():
        return False
    if os.environ.get("WIFI_MONITOR_NO_ELEVATE") == "1":
        return False
    try:
        import ctypes
        args = subprocess_args(argv)
        # ShellExecuteW با runas
        params = " ".join(f'"{a}"' if " " in a else a for a in args[1:])
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", args[0], params, None, 1
        )
        return int(rc) > 32
    except Exception:
        return False


def subprocess_args(argv=None):
    argv = list(argv if argv is not None else sys.argv)
    if getattr(sys, "frozen", False):
        return [sys.executable] + argv[1:]
    # اسکریپت پایتون
    script = os.path.abspath(argv[0]) if argv else os.path.abspath(sys.argv[0])
    return [sys.executable, script] + argv[1:]
