"""Projections from 3D world space to canvas pixels.

World convention: x east, y north, z up, one unit per game-specific world unit.
A sprite direction is modelled as the character turning (yaw about +z at the
ground origin) under a fixed camera, which is how most multi-direction sprite
sets were rendered or drawn.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class AffineOrthographicCamera:
    """canvas_xy = anchor + matrix @ world_xyz (x right, y down on the canvas)."""
    matrix: np.ndarray  # (2, 3)
    anchor: np.ndarray  # (2,)

    @classmethod
    def from_dict(cls, data: dict, anchor=None) -> "AffineOrthographicCamera":
        if data.get("type") != "affine_orthographic":
            raise ValueError(f"Unsupported camera type {data.get('type')!r}.")
        chosen = data.get("anchor", anchor)
        if chosen is None:
            raise ValueError("Camera needs an anchor (in the camera or the dataset canvas).")
        return cls(np.asarray(data["matrix"], dtype=float), np.asarray(chosen, dtype=float))

    def to_dict(self) -> dict:
        return {"type": "affine_orthographic", "matrix": self.matrix.tolist(), "anchor": self.anchor.tolist()}

    def project(self, points: np.ndarray) -> np.ndarray:
        points = np.asarray(points, dtype=float)
        return points @ self.matrix.T + self.anchor

    def view_direction(self) -> np.ndarray:
        """Unit world vector pointing from the scene toward the viewer (the projection's null space)."""
        null = np.cross(self.matrix[0], self.matrix[1])
        norm = np.linalg.norm(null)
        if norm == 0:
            raise ValueError("Degenerate camera matrix.")
        null = null / norm
        # Assumes the camera looks down onto the ground, so the viewer is on the +z side.
        return null if null[2] >= 0 else -null


def yaw_between(forward, facing) -> float:
    """Radians turning the model's rest forward vector (world xy) onto a view's facing vector."""
    return math.atan2(facing[1], facing[0]) - math.atan2(forward[1], forward[0])


def rotation_z(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def direction_rotations(directions: list[dict], model_forward=(0.0, -1.0)) -> dict[int, np.ndarray]:
    """World rotation for each direction that declares a facing vector."""
    return {d["id"]: rotation_z(yaw_between(model_forward, d["facing"])) for d in directions if "facing" in d}
