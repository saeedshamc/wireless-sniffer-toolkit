#!/usr/bin/env python3
"""
main_gui.py — Wi-Fi Monitor Suite (نسخه ۲)

رابط گرافیکی مدرن با PySide6: جدول زنده SSIDها، شمارنده بسته‌ها، تم تیره،
و پشتیبانی چندپلتفرمی (لینوکس کامل / ویندوز و مک به‌صورت best-effort).

اجرا:
    pip install -r requirements.txt
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
    QHeaderView, QSplitter,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.engine_factory import create_engine
from core.base_engine import EngineError
from core.platform_utils import current_platform


DARK_STYLESHEET = """
QWidget { background-color: #1e1f26; color: #e6e6e6; font-family: 'Segoe UI', 'Tahoma', sans-serif; font-size: 13px; }
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
QTextEdit { background-color: #0e0f13; color: #6cf07a; border: 1px solid #33343f; border-radius: 6px; font-family: Consolas, monospace; }
QLabel#bigStat { font-size: 22px; font-weight: bold; color: #7cc4ff; }
QLabel#caveat { color: #d0a24c; font-size: 11px; }
QLabel#readyOk { color: #6cf07a; font-size: 12px; }
QLabel#readyBad { color: #f07178; font-size: 12px; }
"""


class Bridge(QObject):
    """پل امن بین threadهای موتور و thread اصلی Qt."""
    log_signal = Signal(str)
    started_signal = Signal()
    stopped_signal = Signal()
    error_signal = Signal(str)


class WifiMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wi-Fi Monitor Suite v2")
        self.resize(960, 680)
        self.setLayoutDirection(Qt.RightToLeft)

        self.bridge = Bridge()
        self.bridge.log_signal.connect(self._append_log)
        self.bridge.started_signal.connect(self._on_started_ui)
        self.bridge.stopped_signal.connect(self._on_stopped_ui)
        self.bridge.error_signal.connect(self._on_error_ui)

        self.engine = create_engine(on_log=lambda msg: self.bridge.log_signal.emit(msg))
        self._last_network_fingerprint = None
        self._busy = False

        self._build_ui()
        self._refresh_interfaces()
        self._show_platform_caveats()
        self._refresh_readiness()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_state)
        self.timer.start(500)

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

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

        self.ready_label = QLabel("")
        self.ready_label.setObjectName("readyOk")
        self.ready_label.setWordWrap(True)
        root.addWidget(self.ready_label)

        stats_row = QHBoxLayout()
        self.channel_stat = self._make_stat_box("کانال فعلی", "-")
        self.packet_stat = self._make_stat_box("تعداد بسته‌ها", "0")
        self.network_stat = self._make_stat_box("شبکه‌های یافت‌شده", "0")
        stats_row.addWidget(self.channel_stat)
        stats_row.addWidget(self.packet_stat)
        stats_row.addWidget(self.network_stat)
        root.addLayout(stats_row)

        splitter = QSplitter(Qt.Vertical)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["SSID", "BSSID", "کانال", "سیگنال (dBm)", "تعداد بسته"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(True)
        splitter.addWidget(self.table)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        splitter.addWidget(self.log_text)
        splitter.setSizes([380, 160])

        root.addWidget(splitter, stretch=1)

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
        level_fa = {
            "full": "کامل",
            "partial": "جزئی/best-effort",
            "experimental": "تجربی",
            "unsupported": "پشتیبانی‌نشده",
        }.get(level, level)
        header = f"پلتفرم: {plat}  —  سطح پشتیبانی: {level_fa}"
        lines = [header] + [f"• {c}" for c in self.engine.caveats]
        self.caveat_label.setText("\n".join(lines))

    def _refresh_readiness(self):
        try:
            problems = self.engine.check_ready()
        except Exception as e:
            problems = [str(e)]
        if problems:
            self.ready_label.setObjectName("readyBad")
            self.ready_label.setText("پیش‌نیازها ناقص: " + " | ".join(problems))
        else:
            self.ready_label.setObjectName("readyOk")
            self.ready_label.setText("پیش‌نیازها آماده‌اند.")
        # برای اعمال مجدد stylesheet روی objectName
        self.ready_label.style().unpolish(self.ready_label)
        self.ready_label.style().polish(self.ready_label)

    def _choose_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "فایل خروجی", self.output_edit.text(), "PCAPNG (*.pcapng)"
        )
        if path:
            if not path.lower().endswith((".pcapng", ".pcap")):
                path += ".pcapng"
            self.output_edit.setText(path)

    def _refresh_interfaces(self):
        try:
            ifaces = self.engine.list_interfaces()
        except Exception as e:
            ifaces = []
            self._append_log(f"[هشدار] خطا در لیست اینترفیس‌ها: {e}")
        current = self.iface_combo.currentText()
        self.iface_combo.clear()
        self.iface_combo.addItems(ifaces)
        if current and current in ifaces:
            self.iface_combo.setCurrentText(current)
        if not ifaces:
            self._append_log("[هشدار] هیچ اینترفیس وای‌فای پیدا نشد.")
        self._refresh_readiness()

    def _reset_stats_ui(self):
        self.packet_stat.value_label.setText("0")
        self.network_stat.value_label.setText("0")
        self.channel_stat.value_label.setText("-")
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setSortingEnabled(True)
        self._last_network_fingerprint = None

    # ---------------- منطق ----------------
    def _on_start(self):
        if self._busy or self.engine.state.running:
            return
        iface = self.iface_combo.currentText().strip()
        if not iface:
            QMessageBox.critical(self, "خطا", "یک اینترفیس انتخاب کنید.")
            return
        output = self.output_edit.text().strip()
        if not output:
            QMessageBox.critical(self, "خطا", "مسیر فایل خروجی را مشخص کنید.")
            return
        band = self.band_combo.currentText()
        dwell = self.dwell_spin.value()

        self._busy = True
        self.start_btn.setEnabled(False)
        self.status_label.setText("در حال راه‌اندازی...")
        self._reset_stats_ui()

        def worker():
            try:
                self.engine.start(iface, output, band, dwell)
                self.bridge.started_signal.emit()
            except EngineError as e:
                self.bridge.error_signal.emit(str(e))
            except Exception as e:
                self.bridge.error_signal.emit(f"خطای غیرمنتظره: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_stop(self):
        if self._busy:
            return
        self._busy = True
        self.stop_btn.setEnabled(False)
        self.status_label.setText("در حال توقف...")

        def worker():
            try:
                self.engine.stop()
            finally:
                self.bridge.stopped_signal.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_started_ui(self):
        self._busy = False
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.iface_combo.setEnabled(False)
        self.band_combo.setEnabled(False)
        self.dwell_spin.setEnabled(False)
        self.status_label.setText("در حال اجرا")

    def _on_stopped_ui(self):
        self._busy = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.iface_combo.setEnabled(True)
        self.band_combo.setEnabled(True)
        self.dwell_spin.setEnabled(True)
        self.status_label.setText("غیرفعال")
        self.channel_stat.value_label.setText("-")
        self._refresh_readiness()

    def _on_error_ui(self, message: str):
        self._busy = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.iface_combo.setEnabled(True)
        self.band_combo.setEnabled(True)
        self.dwell_spin.setEnabled(True)
        self.status_label.setText("خطا")
        self._append_log(f"[خطا] {message}")
        QMessageBox.critical(self, "خطا", message)
        self._refresh_readiness()

    def _poll_state(self):
        if not self.engine.state.running:
            return
        ch = self.engine.current_channel()
        if ch is not None:
            self.channel_stat.value_label.setText(str(ch))

        total, networks = self.engine.get_live_stats()
        self.packet_stat.value_label.setText(str(total))
        self.network_stat.value_label.setText(str(len(networks)))
        self._update_table(networks)

    def _update_table(self, networks: dict):
        # فقط وقتی داده عوض شده جدول را بازنویسی کن تا سورت/فلیکر کمتر شود
        fingerprint = tuple(
            sorted(
                (bssid, info.get("ssid"), info.get("channel"), info.get("last_signal"), info.get("count"))
                for bssid, info in networks.items()
            )
        )
        if fingerprint == self._last_network_fingerprint:
            return
        self._last_network_fingerprint = fingerprint

        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(networks))
        for row, (bssid, info) in enumerate(
            sorted(networks.items(), key=lambda kv: -kv[1].get("count", 0))
        ):
            self.table.setItem(row, 0, QTableWidgetItem(info.get("ssid", "")))
            self.table.setItem(row, 1, QTableWidgetItem(bssid))
            channel = info.get("channel")
            self.table.setItem(row, 2, QTableWidgetItem(str(channel) if channel is not None else "-"))
            signal = info.get("last_signal")
            signal_item = QTableWidgetItem()
            if signal is not None:
                signal_item.setData(Qt.DisplayRole, int(signal))
            else:
                signal_item.setText("-")
            self.table.setItem(row, 3, signal_item)
            count_item = QTableWidgetItem()
            count_item.setData(Qt.DisplayRole, int(info.get("count", 0)))
            self.table.setItem(row, 4, count_item)
        self.table.setSortingEnabled(sorting)

    def _append_log(self, msg: str):
        self.log_text.append(msg)

    def closeEvent(self, event):
        if self.engine.state.running:
            try:
                self.engine.stop()
            except Exception:
                pass
        event.accept()


def main():
    # روی ویندوز High-DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)
    app.setLayoutDirection(Qt.RightToLeft)
    window = WifiMonitorApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
