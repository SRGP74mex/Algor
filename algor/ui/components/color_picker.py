"""Paleta rápida y barra de tono para contenido LCD."""
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel, QColorDialog
from algor.core.i18n import _


class ColorPicker(QWidget):
    color_changed = pyqtSignal(str)
    PRESETS = ('#3286e6', '#2094a0', '#369849', '#d29300', '#fa5b00', '#ef2541', '#d659a4', '#9643b0', '#74899c')

    def __init__(self, color='#00f0ff', parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(90)
        self._timer.timeout.connect(lambda: self.color_changed.emit(self._color.name()))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        row = QHBoxLayout()
        row.setSpacing(5)
        self._buttons = []
        for hex_color in self.PRESETS:
            button = QPushButton()
            button.setFixedSize(28,28)
            button.setToolTip(hex_color)
            button.setAccessibleName(_('Color {hex}').format(hex=hex_color))
            button.clicked.connect(lambda checked=False, c=hex_color: self.set_color(c, emit=True))
            self._buttons.append((button, hex_color)); row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel(_('Tono')))
        self.hue = QSlider(Qt.Orientation.Horizontal)
        self.hue.setRange(0,359)
        self.hue.setAccessibleName(_('Tono del color del LCD'))
        self.hue.setStyleSheet('''QSlider::groove:horizontal {height: 12px; border-radius: 5px;
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 red,stop:0.17 yellow,stop:0.33 lime,stop:0.5 cyan,stop:0.67 blue,stop:0.83 magenta,stop:1 red);}
            QSlider::sub-page:horizontal, QSlider::add-page:horizontal {background: transparent; border: none;}
            QSlider::handle:horizontal {background: white; border: 2px solid #222; width:18px; margin:-5px 0; border-radius:10px;}''')
        row.addWidget(self.hue)
        self.custom = QPushButton()
        self.custom.setFixedWidth(96)
        self.custom.setToolTip(_('Elegir color personalizado'))
        self.custom.clicked.connect(self._choose)
        row.addWidget(self.custom)
        layout.addLayout(row)
        self.hue.valueChanged.connect(self._hue_changed)
        self.set_color(color)

    def set_color(self, color, emit=False):
        value = QColor(color)
        if not value.isValid():
            return
        self._color = value
        self.hue.blockSignals(True)
        self.hue.setValue(max(0, value.hsvHue()))
        self.hue.blockSignals(False)
        for button, preset in self._buttons:
            border = '2px solid white' if value.name() == preset else '1px solid #445066'
            button.setStyleSheet(f'background: {preset}; border: {border}; border-radius: 14px; padding: 0;')
        self.custom.setText(value.name().upper())
        text = '#101827' if value.lightness() > 150 else 'white'
        self.custom.setStyleSheet(f'background:{value.name()}; color:{text}; border:1px solid #778899; border-radius:8px; padding:5px;')
        if emit:
            self._timer.stop()
            self.color_changed.emit(value.name())

    def _hue_changed(self, hue):
        self.set_color(QColor.fromHsv(hue,255,255))
        self._timer.start()

    def _choose(self):
        value = QColorDialog.getColor(self._color, self, _('Color del LCD'))
        if value.isValid():
            self.set_color(value, emit=True)
