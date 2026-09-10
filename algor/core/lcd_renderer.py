"""Renderizado de contenido compartido por previsualización y LCD físico."""
from io import BytesIO
import math
import time
from bisect import bisect_right
from algor.core.media_library import validate_media, MAX_FILE_BYTES
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps


def normalize_settings(settings):
    def bounded(value, default, low, high):
        try:
            return max(low, min(high, int(value)))
        except (TypeError, ValueError, OverflowError):
            return default
    mode = settings.get('mode')
    accent = settings.get('accent_color', '#00d9d0')
    if not isinstance(accent, str) or len(accent) != 7 or not accent.startswith('#'):
        accent = '#00d9d0'
    try:
        int(accent[1:], 16)
    except ValueError:
        accent = '#00d9d0'
    rotation = bounded(settings.get('rotation', 0), 0, 0, 270)
    return dict(mode=mode if mode in ('cpu_temp', 'custom_image') else 'cpu_temp',
                custom_image_path=str(settings.get('custom_image_path', '') or ''),
                brightness=bounded(settings.get('brightness', 80), 80, 0, 100),
                rotation=rotation if rotation in (0, 90, 180, 270) else 0,
                accent_color=accent,
                show_temperature=settings.get('show_temperature', True) is not False,
                show_usage=settings.get('show_usage', False) is True)


def cpu_reading(data, received_at, now):
    if data is None or received_at is None or now - received_at > 5:
        return None
    value = getattr(data, 'cpu_temp_package', None)
    if not getattr(data, 'cpu_temp_available', False) or value is None or not math.isfinite(value):
        return None
    return float(value)


def cpu_usage_reading(data, received_at, now):
    if data is None or received_at is None or now - received_at > 5:
        return None
    value = getattr(data, 'cpu_usage_total', None)
    if not getattr(data, 'cpu_usage_available', False) or value is None or not math.isfinite(value) or not 0 <= value <= 100:
        return None
    return float(value)


class LCDRenderer:
    def __init__(self):
        self._image_key = None
        self._image = None
        self._frames = []
        self._ends = []
        self._started = 0
        self._encoded = {}

    def render(self, settings, cpu_temp, now=None, cpu_usage=None):
        now = time.monotonic() if now is None else now
        settings = normalize_settings(settings)
        if settings['mode'] == 'custom_image':
            path = Path(settings['custom_image_path']).expanduser()
            if not settings['custom_image_path']:
                raise ValueError('Selecciona una imagen para mostrar en el LCD.')
            stat = path.stat()
            key = (str(path), stat.st_mtime_ns, stat.st_size)
            if stat.st_size > MAX_FILE_BYTES:
                raise ValueError('El archivo supera 25 MiB.')
            if key != self._image_key:
                frames, ends, elapsed = [], [], 0
                deadline = time.monotonic() + 10
                with Image.open(path) as source:
                    validate_media(source)
                    for index in range(getattr(source, 'n_frames', 1)):
                        if time.monotonic() > deadline:
                            raise ValueError('La preparación de la animación excedió 10 segundos.')
                        source.seek(index)
                        # Pillow compone los cuadros GIF y sus modos de disposición.
                        rgba = ImageOps.exif_transpose(source).convert('RGBA')
                        background = Image.new('RGBA', rgba.size, 'black')
                        background.alpha_composite(rgba)
                        frames.append(ImageOps.fit(background.convert('RGB'), (480, 480), method=Image.Resampling.LANCZOS))
                        duration = max(10, min(60000, int(source.info.get('duration', 100) or 100)))
                        elapsed += duration / 1000
                        ends.append(elapsed)
                self._frames, self._ends = frames, ends
                self._started = now
                self._encoded = {}
                self._image_key = key
            position = max(0, now - self._started) % self._ends[-1]
            frame = min(bisect_right(self._ends, position), len(self._frames) - 1)
            encoded_key = (frame, settings['rotation'])
            if encoded_key in self._encoded:
                return self._encoded[encoded_key]
            image = self._frames[frame].copy()
        else:
            image = Image.new('RGB', (480, 480), '#101827')
            draw = ImageDraw.Draw(image)
            color = settings['accent_color']
            font_path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
            def font(size):
                return ImageFont.truetype(str(font_path), size) if font_path.exists() else ImageFont.load_default()
            draw.ellipse((25, 25, 455, 455), outline=color, width=8)
            readings = []
            if settings['show_temperature']:
                readings.append(('TEMPERATURA CPU', f'{cpu_temp:.1f} °C' if cpu_temp is not None else 'N/D'))
            if settings['show_usage']:
                readings.append(('CARGA CPU', f'{cpu_usage:.0f} %' if cpu_usage is not None else 'N/D'))
            draw.text((240, 92), 'ALGOR', font=font(28), fill=color, anchor='mm')
            if len(readings) == 2:
                for (title, reading), y in zip(readings, (170, 295)):
                    draw.text((240, y), title, font=font(21), fill='#b9c2d4', anchor='mm')
                    draw.text((240, y+47), reading, font=font(52), fill=color, anchor='mm')
                draw.line((125,258,355,258), fill='#36445e', width=2)
            elif readings:
                title, reading = readings[0]
                draw.text((240, 178), title, font=font(24), fill='#b9c2d4', anchor='mm')
                draw.text((240, 255), reading, font=font(66), fill=color, anchor='mm')
            else:
                draw.text((240, 235), 'Sensores ocultos', font=font(27), fill=color, anchor='mm')
            draw.text((240, 385), 'Sensores Linux', font=font(18), fill='#b9c2d4', anchor='mm')
        # Giro adicional del contenido: conserva la orientación física previamente
        # guardada por iCUE. No presupone el mapa 0..3 del comando de hardware.
        image = image.rotate(-settings['rotation'])
        result = BytesIO()
        image.save(result, 'JPEG', quality=90, subsampling=0)
        jpeg = result.getvalue()
        if settings['mode'] == 'custom_image':
            if len(self._encoded) >= 120:
                self._encoded.clear()
            self._encoded[encoded_key] = jpeg
        return jpeg
