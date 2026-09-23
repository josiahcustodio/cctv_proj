"""
Application Main Entry Point
Configures High-DPI scaling, application lifecycle, and initializes GUI loop.
"""

import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from database import DatabaseManager
from styles import DARK_THEME_QSS
from ui_main import MainWindow
from engine_builder import ensure_tensorrt_engine


def configure_high_dpi():
    """Configures environment settings for High-DPI display scaling."""
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"


def main():
    configure_high_dpi()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_THEME_QSS)

    # Initialize Thread-Safe SQLite Database
    db_manager = DatabaseManager()

    # Launch Main Window immediately so the UI is visible
    window = MainWindow(db_manager)
    window.show()

    # Defer heavy startup (TensorRT check + camera connections) to after the
    # event loop is running so the window is responsive from the start, even
    # when no cameras are reachable.
    from PySide6.QtCore import QTimer

    def _deferred_startup():
        print("[INFO] Checking TensorRT Engine...")
        ensure_tensorrt_engine()
        window.start_camera_workers()

    QTimer.singleShot(0, _deferred_startup)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()