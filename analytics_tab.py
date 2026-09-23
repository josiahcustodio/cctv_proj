"""
Historical Analytics Tab
Date-range filtered charts over the logged crossing, dwell, and zone-occupancy data.

Charts are rendered with matplotlib embedded via FigureCanvasQTAgg and themed to
match the application's dark QSS palette.
"""

from datetime import date, timedelta
from typing import List

import matplotlib
matplotlib.use("QtAgg")  # must be set before pyplot-adjacent imports

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import CAMERA_CONFIGS, ENGAGED_DWELL_SEC
from database import DatabaseManager
from widgets import MetricCard

# Palette aligned with styles.DARK_THEME_QSS
BG = "#252525"
FG = "#E0E0E0"
MUTED = "#808080"
GRID = "#383838"
CYAN = "#00A8E8"
RED = "#FF6B6B"
GREEN = "#2ECC71"
AMBER = "#F5A623"
PURPLE = "#9B59B6"
ZONE_COLORS = [CYAN, GREEN, AMBER, PURPLE, RED]

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _camera_label(cam_id: int) -> str:
    cfg = CAMERA_CONFIGS.get(cam_id)
    return cfg["name"] if cfg else f"Cam {cam_id}"


class ChartCanvas(FigureCanvasQTAgg):
    """A single dark-themed matplotlib figure sized for the chart grid."""

    def __init__(self, title: str, height: float = 3.1):
        self.fig = Figure(figsize=(5.5, height), dpi=100, facecolor=BG)
        super().__init__(self.fig)
        self.chart_title = title
        self.setMinimumHeight(int(height * 100))
        self.ax = self.fig.add_subplot(111)
        self._style_axes()

    def _style_axes(self):
        ax = self.ax
        ax.set_facecolor(BG)
        ax.tick_params(colors=MUTED, labelsize=8)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(GRID)
        ax.grid(True, color=GRID, linewidth=0.6, alpha=0.6)
        ax.set_axisbelow(True)
        ax.set_title(self.chart_title, color=FG, fontsize=10, fontweight="bold", pad=10, loc="left")

    def reset(self):
        """Clears the figure back to a styled, empty axes ready for redraw."""
        self.fig.clear()
        self.ax = self.fig.add_subplot(111)
        self._style_axes()

    def show_empty(self, message: str = "No data for this range"):
        self.ax.text(
            0.5, 0.5, message, ha="center", va="center",
            transform=self.ax.transAxes, color=MUTED, fontsize=10,
        )
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.grid(False)
        self.finish()

    def finish(self):
        try:
            self.fig.tight_layout()
        except Exception:
            pass  # tight_layout can fail on degenerate/empty axes; not worth crashing a redraw
        self.draw_idle()


