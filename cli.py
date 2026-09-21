#!/usr/bin/env python3
"""
cli.py — مانیتورینگ بدون GUI برای automation.

مثال:
  python cli.py --iface wlan0 --band 2.4 --output capture.pcapng
  python cli.py --list-ifaces
  python cli.py --iface "Wi-Fi" --channel-mode fixed --channel 6 --duration 30
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.engine_factory import create_engine
from core.base_engine import EngineError
from core.export_utils import write_networks_csv, write_clients_csv


def main(argv=None):
    parser = argparse.ArgumentParser(description="Wi-Fi Monitor Suite CLI")
    parser.add_argument("--list-ifaces", action="store_true", help="لیست اینترفیس‌ها")
    parser.add_argument("--iface", help="نام اینترفیس")
    parser.add_argument("--band", default="2.4", choices=["2.4", "5", "both"])
    parser.add_argument("--dwell", type=float, default=0.5)
    parser.add_argument("--output", default="capture.pcapng")
    parser.add_argument("--channel-mode", default="hop", choices=["hop", "fixed"])
    parser.add_argument("--channel", type=int, default=6, help="کانال ثابت")
    parser.add_argument("--duration", type=float, default=0, help="ثانیه (0=تا Ctrl+C)")
    parser.add_argument("--csv-networks", default="", help="مسیر CSV شبکه‌ها در پایان")
    parser.add_argument("--csv-clients", default="", help="مسیر CSV کلاینت‌ها در پایان")
    args = parser.parse_args(argv)

    def on_log(msg):
        print(msg, flush=True)

    engine = create_engine(on_log=on_log)

    if args.list_ifaces:
        for name in engine.list_interfaces():
            print(name)
        return 0

    problems = engine.check_ready()
    if problems:
        print("پیش‌نیازها ناقص:", " | ".join(problems), file=sys.stderr)
        return 2
    if not args.iface:
        print("--iface لازم است (یا --list-ifaces).", file=sys.stderr)
        return 2

    try:
        engine.start(
            args.iface,
            args.output,
            args.band,
            args.dwell,
            channel_mode=args.channel_mode,
            fixed_channel=args.channel if args.channel_mode == "fixed" else None,
        )
    except EngineError as e:
        print(f"خطا: {e}", file=sys.stderr)
        return 1

    print("مانیتورینگ شروع شد. Ctrl+C برای توقف.", flush=True)
    started = time.monotonic()
    try:
        while True:
            time.sleep(1)
            data = engine.get_live_full()
            print(
                f"\r بسته‌ها={data.get('total', 0)} "
                f"شبکه={len(data.get('networks') or {})} "
                f"کلاینت={len(data.get('clients') or {})} "
                f"کانال={engine.current_channel()}",
                end="",
                flush=True,
            )
            if args.duration > 0 and (time.monotonic() - started) >= args.duration:
                break
    except KeyboardInterrupt:
        print("\nتوقف توسط کاربر...", flush=True)
    finally:
        engine.stop()
        data = engine.get_live_full()
        if args.csv_networks:
            write_networks_csv(args.csv_networks, data.get("networks") or {})
            print(f"CSV شبکه‌ها: {args.csv_networks}")
        if args.csv_clients:
            write_clients_csv(args.csv_clients, data.get("clients") or {})
            print(f"CSV کلاینت‌ها: {args.csv_clients}")
        print("تمام.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
