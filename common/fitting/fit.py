"""Fit armature poses to 2D joint annotations.

One animation frame is one 3D pose. Each sprite direction shows that pose
turned to a different facing under the same camera, so annotations of the
same frame in several directions jointly constrain depth; a single view
cannot. Unknowns per frame: a rotation (rotation vector, relative to a seed
pose) for each fitted bone plus a world-space root offset.

Residuals:
  reprojection  weight * confidence * (projected joint - annotated joint), px
  prior         prior_weight * rotation away from the seed (radians)
  temporal      temporal_weight * change from the previous frame's solution
  floor         floor_weight * depth below ground of selected joints
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .camera import AffineOrthographicCamera
from .mapping import RigMapping
from .rig import Rig, basis_matrix, quat_from_rotvec, quat_multiply, quat_to_rotvec
from .solver import least_squares


@dataclass
class ViewTarget:
    direction: int
    points: np.ndarray    # (J, 2) canvas px; NaN where a joint is not used
    weights: np.ndarray   # (J,)


@dataclass
class FitSettings:
    prior_weight: float = 4.0
    temporal_weight: float = 2.0
    root_weight: float = 0.5
    floor_weight: float = 50.0
    floor_joints: list[str] = field(default_factory=list)
    root_limit: float = 1.0          # world units
    max_iterations: int = 60


@dataclass
class FrameFit:
    frame: int
    x: np.ndarray
    bones: dict                        # name -> {"rotation_quaternion": [...], "location"?: [...]}
    errors: dict[int, list[float]]     # direction -> per-joint px error
    cost: float
    initial_cost: float
    iterations: int

    def report(self, joint_names: list[str]) -> dict:
        per_view = {}
        for direction, err in self.errors.items():
            finite = [e for e in err if np.isfinite(e)]
            per_view[str(direction)] = {"mean_px": float(np.mean(finite)) if finite else None,
                                        "max_px": float(np.max(finite)) if finite else None,
                                        "joints": {n: (round(e, 3) if np.isfinite(e) else None)
                                                   for n, e in zip(joint_names, err)}}
        return {"frame": self.frame, "cost": self.cost, "initial_cost": self.initial_cost,
                "iterations": self.iterations, "views": per_view}


class PoseFitter:
    def __init__(self, rig: Rig, mapping: RigMapping, camera: AffineOrthographicCamera, joint_names: list[str],
                 rotations: dict[int, np.ndarray], settings: FitSettings | None = None):
        self.rig, self.mapping, self.camera = rig, mapping, camera
        self.joint_names = list(joint_names)
        self.rotations = rotations
        self.settings = settings or FitSettings()
        self.fit_bones = [b for b in mapping.fit_bones]
        self.root_bone = mapping.root_bone
        self.subset = rig.chain_to_root(mapping.referenced_bones() + self.fit_bones +
                                        ([self.root_bone] if self.root_bone else []))
        self.limits = np.array([mapping.rotation_limit(b) for b in self.fit_bones for _ in range(3)] +
                               ([self.settings.root_limit] * 3 if self.root_bone else []))
        self.size = self.limits.size
        self._floor = [self.joint_names.index(j) for j in self.settings.floor_joints if j in self.joint_names]
        if self.root_bone:
            root = rig.bones[rig.index[self.root_bone]]
            # World offset -> root bone local translation, assuming the root's ancestors stay at rest.
            self._root_to_local = np.linalg.inv(rig.world[:3, :3] @ root.rest[:3, :3])

    # ---- parameterization ----
    def basis(self, x: np.ndarray, seed: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """4x4 local basis per bone for parameters x relative to seed (name -> 4x4)."""
        result = dict(seed)
        for k, name in enumerate(self.fit_bones):
            base = seed.get(name, np.eye(4))
            q_seed = _matrix_to_quat(base[:3, :3])
            q = quat_multiply(q_seed, quat_from_rotvec(x[3 * k:3 * k + 3]))
            result[name] = basis_matrix(q, base[:3, 3])
        if self.root_bone:
            base = result.get(self.root_bone, np.eye(4)).copy()
            base[:3, 3] = base[:3, 3] + self._root_to_local @ x[-3:]
            result[self.root_bone] = base
        return result

    def joints_world(self, basis: dict[str, np.ndarray]) -> np.ndarray:
        matrices = self.rig.pose_matrices(basis, self.subset)
        return self.mapping.joint_positions(self.rig, matrices, self.joint_names)

    def project(self, joints: np.ndarray, direction: int) -> np.ndarray:
        return self.camera.project(joints @ self.rotations[direction].T)

    # ---- solving ----
    def _residual(self, x, seed, targets, previous):
        s = self.settings
        joints = self.joints_world(self.basis(x, seed))
        parts = []
        for target in targets:
            diff = (self.project(joints, target.direction) - target.points) * target.weights[:, None]
            parts.append(np.nan_to_num(diff, nan=0.0).ravel())
        rot = x[:3 * len(self.fit_bones)]
        parts.append(s.prior_weight * rot)
        if self.root_bone:
            parts.append(s.root_weight * x[-3:])
        if previous is not None:
            parts.append(s.temporal_weight * (x - previous))
        if self._floor:
            parts.append(s.floor_weight * np.minimum(joints[self._floor, 2], 0.0))
        return np.concatenate(parts)

    def fit_frame(self, frame: int, targets: list[ViewTarget], seed: dict[str, np.ndarray] | None = None,
                  previous: np.ndarray | None = None, start: np.ndarray | None = None) -> FrameFit:
        """previous: the previous frame's parameters (temporal term); start: where the solver starts
        (default: previous, else the seed pose). Distinct starts let a caller try several and keep the best."""
        seed = seed or {}
        missing = [t.direction for t in targets if t.direction not in self.rotations]
        if missing:
            raise ValueError(f"No facing for directions {missing}; add 'facing' to the dataset directions.")
        if start is None:
            start = previous.copy() if previous is not None else np.zeros(self.size)
        result = least_squares(lambda x: self._residual(x, seed, targets, previous), start,
                               -self.limits, self.limits, max_iterations=self.settings.max_iterations)
        basis = self.basis(result.x, seed)
        joints = self.joints_world(basis)
        errors = {t.direction: np.linalg.norm(self.project(joints, t.direction) - t.points, axis=1).tolist()
                  for t in targets}
        bones = {}
        for name in self.fit_bones + ([self.root_bone] if self.root_bone else []):
            entry = {"rotation_quaternion": _matrix_to_quat(basis[name][:3, :3]).round(6).tolist()}
            if name == self.root_bone:
                entry["location"] = basis[name][:3, 3].round(6).tolist()
            bones[name] = entry
        return FrameFit(frame, result.x, bones, errors, result.cost, result.initial_cost, result.iterations)


def _matrix_to_quat(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=float)
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0:
        s = np.sqrt(trace + 1.0) * 2
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = np.array(q)
    q /= np.linalg.norm(q)
    return q if q[0] >= 0 else -q


matrix_to_quat = _matrix_to_quat
__all__ = ["FitSettings", "FrameFit", "PoseFitter", "ViewTarget", "matrix_to_quat", "quat_to_rotvec"]
