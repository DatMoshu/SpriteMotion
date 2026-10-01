"""Canvas images: placement, mirroring, bounds and fingerprints.

Canvas coordinates: origin at the top-left corner, x right, y down, one unit
per source pixel. Pixel column i is addressed by x = i. Mirroring about
axis_x maps x to 2*axis_x - x for joints and pixel column i to 2*axis_x - i,
so with axis_x = (width - 1) / 2 a mirrored image stays pixel-aligned.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np


def blank_canvas(width: int, height: int) -> np.ndarray:
    return np.zeros((height, width, 4), dtype=np.uint8)


def place(canvas: np.ndarray, image: np.ndarray, offset: tuple[int, int]) -> np.ndarray:
    """Copy an RGBA image onto the canvas with its top-left at offset. Raises if it does not fit."""
    x, y = int(offset[0]), int(offset[1])
    h, w = image.shape[:2]
    if x < 0 or y < 0 or x + w > canvas.shape[1] or y + h > canvas.shape[0]:
        raise ValueError(f"Image {w}x{h} at {x},{y} does not fit a {canvas.shape[1]}x{canvas.shape[0]} canvas.")
    region = canvas[y:y + h, x:x + w]
    opaque = image[:, :, 3] > 0
    region[opaque] = image[opaque]
    return canvas


def mirror_canvas(canvas: np.ndarray, axis_x: float) -> np.ndarray:
    """Mirror a canvas image about axis_x (pixel column i -> 2*axis_x - i)."""
    width = canvas.shape[1]
    shift = int(round(2 * axis_x - (width - 1)))
    flipped = canvas[:, ::-1]
    if shift == 0:
        return flipped.copy()
    result = np.zeros_like(canvas)
    if shift > 0:
        result[:, shift:] = flipped[:, :width - shift]
    else:
        result[:, :width + shift] = flipped[:, -shift:]
    return result


def mirror_x(x: float, axis_x: float) -> float:
    return 2.0 * axis_x - x


def opaque_bounds(image: np.ndarray, threshold: int = 0) -> list[int] | None:
    """[x0, y0, x1, y1) of pixels with alpha > threshold, or None for an empty image."""
    mask = image[:, :, 3] > threshold
    if not mask.any():
        return None
    ys = np.flatnonzero(mask.any(axis=1))
    xs = np.flatnonzero(mask.any(axis=0))
    return [int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1]


def fingerprint(image: np.ndarray) -> str:
    """Content fingerprint of an RGBA canvas, independent of PNG encoding.

    Fully transparent pixels are normalized so their hidden color does not matter.
    """
    rgba = np.ascontiguousarray(image, dtype=np.uint8).copy()
    rgba[rgba[:, :, 3] == 0] = 0
    digest = hashlib.sha256()
    digest.update(f"rgba8:{rgba.shape[1]}x{rgba.shape[0]}:".encode())
    digest.update(rgba.tobytes())
    return "sha256:" + digest.hexdigest()


def load_rgba(path: str | Path) -> np.ndarray:
    from PIL import Image  # imported lazily so Blender's Python can use the rest of this module
    with Image.open(path) as image:
        return np.array(image.convert("RGBA"))


def save_png(path: str | Path, image: np.ndarray) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    Image.fromarray(image, "RGBA").save(path, optimize=False, compress_level=6)
    return path


def alpha_mask(image: np.ndarray, threshold: int = 0) -> np.ndarray:
    return image[:, :, 3] > threshold
