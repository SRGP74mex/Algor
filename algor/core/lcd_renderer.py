"""Renderizado de contenido compartido por previsualización y LCD físico."""
from io import BytesIO
import math
import time
from bisect import bisect_right
from functools import lru_cache
from algor.core.media_library import validate_media, MAX_FILE_BYTES
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

LCD_CANVAS_SIZE = 480

# Rango del texto de sensores en el LCD Cap físico (pantalla redonda de ~2.1"-2.3",
# nada que ver con la fuente de la interfaz de escritorio). El mínimo es el tamaño
# original, elegido a propósito por ser armónico en la pantalla; el máximo se midió
# con textbbox contra la cuerda disponible del círculo en cada fila (con margen) para
# que nunca se recorte contra el borde físico — ver tests/test_lcd_renderer.py.
# `text_scale` (0-100, ver normalize_settings) interpola entre ambos extremos.
LCD_TITLE_FONT_SIZE_DUAL_MIN = 21
LCD_TITLE_FONT_SIZE_DUAL_MAX = 27
LCD_VALUE_FONT_SIZE_DUAL_MIN = 52
LCD_VALUE_FONT_SIZE_DUAL_MAX = 70
LCD_TITLE_FONT_SIZE_SINGLE_MIN = 24
LCD_TITLE_FONT_SIZE_SINGLE_MAX = 32
LCD_VALUE_FONT_SIZE_SINGLE_MIN = 66
LCD_VALUE_FONT_SIZE_SINGLE_MAX = 84


def scaled_font_size(min_size: int, max_size: int, text_scale: int) -> int:
    """Interpola entre el tamaño mínimo (armónico, por defecto) y el máximo
    (el límite seguro sin recortarse contra el borde del LCD) según text_scale
    (0-100)."""
    return round(min_size + (max_size - min_size) * (text_scale / 100))


# La fuente va incluida con Algor: la ruta de DejaVu cambia entre distribuciones
# (Debian: truetype/dejavu, Arch: TTF, Fedora: dejavu-sans-fonts...) y, si no se
# encontraba, Pillow caía a su fuente bitmap de ~11 px que ignora el tamaño: el
# texto salía diminuto en el LCD y el control de tamaño no tenía efecto.
LCD_FONT_CANDIDATES = (
    Path(__file__).resolve().parent.parent / 'assets' / 'fonts' / 'DejaVuSans.ttf',
    Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
    Path('/usr/share/fonts/TTF/DejaVuSans.ttf'),
    Path('/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf'),
    Path('/usr/share/fonts/dejavu/DejaVuSans.ttf'),
    Path('/usr/share/fonts/truetype/DejaVuSans.ttf'),
)


@lru_cache(maxsize=1)
def lcd_font_path():
    return next((path for path in LCD_FONT_CANDIDATES if path.is_file()), None)


@lru_cache(maxsize=32)
def lcd_font(size: int):
    path = lcd_font_path()
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    # Pillow >= 10.1 escala la fuente por defecto si recibe el tamaño.
    return ImageFont.load_default(size)


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
                show_usage=settings.get('show_usage', False) is True,
                # 0 = tamaño original armónico (por defecto); 100 = máximo legible sin desbordar.
                text_scale=bounded(settings.get('text_scale', 0), 0, 0, 100))


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
            font = lcd_font
            draw.ellipse((25, 25, 455, 455), outline=color, width=8)
            readings = []
            if settings['show_temperature']:
                readings.append(('TEMPERATURA CPU', f'{cpu_temp:.1f} °C' if cpu_temp is not None else 'N/D'))
            if settings['show_usage']:
                readings.append(('CARGA CPU', f'{cpu_usage:.0f} %' if cpu_usage is not None else 'N/D'))
            text_scale = settings['text_scale']
            draw.text((240, 92), 'ALGOR', font=font(28), fill=color, anchor='mm')
            if len(readings) == 2:
                title_size = scaled_font_size(LCD_TITLE_FONT_SIZE_DUAL_MIN, LCD_TITLE_FONT_SIZE_DUAL_MAX, text_scale)
                value_size = scaled_font_size(LCD_VALUE_FONT_SIZE_DUAL_MIN, LCD_VALUE_FONT_SIZE_DUAL_MAX, text_scale)
                for (title, reading), y in zip(readings, (170, 295)):
                    draw.text((240, y), title, font=font(title_size), fill='#b9c2d4', anchor='mm')
                    draw.text((240, y+47), reading, font=font(value_size), fill=color, anchor='mm')
                draw.line((125,258,355,258), fill='#36445e', width=2)
            elif readings:
                title, reading = readings[0]
                title_size = scaled_font_size(LCD_TITLE_FONT_SIZE_SINGLE_MIN, LCD_TITLE_FONT_SIZE_SINGLE_MAX, text_scale)
                value_size = scaled_font_size(LCD_VALUE_FONT_SIZE_SINGLE_MIN, LCD_VALUE_FONT_SIZE_SINGLE_MAX, text_scale)
                draw.text((240, 178), title, font=font(title_size), fill='#b9c2d4', anchor='mm')
                draw.text((240, 255), reading, font=font(value_size), fill=color, anchor='mm')
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
