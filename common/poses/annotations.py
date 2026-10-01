"""Pose annotations: layers, merging, mirroring and frame-identity checks.

Two layers per sequence:
  estimate   - starting points (manual baselines, projections, estimator output)
  correction - only the poses a person edited, reviewed or annotated

The effective pose of a frame is its correction when present, otherwise its
estimate. Annotations are matched to frames by frame_id AND source_fingerprint,
never by filename, so art from a different client version is detected instead
of silently receiving joints drawn for other pixels.
"""
from __future__ import annotations

import copy
import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ..jsonio import read_json, write_json
from ..schemas import SchemaError, validate
from ..sprites.dataset import Dataset
from ..sprites.images import mirror_x
from .skeleton import Skeleton

Key = tuple[int, int]  # (direction, frame)
LAYERS = ("estimate", "correction")


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _integral(value):
    # Godot's JSON writer turns every number into a float (22 -> 22.0).
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def normalize_pose(pose: dict) -> dict:
    pose["direction"] = _integral(pose["direction"])
    pose["frame"] = _integral(pose["frame"])
    provenance = pose.get("provenance")
    if provenance and "mirrored_from" in provenance:
        provenance["mirrored_from"] = _integral(provenance["mirrored_from"])
    return pose


def review_status(pose: dict) -> str:
    return pose.get("review", {}).get("status", "unreviewed")


def is_approved(pose: dict) -> bool:
    return review_status(pose) == "approved"


def is_independent(pose: dict) -> bool:
    return bool(pose.get("provenance", {}).get("independent", False))


@dataclass
class AnnotationSet:
    data: dict
    path: Path | None = None
    _poses: dict = field(default_factory=dict, repr=False)

    @classmethod
    def new(cls, dataset_id: str, sequence: str, skeleton: str, layer: str, **extra) -> "AnnotationSet":
        if layer not in LAYERS:
            raise ValueError(f"Unknown layer {layer!r}.")
        data = {"schema": "spritemotion.pose-annotations", "schema_version": 1, "dataset_id": dataset_id,
                "sequence": sequence, "skeleton": skeleton, "layer": layer, "coordinate_space": "canvas-px"}
        data.update(extra)
        data["poses"] = []
        return cls(data)

    @classmethod
    def load(cls, path: str | Path) -> "AnnotationSet":
        data = read_json(path)
        for pose in data.get("poses", []):
            normalize_pose(pose)
        errors = validate(data, "spritemotion.pose-annotations")
        if errors:
            raise SchemaError(f"{path}: " + "; ".join(errors[:5]))
        result = cls(data, Path(path))
        result._reindex()
        return result

    def _reindex(self) -> None:
        self._poses = {}
        for pose in self.data["poses"]:
            key = (pose["direction"], pose["frame"])
            if key in self._poses:
                raise SchemaError(f"{self.path}: duplicate pose for direction {key[0]} frame {key[1]}.")
            self._poses[key] = pose

    def save(self, path: str | Path | None = None, backup: bool = False) -> Path:
        self.data["poses"].sort(key=lambda p: (p["direction"], p["frame"]))
        target = Path(path or self.path)
        write_json(target, self.data, backup=backup)
        self.path = target
        return target

    @property
    def layer(self) -> str:
        return self.data["layer"]

    @property
    def sequence(self) -> str:
        return self.data["sequence"]

    @property
    def poses(self) -> dict[Key, dict]:
        return self._poses

    def get(self, direction: int, frame: int) -> dict | None:
        return self._poses.get((direction, frame))

    def put(self, pose: dict) -> None:
        normalize_pose(pose)
        key = (pose["direction"], pose["frame"])
        if key in self._poses:
            self.data["poses"].remove(self._poses[key])
        self.data["poses"].append(pose)
        self._poses[key] = pose

    def remove(self, direction: int, frame: int) -> None:
        pose = self._poses.pop((direction, frame), None)
        if pose is not None:
            self.data["poses"].remove(pose)

    def __len__(self) -> int:
        return len(self._poses)


def load_layer(dataset: Dataset, layer: str, sequence: str) -> AnnotationSet | None:
    path = dataset.annotation_path(layer, sequence)
    return AnnotationSet.load(path) if path.exists() else None


def effective_poses(estimates: AnnotationSet | None, corrections: AnnotationSet | None) -> dict[Key, tuple[str, dict]]:
    """Merge layers: {(direction, frame): (layer, pose)}; corrections win."""
    result: dict[Key, tuple[str, dict]] = {}
    for layer, source in (("estimate", estimates), ("correction", corrections)):
        if source is not None:
            for key, pose in source.poses.items():
                result[key] = (layer, pose)
    return result


