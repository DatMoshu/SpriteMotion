"""Fit a sequence: choose annotation targets, run the solver per frame, write a pose solution.

Pose solutions (spritemotion.pose-solution) are the hand-off to Blender: per
frame, a local basis rotation (and root location) for each fitted bone.
tools/blender/export_action.py writes the same format for seed poses, and
tools/blender/apply_solution.py keys a solution into an action.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..fitting.camera import AffineOrthographicCamera, direction_rotations
from ..fitting.fit import FitSettings, PoseFitter, ViewTarget
from ..fitting.mapping import RigMapping
from ..fitting.rig import Rig, basis_matrix
from ..jsonio import read_json, write_json
from ..poses.annotations import effective_poses, is_approved, is_independent, load_layer
from ..poses.skeleton import Skeleton
from ..sprites.dataset import Dataset

TARGET_MODES = ("approved", "independent", "all")
VISIBILITY_WEIGHT = {"visible": 1.0, "unknown": 0.7, "occluded": 0.3, "outside": 0.0}


def read_solution(path: Path) -> dict[int, dict[str, np.ndarray]]:
    """Pose solution -> {frame: {bone: 4x4 basis}}."""
    data = read_json(path)
    if data.get("schema") != "spritemotion.pose-solution":
        raise ValueError(f"{path} is not a spritemotion.pose-solution.")
    out = {}
    for entry in data["frames"]:
        out[int(entry["frame"])] = {name: basis_matrix(np.asarray(b["rotation_quaternion"]),
                                                       np.asarray(b["location"]) if "location" in b else None)
                                    for name, b in entry["bones"].items()}
    return out


def dataset_camera(dataset: Dataset, override: dict | None = None) -> AffineOrthographicCamera:
    data = override if override is not None else dataset.data.get("camera")
    if data is None:
        raise ValueError("The dataset has no camera; pass one (--camera) to fit or project.")
    return AffineOrthographicCamera.from_dict(data, dataset.canvas.get("anchor"))


def select_targets(dataset: Dataset, sequence: str, joint_names: list[str], mode: str = "approved",
                   allow_dependent: bool = False) -> tuple[dict[int, list[ViewTarget]], dict]:
    """Group usable annotated poses by frame. Returns (targets, selection report).

    Poses on a mirrored-only view (dataset.mirror_source) are flipped into their
    stored partner view: the game draws that view as the mirror-image character,
    so it constrains the partner's 3D pose, not a second angle of the same one.
    When the partner has a usable pose too, the partner's own pose wins and the
    mirrored one is reported under `skipped_mirrored_view`.
    """
    if mode not in TARGET_MODES:
        raise ValueError(f"mode must be one of {TARGET_MODES}")
    merged = effective_poses(load_layer(dataset, "estimate", sequence), load_layer(dataset, "correction", sequence))
    targets: dict[int, list[ViewTarget]] = {}
    report = {"mode": mode, "used": [], "skipped_dependent": [], "skipped_unapproved": [], "skipped_mismatch": [],
              "skipped_mirrored_view": [], "mirrored_into_partner": []}
    axis = dataset.mirror_axis_x
    usable = []
    for (direction, frame), (layer, pose) in sorted(merged.items()):
        record = dataset.frame(sequence, direction, frame)
        if pose["source_fingerprint"] != record["fingerprint"]:
            report["skipped_mismatch"].append([direction, frame])
            continue
        if mode == "approved" and not is_approved(pose):
            report["skipped_unapproved"].append([direction, frame])
            continue
        if not (is_independent(pose) or is_approved(pose)):
            if mode == "independent" or not allow_dependent:
                report["skipped_dependent"].append([direction, frame])
                continue
        usable.append((direction, frame, pose))
    stored_views = {(d, f) for d, f, _ in usable if dataset.mirror_source(d) is None}
    for direction, frame, pose in usable:
        partner = dataset.mirror_source(direction)
        if partner is not None and (partner, frame) in stored_views:
            report["skipped_mirrored_view"].append([direction, frame])
            continue
        points = np.full((len(joint_names), 2), np.nan)
        weights = np.zeros(len(joint_names))
        for k, name in enumerate(joint_names):
            joint = pose["joints"].get(name)
            if joint is None:
                continue
            x = joint["x"] if partner is None else 2 * axis - joint["x"]
            points[k] = (x, joint["y"])
            confidence = 1.0 if is_approved(pose) else float(joint.get("confidence", 0.5))
            weights[k] = confidence * VISIBILITY_WEIGHT.get(joint.get("visibility", "unknown"), 0.7)
        targets.setdefault(frame, []).append(ViewTarget(direction if partner is None else partner, points, weights))
        report["used"].append([direction, frame])
        if partner is not None:
            report["mirrored_into_partner"].append([direction, frame, partner])
    return targets, report


def fit_sequence(dataset: Dataset, sequence: str, rig: Rig, mapping: RigMapping, out: Path, mode: str = "approved",
                 allow_dependent: bool = False, seeds: dict[int, dict] | None = None, frames: list[int] | None = None,
                 settings: FitSettings | None = None, model_forward=(0.0, -1.0), camera: dict | None = None) -> dict:
    """camera: an affine_orthographic camera overriding the dataset's (e.g. a candidate variant)."""
    skeleton = Skeleton.load(dataset.skeleton_path)
    names = skeleton.joint_names
    issues = mapping.check(rig, names)
    if issues:
        raise ValueError("Rig mapping does not match rig/skeleton: " + "; ".join(issues[:8]))
    projection = dataset_camera(dataset, camera)
    fitter = PoseFitter(rig, mapping, projection, names, direction_rotations(dataset.directions, model_forward), settings)
    targets, selection = select_targets(dataset, sequence, names, mode, allow_dependent)
    if frames is not None:
        targets = {f: t for f, t in targets.items() if f in frames}
    if not targets:
        raise ValueError(f"No usable targets for {sequence} in mode {mode!r}: {_why(selection)}")
    solution = {"schema": "spritemotion.pose-solution", "schema_version": 1, "dataset_id": dataset.dataset_id,
                "sequence": sequence, "rig": rig.name, "camera": projection.to_dict(), "target_selection": selection,
                "settings": vars(fitter.settings), "frames": []}
    previous = None
    for frame in sorted(targets):
        fit = fitter.fit_frame(frame, targets[frame], (seeds or {}).get(frame), previous)
        previous = fit.x
        solution["frames"].append({"frame": frame, "bones": fit.bones, "report": fit.report(names)})
    write_json(out, solution)
    return solution


def _why(selection: dict) -> str:
    return ", ".join(f"{len(v)} {k.replace('_', ' ')}" for k, v in selection.items() if isinstance(v, list) and v) \
        or "no annotations"
