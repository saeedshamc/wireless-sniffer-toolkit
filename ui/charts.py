"""ویجت‌های نموداری سبک با QPainter (بدون QtCharts)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget


class SignalSparkline(QWidget):
    """نمودار سیگنال در زمان برای یک BSSID."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []  # list of dBm
        self._title = "سیگنال"
        self.setMinimumHeight(120)

    def set_data(self, points, title="سیگنال"):
        self._points = list(points or [])
        self._title = title
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#16171d"))
        p.setPen(QColor("#7cc4ff"))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(10, 18, self._title)

        if len(self._points) < 2:
            p.setPen(QColor("#888"))
            p.drawText(self.rect(), Qt.AlignCenter, "داده‌ای نیست")
            return

        w, h = self.width(), self.height()
        left, right, top, bottom = 40, 10, 28, 16
        plot_w = max(1, w - left - right)
        plot_h = max(1, h - top - bottom)

        lo, hi = -100, -20
        vals = self._points
        p.setPen(QPen(QColor("#33343f"), 1))
        p.drawRect(left, top, plot_w, plot_h)

        path_pen = QPen(QColor("#6cf07a"), 2)
        p.setPen(path_pen)
        last = None
        n = len(vals)
        for i, v in enumerate(vals):
            x = left + (i / (n - 1)) * plot_w
            y = top + (1 - (max(lo, min(hi, v)) - lo) / (hi - lo)) * plot_h
            if last:
                p.drawLine(int(last[0]), int(last[1]), int(x), int(y))
            last = (x, y)

        p.setPen(QColor("#888"))
        p.drawText(4, top + 10, f"{hi}")
        p.drawText(4, top + plot_h, f"{lo}")


class ChannelHeatmap(QWidget):
    """نمایش ساده شلوغی کانال‌ها."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stats = {}  # channel -> {count, best_signal}
        self.setMinimumHeight(160)

    def set_stats(self, stats: dict):
        self._stats = dict(stats or {})
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#16171d"))
        p.setPen(QColor("#7cc4ff"))
        p.drawText(10, 18, "تراکم کانال‌ها")

        if not self._stats:
            p.setPen(QColor("#888"))
            p.drawText(self.rect(), Qt.AlignCenter, "داده‌ای نیست")
            return

        channels = sorted(self._stats.keys())
        max_count = max(v.get("count", 0) for v in self._stats.values()) or 1
        w, h = self.width(), self.height()
        left, top, bottom = 10, 30, 24
        bar_area_h = h - top - bottom
        gap = 4
        bar_w = max(6, (w - 2 * left - gap * (len(channels) - 1)) // len(channels))

        for i, ch in enumerate(channels):
            count = self._stats[ch].get("count", 0)
            ratio = count / max_count
            bh = max(2, int(bar_area_h * ratio))
            x = left + i * (bar_w + gap)
            y = top + bar_area_h - bh
            color = QColor("#1f7a3d")
            if ratio > 0.66:
                color = QColor("#c45c26")
            elif ratio > 0.33:
                color = QColor("#d0a24c")
            p.fillRect(QRectF(x, y, bar_w, bh), color)
            p.setPen(QColor("#aaa"))
            p.drawText(int(x), h - 6, str(ch))