def check_pose(pose: dict, skeleton: Skeleton, width: int, height: int) -> list[str]:
    issues = []
    names = set(skeleton.joint_names)
    joints = pose.get("joints", {})
    missing = [n for n in skeleton.joint_names if n not in joints]
    unknown = [n for n in joints if n not in names]
    if missing:
        issues.append(f"missing joints {missing}")
    if unknown:
        issues.append(f"unknown joints {unknown}")
    for name, joint in joints.items():
        if not (0 <= joint["x"] <= width - 1 + 1e-6 and 0 <= joint["y"] <= height - 1 + 1e-6):
            issues.append(f"joint {name} at ({joint['x']}, {joint['y']}) is outside the canvas")
    return issues


@dataclass
class MatchReport:
    matched: list[Key] = field(default_factory=list)
    mismatched: list[Key] = field(default_factory=list)   # frame exists, pixels differ
    unknown_frame: list[Key] = field(default_factory=list)  # no such frame in the dataset
    invalid: list[tuple[Key, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.mismatched or self.unknown_frame or self.invalid)

    def summary(self) -> str:
        return (f"{len(self.matched)} matched, {len(self.mismatched)} fingerprint mismatches, "
                f"{len(self.unknown_frame)} unknown frames, {len(self.invalid)} invalid")


def match_to_dataset(annotations: AnnotationSet, dataset: Dataset, skeleton: Skeleton | None = None) -> MatchReport:
    report = MatchReport()
    for key, pose in sorted(annotations.poses.items()):
        try:
            record = dataset.frame(annotations.sequence, *key)
        except KeyError:
            report.unknown_frame.append(key)
            continue
        if pose["frame_id"] != record["frame_id"]:
            report.invalid.append((key, f"frame_id {pose['frame_id']!r} != dataset {record['frame_id']!r}"))
            continue
        if pose["source_fingerprint"] != record["fingerprint"]:
            report.mismatched.append(key)
            continue
        if skeleton is not None:
            issues = check_pose(pose, skeleton, dataset.width, dataset.height)
            if issues:
                report.invalid.append((key, "; ".join(issues)))
                continue
        report.matched.append(key)
    return report


def mirror_pose(pose: dict, axis_x: float, direction: int, frame_id: str, fingerprint: str,
                swap: dict[str, str] | None = None) -> dict:
    """Mirror a pose into its partner view.

    Joint names are preserved by default (a chain keeps its identity across the
    mirror); pass the skeleton's swap_map() to exchange anatomical sides instead.
    """
    swap = swap or {}
    source = pose.get("provenance", {})
    result = {
        "frame_id": frame_id,
        "direction": direction,
        "frame": pose["frame"],
        "source_fingerprint": fingerprint,
        "provenance": {
            "method": "mirrored",
            "independent": bool(source.get("independent", False)),
            "source_method": source.get("method", "unknown"),
            "mirrored_from": pose["direction"],
        },
        "review": {"status": "unreviewed"},
        "joints": {},
    }
    for name, joint in pose["joints"].items():
        mirrored = copy.deepcopy(joint)
        mirrored["x"] = round(mirror_x(joint["x"], axis_x), 4)
        result["joints"][swap.get(name, name)] = mirrored
    return result


def _joints_differ(a: dict, b: dict, tolerance: float = 1e-4) -> bool:
    if set(a) != set(b):
        return True
    return any(abs(a[n]["x"] - b[n]["x"]) > tolerance or abs(a[n]["y"] - b[n]["y"]) > tolerance for n in a)


def is_meaningful_correction(pose: dict, baseline: dict | None) -> bool:
    """A correction is worth keeping if it moved joints, carries a review decision, or has notes."""
    review = pose.get("review", {})
    if review.get("status", "unreviewed") != "unreviewed" or review.get("notes", "").strip():
        return True
    return baseline is None or _joints_differ(pose["joints"], baseline["joints"])


def corrections_from_poses(edited: Iterable[dict], baseline: AnnotationSet | None, template: AnnotationSet) -> AnnotationSet:
    """Build a correction layer holding only meaningful corrections."""
    result = AnnotationSet.new(template.data["dataset_id"], template.sequence, template.data["skeleton"], "correction")
    for key in ("limb_identity", "notes"):
        if key in template.data:
            result.data[key] = template.data[key]
    for pose in edited:
        base = baseline.get(pose["direction"], pose["frame"]) if baseline else None
        if is_meaningful_correction(pose, base):
            result.put(copy.deepcopy(pose))
    return result
