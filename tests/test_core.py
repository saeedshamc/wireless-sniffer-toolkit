"""تست‌های واحد هسته — بدون نیاز به سخت‌افزار مانیتور مود."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.base_engine import CHANNELS_24GHZ, CHANNELS_5GHZ, channels_for_band, EngineError
from core.capture_display import parse_live_fields_line, LiveDisplayReader
from core.export_utils import networks_to_csv_text, write_networks_csv
from core.platform_utils import (
    current_platform,
    parse_tshark_interfaces_output,
    looks_like_wireless,
    subprocess_creationflags,
)
from core.engine_factory import create_engine


class TestChannels(unittest.TestCase):
    def test_band_24(self):
        ch = channels_for_band("2.4")
        self.assertEqual(ch, CHANNELS_24GHZ)
        self.assertEqual(len(ch), 13)
        self.assertIn(1, ch)
        self.assertIn(13, ch)

    def test_band_5(self):
        ch = channels_for_band("5")
        self.assertEqual(ch, CHANNELS_5GHZ)
        self.assertIn(36, ch)
        self.assertIn(165, ch)

    def test_band_both(self):
        ch = channels_for_band("both")
        self.assertEqual(len(ch), len(CHANNELS_24GHZ) + len(CHANNELS_5GHZ))

    def test_invalid_band(self):
        with self.assertRaises(ValueError):
            channels_for_band("6")


class TestParseLiveFields(unittest.TestCase):
    def test_full_line(self):
        parsed = parse_live_fields_line("AA:BB:CC:DD:EE:FF\tHomeWiFi\t-42\t6")
        self.assertEqual(parsed["bssid"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(parsed["ssid"], "HomeWiFi")
        self.assertEqual(parsed["signal"], -42)
        self.assertEqual(parsed["channel"], 6)

    def test_hidden_ssid(self):
        parsed = parse_live_fields_line("11:22:33:44:55:66\t\t-55\t11")
        self.assertEqual(parsed["ssid"], "(پنهان/بدون نام)")
        self.assertEqual(parsed["signal"], -55)

    def test_multi_antenna_signal(self):
        parsed = parse_live_fields_line("aa:bb:cc:dd:ee:ff\tX\t-40,-45\t36")
        self.assertEqual(parsed["signal"], -40)

    def test_empty(self):
        self.assertIsNone(parse_live_fields_line(""))
        self.assertIsNone(parse_live_fields_line("\t\t"))


class TestLiveDisplayReaderAccumulate(unittest.TestCase):
    def test_accumulate(self):
        reader = LiveDisplayReader("tshark", "wlan0")
        reader._handle_line("aa:bb:cc:dd:ee:ff\tNetA\t-40\t1")
        reader._handle_line("aa:bb:cc:dd:ee:ff\tNetA\t-38\t1")
        reader._handle_line("11:22:33:44:55:66\tNetB\t-60\t6")
        total, nets = reader.snapshot()
        self.assertEqual(total, 3)
        self.assertEqual(len(nets), 2)
        self.assertEqual(nets["aa:bb:cc:dd:ee:ff"]["count"], 2)
        self.assertEqual(nets["aa:bb:cc:dd:ee:ff"]["last_signal"], -38)


class TestTsharkInterfaceParse(unittest.TestCase):
    def test_windows_style(self):
        raw = (
            r"1. \Device\NPF_{ABC-123} (Wi-Fi)" + "\n"
            r"2. \Device\NPF_{DEF-456} (Ethernet)" + "\n"
        )
        ifaces = parse_tshark_interfaces_output(raw)
        self.assertEqual(len(ifaces), 2)
        self.assertEqual(ifaces[0]["description"], "Wi-Fi")
        self.assertTrue(looks_like_wireless(ifaces[0]["description"], ifaces[0]["name"]))
        self.assertFalse(looks_like_wireless(ifaces[1]["description"], ifaces[1]["name"]))

    def test_linux_style(self):
        ifaces = parse_tshark_interfaces_output("1. wlan0\n2. eth0\n")
        self.assertEqual(ifaces[0]["name"], "wlan0")
        self.assertEqual(ifaces[0]["display"], "wlan0")


class TestExportCsv(unittest.TestCase):
    def test_csv_text(self):
        networks = {
            "aa:bb:cc:dd:ee:ff": {"ssid": "A", "channel": 6, "last_signal": -40, "count": 5},
            "11:22:33:44:55:66": {"ssid": "B", "channel": 1, "last_signal": -70, "count": 2},
        }
        text = networks_to_csv_text(networks)
        self.assertIn("ssid,bssid,channel,signal_dbm,packet_count", text)
        self.assertIn("A,aa:bb:cc:dd:ee:ff,6,-40,5", text)
        lines = [ln for ln in text.strip().splitlines() if ln]
        self.assertEqual(len(lines), 3)

    def test_write_file(self):
        networks = {"aa:bb": {"ssid": "X", "channel": 1, "last_signal": -1, "count": 1}}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.csv")
            write_networks_csv(path, networks)
            with open(path, encoding="utf-8-sig") as f:
                body = f.read()
            self.assertIn("X,aa:bb,1,-1,1", body)


class TestEngineFactorySmoke(unittest.TestCase):
    def test_create(self):
        engine = create_engine()
        self.assertIn(engine.support_level, ("full", "partial", "experimental"))
        self.assertEqual(current_platform() != "unknown", True)
        problems = engine.check_ready()
        self.assertIsInstance(problems, list)
        # بدون سخت‌افزار نباید کرش کند
        ifaces = engine.list_interfaces()
        self.assertIsInstance(ifaces, list)
        stats = engine.get_live_stats()
        self.assertEqual(stats[0], 0)
        self.assertEqual(stats[1], {})

    def test_engine_error_type(self):
        self.assertTrue(issubclass(EngineError, Exception))


class TestSubprocessFlags(unittest.TestCase):
    def test_flags_type(self):
        flags = subprocess_creationflags()
        self.assertIsInstance(flags, int)


if __name__ == "__main__":
    unittest.main()
