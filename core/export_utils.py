"""خروجی گرفتن از داده‌های شبکهٔ کشف‌شده."""

import csv
import io


def networks_to_csv_text(networks: dict) -> str:
    """networks: bssid -> {ssid, channel, last_signal, count}"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ssid", "bssid", "channel", "signal_dbm", "packet_count"])
    rows = sorted(networks.items(), key=lambda kv: -kv[1].get("count", 0))
    for bssid, info in rows:
        writer.writerow([
            info.get("ssid", ""),
            bssid,
            info.get("channel") if info.get("channel") is not None else "",
            info.get("last_signal") if info.get("last_signal") is not None else "",
            info.get("count", 0),
        ])
    return buf.getvalue()


def write_networks_csv(path: str, networks: dict) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(networks_to_csv_text(networks))
