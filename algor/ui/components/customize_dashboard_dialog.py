from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                             QPushButton, QCheckBox, QScrollArea, QWidget)

from algor.core.hardware import TelemetryData
from algor.core.i18n import _
from algor.core.sensors import build_sensor_list
from algor.ui.theme import Theme


class CustomizeDashboardDialog(QDialog):
    """Modal 'Personalizar Panel' estilo iCUE: activa/desactiva qué sensores
    se muestran como medidores en el Panel General."""

    def __init__(self, current_ids: List[str], latest_data: Optional[TelemetryData], parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Personalizar Panel"))
        self.setMinimumSize(440, 540)
        self.setStyleSheet(Theme.build_stylesheet())
        self._checks: Dict[str, QCheckBox] = {}
        self._build_ui(current_ids, latest_data)

    def _build_ui(self, current_ids: List[str], latest_data: Optional[TelemetryData]) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        title = QLabel(_("🧩 Personalizar Panel General"))
        title.setStyleSheet(f"font-weight: bold; font-size: {Theme.pt(3)}pt; color: #f0f6fc;")
        layout.addWidget(title)

        subtitle = QLabel(_("Elige qué sensores se muestran como medidores circulares en el Panel General."))
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: {Theme.pt(-1)}pt;")
        layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(10)

        sensors = build_sensor_list(latest_data)
        categories: Dict[str, list] = {}
        for sensor in sensors:
            categories.setdefault(sensor.category, []).append(sensor)

        for category, cat_sensors in categories.items():
            group = QFrame()
            group.setObjectName("InnerCard")
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(14, 10, 14, 10)
            group_layout.setSpacing(4)

            cat_label = QLabel(category.upper())
            cat_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: {Theme.pt(-2)}pt; font-weight: 700; letter-spacing: 1px;")
            group_layout.addWidget(cat_label)

            for sensor in cat_sensors:
                chk = QCheckBox(f"{sensor.label}   ({sensor.unit})")
                chk.setChecked(sensor.id in current_ids)
                chk.setCursor(Qt.CursorShape.PointingHandCursor)
                self._checks[sensor.id] = chk
                group_layout.addWidget(chk)

            content_layout.addWidget(group)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        button_row = QHBoxLayout()
        btn_all = QPushButton(_("Activar Todo"))
        btn_all.clicked.connect(self._activate_all)
        button_row.addWidget(btn_all)
        button_row.addStretch()

        btn_cancel = QPushButton(_("Cancelar"))
        btn_cancel.clicked.connect(self.reject)
        button_row.addWidget(btn_cancel)

        btn_apply = QPushButton(_("Aplicar"))
        btn_apply.setObjectName("PrimaryBtn")
        btn_apply.clicked.connect(self.accept)
        button_row.addWidget(btn_apply)

        layout.addLayout(button_row)

    def _activate_all(self) -> None:
        for chk in self._checks.values():
            chk.setChecked(True)

    def selected_ids(self) -> List[str]:
        return [sid for sid, chk in self._checks.items() if chk.isChecked()]
