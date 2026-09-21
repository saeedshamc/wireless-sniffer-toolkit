"""ذخیره و بازیابی تنظیمات کاربر."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any


DEFAULTS: dict[str, Any] = {
    "iface": "",
    "band": "2.4",
    "dwell": 0.5,
    "output": "",
    "channel_mode": "hop",  # hop | fixed
    "fixed_channel": 6,
    "filter_text": "",
    "filter_hidden_only": False,
    "filter_min_signal": -100,
    "filter_encryption": "any",  # any | open | wpa2 | wpa3
    "adapter_preset": "",
}


def settings_dir() -> str:
    plat = os.name
    if plat == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "WiFiMonitorSuite")
    else:
        path = os.path.join(os.path.expanduser("~"), ".config", "WiFiMonitorSuite")
    os.makedirs(path, exist_ok=True)
    return path


def settings_path() -> str:
    return os.path.join(settings_dir(), "settings.json")


def load_settings() -> dict:
    path = settings_path()
    data = deepcopy(DEFAULTS)
    if not os.path.isfile(path):
        return data
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in DEFAULTS:
                    data[k] = v
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return data


def save_settings(data: dict) -> None:
    merged = deepcopy(DEFAULTS)
    for k, v in (data or {}).items():
        if k in DEFAULTS:
            merged[k] = v
    path = settings_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
