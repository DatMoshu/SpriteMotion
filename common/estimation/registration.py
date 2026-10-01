"""Register projected points to a sprite's bounds.

Projected rig joints and a sprite rarely share exact placement or scale. This
moves points so that a model bounding box lands on the sprite's bounding box,
with the scale clamped so a bad silhouette cannot distort the pose wildly.
It does not snap joints to edges: occluded joints stay where the rig put them.
"""
from __future__ import annotations

import numpy as np


def register_to_bounds(points: np.ndarray, model_bounds, sprite_bounds, clamp=(0.75, 1.25),
                       canvas: tuple[int, int] | None = None) -> tuple[np.ndarray, list[float]]:
    """Map points from model_bounds [x0,y0,x1,y1] to sprite_bounds. Returns (points, [sx, sy])."""
    mb = np.asarray(model_bounds, dtype=float)
    sb = np.asarray(sprite_bounds, dtype=float)
    model_size = np.maximum(mb[2:] - mb[:2], 1e-6)
    scale = np.clip((sb[2:] - sb[:2]) / model_size, clamp[0], clamp[1])
    out = (np.asarray(points, dtype=float) - (mb[:2] + mb[2:]) / 2) * scale + (sb[:2] + sb[2:]) / 2
    if canvas is not None:
        out = np.clip(out, 0, np.asarray(canvas, dtype=float) - 1)
    return out, scale.tolist()
