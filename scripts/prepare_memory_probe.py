#!/usr/bin/env python3
"""Genera medios de calibración de tiempos, sin acceso USB."""
from pathlib import Path
from PIL import Image, ImageDraw
import json


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    for label, color in [('A · 200 ms', '#126e75'), ('B · 800 ms', '#6c287c')]:
        image = Image.new('RGB', (480, 480), color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((40, 40, 440, 440), outline='white', width=8)
        draw.text((240, 230), label, fill='white', anchor='mm')
        frames.append(image)
    frames[0].save(folder/'probe_static.png')
    frames[0].save(folder/'probe_200_800.gif', save_all=True, append_images=frames[1:],
                   duration=[200, 800], loop=0, disposal=2, optimize=False)
    (folder/'probe.json').write_text(json.dumps(dict(dimensions=[480, 480], durations_ms=[200, 800],
        hypothesis='Compare the unknown memory envelope field with known GIF frame durations.',
        action='In iCUE Device Memory Mode import this GIF and save once while capturing USB.'), indent=2))
    return folder/'probe_200_800.gif'


if __name__ == '__main__':
    print(prepare(Path(__file__).resolve().parents[1]/'captures/memory_probe_media'))
