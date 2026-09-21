"""لاگ فایل سشن."""

from __future__ import annotations

import os
from datetime import datetime

from .settings import settings_dir


def logs_dir() -> str:
    path = os.path.join(settings_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


class SessionFileLogger:
    def __init__(self):
        self._fp = None
        self.path = ""

    def start(self):
        self.close()
        name = datetime.now().strftime("session-%Y%m%d-%H%M%S.log")
        self.path = os.path.join(logs_dir(), name)
        self._fp = open(self.path, "a", encoding="utf-8")

    def write(self, msg: str):
        if not self._fp:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            self._fp.write(f"[{ts}] {msg}\n")
            self._fp.flush()
        except OSError:
            pass

    def close(self):
        if self._fp:
            try:
                self._fp.close()
            except OSError:
                pass
            self._fp = None
