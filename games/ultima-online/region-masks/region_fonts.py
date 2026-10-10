"""Font loading that works without Arial (Linux, macOS, stripped Windows)."""
import os
from pathlib import Path
from PIL import ImageFont

def candidates():
    windir = os.environ.get('WINDIR') or os.environ.get('SystemRoot')
    return ([Path(windir, 'Fonts', 'arial.ttf')] if windir else []) + [Path('/Library/Fonts/Arial.ttf'),
            Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), Path('/usr/share/fonts/TTF/DejaVuSans.ttf')]

def load_font(size, paths=None):
    """Return a TrueType font of `size`, or PIL's built-in default when none is installed."""
    for path in (candidates() if paths is None else paths):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow < 10.1 has no sized default
        return ImageFont.load_default()
