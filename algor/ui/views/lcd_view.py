from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QPixmap, QDesktopServices
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                             QPushButton, QComboBox, QSlider, QFileDialog, QCheckBox, QScrollArea, QMessageBox)
from algor.core.config import config
from algor.core.i18n import _
from algor.core.media_library import library_directory
from algor.core.media_import_worker import MediaImportWorker
from algor.core.lcd_memory import load_captured_image
from algor.core.lcd_renderer import normalize_settings
from algor.ui.components.lcd_preview import LCDCapPreview
from algor.ui.components.color_picker import ColorPicker


class LCDView(QWidget):
    settings_changed = pyqtSignal(dict)
    session_requested = pyqtSignal(bool)
    memory_requested = pyqtSignal(object)
    memory_prepare_requested = pyqtSignal(str, int)
    memory_query_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lcd_cfg = normalize_settings(config.get('lcd_cap', {}))
        self._import_worker = None
        self._requested = False
        self._memory_busy = False
        self._custom_memory = None
        self._memory_asset_valid = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(16)
        preview_card = QFrame()
        preview_card.setObjectName('Card')
        left = QVBoxLayout(preview_card)
        title = QLabel('Nautilus LCD Cap')
        title.setStyleSheet('font-size: 19px; font-weight: 700; color: #f0f6fc;')
        left.addWidget(title)
        left.addWidget(QLabel(_('Contenido de pantalla · 480 × 480')))
        self.lcd_preview = LCDCapPreview()
        left.addWidget(self.lcd_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        self.lbl_usb_status = QLabel(_('LCD detenido · previsualización local'))
        self.lbl_usb_status.setWordWrap(True)
        left.addWidget(self.lbl_usb_status)
        self.lbl_session_note = QLabel(_('La imagen se mantiene mientras Algor esté en ejecución, incluso en la bandeja.'))
        self.lbl_session_note.setWordWrap(True)
        left.addWidget(self.lbl_session_note)
        left.addStretch()
        layout.addWidget(preview_card, 2)

        controls = QFrame()
        controls.setObjectName('Card')
        right = QVBoxLayout(controls)
        right.setSpacing(12)
        heading = QLabel(_('Contenido y sesión'))
        heading.setStyleSheet('font-size: 16px; font-weight: 700;')
        right.addWidget(heading)
        right.addWidget(QLabel(_('Mostrar')))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem(_('Sensores de CPU'), 'cpu_temp')
        self.combo_mode.addItem(_('Imagen / GIF de la biblioteca'), 'custom_image')
        self.combo_mode.setCurrentIndex(self.combo_mode.findData(self.lcd_cfg['mode']))
        right.addWidget(self.combo_mode)
        self.sensor_controls = QWidget()
        sensor_layout = QVBoxLayout(self.sensor_controls)
        sensor_layout.setContentsMargins(0,0,0,0)
        self.chk_temperature = QCheckBox(_('Mostrar temperatura de CPU'))
        self.chk_temperature.setChecked(self.lcd_cfg['show_temperature'])
        self.chk_usage = QCheckBox(_('Mostrar carga de CPU (%)'))
        self.chk_usage.setChecked(self.lcd_cfg['show_usage'])
        sensor_layout.addWidget(self.chk_temperature)
        sensor_layout.addWidget(self.chk_usage)
        sensor_layout.addWidget(QLabel(_('Color del contenido')))
        self.color_picker = ColorPicker(self.lcd_cfg['accent_color'])
        sensor_layout.addWidget(self.color_picker)
        right.addWidget(self.sensor_controls)
        self.chk_temperature.toggled.connect(self._sensor_options_changed)
        self.chk_usage.toggled.connect(self._sensor_options_changed)
        self.color_picker.color_changed.connect(self._color_changed)
        self.btn_select_img = QPushButton(_('Importar imagen / GIF…'))
        self.lbl_image_path = QLabel(self.lcd_cfg['custom_image_path'] or _('Ninguna imagen seleccionada'))
        self.lbl_image_path.setWordWrap(True)
        right.addWidget(self.btn_select_img)
        self.btn_media_folder = QPushButton(_('Abrir carpeta de imágenes y GIF'))
        self.btn_media_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(library_directory()))))
        right.addWidget(self.btn_media_folder)
        self.lbl_gif_note = QLabel(_('GIF en bucle mientras Algor está abierto · hasta 10 cuadros/s. Importar copia el archivo a tu biblioteca local.'))
        self.lbl_gif_note.setWordWrap(True)
        right.addWidget(self.lbl_gif_note)
        right.addWidget(self.lbl_image_path)
        right.addWidget(QLabel(_('Brillo al iniciar la sesión')))
        row = QHBoxLayout()
        self.slider_bright = QSlider(Qt.Orientation.Horizontal)
        self.slider_bright.setRange(0, 100)
        self.slider_bright.setValue(self.lcd_cfg['brightness'])
        self.lbl_bright_val = QLabel(f"{self.lcd_cfg['brightness']} %")
        row.addWidget(self.slider_bright)
        row.addWidget(self.lbl_bright_val)
        right.addLayout(row)
        self.slider_bright.valueChanged.connect(lambda v: self.lbl_bright_val.setText(f'{v} %'))
        self.slider_bright.sliderReleased.connect(self._brightness_released)
        # Cambios con teclado también se confirman al recibir el valor (sin arrastre).
        self.slider_bright.valueChanged.connect(self._brightness_keyboard)

        row = QHBoxLayout()
        self.lbl_rotation_val = QLabel(_('Giro adicional: {deg}°').format(deg=self.lcd_cfg['rotation']))
        self.btn_rotate = QPushButton(_('Girar contenido 90°'))
        row.addWidget(self.lbl_rotation_val)
        row.addWidget(self.btn_rotate)
        right.addLayout(row)
        explanation = QLabel(_('Ajusta el contenido al montaje de tu equipo. Se conserva la orientación física guardada en el LCD.'))
        explanation.setWordWrap(True)
        right.addWidget(explanation)
        self.chk_autostart = QCheckBox(_('Iniciar el LCD al abrir Algor'))
        self.chk_autostart.setChecked(bool(config.get('lcd_cap', {}).get('auto_start_session', False)))
        right.addWidget(self.chk_autostart)
        limitation = QLabel(_('Líquido y bomba: sensores sin verificar.\nImágenes y GIF: guardado disponible.\nBomba y ventiladores: controlados por BIOS.'))
        limitation.setWordWrap(True)
        limitation.setStyleSheet('color: #a5afc5; font-size: 12px;')
        right.addWidget(limitation)
        right.addStretch()
        self.btn_sync = QPushButton(_('Iniciar LCD'))
        self.btn_sync.setObjectName('PrimaryBtn')
        self.btn_sync.setCheckable(True)
        right.addWidget(self.btn_sync)
        right.addWidget(QLabel(_('Imagen al salir · memoria del dispositivo')))
        self.combo_memory = QComboBox()
        # Captured reference media is optional and not part of the public distribution.
        for label in 'ABC':
            try:
                load_captured_image(label)
            except (OSError, ValueError):
                continue
            self.combo_memory.addItem(_('{label} · Muestra local capturada').format(label=label), label)
        self.combo_memory.addItem(_('Archivo propio'), 'custom')
        right.addWidget(self.combo_memory)
        self.btn_prepare_memory = QPushButton(_('Preparar / optimizar imagen o GIF…'))
        self.btn_prepare_memory.clicked.connect(self._choose_memory_media)
        right.addWidget(self.btn_prepare_memory)
        self.lbl_custom_memory = QLabel(_('Archivo propio: preparación local, seguida de guardado manual. GIF: intervalo medio; '
            'las pausas individuales pueden cambiar. Optimización automática hasta 150 cuadros y 12 MiB preparados; '
            'conserva el archivo original.'))
        self.lbl_custom_memory.setWordWrap(True)
        right.addWidget(self.lbl_custom_memory)
        self.memory_preview = QLabel()
        self.memory_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.memory_preview)
        note = QLabel(_('Guarda la imagen de esta sección como respaldo al salir. A/B/C conservan su orientación capturada. '
            'Los archivos propios incorporan el giro seleccionado al prepararlos.'))
        note.setWordWrap(True)
        right.addWidget(note)
        self.btn_save_memory = QPushButton(_('Guardar A en el dispositivo'))
        right.addWidget(self.btn_save_memory)
        self.btn_query_memory = QPushButton(_('Consultar imagen guardada'))
        right.addWidget(self.btn_query_memory)
        self.btn_query_memory.clicked.connect(self._request_memory_query)
        self.lbl_memory_status = QLabel(_('Detén la sesión LCD antes de guardar. La imagen elegida reemplazará la anterior.'))
        self.lbl_memory_status.setWordWrap(True)
        self.lbl_memory_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.addWidget(self.lbl_memory_status)
        self.combo_memory.currentIndexChanged.connect(self._memory_selected)
        self.btn_save_memory.clicked.connect(self._request_memory)
        self._memory_selected()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(controls)
        layout.addWidget(scroll, 3)

        self.combo_mode.currentIndexChanged.connect(self._mode_changed)
        self.btn_select_img.clicked.connect(self._choose_image)
        self.btn_rotate.clicked.connect(self._rotate)
        self.btn_sync.toggled.connect(self.set_session_requested)
        self.chk_autostart.toggled.connect(lambda _unused: self._persist())
        self._update_image_controls()

    def _persist(self):
        saved = dict(config.get('lcd_cap', {}))
        saved.update(self.lcd_cfg)
        saved['auto_start_session'] = self.chk_autostart.isChecked()
        config.set('lcd_cap', saved)
        self.settings_changed.emit(dict(self.lcd_cfg))

    def _mode_changed(self, _index):
        self.lcd_cfg['mode'] = self.combo_mode.currentData()
        self._update_image_controls()
        self._persist()

    def _update_image_controls(self):
        image_mode = self.lcd_cfg['mode'] == 'custom_image'
        self.sensor_controls.setVisible(not image_mode)
        self.btn_select_img.setVisible(image_mode)
        self.btn_media_folder.setVisible(image_mode)
        self.lbl_gif_note.setVisible(image_mode)
        self.lbl_image_path.setVisible(image_mode)

    def _sensor_options_changed(self, *_args):
        self.lcd_cfg['show_temperature'] = self.chk_temperature.isChecked()
        self.lcd_cfg['show_usage'] = self.chk_usage.isChecked()
        self._persist()

    def _color_changed(self, color):
        self.lcd_cfg['accent_color'] = color
        self._persist()

    def _brightness_released(self):
        self.lcd_cfg['brightness'] = self.slider_bright.value()
        self._persist()

    def _brightness_keyboard(self, value):
        if not self.slider_bright.isSliderDown():
            self._brightness_released()

    def _rotate(self):
        self.lcd_cfg['rotation'] = (self.lcd_cfg['rotation'] + 90) % 360
        self.lbl_rotation_val.setText(_('Giro adicional: {deg}°').format(deg=self.lcd_cfg['rotation']))
        self._persist()

    def _media_dialog_directory(self):
        remembered = config.get('lcd_last_media_directory', '')
        if isinstance(remembered, str) and remembered:
            folder = Path(remembered).expanduser()
            if folder.is_dir():
                return str(folder)
        current = self.lcd_cfg.get('custom_image_path', '')
        if current:
            folder = Path(current).expanduser().parent
            if folder.is_dir():
                return str(folder)
        return str(library_directory())

    def _remember_media_directory(self, path):
        # Recordar el origen antes de copiar el archivo a la biblioteca local.
        config.set('lcd_last_media_directory', str(Path(path).expanduser().resolve().parent))

    def _choose_image(self):
        path, _filter = QFileDialog.getOpenFileName(self, _('Imagen o GIF para LCD'), self._media_dialog_directory(),
                                            _('Imágenes y GIF') + ' (*.png *.jpg *.jpeg *.bmp *.webp *.gif)')
        if path:
            self._remember_media_directory(path)
            self.btn_select_img.setEnabled(False)
            self.lbl_image_path.setText(_('Importando y optimizando si es necesario…'))
            self._import_worker = MediaImportWorker(path, self)
            self._import_worker.imported.connect(self._import_complete)
            self._import_worker.failed.connect(self._import_failed)
            self._import_worker.finished.connect(lambda: self.btn_select_img.setEnabled(True))
            self._import_worker.finished.connect(self._import_worker.deleteLater)
            self._import_worker.start()

    def _import_complete(self, path, summary=""):
        self.lcd_cfg['custom_image_path'] = path
        self.lbl_image_path.setText(path + ("\n" + summary if summary else ""))
        self._persist()

    def _import_failed(self, message):
        self.lbl_image_path.setText(_('No se pudo importar: {message}').format(message=message))

    def stop_import(self):
        for worker in self.findChildren(MediaImportWorker):
            worker.wait()

    def set_session_requested(self, enabled):
        self._requested = bool(enabled)
        self.btn_sync.blockSignals(True)
        self.btn_sync.setChecked(self._requested)
        self.btn_sync.setText(_('Detener LCD') if enabled else _('Iniciar LCD'))
        self.btn_sync.blockSignals(False)
        self.session_requested.emit(self._requested)
        self._update_memory_enabled()

    def set_status(self, state, message):
        self.lbl_usb_status.setText(message)
        color = {'active': '#00d9b0', 'error': '#ffaa55'}.get(state, '#a5afc5')
        self.lbl_usb_status.setStyleSheet(f'color: {color}; font-weight: 600;')


    def _memory_selected(self, *_args):
        label = self.combo_memory.currentData()
        self.btn_save_memory.setText(_('Guardar archivo propio') if label == 'custom'
                                      else _('Guardar {label} en el dispositivo').format(label=label))
        try:
            if label == 'custom':
                if self._custom_memory is None:
                    raise ValueError(_('Primero prepara un archivo propio.'))
                jpeg = self._custom_memory.frames[0]
            else:
                jpeg = load_captured_image(label).jpeg
            pixmap = QPixmap()
            pixmap.loadFromData(jpeg, 'JPEG')
            self.memory_preview.setPixmap(pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self._memory_asset_valid = True
        except Exception as exc:
            self.memory_preview.clear()
            self.lbl_memory_status.setText(_('Imagen no disponible: {error}').format(error=exc))
            self._memory_asset_valid = False
        self._update_memory_enabled()

    def _update_memory_enabled(self):
        self.btn_save_memory.setEnabled(self._memory_asset_valid and not self._requested and not self._memory_busy)
        self.btn_prepare_memory.setEnabled(not self._requested and not self._memory_busy)
        self.btn_query_memory.setEnabled(not self._requested and not self._memory_busy)
        self.combo_memory.setEnabled(not self._memory_busy)
        self.btn_sync.setEnabled(not self._memory_busy)

    def _request_memory_query(self):
        self.set_memory_status(True, _('Consultando memoria sin escritura…'))
        self.memory_query_requested.emit()

    def _request_memory(self):
        self.set_memory_status(True, _('Preparando guardado… Espera a que termine.'))
        label = self.combo_memory.currentData()
        self.memory_requested.emit(self._custom_memory if label == 'custom' else label)

    def set_memory_status(self, busy, message):
        self._memory_busy = busy
        self.lbl_memory_status.setText(message)
        self._update_memory_enabled()


    def _choose_memory_media(self):
        path, _filter = QFileDialog.getOpenFileName(self, _('Preparar imagen o GIF para memoria'), self._media_dialog_directory(),
            _('Imágenes y GIF') + ' (*.png *.jpg *.jpeg *.bmp *.webp *.gif)')
        if not path:
            return
        self._remember_media_directory(path)
        self._custom_memory = None
        self.combo_memory.setCurrentIndex(self.combo_memory.findData('custom'))
        self._memory_selected()
        self.set_memory_status(True, _('Preparando sin escribir en el LCD…'))
        self.memory_prepare_requested.emit(path, self.lcd_cfg['rotation'])

    def set_prepared_memory(self, asset):
        self._custom_memory = asset
        if asset is not None:
            parts = [_('{label} · {count} cuadro(s) · {kib:.0f} KiB JPEG · giro preparado {deg}°.').format(
                label=asset.label, count=len(asset.frames),
                kib=sum(map(len, asset.frames)) / 1024, deg=asset.rotation)]
            if len(asset.frames) > 1:
                parts.append(_('Intervalo por cuadro: {ms} ms · duración prevista {sec:.2f} s.').format(
                    ms=asset.interval_field, sec=asset.interval_field * len(asset.frames) / 1000))
            parts.append(_('Miniatura del primer cuadro. Confirma el ritmo en el LCD; las pausas individuales pueden cambiar.'))
            parts.append(asset.optimization_summary)
            self.lbl_custom_memory.setText(' '.join(parts))
        self._memory_selected()
