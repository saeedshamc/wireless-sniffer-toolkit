"""
core/base_engine.py — قرارداد مشترکی که هر موتور پلتفرمی (لینوکس/ویندوز/مک)
باید پیاده‌سازی کنه، به‌علاوه ثابت‌های کانال و یک dataclass برای وضعیت.
"""

from dataclasses import dataclass, field

CHANNELS_24GHZ = list(range(1, 14))
CHANNELS_5GHZ = [36, 40, 44, 48, 52, 56, 60, 64,
                 100, 104, 108, 112, 116, 120, 124, 128,
                 132, 136, 140, 144, 149, 153, 157, 161, 165]


def channels_for_band(band: str):
    return {
        "2.4": CHANNELS_24GHZ,
        "5": CHANNELS_5GHZ,
        "both": CHANNELS_24GHZ + CHANNELS_5GHZ,
    }[band]


class EngineError(Exception):
    pass


@dataclass
class EngineState:
    running: bool = False
    monitor_iface: str = ""
    original_iface: str = ""
    log_lines: list = field(default_factory=list)


class BaseEngine:
    """
    قرارداد مشترک: هر زیرکلاس پلتفرمی باید این متدها رو پیاده‌سازی کنه.
    پارامترهای support_level و caveats برای این هستن که GUI بتونه صادقانه
    به کاربر بگه چه سطحی از قابلیت روی این پلتفرم واقعاً در دسترسه.
    """

    support_level = "unknown"   # "full" | "partial" | "unsupported"
    caveats = []

    def __init__(self, on_log=None):
        self.state = EngineState()
        self.on_log = on_log or (lambda msg: None)
        self._current_channel = None

    def _log(self, msg: str):
        self.state.log_lines.append(msg)
        self.on_log(msg)

    def check_ready(self) -> list:
        """لیستی از مشکلات/پیش‌نیازهای گمشده رو برمی‌گردونه (خالی یعنی آماده‌ست)."""
        raise NotImplementedError

    def list_interfaces(self) -> list:
        raise NotImplementedError

    def start(self, iface: str, output_path: str, band: str, dwell: float):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def current_channel(self):
        return self._current_channel
