"""تست‌های واحد هسته — بدون نیاز به سخت‌افزار مانیتور مود."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.base_engine import CHANNELS_24GHZ, CHANNELS_5GHZ, channels_for_band, EngineError
from core.capture_display import (
    parse_live_fields_line, LiveDisplayReader, infer_encryption, infer_width,
)
from core.export_utils import networks_to_csv_text, write_networks_csv, clients_to_csv_text
from core.platform_utils import (
    current_platform,
    parse_tshark_interfaces_output,
    looks_like_wireless,
    subprocess_creationflags,
)
from core.engine_factory import create_engine
from core.process_utils import process_is_alive, terminate_process, ensure_process_started
from core.oui_lookup import vendor_from_bssid
from core.alerts import find_evil_twins
from core.settings import load_settings, save_settings, DEFAULTS
from core.hardware_hints import monitor_mode_failure_message


class TestChannels(unittest.TestCase):
    def test_band_24(self):
        ch = channels_for_band("2.4")
        self.assertEqual(ch, CHANNELS_24GHZ)
        self.assertEqual(len(ch), 13)

    def test_band_5(self):
        ch = channels_for_band("5")
        self.assertEqual(ch, CHANNELS_5GHZ)
        self.assertIn(36, ch)

    def test_band_both(self):
        ch = channels_for_band("both")
        self.assertEqual(len(ch), len(CHANNELS_24GHZ) + len(CHANNELS_5GHZ))

    def test_invalid_band(self):
        with self.assertRaises(ValueError):
            channels_for_band("6")


class TestParseLiveFields(unittest.TestCase):
    def test_full_line(self):
        # bssid ssid signal channel sa da subtype rsn wpa ht vht
        line = "AA:BB:CC:DD:EE:FF\tHomeWiFi\t-42\t6\taa:bb:cc:dd:ee:01\tff:ff:ff:ff:ff:ff\t8\t1\t\t0\t"
        parsed = parse_live_fields_line(line)
        self.assertEqual(parsed["bssid"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(parsed["ssid"], "HomeWiFi")
        self.assertEqual(parsed["signal"], -42)
        self.assertEqual(parsed["channel"], 6)
        self.assertIn("WPA", parsed["encryption"])

    def test_hidden_ssid(self):
        parsed = parse_live_fields_line("11:22:33:44:55:66\t\t-55\t11")
        self.assertEqual(parsed["ssid"], "(پنهان/بدون نام)")

    def test_multi_antenna_signal(self):
        parsed = parse_live_fields_line("aa:bb:cc:dd:ee:ff\tX\t-40,-45\t36")
        self.assertEqual(parsed["signal"], -40)

    def test_empty(self):
        self.assertIsNone(parse_live_fields_line(""))
        self.assertIsNone(parse_live_fields_line("\t\t"))

    def test_infer_encryption(self):
        self.assertEqual(infer_encryption("1", ""), "WPA2/WPA3")
        self.assertEqual(infer_encryption("", "1"), "WPA")
        self.assertEqual(infer_encryption("", ""), "Open/Unknown")

    def test_infer_width(self):
        self.assertEqual(infer_width("1", ""), "40")
        self.assertEqual(infer_width("", "2"), "80")


class TestLiveDisplayReaderAccumulate(unittest.TestCase):
    def test_accumulate(self):
        reader = LiveDisplayReader("tshark", "wlan0")
        reader._handle_line("aa:bb:cc:dd:ee:ff\tNetA\t-40\t1\taa:bb:cc:dd:ee:01\tff:ff:ff:ff:ff:ff\t8\t1\t\t0\t")
        reader._handle_line("aa:bb:cc:dd:ee:ff\tNetA\t-38\t1\taa:bb:cc:dd:ee:02\tff:ff:ff:ff:ff:ff\t8\t1\t\t0\t")
        total, nets = reader.snapshot()
        self.assertEqual(total, 2)
        self.assertEqual(nets["aa:bb:cc:dd:ee:ff"]["count"], 2)
        full = reader.snapshot_full()
        self.assertIn("clients", full)
        self.assertIn(1, full["channels"])


class TestTsharkInterfaceParse(unittest.TestCase):
    def test_windows_style(self):
        raw = (
            r"1. \Device\NPF_{ABC-123} (Wi-Fi)" + "\n"
            r"2. \Device\NPF_{DEF-456} (Ethernet)" + "\n"
        )
        ifaces = parse_tshark_interfaces_output(raw)
        self.assertEqual(len(ifaces), 2)
        self.assertTrue(looks_like_wireless(ifaces[0]["description"], ifaces[0]["name"]))

    def test_linux_style(self):
        ifaces = parse_tshark_interfaces_output("1. wlan0\n2. eth0\n")
        self.assertEqual(ifaces[0]["name"], "wlan0")


class TestExportCsv(unittest.TestCase):
    def test_csv_text(self):
        networks = {
            "aa:bb:cc:dd:ee:ff": {
                "ssid": "A", "channel": 6, "last_signal": -40, "count": 5,
                "encryption": "WPA2", "vendor": "X", "width": "20",
            },
        }
        text = networks_to_csv_text(networks)
        self.assertIn("ssid,bssid,channel", text)
        self.assertIn("A,aa:bb:cc:dd:ee:ff,6", text)

    def test_clients_csv(self):
        text = clients_to_csv_text({
            "11:22:33:44:55:66": {
                "ap_bssid": "aa:bb", "ssid": "A", "vendor": "Y",
                "last_signal": -50, "count": 3,
            }
        })
        self.assertIn("station,ap_bssid", text)

    def test_write_file(self):
        networks = {"aa:bb": {"ssid": "X", "channel": 1, "last_signal": -1, "count": 1}}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.csv")
            write_networks_csv(path, networks)
            with open(path, encoding="utf-8-sig") as f:
                body = f.read()
            self.assertIn("X,aa:bb,1", body)


class TestEngineFactorySmoke(unittest.TestCase):
    def test_create(self):
        engine = create_engine()
        self.assertIn(engine.support_level, ("full", "partial", "experimental", "unsupported"))
        problems = engine.check_ready()
        self.assertIsInstance(problems, list)
        ifaces = engine.list_interfaces()
        self.assertIsInstance(ifaces, list)
        full = engine.get_live_full()
        self.assertEqual(full["total"], 0)

    def test_engine_error_type(self):
        self.assertTrue(issubclass(EngineError, Exception))


class TestSubprocessFlags(unittest.TestCase):
    def test_flags_type(self):
        self.assertIsInstance(subprocess_creationflags(), int)


class TestProcessUtils(unittest.TestCase):
    def test_terminate_none(self):
        terminate_process(None)

    def test_process_is_alive_none(self):
        self.assertFalse(process_is_alive(None))

    def test_ensure_started_alive(self):
        import subprocess
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        try:
            err = ensure_process_started(proc, grace_seconds=0.2)
            self.assertEqual(err, "")
            self.assertTrue(process_is_alive(proc))
        finally:
            terminate_process(proc, timeout=2)

    def test_ensure_started_dead(self):
        import subprocess
        proc = subprocess.Popen(
            [sys.executable, "-c", "raise SystemExit(3)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        err = ensure_process_started(proc, grace_seconds=0.3)
        self.assertTrue(err)
        self.assertFalse(process_is_alive(proc))
        terminate_process(proc)


class TestCaptureHealthApi(unittest.TestCase):
    def test_health_when_idle(self):
        engine = create_engine()
        health = engine.capture_health()
        self.assertFalse(health["running"])
        self.assertFalse(health["capture_alive"])


class TestOuiAndAlerts(unittest.TestCase):
    def test_vendor(self):
        self.assertEqual(vendor_from_bssid("00:1A:11:00:00:01"), "Google")
        self.assertEqual(vendor_from_bssid("ff:ff:ff:ff:ff:ff"), "Unknown")

    def test_evil_twin(self):
        nets = {
            "aa:aa:aa:aa:aa:01": {"ssid": "Home"},
            "aa:aa:aa:aa:aa:02": {"ssid": "Home"},
            "bb:bb:bb:bb:bb:01": {"ssid": "Other"},
        }
        twins = find_evil_twins(nets)
        self.assertEqual(len(twins), 1)
        self.assertEqual(twins[0]["ssid"], "Home")
        self.assertEqual(twins[0]["count"], 2)


class TestSettings(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["APPDATA"] = td
            # force settings_dir under APPDATA on Windows; on unix uses ~/.config
            from core import settings as settings_mod
            orig = settings_mod.settings_dir
            settings_mod.settings_dir = lambda: td
            try:
                save_settings({"band": "5", "dwell": 1.2})
                data = load_settings()
                self.assertEqual(data["band"], "5")
                self.assertEqual(data["dwell"], 1.2)
                for k in DEFAULTS:
                    self.assertIn(k, data)
            finally:
                settings_mod.settings_dir = orig


class TestHardwareHints(unittest.TestCase):
    def test_message(self):
        msg = monitor_mode_failure_message("OID fail")
        self.assertIn("Alfa", msg)
        self.assertIn("OID fail", msg)


if __name__ == "__main__":
    unittest.main()
