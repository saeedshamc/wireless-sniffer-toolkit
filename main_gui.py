#!/usr/bin/env python3
"""
main_gui.py — Wi-Fi Monitor Suite v2 (ارتقایافته)
"""

import os
import sys
import threading
import time
import webbrowser

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QLineEdit, QFileDialog, QDoubleSpinBox,
    QTextEdit, QTableWidget, QTableWidgetItem, QGroupBox, QMessageBox,
    QHeaderView, QSplitter, QSpinBox, QCheckBox, QTabWidget, QAbstractItemView,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.engine_factory import create_engine
from core.base_engine import EngineError, CHANNELS_24GHZ, CHANNELS_5GHZ
from core.platform_utils import current_platform
from core.export_utils import write_networks_csv, write_clients_csv
from core.settings import load_settings, save_settings
from core.hardware_hints import recommended_adapters_text
from core.alerts import find_evil_twins
from core.session_log import SessionFileLogger
from core.elevate import ensure_windows_admin
from ui.charts import SignalSparkline, ChannelHeatmap


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
QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox { background-color: #26272f; border: 1px solid #40424f; border-radius: 6px; padding: 5px; }
QTableWidget { background-color: #16171d; gridline-color: #2b2c36; border: 1px solid #33343f; border-radius: 6px; alternate-background-color: #1a1b22; }
QHeaderView::section { background-color: #26272f; color: #7cc4ff; padding: 6px; border: none; }
QTextEdit { background-color: #0e0f13; color: #6cf07a; border: 1px solid #33343f; border-radius: 6px; font-family: Consolas, monospace; }
QLabel#bigStat { font-size: 20px; font-weight: bold; color: #7cc4ff; }
QLabel#caveat { color: #d0a24c; font-size: 11px; }
QLabel#readyOk { color: #6cf07a; font-size: 12px; }
QLabel#readyBad { color: #f07178; font-size: 12px; }
QTabWidget::pane { border: 1px solid #33343f; }
QTabBar::tab { background: #26272f; color: #ccc; padding: 8px 14px; margin-right: 2px; }
QTabBar::tab:selected { background: #3a3d4d; color: #7cc4ff; }
"""

ADAPTER_PRESETS = {
    "": "— بدون preset —",
    "alfa_ach": "Alfa AWUS036ACH / ACM",
    "alfa_nha": "Alfa AWUS036NHA (AR9271)",
    "tplink_722n_v1": "TP-Link TL-WN722N v1",
    "panda": "Panda PAU09 / PAU06",
}


class Bridge(QObject):
    log_signal = Signal(str)
    started_signal = Signal()
    stopped_signal = Signal()
    error_signal = Signal(str)


class WifiMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wi-Fi Monitor Suite v2")
        self.resize(1180, 780)
        self.setLayoutDirection(Qt.RightToLeft)

        self.bridge = Bridge()
        self.bridge.log_signal.connect(self._append_log)
        self.bridge.started_signal.connect(self._on_started_ui)
        self.bridge.stopped_signal.connect(self._on_stopped_ui)
        self.bridge.error_signal.connect(self._on_error_ui)

        self.engine = create_engine(on_log=self._on_engine_log)
        self._settings = load_settings()
        self._file_logger = SessionFileLogger()
        self._last_network_fp = None
        self._last_client_fp = None
        self._networks_cache = {}
        self._clients_cache = {}
        self._channels_cache = {}
        self._signal_history = {}
        self._busy = False
        self._session_started_at = None
        self._capture_dead_warned = False
        self._evil_warned = set()
        self._selected_bssid = ""

        self._build_ui()
        self._apply_settings_to_ui()
        self._refresh_interfaces()
        self._show_platform_caveats()
        self._refresh_readiness()
        self._on_channel_mode_changed()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_state)
        self.timer.start(500)

    def _on_engine_log(self, msg: str):
        self.bridge.log_signal.emit(msg)
        self._file_logger.write(msg)

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

        grid.addWidget(QLabel("Dwell:"), 0, 5)
        self.dwell_spin = QDoubleSpinBox()
        self.dwell_spin.setRange(0.1, 5.0)
        self.dwell_spin.setSingleStep(0.1)
        self.dwell_spin.setValue(0.5)
        grid.addWidget(self.dwell_spin, 0, 6)

        grid.addWidget(QLabel("حالت کانال:"), 1, 0)
        self.channel_mode_combo = QComboBox()
        self.channel_mode_combo.addItem("Hopping", "hop")
        self.channel_mode_combo.addItem("قفل کانال", "fixed")
        self.channel_mode_combo.currentIndexChanged.connect(self._on_channel_mode_changed)
        grid.addWidget(self.channel_mode_combo, 1, 1)

        grid.addWidget(QLabel("کانال ثابت:"), 1, 2)
        self.fixed_channel_spin = QSpinBox()
        self.fixed_channel_spin.setRange(1, 165)
        self.fixed_channel_spin.setValue(6)
        grid.addWidget(self.fixed_channel_spin, 1, 3)

        grid.addWidget(QLabel("Preset آداپتور:"), 1, 4)
        self.preset_combo = QComboBox()
        for key, label in ADAPTER_PRESETS.items():
            self.preset_combo.addItem(label, key)
        grid.addWidget(self.preset_combo, 1, 5, 1, 2)

        grid.addWidget(QLabel("فایل خروجی:"), 2, 0)
        self.output_edit = QLineEdit(os.path.join(os.getcwd(), "capture.pcapng"))
        grid.addWidget(self.output_edit, 2, 1, 1, 4)
        browse_btn = QPushButton("انتخاب...")
        browse_btn.clicked.connect(self._choose_output)
        grid.addWidget(browse_btn, 2, 5)
        open_dir_btn = QPushButton("پوشه")
        open_dir_btn.clicked.connect(self._open_output_dir)
        grid.addWidget(open_dir_btn, 2, 6)

        grid.addWidget(QLabel("فیلتر متن:"), 3, 0)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("SSID یا BSSID...")
        self.filter_edit.textChanged.connect(self._apply_filters)
        grid.addWidget(self.filter_edit, 3, 1, 1, 2)

        self.hidden_only_cb = QCheckBox("فقط Hidden")
        self.hidden_only_cb.stateChanged.connect(self._apply_filters)
        grid.addWidget(self.hidden_only_cb, 3, 3)

        grid.addWidget(QLabel("حداقل dBm:"), 3, 4)
        self.min_signal_spin = QSpinBox()
        self.min_signal_spin.setRange(-100, 0)
        self.min_signal_spin.setValue(-100)
        self.min_signal_spin.valueChanged.connect(self._apply_filters)
        grid.addWidget(self.min_signal_spin, 3, 5)

        grid.addWidget(QLabel("رمز:"), 3, 6)
        self.enc_filter = QComboBox()
        self.enc_filter.addItems(["any", "open", "wpa2", "wpa3", "wpa"])
        self.enc_filter.currentTextChanged.connect(self._apply_filters)
        grid.addWidget(self.enc_filter, 4, 6)

        hw_btn = QPushButton("راهنمای سخت‌افزار")
        hw_btn.clicked.connect(self._show_hardware_help)
        grid.addWidget(hw_btn, 4, 0, 1, 2)

        root.addWidget(controls)

        action_row = QHBoxLayout()
        self.start_btn = QPushButton("▶  شروع مانیتورینگ")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn = QPushButton("■  توقف")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        export_btn = QPushButton("CSV شبکه‌ها")
        export_btn.clicked.connect(self._export_csv)
        export_cli_btn = QPushButton("CSV کلاینت‌ها")
        export_cli_btn.clicked.connect(self._export_clients_csv)
        clear_log_btn = QPushButton("پاک‌کردن لاگ")
        clear_log_btn.clicked.connect(self._clear_log)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.stop_btn)
        action_row.addWidget(export_btn)
        action_row.addWidget(export_cli_btn)
        action_row.addWidget(clear_log_btn)
        action_row.addStretch()
        self.status_label = QLabel("غیرفعال")
        action_row.addWidget(self.status_label)
        root.addLayout(action_row)

        self.ready_label = QLabel("")
        self.ready_label.setObjectName("readyOk")
        self.ready_label.setWordWrap(True)
        root.addWidget(self.ready_label)

        stats_row = QHBoxLayout()
        self.channel_stat = self._make_stat_box("کانال", "-")
        self.packet_stat = self._make_stat_box("بسته‌ها", "0")
        self.network_stat = self._make_stat_box("شبکه‌ها", "0")
        self.client_stat = self._make_stat_box("کلاینت‌ها", "0")
        self.elapsed_stat = self._make_stat_box("مدت", "00:00")
        self.filesize_stat = self._make_stat_box("حجم فایل", "-")
        for w in (
            self.channel_stat, self.packet_stat, self.network_stat,
            self.client_stat, self.elapsed_stat, self.filesize_stat,
        ):
            stats_row.addWidget(w)
        root.addLayout(stats_row)

        splitter = QSplitter(Qt.Vertical)
        self.tabs = QTabWidget()

        # Networks tab
        net_page = QWidget()
        net_lay = QVBoxLayout(net_page)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "SSID", "BSSID", "کانال", "عرض", "رمز", "Vendor", "سیگنال", "بسته",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemSelectionChanged.connect(self._on_network_selected)
        net_lay.addWidget(self.table)
        self.signal_chart = SignalSparkline()
        net_lay.addWidget(self.signal_chart)
        self.tabs.addTab(net_page, "Networks")

        # Clients tab
        self.client_table = QTableWidget(0, 6)
        self.client_table.setHorizontalHeaderLabels([
            "Station", "AP BSSID", "SSID", "Vendor", "سیگنال", "بسته",
        ])
        self.client_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.client_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.client_table.setSortingEnabled(True)
        self.client_table.setAlternatingRowColors(True)
        self.tabs.addTab(self.client_table, "Clients")

        # Channels tab
        ch_page = QWidget()
        ch_lay = QVBoxLayout(ch_page)
        self.heatmap = ChannelHeatmap()
        ch_lay.addWidget(self.heatmap)
        self.tabs.addTab(ch_page, "Channels")

        splitter.addWidget(self.tabs)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        splitter.addWidget(self.log_text)
        splitter.setSizes([480, 160])
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

    def _on_channel_mode_changed(self):
        fixed = self.channel_mode_combo.currentData() == "fixed"
        self.fixed_channel_spin.setEnabled(fixed)
        self.dwell_spin.setEnabled(not fixed)

    def _show_platform_caveats(self):
        plat = current_platform()
        level = self.engine.support_level
        level_fa = {
            "full": "کامل", "partial": "جزئی", "experimental": "تجربی",
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
        unsupported = self.engine.support_level == "unsupported"
        if unsupported:
            problems = problems or ["پلتفرم/سخت‌افزار برای مانیتور مود پشتیبانی نمی‌شود."]
        if problems:
            self.ready_label.setObjectName("readyBad")
            self.ready_label.setText("پیش‌نیازها ناقص: " + " | ".join(problems))
            self.start_btn.setEnabled(not self.engine.state.running and not unsupported)
        else:
            self.ready_label.setObjectName("readyOk")
            self.ready_label.setText("پیش‌نیازها آماده‌اند.")
            if not self.engine.state.running and not self._busy:
                self.start_btn.setEnabled(True)
        self.ready_label.style().unpolish(self.ready_label)
        self.ready_label.style().polish(self.ready_label)

    def _show_hardware_help(self):
        QMessageBox.information(self, "راهنمای سخت‌افزار", recommended_adapters_text())

    def _choose_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "فایل خروجی", self.output_edit.text(), "PCAPNG (*.pcapng)"
        )
        if path:
            if not path.lower().endswith((".pcapng", ".pcap")):
                path += ".pcapng"
            self.output_edit.setText(path)

    def _open_output_dir(self):
        path = self.output_edit.text().strip()
        folder = os.path.dirname(os.path.abspath(path)) if path else os.getcwd()
        if os.path.isdir(folder):
            webbrowser.open(folder)
        else:
            QMessageBox.warning(self, "پوشه", "پوشهٔ خروجی وجود ندارد.")

    def _refresh_interfaces(self):
        try:
            ifaces = self.engine.list_interfaces()
        except Exception as e:
            ifaces = []
            self._append_log(f"[هشدار] خطا در لیست اینترفیس‌ها: {e}")
        current = self.iface_combo.currentText()
        wanted = self._settings.get("iface") or current
        self.iface_combo.clear()
        self.iface_combo.addItems(ifaces)
        if wanted and wanted in ifaces:
            self.iface_combo.setCurrentText(wanted)
        if not ifaces:
            self._append_log("[هشدار] هیچ اینترفیس وای‌فای پیدا نشد.")
        self._refresh_readiness()

    def _apply_settings_to_ui(self):
        s = self._settings
        if s.get("output"):
            self.output_edit.setText(s["output"])
        idx = self.band_combo.findText(s.get("band", "2.4"))
        if idx >= 0:
            self.band_combo.setCurrentIndex(idx)
        self.dwell_spin.setValue(float(s.get("dwell", 0.5)))
        mode = s.get("channel_mode", "hop")
        for i in range(self.channel_mode_combo.count()):
            if self.channel_mode_combo.itemData(i) == mode:
                self.channel_mode_combo.setCurrentIndex(i)
                break
        self.fixed_channel_spin.setValue(int(s.get("fixed_channel", 6)))
        self.filter_edit.setText(s.get("filter_text", ""))
        self.hidden_only_cb.setChecked(bool(s.get("filter_hidden_only")))
        self.min_signal_spin.setValue(int(s.get("filter_min_signal", -100)))
        enc = s.get("filter_encryption", "any")
        ei = self.enc_filter.findText(enc)
        if ei >= 0:
            self.enc_filter.setCurrentIndex(ei)
        preset = s.get("adapter_preset", "")
        for i in range(self.preset_combo.count()):
            if self.preset_combo.itemData(i) == preset:
                self.preset_combo.setCurrentIndex(i)
                break

    def _collect_settings(self) -> dict:
        return {
            "iface": self.iface_combo.currentText(),
            "band": self.band_combo.currentText(),
            "dwell": self.dwell_spin.value(),
            "output": self.output_edit.text().strip(),
            "channel_mode": self.channel_mode_combo.currentData(),
            "fixed_channel": self.fixed_channel_spin.value(),
            "filter_text": self.filter_edit.text(),
            "filter_hidden_only": self.hidden_only_cb.isChecked(),
            "filter_min_signal": self.min_signal_spin.value(),
            "filter_encryption": self.enc_filter.currentText(),
            "adapter_preset": self.preset_combo.currentData() or "",
        }

    def _save_settings(self):
        try:
            save_settings(self._collect_settings())
        except OSError as e:
            self._append_log(f"[هشدار] ذخیره تنظیمات ناموفق: {e}")

    def _reset_stats_ui(self):
        for box, val in (
            (self.packet_stat, "0"), (self.network_stat, "0"),
            (self.client_stat, "0"), (self.channel_stat, "-"),
            (self.elapsed_stat, "00:00"), (self.filesize_stat, "-"),
        ):
            box.value_label.setText(val)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setSortingEnabled(True)
        self.client_table.setSortingEnabled(False)
        self.client_table.setRowCount(0)
        self.client_table.setSortingEnabled(True)
        self.heatmap.set_stats({})
        self.signal_chart.set_data([])
        self._last_network_fp = None
        self._last_client_fp = None
        self._networks_cache = {}
        self._clients_cache = {}
        self._channels_cache = {}
        self._signal_history = {}
        self._capture_dead_warned = False
        self._evil_warned = set()

    def _clear_log(self):
        self.log_text.clear()

    def _filtered_networks(self, networks: dict) -> dict:
        q = self.filter_edit.text().strip().lower()
        hidden_only = self.hidden_only_cb.isChecked()
        min_sig = self.min_signal_spin.value()
        enc_f = self.enc_filter.currentText().lower()
        out = {}
        for bssid, info in networks.items():
            ssid = str(info.get("ssid", ""))
            if hidden_only and ssid != "(پنهان/بدون نام)":
                continue
            if q and q not in bssid.lower() and q not in ssid.lower():
                continue
            sig = info.get("last_signal")
            if sig is not None and sig < min_sig:
                continue
            enc = str(info.get("encryption", "")).lower()
            if enc_f == "open" and "open" not in enc:
                continue
            if enc_f == "wpa3" and "wpa3" not in enc:
                continue
            if enc_f == "wpa2" and "wpa2" not in enc and "wpa3" not in enc:
                continue
            if enc_f == "wpa" and "wpa" not in enc:
                continue
            out[bssid] = info
        return out

    def _apply_filters(self):
        self._last_network_fp = None
        self._update_network_table(self._networks_cache)

    def _export_csv(self):
        if not self._networks_cache:
            QMessageBox.information(self, "CSV", "هنوز شبکه‌ای نیست.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره CSV", os.path.join(os.getcwd(), "networks.csv"), "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            write_networks_csv(path, self._networks_cache)
            self._append_log(f"CSV شبکه‌ها: {path}")
        except OSError as e:
            QMessageBox.critical(self, "خطا", str(e))

    def _export_clients_csv(self):
        if not self._clients_cache:
            QMessageBox.information(self, "CSV", "هنوز کلاینتی نیست.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره CSV", os.path.join(os.getcwd(), "clients.csv"), "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            write_clients_csv(path, self._clients_cache)
            self._append_log(f"CSV کلاینت‌ها: {path}")
        except OSError as e:
            QMessageBox.critical(self, "خطا", str(e))

    def _on_start(self):
        if self._busy or self.engine.state.running:
            return
        if self.engine.support_level == "unsupported":
            QMessageBox.critical(self, "خطا", "این پلتفرم پشتیبانی نمی‌شود.")
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
        channel_mode = self.channel_mode_combo.currentData()
        fixed_channel = self.fixed_channel_spin.value()
        if channel_mode == "fixed":
            allowed = set(CHANNELS_24GHZ + CHANNELS_5GHZ)
            if band == "2.4":
                allowed = set(CHANNELS_24GHZ)
            elif band == "5":
                allowed = set(CHANNELS_5GHZ)
            if fixed_channel not in allowed:
                QMessageBox.warning(
                    self, "کانال",
                    f"کانال {fixed_channel} با باند {band} سازگار نیست.",
                )
                return

        self._save_settings()
        self._file_logger.start()
        self._busy = True
        self.start_btn.setEnabled(False)
        self.status_label.setText("در حال راه‌اندازی...")
        self._reset_stats_ui()
        preset = self.preset_combo.currentData()
        if preset:
            self._append_log(f"Preset آداپتور: {ADAPTER_PRESETS.get(preset, preset)}")

        def worker():
            try:
                self.engine.start(
                    iface, output, band, dwell,
                    channel_mode=channel_mode,
                    fixed_channel=fixed_channel if channel_mode == "fixed" else None,
                )
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

    def _set_controls_enabled(self, enabled: bool):
        for w in (
            self.iface_combo, self.band_combo, self.dwell_spin,
            self.channel_mode_combo, self.fixed_channel_spin, self.preset_combo,
        ):
            w.setEnabled(enabled)
        if enabled:
            self._on_channel_mode_changed()

    def _on_started_ui(self):
        self._busy = False
        self._session_started_at = time.monotonic()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_controls_enabled(False)
        self.status_label.setText("در حال اجرا")

    def _on_stopped_ui(self):
        self._busy = False
        self._session_started_at = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._set_controls_enabled(True)
        self.status_label.setText("غیرفعال")
        self.channel_stat.value_label.setText("-")
        self._file_logger.close()
        self._refresh_readiness()
        self._save_settings()

    def _on_error_ui(self, message: str):
        self._busy = False
        self._session_started_at = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._set_controls_enabled(True)
        self.status_label.setText("خطا")
        self._append_log(f"[خطا] {message}")
        self._file_logger.close()
        QMessageBox.critical(self, "خطا", message)
        self._refresh_readiness()

    def _format_elapsed(self) -> str:
        if not self._session_started_at:
            return "00:00"
        secs = int(time.monotonic() - self._session_started_at)
        mm, ss = divmod(secs, 60)
        hh, mm = divmod(mm, 60)
        if hh:
            return f"{hh:02d}:{mm:02d}:{ss:02d}"
        return f"{mm:02d}:{ss:02d}"

    def _format_filesize(self, path: str) -> str:
        try:
            if path and os.path.isfile(path):
                n = os.path.getsize(path)
                if n < 1024:
                    return f"{n} B"
                if n < 1024 * 1024:
                    return f"{n/1024:.1f} KB"
                return f"{n/1024/1024:.2f} MB"
        except OSError:
            pass
        return "-"

    def _on_network_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 1)
        if item:
            self._selected_bssid = item.text().lower()
            self._refresh_sparkline()

    def _refresh_sparkline(self):
        hist = self._signal_history.get(self._selected_bssid) or []
        vals = [v for _, v in hist]
        title = f"سیگنال {self._selected_bssid}" if self._selected_bssid else "سیگنال"
        self.signal_chart.set_data(vals, title)

    def _check_evil_twins(self, networks: dict):
        for twin in find_evil_twins(networks):
            key = twin["ssid"]
            if key in self._evil_warned:
                continue
            self._evil_warned.add(key)
            msg = (
                f"[هشدار Evil Twin] SSID «{twin['ssid']}» روی "
                f"{twin['count']} BSSID: {', '.join(twin['bssids'])}"
            )
            self._append_log(msg)

    def _poll_state(self):
        if not self.engine.state.running:
            return
        health = self.engine.capture_health()
        if not health.get("capture_alive", True) and not self._capture_dead_warned:
            self._capture_dead_warned = True
            self._append_log("[هشدار] فرآیند کپچر متوقف شده — Stop کنید.")
            self.status_label.setText("کپچر قطع شد")

        ch = self.engine.current_channel()
        if ch is not None:
            self.channel_stat.value_label.setText(str(ch))

        data = self.engine.get_live_full()
        networks = data.get("networks") or {}
        clients = data.get("clients") or {}
        channels = data.get("channels") or {}
        self._signal_history = data.get("signal_history") or {}
        self._networks_cache = networks
        self._clients_cache = clients
        self._channels_cache = channels

        self.packet_stat.value_label.setText(str(data.get("total", 0)))
        self.network_stat.value_label.setText(str(len(networks)))
        self.client_stat.value_label.setText(str(len(clients)))
        self.elapsed_stat.value_label.setText(self._format_elapsed())
        self.filesize_stat.value_label.setText(
            self._format_filesize(health.get("output_path") or self.output_edit.text())
        )
        self._update_network_table(networks)
        self._update_client_table(clients)
        self.heatmap.set_stats(channels)
        self._refresh_sparkline()
        self._check_evil_twins(networks)

    def _update_network_table(self, networks: dict):
        visible = self._filtered_networks(networks)
        fp = (
            self.filter_edit.text(),
            self.hidden_only_cb.isChecked(),
            self.min_signal_spin.value(),
            self.enc_filter.currentText(),
            tuple(sorted(
                (b, i.get("ssid"), i.get("channel"), i.get("width"),
                 i.get("encryption"), i.get("vendor"), i.get("last_signal"), i.get("count"))
                for b, i in visible.items()
            )),
        )
        if fp == self._last_network_fp:
            return
        self._last_network_fp = fp
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(visible))
        for row, (bssid, info) in enumerate(
            sorted(visible.items(), key=lambda kv: -kv[1].get("count", 0))
        ):
            vals = [
                info.get("ssid", ""),
                bssid,
                str(info.get("channel") if info.get("channel") is not None else "-"),
                str(info.get("width") or "-"),
                str(info.get("encryption") or "-"),
                str(info.get("vendor") or "-"),
            ]
            for col, text in enumerate(vals):
                self.table.setItem(row, col, QTableWidgetItem(text))
            signal = info.get("last_signal")
            sitem = QTableWidgetItem()
            if signal is not None:
                sitem.setData(Qt.DisplayRole, int(signal))
            else:
                sitem.setText("-")
            self.table.setItem(row, 6, sitem)
            citem = QTableWidgetItem()
            citem.setData(Qt.DisplayRole, int(info.get("count", 0)))
            self.table.setItem(row, 7, citem)
        self.table.setSortingEnabled(sorting)

    def _update_client_table(self, clients: dict):
        fp = tuple(sorted(
            (k, v.get("ap_bssid"), v.get("ssid"), v.get("last_signal"), v.get("count"))
            for k, v in clients.items()
        ))
        if fp == self._last_client_fp:
            return
        self._last_client_fp = fp
        sorting = self.client_table.isSortingEnabled()
        self.client_table.setSortingEnabled(False)
        self.client_table.setRowCount(len(clients))
        for row, (sta, info) in enumerate(
            sorted(clients.items(), key=lambda kv: -kv[1].get("count", 0))
        ):
            self.client_table.setItem(row, 0, QTableWidgetItem(sta))
            self.client_table.setItem(row, 1, QTableWidgetItem(info.get("ap_bssid", "")))
            self.client_table.setItem(row, 2, QTableWidgetItem(info.get("ssid", "")))
            self.client_table.setItem(row, 3, QTableWidgetItem(info.get("vendor", "")))
            signal = info.get("last_signal")
            sitem = QTableWidgetItem()
            if signal is not None:
                sitem.setData(Qt.DisplayRole, int(signal))
            else:
                sitem.setText("-")
            self.client_table.setItem(row, 4, sitem)
            citem = QTableWidgetItem()
            citem.setData(Qt.DisplayRole, int(info.get("count", 0)))
            self.client_table.setItem(row, 5, citem)
        self.client_table.setSortingEnabled(sorting)

    def _append_log(self, msg: str):
        self.log_text.append(msg)

    def closeEvent(self, event):
        self._save_settings()
        if self.engine.state.running:
            try:
                self.engine.stop()
            except Exception:
                pass
        self._file_logger.close()
        event.accept()


def main():
    if ensure_windows_admin():
        # فرآیند elevated جداگانه شروع شده
        return
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
