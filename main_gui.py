#!/usr/bin/env python3
"""
main_gui.py — Wi-Fi Monitor Suite (نسخه ۲)

رابط گرافیکی مدرن با PySide6: جدول زنده SSIDها، شمارنده بسته‌ها، تم تیره،
و پشتیبانی چندپلتفرمی (لینوکس کامل / ویندوز و مک به‌صورت best-effort).

اجرا:
    pip install PySide6
    sudo python3 main_gui.py        # لینوکس/مک
    (Run as Administrator)          # ویندوز
"""

import os
import sys
import threading

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QLineEdit, QFileDialog, QDoubleSpinBox,
    QTextEdit, QTableWidget, QTableWidgetItem, QGroupBox, QMessageBox,
    QHeaderView, QSplitter
)
from PySide6.QtGui import QColor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.engine_factory import create_engine
from core.base_engine import EngineError
from core.platform_utils import current_platform


DARK_STYLESHEET = """
QWidget { background-color: #1e1f26; color: #e6e6e6; font-family: 'Segoe UI', sans-serif; font-size: 13px; }
QGroupBox { border: 1px solid #33343f; border-radius: 8px; margin-top: 10px; padding-top: 8px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #7cc4ff; }
QPushButton { background-color: #2c2e3a; border: 1px solid #40424f; border-radius: 6px; padding: 8px 16px; }
QPushButton:hover { background-color: #3a3d4d; }
QPushButton:disabled { color: #666; }
QPushButton#startBtn { background-color: #1f7a3d; }
QPushButton#startBtn:hover { background-color: #24923f; }
QPushButton#stopBtn { background-color: #7a1f1f; }
QPushButton#stopBtn:hover { background-color: #922424; }
QComboBox, QLineEdit, QDoubleSpinBox { background-color: #26272f; border: 1px solid #40424f; border-radius: 6px; padding: 5px; }
QTableWidget { background-color: #16171d; gridline-color: #2b2c36; border: 1px solid #33343f; border-radius: 6px; }
QHeaderView::section { background-color: #26272f; color: #7cc4ff; padding: 6px; border: none; }
QTextEdit { background-color: #0e0f13; color: #6cf07a; border: 1px solid #33343f; border-radius: 6px; font-family: monospace; }
QLabel#bigStat { font-size: 22px; font-weight: bold; color: #7cc4ff; }
QLabel#caveat { color: #d0a24c; font-size: 11px; }
"""


class Bridge(QObject):
    log_signal = Signal(str)


class WifiMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wi-Fi Monitor Suite")
        self.resize(880, 640)

        self.bridge = Bridge()
        self.bridge.log_signal.connect(self._append_log)
        self.engine = create_engine(on_log=lambda msg: self.bridge.log_signal.emit(msg))

        self._build_ui()
        self._refresh_interfaces()
        self._show_platform_caveats()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_state)
        self.timer.start(500)

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- کنترل‌ها ---
        controls = QGroupBox("تنظیمات")
        grid = QGridLayout(controls)

        grid.addWidget(QLabel("اینترفیس:"), 0, 0)
        self.iface_combo = QComboBox()
        grid.addWidget(self.iface_combo, 0, 1)
        refresh_btn = QPushButton("بازخوانی")
        refresh_btn.clicked.connect(self._refresh_interfaces)
        grid.addWidget(refresh_btn, 0, 2)

        grid.addWidget(QLabel("باند:"), 0, 3)
        self.band_combo = QComboBox()
        self.band_combo.addItems(["2.4", "5", "both"])
        grid.addWidget(self.band_combo, 0, 4)

        grid.addWidget(QLabel("Dwell (ثانیه):"), 0, 5)
        self.dwell_spin = QDoubleSpinBox()
        self.dwell_spin.setRange(0.1, 5.0)
        self.dwell_spin.setSingleStep(0.1)
        self.dwell_spin.setValue(0.5)
        grid.addWidget(self.dwell_spin, 0, 6)

        grid.addWidget(QLabel("فایل خروجی:"), 1, 0)
        self.output_edit = QLineEdit(os.path.join(os.getcwd(), "capture.pcapng"))
        grid.addWidget(self.output_edit, 1, 1, 1, 5)
        browse_btn = QPushButton("انتخاب...")
        browse_btn.clicked.connect(self._choose_output)
        grid.addWidget(browse_btn, 1, 6)

        root.addWidget(controls)

        # --- دکمه‌های شروع/توقف + وضعیت ---
        action_row = QHBoxLayout()
        self.start_btn = QPushButton("▶  شروع مانیتورینگ")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn = QPushButton("■  توقف")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.stop_btn)
        action_row.addStretch()

        self.status_label = QLabel("غیرفعال")
        action_row.addWidget(self.status_label)
        root.addLayout(action_row)

        # --- کارت‌های آماری ---
        stats_row = QHBoxLayout()
        self.channel_stat = self._make_stat_box("کانال فعلی", "-")
        self.packet_stat = self._make_stat_box("تعداد بسته‌ها", "0")
        self.network_stat = self._make_stat_box("شبکه‌های یافت‌شده", "0")
        stats_row.addWidget(self.channel_stat)
        stats_row.addWidget(self.packet_stat)
        stats_row.addWidget(self.network_stat)
        root.addLayout(stats_row)

        # --- جدول SSID + لاگ ---
        splitter = QSplitter(Qt.Vertical)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["SSID", "BSSID", "سیگنال (dBm)", "تعداد بسته"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        splitter.addWidget(self.table)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        splitter.addWidget(self.log_text)
        splitter.setSizes([350, 150])

        root.addWidget(splitter, stretch=1)

        # --- هشدارهای پلتفرم ---
        self.caveat_label = QLabel("")
        self.caveat_label.setObjectName("caveat")
        self.caveat_label.setWordWrap(True)
        root.addWidget(self.caveat_label)

    def _make_stat_box(self, title, value):
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        lbl = QLabel(value)
        lbl.setObjectName("bigStat")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        box.value_label = lbl
        return box

    def _show_platform_caveats(self):
        plat = current_platform()
        level = self.engine.support_level
        level_fa = {"full": "کامل", "partial": "جزئی/best-effort", "experimental": "تجربی"}.get(level, level)
        header = f"پلتفرم: {plat}  —  سطح پشتیبانی: {level_fa}"
        lines = [header] + [f"• {c}" for c in self.engine.caveats]
        self.caveat_label.setText("\n".join(lines))

    def _choose_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "فایل خروجی", self.output_edit.text(), "PCAPNG (*.pcapng)")
        if path:
            self.output_edit.setText(path)

    def _refresh_interfaces(self):
        try:
            ifaces = self.engine.list_interfaces()
        except Exception as e:
            ifaces = []
            self._append_log(f"[هشدار] خطا در لیست اینترفیس‌ها: {e}")
        self.iface_combo.clear()
        self.iface_combo.addItems(ifaces)

    # ---------------- منطق ----------------
    def _on_start(self):
        iface = self.iface_combo.currentText()
        if not iface:
            QMessageBox.critical(self, "خطا", "یک اینترفیس انتخاب کنید.")
            return
        output = self.output_edit.text()
        band = self.band_combo.currentText()
        dwell = self.dwell_spin.value()

        def worker():
            try:
                self.engine.start(iface, output, band, dwell)
                self.start_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
                self.status_label.setText("در حال اجرا")
            except EngineError as e:
                self._append_log(f"[خطا] {e}")
                QMessageBox.critical(self, "خطا", str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_stop(self):
        def worker():
            self.engine.stop()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText("غیرفعال")
            self.channel_stat.value_label.setText("-")

        threading.Thread(target=worker, daemon=True).start()

    def _poll_state(self):
        ch = self.engine.current_channel()
        if ch:
            self.channel_stat.value_label.setText(str(ch))

        get_stats = getattr(self.engine, "get_live_stats", None)
        if get_stats:
            total, networks = get_stats()
            self.packet_stat.value_label.setText(str(total))
            self.network_stat.value_label.setText(str(len(networks)))
            self._update_table(networks)

    def _update_table(self, networks: dict):
        self.table.setRowCount(len(networks))
        for row, (bssid, info) in enumerate(sorted(networks.items(), key=lambda kv: -kv[1]["count"])):
            self.table.setItem(row, 0, QTableWidgetItem(info.get("ssid", "")))
            self.table.setItem(row, 1, QTableWidgetItem(bssid))
            signal = info.get("last_signal")
            self.table.setItem(row, 2, QTableWidgetItem(str(signal) if signal is not None else "-"))
            self.table.setItem(row, 3, QTableWidgetItem(str(info.get("count", 0))))

    def _append_log(self, msg: str):
        self.log_text.append(msg)

    def closeEvent(self, event):
        if self.engine.state.running:
            self.engine.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)
    window = WifiMonitorApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
