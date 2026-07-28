"""
core/engine_factory.py — بر اساس سیستم‌عامل، موتور مناسب رو برمی‌گردونه.
"""

from .platform_utils import current_platform


def create_engine(on_log=None):
    plat = current_platform()
    if plat == "linux":
        from .engine_linux import LinuxEngine
        return LinuxEngine(on_log=on_log)
    if plat == "windows":
        from .engine_windows import WindowsEngine
        return WindowsEngine(on_log=on_log)
    if plat == "macos":
        from .engine_macos import MacOSEngine
        return MacOSEngine(on_log=on_log)
    raise RuntimeError(f"سیستم‌عامل «{plat}» پشتیبانی نمی‌شه.")
