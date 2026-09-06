"""تست دود GUI بدون نمایش پنجره پایدار."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

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
        self.assertEqual(window.table.columnCount(), 5)
        self.assertIsNotNone(window.filter_edit)
        self.assertIsNotNone(window.elapsed_stat)
        # فیلتر خالی روی کش خالی نباید کرش کند
        window._apply_filter_to_table()
        window._reset_stats_ui()
        window.close()


if __name__ == "__main__":
    unittest.main()
