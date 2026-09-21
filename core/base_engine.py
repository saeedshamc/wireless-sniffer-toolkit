"""
core/base_engine.py — قرارداد مشترک موتورها + ثابت‌های کانال.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


CHANNELS_24GHZ = list(range(1, 14))
CHANNELS_5GHZ = [
    36, 40, 44, 48, 52, 56, 60, 64,
    100, 104, 108, 112, 116, 120, 124, 128,
    132, 136, 140, 144, 149, 153, 157, 161, 165,
]


def channels_for_band(band: str):
    try:
        return {
            "2.4": CHANNELS_24GHZ,
            "5": CHANNELS_5GHZ,
            "both": CHANNELS_24GHZ + CHANNELS_5GHZ,
        }[band]
    except KeyError as exc:
        raise ValueError(f"باند نامعتبر: {band!r} — یکی از 2.4 / 5 / both") from exc


class EngineError(Exception):
    pass


@dataclass
class EngineState:
    running: bool = False
    monitor_iface: str = ""
    original_iface: str = ""
    log_lines: list = field(default_factory=list)
    output_path: str = ""


class BaseEngine:
    support_level = "unknown"  # full | partial | experimental | unsupported
    caveats: list = []

    def __init__(self, on_log: Optional[Callable[[str], None]] = None):
        self.state = EngineState()
        self.on_log = on_log or (lambda msg: None)
        self._current_channel = None
        self._channel_mode = "hop"
        self._fixed_channel = None

    def _log(self, msg: str):
        self.state.log_lines.append(msg)
        self.on_log(msg)

    def check_ready(self) -> list:
        raise NotImplementedError

    def list_interfaces(self) -> list:
        raise NotImplementedError

    def start(
        self,
        iface: str,
        output_path: str,
        band: str,
        dwell: float,
        channel_mode: str = "hop",
        fixed_channel: Optional[int] = None,
    ):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def current_channel(self):
        return self._current_channel

    def get_live_stats(self):
        return 0, {}

    def get_live_full(self) -> dict:
        total, networks = self.get_live_stats()
        return {
            "total": total,
            "networks": networks,
            "clients": {},
            "channels": {},
            "signal_history": {},
        }

    def is_capture_alive(self) -> bool:
        return bool(self.state.running)

    def capture_health(self) -> dict:
        return {
            "running": self.state.running,
            "capture_alive": self.is_capture_alive(),
            "channel": self._current_channel,
            "output_path": self.state.output_path,
        }
