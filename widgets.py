"""
Shared UI Components
Lives in its own module so both the Live View and the Analytics tab can use these
without ui_main and analytics_tab importing each other.
"""

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class MetricCard(QFrame):
    """Elevated Dashboard Metric Display Card."""

    def __init__(self, title: str, initial_value: str = "0", subtext: str = ""):
        super().__init__()
        self.setObjectName("MetricCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("MetricTitle")

        self.lbl_value = QLabel(initial_value)
        self.lbl_value.setObjectName("MetricValue")

        self.lbl_subtext = QLabel(subtext)
        self.lbl_subtext.setObjectName("MetricSubtext")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_subtext)

    def update_value(self, val: str):
        self.lbl_value.setText(val)

    def update_subtext(self, val: str):
        self.lbl_subtext.setText(val)
