"""Estimates projected from a posed 3D rig.

These are useful starting points for a person to correct, but they are NOT
independent observations of the sprite: fitting the same rig back to them
only proves the rig agrees with itself. They are therefore written with
provenance {method: rig_projection, independent: false}, and the fitting
tools refuse them as targets unless explicitly allowed.
"""
from __future__ import annotations

import numpy as np

from ..fitting.camera import AffineOrthographicCamera
from ..fitting.mapping import RigMapping
from ..fitting.rig import Rig
from ..poses.annotations import AnnotationSet
from ..sprites.dataset import Dataset
from .registration import register_to_bounds


def project_rig_joints(rig: Rig, mapping: RigMapping, camera: AffineOrthographicCamera, rotation: np.ndarray,
                       basis: dict[str, np.ndarray], joint_names: list[str]) -> np.ndarray:
    matrices = rig.pose_matrices(basis)
    joints = mapping.joint_positions(rig, matrices, joint_names)
    return camera.project(joints @ rotation.T)


def rig_projection_pose(points: np.ndarray, joint_names: list[str], record: dict, confidence: float = 0.35,
                        detail: str = "", parameters: dict | None = None) -> dict:
    provenance = {"method": "rig_projection", "independent": False, "detail": detail}
    if parameters:
        provenance["parameters"] = parameters
    return {
        "frame_id": record["frame_id"],
        "direction": record["direction"],
        "frame": record["frame"],
        "source_fingerprint": record["fingerprint"],
        "provenance": provenance,
        "review": {"status": "unreviewed"},
        "joints": {name: {"x": round(float(p[0]), 3), "y": round(float(p[1]), 3), "confidence": confidence,
                          "visibility": "unknown", "status": "estimate"}
                   for name, p in zip(joint_names, points)},
    }


def add_rig_projection(existing: AnnotationSet, dataset: Dataset, sequence: str, direction: int, frame: int,
                       points: np.ndarray, joint_names: list[str], model_bounds=None, detail: str = "",
                       clamp=(0.75, 1.25)) -> dict | None:
    """Add one projected pose unless the frame already has one. Optionally register to sprite bounds."""
    if existing.get(direction, frame):
        return None
    record = dataset.frame(sequence, direction, frame)
    parameters = {}
    if model_bounds is not None and record.get("bounds"):
        points, scale = register_to_bounds(points, model_bounds, record["bounds"], clamp,
                                           (dataset.width, dataset.height))
        parameters["registration_scale"] = scale
    pose = rig_projection_pose(points, joint_names, record, detail=detail, parameters=parameters)
    existing.put(pose)
    return pose
