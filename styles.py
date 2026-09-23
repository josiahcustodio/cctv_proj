"""
Modern Flat Dark Qt Style Sheet (QSS)
Color Palette: Charcoal/Slate (#1E1E1E, #252525), Cards (#2D2D2D), Cyan (#00A8E8), Soft Red (#FF6B6B)
"""

DARK_THEME_QSS = """
QMainWindow {
    background-color: #1E1E1E;
}

QWidget {
    font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    color: #E0E0E0;
}

/* Header & Toolbars */
#HeaderFrame {
    background-color: #252525;
    border-bottom: 1px solid #333333;
    padding: 10px 20px;
}

#AppTitle {
    font-size: 20px;
    font-weight: bold;
    color: #00A8E8;
}

#StatusDot {
    border-radius: 6px;
    min-width: 12px;
    max-width: 12px;
    min-height: 12px;
    max-height: 12px;
}

.StatusOnline {
    background-color: #2ECC71;
}

.StatusOffline {
    background-color: #FF6B6B;
}

/* Analytics Metric Cards */
#MetricCard {
    background-color: #2D2D2D;
    border-radius: 8px;
    border: 1px solid #383838;
    padding: 8px 15px;
}

#MetricCard:hover {
    border: 1px solid #00A8E8;
}

#MetricTitle {
    font-size: 12px;
    font-weight: 600;
    color: #A0A0A0;
    text-transform: uppercase;
}

#MetricValue {
    font-size: 22px;
    font-weight: bold;
    color: #FFFFFF;
    margin-top: 2px;
}

#MetricSubtext {
    font-size: 11px;
    color: #707070;
}

/* Buttons & Controls */
QPushButton {
    background-color: #333333;
    border: 1px solid #444444;
    border-radius: 5px;
    padding: 8px 16px;
    color: #FFFFFF;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #00A8E8;
    border-color: #00A8E8;
    color: #FFFFFF;
}

QPushButton:pressed {
    background-color: #0077A3;
}

QPushButton:checked {
    background-color: #00A8E8;
    color: #FFFFFF;
}

/* Video Grid & Placeholders */
#CameraCard {
    background-color: #252525;
    border-radius: 8px;
    border: 1px solid #333333;
}

#CameraCardSelected {
    background-color: #252525;
    border-radius: 8px;
    border: 2px solid #00A8E8;
}

#VideoSurface {
    background-color: #121212;
    border-radius: 6px;
}

#PlaceholderLabel {
    color: #555555;
    font-size: 14px;
    font-weight: bold;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #1E1E1E;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #333333;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #00A8E8;
}

/* Tab Bar */
#MainTabs::pane {
    border: none;
    background-color: #1E1E1E;
}

QTabBar::tab {
    background-color: #252525;
    color: #A0A0A0;
    padding: 10px 26px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
    font-size: 12px;
}

QTabBar::tab:hover {
    color: #E0E0E0;
}

QTabBar::tab:selected {
    color: #00A8E8;
    border-bottom: 2px solid #00A8E8;
}

/* Analytics Controls */
#ControlBar {
    background-color: #252525;
    border-radius: 8px;
    border: 1px solid #333333;
}

#ControlLabel {
    font-size: 11px;
    font-weight: 600;
    color: #A0A0A0;
    text-transform: uppercase;
}

QDateEdit {
    background-color: #2D2D2D;
    border: 1px solid #444444;
    border-radius: 5px;
    padding: 6px 10px;
    color: #FFFFFF;
    min-width: 100px;
}

QDateEdit:hover {
    border-color: #00A8E8;
}

QDateEdit::drop-down {
    border: none;
    width: 18px;
}

QCalendarWidget QWidget {
    background-color: #252525;
    color: #E0E0E0;
}

QCalendarWidget QAbstractItemView:enabled {
    background-color: #252525;
    color: #E0E0E0;
    selection-background-color: #00A8E8;
    selection-color: #FFFFFF;
}

/* Chart Containers */
#ChartCard {
    background-color: #252525;
    border-radius: 8px;
    border: 1px solid #333333;
}
"""
