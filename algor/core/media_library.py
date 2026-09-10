"""Biblioteca local: originales importados, independientes de la memoria USB."""
import hashlib
from io import BytesIO
from pathlib import Path
from PIL import Image

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FRAMES = 150
MAX_DECODED_PIXELS = 50_000_000


def library_directory():
    folder = Path.home() / '.local/share/algor/media'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def validate_media(source):
    if source.width * source.height > 25_000_000:
        raise ValueError('La imagen supera 25 megapíxeles.')
    frames = getattr(source, 'n_frames', 1)
    if frames > MAX_FRAMES or frames * source.width * source.height > MAX_DECODED_PIXELS:
        raise ValueError('Animación demasiado grande: máximo 150 cuadros y 50 megapíxeles acumulados.')
    if frames > 1 and source.format != 'GIF':
        raise ValueError('Por ahora las animaciones deben ser GIF.')
    if source.format not in ('PNG', 'JPEG', 'BMP', 'WEBP', 'GIF'):
        raise ValueError('Formato de imagen no admitido.')


def import_media(path, details=None):
    details = details if details is not None else {}
    with Path(path).expanduser().open('rb') as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError('El archivo supera 25 MiB.')
    optimized = False
    with Image.open(BytesIO(data)) as source:
        try:
            validate_media(source)
        except ValueError:
            optimized = True
        suffix = {'JPEG': '.jpg', 'PNG': '.png', 'BMP': '.bmp', 'WEBP': '.webp', 'GIF': '.gif'}.get(source.format)
        if suffix is None:
            raise ValueError('Formato no admitido.')
        if not optimized:
            source.verify()
    if optimized:
        from algor.core.lcd_memory import prepare_custom_media
        asset = prepare_custom_media(path)
        details["summary"] = f'Copia optimizada: {len(asset.frames)} cuadros · {sum(asset.source_durations)/1000:.2f} s · 320×320. Original conservado.'
        frames = []
        for jpeg in asset.frames:
            with Image.open(BytesIO(jpeg)) as image:
                frames.append(image.convert('RGB').resize((320,320), Image.Resampling.LANCZOS).quantize(colors=128, dither=Image.Dither.NONE))
        output = BytesIO()
        if len(frames) > 1:
            # GIF usa centésimas. Redondear tiempos acumulados evita acortar el bucle.
            durations, elapsed, previous = [], 0, 0
            for duration in asset.source_durations:
                elapsed += duration
                rounded = round(elapsed / 10) * 10
                durations.append(max(10, rounded - previous)); previous = rounded
            frames[0].save(output, 'GIF', save_all=True, append_images=frames[1:], duration=durations, loop=0, disposal=2)
            suffix = '.gif'
        else:
            frames[0].convert('RGB').save(output, 'PNG'); suffix = '.png'
        data = output.getvalue()
        if len(data) > MAX_FILE_BYTES:
            raise ValueError('La copia optimizada aún supera 25 MiB.')
        with Image.open(BytesIO(data)) as source:
            validate_media(source)
    if not optimized:
        details["summary"] = "Archivo compatible: copia original sin conversión."
    name = hashlib.sha256(data).hexdigest() + suffix
    destination = library_directory() / name
    if not destination.exists():
        # Escritura atómica; nunca sustituir un original del usuario.
        import tempfile, os
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as tmp:
            temporary = Path(tmp.name)
            tmp.write(data)
        try:
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination
