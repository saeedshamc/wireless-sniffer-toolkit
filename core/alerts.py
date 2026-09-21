"""هشدار evil twin: یک SSID با چند BSSID متفاوت."""

from __future__ import annotations


HIDDEN = "(پنهان/بدون نام)"


def find_evil_twins(networks: dict) -> list:
    """
    برمی‌گرداند لیست dict:
      {ssid, bssids: [..], count}
    فقط برای SSIDهای غیرمخفی با بیش از یک BSSID.
    """
    by_ssid: dict[str, set] = {}
    for bssid, info in (networks or {}).items():
        ssid = (info or {}).get("ssid") or ""
        if not ssid or ssid == HIDDEN:
            continue
        by_ssid.setdefault(ssid, set()).add(bssid.lower())
    out = []
    for ssid, bssids in by_ssid.items():
        if len(bssids) > 1:
            out.append({
                "ssid": ssid,
                "bssids": sorted(bssids),
                "count": len(bssids),
            })
    out.sort(key=lambda x: -x["count"])
    return out
