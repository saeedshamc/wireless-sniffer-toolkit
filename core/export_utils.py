"""خروجی CSV برای شبکه‌ها و کلاینت‌ها."""

import csv
import io


def networks_to_csv_text(networks: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "ssid", "bssid", "channel", "width", "encryption", "vendor",
        "signal_dbm", "packet_count",
    ])
    rows = sorted(networks.items(), key=lambda kv: -kv[1].get("count", 0))
    for bssid, info in rows:
        writer.writerow([
            info.get("ssid", ""),
            bssid,
            info.get("channel") if info.get("channel") is not None else "",
            info.get("width", ""),
            info.get("encryption", ""),
            info.get("vendor", ""),
            info.get("last_signal") if info.get("last_signal") is not None else "",
            info.get("count", 0),
        ])
    return buf.getvalue()


def write_networks_csv(path: str, networks: dict) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(networks_to_csv_text(networks))


def clients_to_csv_text(clients: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "station", "ap_bssid", "ssid", "vendor", "signal_dbm", "packet_count",
    ])
    rows = sorted(clients.items(), key=lambda kv: -kv[1].get("count", 0))
    for sta, info in rows:
        writer.writerow([
            sta,
            info.get("ap_bssid", ""),
            info.get("ssid", ""),
            info.get("vendor", ""),
            info.get("last_signal") if info.get("last_signal") is not None else "",
            info.get("count", 0),
        ])
    return buf.getvalue()


def write_clients_csv(path: str, clients: dict) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(clients_to_csv_text(clients))
