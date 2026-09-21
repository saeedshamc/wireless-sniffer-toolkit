"""تست دود GUI بدون نمایش پنجره پایدار."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ["WIFI_MONITOR_NO_ELEVATE"] = "1"

from PySide6.QtWidgets import QApplication


class TestGuiSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def test_window_builds(self):
        import main_gui
        window = main_gui.WifiMonitorApp()
        self.assertTrue(window.windowTitle())
        self.assertEqual(window.table.columnCount(), 8)
        self.assertIsNotNone(window.filter_edit)
        self.assertIsNotNone(window.tabs)
        self.assertEqual(window.tabs.count(), 3)
        window._apply_filters()
        window._reset_stats_ui()
        window.close()


class TestCliHelp(unittest.TestCase):
    def test_list_ifaces_runs(self):
        import cli
        code = cli.main(["--list-ifaces"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
