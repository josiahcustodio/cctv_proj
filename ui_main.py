"""
Main Application UI Window & Component Widgets
Implements elevated metric cards, responsive video grid switcher, and offline indicator.
"""

from typing import Dict, List
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from analytics_tab import AnalyticsTab
from config import CAMERA_CONFIGS
from database import DatabaseManager
from rtsp_capture import RTSPCaptureThread
from inference_engine import BatchedInferenceThread
from widgets import MetricCard


class CameraWidget(QFrame):
    """Widget container for camera streams with click-to-pin support."""

    clicked = Signal(int)

    def __init__(self, camera_id: int, camera_name: str):
        super().__init__()
        self.camera_id = camera_id
        self.setObjectName("CameraCard")
        self.setMinimumSize(320, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # Header Title
        self.lbl_name = QLabel(f"CAM {camera_id}: {camera_name}")
        self.lbl_name.setStyleSheet("font-weight: bold; color: #00A8E8; font-size: 11px;")
        layout.addWidget(self.lbl_name)

        # Video Display Surface
        self.video_surface = QLabel()
        self.video_surface.setObjectName("VideoSurface")
        self.video_surface.setAlignment(Qt.AlignCenter)
        self.video_surface.setMinimumSize(1, 1)
        
        # Sleek Offline Placeholder State
        self.show_placeholder("Camera Disconnected / Offline Slot")
        layout.addWidget(self.video_surface, stretch=1)

    def show_placeholder(self, message: str):
        self.video_surface.setPixmap(QPixmap())
        self.video_surface.setText(message)
        self.video_surface.setStyleSheet("color: #555555; font-size: 12px; font-weight: bold;")

    def update_image(self, qimg: QImage):
        self.video_surface.setText("")
        pixmap = QPixmap.fromImage(qimg)
        # Scale to fit while maintaining aspect ratio
        scaled = pixmap.scaled(
            self.video_surface.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.video_surface.setPixmap(scaled)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.camera_id)
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db = db_manager
        self.capture_threads: List[RTSPCaptureThread] = []
        self.inference_thread = None
        self.camera_widgets: Dict[int, CameraWidget] = {}
        self.pinned_camera_id: int = None
        self.live_occupancy: Dict[int, int] = {}

        self.setWindowTitle("VisionAnalytics - Retail Intelligence Suite")
        self.resize(1600, 950)

        self._build_ui()

        # Timer for polling database aggregation summary metrics
        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self._refresh_metrics)
        self.metrics_timer.start(2000)

    def _build_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        root_layout = QVBoxLayout(main_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Top Header Bar
        header = QFrame()
        header.setObjectName("HeaderFrame")
        header_layout = QHBoxLayout(header)

        title = QLabel("RETAIL STORE TRAFFIC & AREA DWELL ANALYTICS")
        title.setObjectName("AppTitle")

        self.sync_dot = QFrame()
        self.sync_dot.setObjectName("StatusDot")
        self.sync_dot.setProperty("class", "StatusOnline")

        self.lbl_sync = QLabel("Database Sync: Active")
        self.lbl_sync.setStyleSheet("font-size: 12px; color: #A0A0A0;")

        # Grid view switcher controls
        self.btn_grid_2x2 = QPushButton("Grid 2x2")
        self.btn_grid_2x2.clicked.connect(lambda: self._set_grid_layout(4))

        self.btn_grid_4x2 = QPushButton("Grid 8-Cam")
        self.btn_grid_4x2.clicked.connect(lambda: self._set_grid_layout(8))

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_grid_2x2)
        header_layout.addWidget(self.btn_grid_4x2)
        header_layout.addSpacing(20)
        header_layout.addWidget(self.sync_dot)
        header_layout.addWidget(self.lbl_sync)

        root_layout.addWidget(header)

        # 2. Tabbed body: the live wall, and the historical analytics dashboard.
        self.tabs = QTabWidget()
        self.tabs.setObjectName("MainTabs")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root_layout.addWidget(self.tabs, stretch=1)

        live_tab = QWidget()
        live_layout = QVBoxLayout(live_tab)
        live_layout.setContentsMargins(0, 0, 0, 0)
        live_layout.setSpacing(0)

        # 2a. Key Performance Indicators (Metrics Row)
        metrics_container = QWidget()
        metrics_layout = QHBoxLayout(metrics_container)
        metrics_layout.setContentsMargins(15, 5, 15, 5)

        self.card_in = MetricCard("Store Entries (IN)", "0", "Total visitors today")
        self.card_out = MetricCard("Store Exits (OUT)", "0", "Total exits today")
        self.card_occ = MetricCard("Current Occupancy", "0", "Real-time count")
        self.card_dwell = MetricCard("Avg Dwell Time", "0.0s", "Zone engagement")

        metrics_layout.addWidget(self.card_in)
        metrics_layout.addWidget(self.card_out)
        metrics_layout.addWidget(self.card_occ)
        metrics_layout.addWidget(self.card_dwell)

        live_layout.addWidget(metrics_container)

        # 2b. Dynamic Video Grid Area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background-color: #1E1E1E;")

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(15, 10, 15, 15)
        self.grid_layout.setSpacing(10)

        # Create camera widgets for all slots (1 to 8)
        for cam_id, cfg in CAMERA_CONFIGS.items():
            cam_widget = CameraWidget(cam_id, cfg["name"])
            cam_widget.clicked.connect(self._handle_camera_pin)
            self.camera_widgets[cam_id] = cam_widget

        scroll_area.setWidget(self.grid_container)
        live_layout.addWidget(scroll_area, stretch=1)

        self.tabs.addTab(live_tab, "Live View")

        # 3. Analytics tab over the historical event tables.
        self.analytics_tab = AnalyticsTab(self.db)
        self.tabs.addTab(self.analytics_tab, "Analytics")

        self._set_grid_layout(4)  # Default 2x2 grid layout

    def start_camera_workers(self):
        """Spawns processing worker threads per configured camera.
        
        Camera pre-connection runs in a background thread so the UI stays
        responsive even when cameras are unreachable.  Each capture thread
        is started as soon as its connection attempt finishes (or fails).
        """
        from PySide6.QtCore import QThread as _QThread, Signal as _Signal

        class _ConnectorThread(_QThread):
            """Background thread that pre-connects cameras one by one."""
            camera_ready = _Signal(int, object)  # cam_id, initial_cap (or None)
            all_done = _Signal()

            def __init__(self, configs):
                super().__init__()
                self.configs = configs

            def run(self):
                from rtsp_capture import pre_connect_camera
                for cam_id, cfg in self.configs.items():
                    if "offline" in cfg["rtsp_url"]:
                        continue
                    initial_cap = pre_connect_camera(cam_id, cfg["rtsp_url"], cfg["fallback_url"])
                    self.camera_ready.emit(cam_id, initial_cap)
                self.all_done.emit()

        def _on_camera_ready(cam_id, initial_cap):
            cfg = CAMERA_CONFIGS[cam_id]
            thread = RTSPCaptureThread(
                cam_id, cfg["rtsp_url"], cfg["fallback_url"],
                initial_cap=initial_cap,
            )
            thread.status_changed.connect(self._on_camera_status)
            self.capture_threads.append(thread)
            thread.start()

        def _on_all_connected():
            if self.capture_threads:
                self.inference_thread = BatchedInferenceThread(self.capture_threads, self.db)
                self.inference_thread.frame_processed.connect(self._on_frame_received)
                self.inference_thread.start()
            # prevent garbage collection of the connector thread
            self._connector_thread = None

        self._connector_thread = _ConnectorThread(CAMERA_CONFIGS)
        self._connector_thread.camera_ready.connect(_on_camera_ready)
        self._connector_thread.all_done.connect(_on_all_connected)
        self._connector_thread.start()

    def _on_tab_changed(self, index: int):
        """Re-queries analytics on entry so the charts never show stale numbers."""
        is_live = self.tabs.tabText(index) == "Live View"
        self.btn_grid_2x2.setVisible(is_live)
        self.btn_grid_4x2.setVisible(is_live)
        if not is_live:
            self.analytics_tab.refresh()

    def _set_grid_layout(self, max_cameras: int):
        """Rearranges visible camera cards into responsive grid layout."""
        self.pinned_camera_id = None
        # Clear current grid
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget().setParent(None)

        cols = 2 if max_cameras <= 4 else 4
        for idx, (cam_id, widget) in enumerate(self.camera_widgets.items()):
            if idx < max_cameras:
                row = idx // cols
                col = idx % cols
                widget.setObjectName("CameraCard")
                widget.setStyle(widget.style())
                widget.setVisible(True)
                self.grid_layout.addWidget(widget, row, col)
            else:
                widget.setVisible(False)

    def _handle_camera_pin(self, camera_id: int):
        """Focuses/pins a single camera view when clicked."""
        if self.pinned_camera_id == camera_id:
            # Unpin and revert layout
            self._set_grid_layout(4)
            return

        self.pinned_camera_id = camera_id
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget().setParent(None)

        for cid, widget in self.camera_widgets.items():
            if cid == camera_id:
                widget.setObjectName("CameraCardSelected")
                widget.setStyle(widget.style())
                widget.setVisible(True)
                self.grid_layout.addWidget(widget, 0, 0)
            else:
                widget.setVisible(False)

    def _on_frame_received(self, camera_id: int, qimg: QImage, metrics: dict):
        if camera_id in self.camera_widgets:
            self.camera_widgets[camera_id].update_image(qimg)
            
        if "people_present" in metrics:
            self.live_occupancy[camera_id] = metrics["people_present"]

    def _on_camera_status(self, camera_id: int, online: bool):
        if camera_id in self.camera_widgets and not online:
            self.camera_widgets[camera_id].show_placeholder("Stream Disconnected - Retrying...")

    def _refresh_metrics(self):
        """Queries SQLite summary and updates UI cards."""
        try:
            data = self.db.get_today_summary()
            self.card_in.update_value(str(data["total_in"]))
            self.card_out.update_value(str(data["total_out"]))

            # Store-wide net occupancy (entrance IN - OUT), matching the card's label.
            self.card_occ.update_value(str(data["occupancy"]))
            zones_now = sum(self.live_occupancy.values())
            self.card_occ.update_subtext(f"{zones_now} currently in display zones")

            self.card_dwell.update_value(f"{data['avg_dwell']}s")

            self.sync_dot.setProperty("class", "StatusOnline")
            self.sync_dot.setStyle(self.sync_dot.style())
            self.lbl_sync.setText("Database Sync: Active")
        except Exception:
            self.sync_dot.setProperty("class", "StatusOffline")
            self.sync_dot.setStyle(self.sync_dot.style())
            self.lbl_sync.setText("Database Sync: Error")

    def closeEvent(self, event):
        """Gracefully closes worker threads on exit."""
        if self.inference_thread:
            self.inference_thread.stop()
        for thread in self.capture_threads:
            thread.stop()
        event.accept()