class AnalyticsTab(QWidget):
    """Date-range analytics dashboard over the historical event tables."""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db = db_manager
        self._build_ui()
        self.set_quick_range(7)  # default view: last 7 days

    # --------------------------------------------------------------- UI setup

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(15, 12, 15, 12)
        root.setSpacing(12)

        root.addWidget(self._build_controls())
        root.addWidget(self._build_kpi_row())

        # Charts live in a scroll area so the grid stays usable on shorter screens.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background-color: #1E1E1E;")

        chart_host = QWidget()
        grid = QGridLayout(chart_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        self.chart_hourly = ChartCanvas("Footfall by Hour of Day")
        self.chart_daily = ChartCanvas("Daily Traffic Trend")
        self.chart_heatmap = ChartCanvas("Entries by Day & Hour")
        self.chart_zone_dwell = ChartCanvas("Average Dwell Time per Zone")
        self.chart_dwell_dist = ChartCanvas("Dwell Duration Distribution")
        self.chart_occupancy = ChartCanvas("People Present per Zone Over Time")

        for idx, canvas in enumerate([
            self.chart_hourly, self.chart_daily,
            self.chart_heatmap, self.chart_zone_dwell,
            self.chart_dwell_dist, self.chart_occupancy,
        ]):
            frame = QFrame()
            frame.setObjectName("ChartCard")
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(8, 8, 8, 8)
            fl.addWidget(canvas)
            grid.addWidget(frame, idx // 2, idx % 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        scroll.setWidget(chart_host)
        root.addWidget(scroll, stretch=1)

    def _build_controls(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("ControlBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        lbl_from = QLabel("From")
        lbl_from.setObjectName("ControlLabel")
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("yyyy-MM-dd")

        lbl_to = QLabel("To")
        lbl_to.setObjectName("ControlLabel")
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDisplayFormat("yyyy-MM-dd")

        btn_refresh = QPushButton("Apply")
        btn_refresh.clicked.connect(self.refresh)

        layout.addWidget(lbl_from)
        layout.addWidget(self.date_start)
        layout.addWidget(lbl_to)
        layout.addWidget(self.date_end)
        layout.addWidget(btn_refresh)
        layout.addSpacing(20)

        for label, days in (("Today", 1), ("7 Days", 7), ("30 Days", 30)):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, d=days: self.set_quick_range(d))
            layout.addWidget(btn)

        btn_all = QPushButton("All Data")
        btn_all.clicked.connect(self.set_full_range)
        layout.addWidget(btn_all)

        layout.addStretch()

        self.lbl_range_info = QLabel("")
        self.lbl_range_info.setObjectName("MetricSubtext")
        layout.addWidget(self.lbl_range_info)

        return bar

    def _build_kpi_row(self) -> QWidget:
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.kpi_visitors = MetricCard("Total Entries", "0", "Across selected range")
        self.kpi_daily_avg = MetricCard("Avg per Day", "0", "Entries per active day")
        self.kpi_peak = MetricCard("Peak Hour", "--", "Busiest time of day")
        self.kpi_dwell = MetricCard("Avg Dwell", "0.0s", "Across all zones")
        self.kpi_engaged = MetricCard("Engagement Rate", "0%", f"Dwells over {int(ENGAGED_DWELL_SEC)}s")
        self.kpi_zone = MetricCard("Top Zone", "--", "Longest average dwell")

        for card in (self.kpi_visitors, self.kpi_daily_avg, self.kpi_peak,
                     self.kpi_dwell, self.kpi_engaged, self.kpi_zone):
            layout.addWidget(card)

        return host

    # ---------------------------------------------------------- range helpers

    def set_quick_range(self, days: int):
        today = date.today()
        start = today - timedelta(days=days - 1)
        self.date_start.setDate(QDate(start.year, start.month, start.day))
        self.date_end.setDate(QDate(today.year, today.month, today.day))
        self.refresh()

    def set_full_range(self):
        first, last = self.db.get_available_date_range()
        if not first:
            self.set_quick_range(7)
            return
        self.date_start.setDate(QDate.fromString(first, "yyyy-MM-dd"))
        self.date_end.setDate(QDate.fromString(last, "yyyy-MM-dd"))
        self.refresh()

    def _range(self):
        start = self.date_start.date().toString("yyyy-MM-dd")
        end = self.date_end.date().toString("yyyy-MM-dd")
        if start > end:  # tolerate an inverted selection rather than showing nothing
            start, end = end, start
        return start, end

    # ----------------------------------------------------------------- redraw

    def refresh(self):
        start, end = self._range()
        self.lbl_range_info.setText(f"Showing {start} to {end}")

        self._refresh_kpis(start, end)
        self._draw_hourly(start, end)
        self._draw_daily(start, end)
        self._draw_heatmap(start, end)
        self._draw_zone_dwell(start, end)
        self._draw_dwell_distribution(start, end)
        self._draw_occupancy(start, end)

    def _refresh_kpis(self, start: str, end: str):
        s = self.db.get_range_summary(start, end)

        self.kpi_visitors.update_value(str(s["total_in"]))
        self.kpi_visitors.update_subtext(f"{s['total_out']} exits logged")

        self.kpi_daily_avg.update_value(str(s["avg_per_day"]))
        self.kpi_daily_avg.update_subtext(f"{s['active_days']} day(s) with data")

        if s["peak_hour"] is not None:
            hour = int(s["peak_hour"])
            self.kpi_peak.update_value(f"{hour:02d}:00")
            self.kpi_peak.update_subtext(f"to {(hour + 1) % 24:02d}:00")
        else:
            self.kpi_peak.update_value("--")
            self.kpi_peak.update_subtext("No entries recorded")

        self.kpi_dwell.update_value(f"{s['avg_dwell']}s")
        self.kpi_dwell.update_subtext(f"{s['dwell_count']} zone visits")

        durations = self.db.get_dwell_durations(start, end)
        if durations:
            engaged = sum(1 for d in durations if d >= ENGAGED_DWELL_SEC)
            pct = round(100.0 * engaged / len(durations))
            self.kpi_engaged.update_value(f"{pct}%")
            self.kpi_engaged.update_subtext(f"{engaged} of {len(durations)} visits")
        else:
            self.kpi_engaged.update_value("0%")
            self.kpi_engaged.update_subtext("No dwell data")

        if s["busiest_zone"] is not None:
            self.kpi_zone.update_value(_camera_label(int(s["busiest_zone"])))
            self.kpi_zone.update_subtext(f"{s['max_dwell']}s longest visit")
        else:
            self.kpi_zone.update_value("--")
            self.kpi_zone.update_subtext("No zone data")

    def _draw_hourly(self, start: str, end: str):
        c = self.chart_hourly
        c.reset()
        rows = self.db.get_hourly_footfall(start, end)
        if not rows:
            c.show_empty()
            return

        # Expand to all 24 hours. Plotting only hours that have rows would place
        # non-adjacent hours side by side (04 next to 17), silently hiding the
        # quiet stretch between them and misreading as continuous trading.
        by_hour = {r[0]: (r[1], r[2]) for r in rows}
        hours = list(range(24))
        ins = [by_hour.get(h, (0, 0))[0] for h in hours]
        outs = [by_hour.get(h, (0, 0))[1] for h in hours]
        width = 0.4

        c.ax.bar([h - width / 2 for h in hours], ins, width, label="IN", color=CYAN)
        c.ax.bar([h + width / 2 for h in hours], outs, width, label="OUT", color=RED)
        c.ax.set_xticks(list(range(0, 24, 2)))
        c.ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)], fontsize=7)
        c.ax.set_xlim(-1, 24)
        c.ax.set_xlabel("Hour", color=MUTED, fontsize=8)
        c.ax.set_ylabel("Crossings", color=MUTED, fontsize=8)
        c.ax.legend(facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=8)
        c.finish()

    def _draw_daily(self, start: str, end: str):
        c = self.chart_daily
        c.reset()
        rows = self.db.get_daily_traffic(start, end)
        if not rows:
            c.show_empty()
            return

        labels = [r[0][5:] for r in rows]  # MM-DD keeps the axis readable
        ins = [r[1] for r in rows]
        outs = [r[2] for r in rows]

        x = list(range(len(labels)))
        c.ax.plot(x, ins, marker="o", color=CYAN, linewidth=2, label="Entries", markersize=4)
        c.ax.plot(x, outs, marker="o", color=RED, linewidth=2, label="Exits", markersize=4)
        c.ax.fill_between(x, ins, color=CYAN, alpha=0.15)
        c.ax.set_xticks(x)
        c.ax.set_xticklabels(labels)
        c.ax.set_ylabel("Crossings", color=MUTED, fontsize=8)
        c.ax.legend(facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=8)
        if len(labels) > 10:
            for lbl in c.ax.get_xticklabels():
                lbl.set_rotation(45)
                lbl.set_ha("right")
        c.finish()

    def _draw_heatmap(self, start: str, end: str):
        c = self.chart_heatmap
        c.reset()
        matrix = self.db.get_dow_hour_matrix(start, end)
        if not any(any(row) for row in matrix):
            c.show_empty()
            return

        im = c.ax.imshow(matrix, aspect="auto", cmap="viridis", interpolation="nearest")
        c.ax.set_yticks(range(7))
        c.ax.set_yticklabels(DAY_LABELS, fontsize=8)
        c.ax.set_xticks(range(0, 24, 2))
        c.ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)], fontsize=7)
        c.ax.set_xlabel("Hour", color=MUTED, fontsize=8)
        c.ax.grid(False)
        cbar = c.fig.colorbar(im, ax=c.ax, fraction=0.03, pad=0.02)
        cbar.ax.tick_params(colors=MUTED, labelsize=7)
        cbar.outline.set_edgecolor(GRID)
        c.finish()

    def _draw_zone_dwell(self, start: str, end: str):
        c = self.chart_zone_dwell
        c.reset()
        rows = self.db.get_dwell_by_zone(start, end)
        if not rows:
            c.show_empty("No zone dwell data yet")
            return

        names = [_camera_label(r[0]) for r in rows]
        avgs = [round(r[1], 1) for r in rows]
        counts = [r[2] for r in rows]
        colors = [ZONE_COLORS[i % len(ZONE_COLORS)] for i in range(len(rows))]

        bars = c.ax.barh(names, avgs, color=colors, height=0.55)
        c.ax.set_xlabel("Average dwell (seconds)", color=MUTED, fontsize=8)
        c.ax.invert_yaxis()
        for bar, avg, count in zip(bars, avgs, counts):
            c.ax.text(
                bar.get_width(), bar.get_y() + bar.get_height() / 2,
                f"  {avg}s ({count} visits)", va="center", color=FG, fontsize=8,
            )
        c.ax.margins(x=0.25)
        c.finish()

    def _draw_dwell_distribution(self, start: str, end: str):
        c = self.chart_dwell_dist
        c.reset()
        durations: List[float] = self.db.get_dwell_durations(start, end)
        if not durations:
            c.show_empty("No zone dwell data yet")
            return

        c.ax.hist(durations, bins=min(24, max(5, len(durations) // 3)),
                  color=CYAN, edgecolor=BG, linewidth=0.8)
        # The threshold line is what separates a passer-by from an engaged shopper,
        # which an average alone hides entirely.
        c.ax.axvline(ENGAGED_DWELL_SEC, color=AMBER, linestyle="--", linewidth=1.5,
                     label=f"Engaged ({int(ENGAGED_DWELL_SEC)}s)")
        c.ax.set_xlabel("Dwell duration (seconds)", color=MUTED, fontsize=8)
        c.ax.set_ylabel("Visits", color=MUTED, fontsize=8)
        c.ax.legend(facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=8)
        c.finish()

    def _draw_occupancy(self, start: str, end: str):
        c = self.chart_occupancy
        c.reset()
        series = self.db.get_zone_occupancy_series(start, end)
        if not series:
            c.show_empty("No occupancy samples yet")
            return

        # Plot against minutes-since-midnight rather than bucket labels, so the
        # axis is a true timeline. Buckets with no samples stay NaN, which breaks
        # the line instead of drawing a phantom trend across a closed period.
        for idx, (cam_id, points) in enumerate(sorted(series.items())):
            by_minute = {}
            for label, value in points:
                hh, mm = label.split(":")
                by_minute[int(hh) * 60 + int(mm)] = round(value, 2)

            xs = list(range(0, 24 * 60, 15))
            ys = [by_minute.get(m, float("nan")) for m in xs]
            c.ax.plot(
                xs, ys, marker="o", markersize=3, linewidth=1.8,
                color=ZONE_COLORS[idx % len(ZONE_COLORS)], label=_camera_label(cam_id),
            )

        c.ax.set_ylabel("Avg people present", color=MUTED, fontsize=8)
        c.ax.set_xlabel("Time of day", color=MUTED, fontsize=8)
        c.ax.set_xlim(0, 24 * 60)
        c.ax.set_xticks(list(range(0, 24 * 60 + 1, 120)))
        c.ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 2)], fontsize=7)
        c.ax.legend(facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=8)
        for lbl in c.ax.get_xticklabels():
            lbl.set_rotation(45)
            lbl.set_ha("right")
        c.finish()
