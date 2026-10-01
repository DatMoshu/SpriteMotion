"""Express an affine orthographic sprite camera as a Blender orthographic camera.

A Blender orthographic camera projects with orthonormal screen axes. The sprite
camera (canvas = anchor + M @ world) is representable when M's two rows are
orthogonal: row 0 gives the camera's right axis, -row 1 its up axis, and the
different row lengths become a non-square pixel aspect. Canvas coordinate x
addresses the centre of pixel column x (see sprites/images.py), so the canvas
centre is ((width - 1) / 2, (height - 1) / 2).

This module is plain numpy; tools/blender applies the result to a camera.
"""
from __future__ import annotations

import numpy as np

from ..fitting.camera import AffineOrthographicCamera

ORTHOGONALITY_TOLERANCE = 1e-6


def blender_camera_params(camera: AffineOrthographicCamera, width: int, height: int,
                          distance: float = 100.0) -> dict:
    """Location, rotation and lens settings reproducing the camera on a width x height render."""
    r0, r1 = np.asarray(camera.matrix[0], dtype=float), np.asarray(camera.matrix[1], dtype=float)
    s0, s1 = np.linalg.norm(r0), np.linalg.norm(r1)
    if s0 == 0 or s1 == 0:
        raise ValueError("Degenerate camera matrix.")
    if abs(np.dot(r0, r1)) > ORTHOGONALITY_TOLERANCE * s0 * s1:
        raise ValueError("The camera's rows are not orthogonal; a Blender orthographic camera cannot reproduce it.")
    right, up = r0 / s0, -r1 / s1
    back = np.cross(right, up)  # Blender cameras look down their local -z
    if back[2] < 0:
        raise ValueError("The camera views the ground from below or is mirrored; not representable.")
    dx = (width - 1) / 2.0 - camera.anchor[0]
    dy = (height - 1) / 2.0 - camera.anchor[1]
    centre = dx / s0 ** 2 * r0 + dy / s1 ** 2 * r1
    smallest = min(s0, s1)
    return {
        "location": (centre + back * distance).tolist(),
        "rotation": np.column_stack([right, up, back]).tolist(),  # columns = camera x, y, z axes
        "ortho_scale": width / s0,
        "sensor_fit": "HORIZONTAL",
        "pixel_aspect_x": s1 / smallest,
        "pixel_aspect_y": s0 / smallest,
        "resolution": [int(width), int(height)],
        "clip_start": 0.01,
        "clip_end": distance * 2.0,
    }
