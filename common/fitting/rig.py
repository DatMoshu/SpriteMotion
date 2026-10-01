"""A minimal armature model with Blender-compatible forward kinematics.

A rig file (spritemotion.rig) is exported from Blender by
tools/blender/export_rig.py. Bone matrices follow Blender's conventions:
matrix_local is the bone's rest matrix in armature space with the bone lying
along its local +y axis, and a pose bone's basis is applied in that local
space: pose[b] = pose[parent] @ inv(rest[parent]) @ rest[b] @ basis[b].
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..jsonio import read_json, write_json


# ---- quaternions (w, x, y, z), matching Blender's rotation_quaternion ----
def quat_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_from_rotvec(v: np.ndarray) -> np.ndarray:
    angle = float(np.linalg.norm(v))
    if angle < 1e-12:
        return np.array([1.0, *(0.5 * np.asarray(v, dtype=float))])
    axis = np.asarray(v, dtype=float) / angle
    return np.array([np.cos(angle / 2), *(axis * np.sin(angle / 2))])


def quat_to_rotvec(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=float)
    q = q / np.linalg.norm(q)
    if q[0] < 0:
        q = -q
    s = np.linalg.norm(q[1:])
    if s < 1e-12:
        return 2.0 * q[1:]
    return q[1:] / s * 2.0 * np.arctan2(s, q[0])


def quat_to_matrix(q: np.ndarray) -> np.ndarray:
    w, x, y, z = np.asarray(q, dtype=float) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


@dataclass
class Bone:
    name: str
    parent: int
    rest: np.ndarray  # 4x4 armature-space rest matrix
    length: float


@dataclass
class Rig:
    bones: list[Bone]
    world: np.ndarray = field(default_factory=lambda: np.eye(4))
    name: str = "rig"
    index: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self.index = {b.name: i for i, b in enumerate(self.bones)}
        for i, bone in enumerate(self.bones):
            if bone.parent >= i:
                raise ValueError(f"Bone {bone.name} appears before its parent; bones must be topologically ordered.")
        self._rest_inv = [np.linalg.inv(b.rest) for b in self.bones]

    # ---- file format ----
    @classmethod
    def from_dict(cls, data: dict) -> "Rig":
        if data.get("schema") != "spritemotion.rig":
            raise ValueError("Not a spritemotion.rig document.")
        names = [b["name"] for b in data["bones"]]
        bones = [Bone(b["name"], names.index(b["parent"]) if b.get("parent") else -1,
                      np.asarray(b["matrix_local"], dtype=float), float(b["length"])) for b in data["bones"]]
        return cls(bones, np.asarray(data.get("matrix_world", np.eye(4)), dtype=float), data.get("name", "rig"))

    @classmethod
    def load(cls, path) -> "Rig":
        return cls.from_dict(read_json(path))

    def to_dict(self) -> dict:
        return {"schema": "spritemotion.rig", "schema_version": 1, "name": self.name,
                "matrix_world": self.world.tolist(),
                "bones": [{"name": b.name, "parent": self.bones[b.parent].name if b.parent >= 0 else None,
                           "matrix_local": b.rest.tolist(), "length": b.length} for b in self.bones]}

    def save(self, path):
        return write_json(path, self.to_dict())

    # ---- kinematics ----
    def chain_to_root(self, names) -> list[int]:
        """Indices of the named bones and all their ancestors, in topological order."""
        needed = set()
        for name in names:
            i = self.index[name]
            while i >= 0 and i not in needed:
                needed.add(i)
                i = self.bones[i].parent
        return sorted(needed)

    def pose_matrices(self, basis: dict[str, np.ndarray], subset: list[int] | None = None) -> dict[int, np.ndarray]:
        """Armature-space pose matrices. basis maps bone name -> 4x4 local basis (identity when absent)."""
        result: dict[int, np.ndarray] = {}
        for i in (subset if subset is not None else range(len(self.bones))):
            bone = self.bones[i]
            local = basis.get(bone.name)
            matrix = bone.rest if local is None else bone.rest @ local
            if bone.parent >= 0:
                matrix = result[bone.parent] @ self._rest_inv[bone.parent] @ matrix
            result[i] = matrix
        return result

    def bone_point(self, matrices: dict[int, np.ndarray], name: str, at: float) -> np.ndarray:
        """World position a fraction `at` along a posed bone (0 = head, 1 = tail)."""
        i = self.index[name]
        local = np.array([0.0, at * self.bones[i].length, 0.0, 1.0])
        return (self.world @ matrices[i] @ local)[:3]


def basis_matrix(rotation: np.ndarray | None = None, location: np.ndarray | None = None) -> np.ndarray:
    m = np.eye(4)
    if rotation is not None:
        m[:3, :3] = quat_to_matrix(rotation)
    if location is not None:
        m[:3, 3] = location
    return m
