"""Rig mappings: where each 2D skeleton joint sits on a 3D armature.

A mapping file (spritemotion.rig-mapping) names, for every annotation joint,
a point on one bone or a weighted mix of points:

    "neck":  {"bone": "head", "at": 0}
    "head":  {"bone": "head", "at": 0.5}
    "chest": {"mix": [{"bone": "neck", "at": 0, "w": 0.6}, {"bone": "hips", "at": 0, "w": 0.4}]}

`at` is the fraction along the bone (0 head, 1 tail). Keys and bone names may
contain {chain} and {side}; they are expanded for every entry of "sides", so a
limb chain's identity (e.g. chain A -> rig side L) is stated in one place and
can be swapped per annotation set.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..jsonio import read_json
from .rig import Rig


def _expand(joints: dict, sides: dict[str, str]) -> dict:
    result = {}
    for key, spec in joints.items():
        if "{chain}" not in key:
            result[key] = spec
            continue
        for chain, side in sides.items():
            def sub(text: str) -> str:
                return text.replace("{chain}", chain).replace("{side}", side)
            if "mix" in spec:
                result[sub(key)] = {"mix": [dict(p, bone=sub(p["bone"])) for p in spec["mix"]]}
            else:
                result[sub(key)] = dict(spec, bone=sub(spec["bone"]))
    return result


@dataclass
class RigMapping:
    data: dict
    sides: dict[str, str]
    joints: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict, swap_sides: bool = False) -> "RigMapping":
        if data.get("schema") != "spritemotion.rig-mapping":
            raise ValueError("Not a spritemotion.rig-mapping document.")
        sides = dict(data.get("sides", {}))
        if swap_sides:
            if len(sides) != 2:
                raise ValueError("swap_sides needs exactly two chains in 'sides'.")
            (a, sa), (b, sb) = sides.items()
            sides = {a: sb, b: sa}
        return cls(data, sides, _expand(data["joints"], sides))

    @classmethod
    def load(cls, path, swap_sides: bool = False) -> "RigMapping":
        return cls.from_dict(read_json(path), swap_sides)

    def expand_bones(self, names: list[str]) -> list[str]:
        out = []
        for name in names:
            if "{side}" in name:
                out += [name.replace("{side}", side) for side in dict.fromkeys(self.sides.values())]
            else:
                out.append(name)
        return out

    @property
    def fit_bones(self) -> list[str]:
        return self.expand_bones(self.data.get("fit", {}).get("bones", []))

    @property
    def root_bone(self) -> str | None:
        return self.data.get("fit", {}).get("root_bone")

    def rotation_limit(self, bone: str) -> float:
        """Maximum rotation away from the seed pose, radians. Keys of limits_deg are bone names ({side} allowed)."""
        limits = self.data.get("fit", {}).get("limits_deg", {})
        expanded = {}
        for key, value in limits.items():
            for name in self.expand_bones([key]):
                expanded[name] = value
        return float(np.radians(expanded.get(bone, limits.get("default", 120.0))))

    def referenced_bones(self) -> list[str]:
        names = set()
        for spec in self.joints.values():
            for part in spec.get("mix", [spec]):
                names.add(part["bone"])
        return sorted(names)

    def check(self, rig: Rig, joint_names: list[str]) -> list[str]:
        issues = [f"joint {j!r} has no mapping" for j in joint_names if j not in self.joints]
        issues += [f"bone {b!r} not in rig" for b in self.referenced_bones() + self.fit_bones if b not in rig.index]
        if self.root_bone and self.root_bone not in rig.index:
            issues.append(f"root bone {self.root_bone!r} not in rig")
        return issues

    def joint_positions(self, rig: Rig, matrices: dict[int, np.ndarray], joint_names: list[str]) -> np.ndarray:
        out = np.zeros((len(joint_names), 3))
        for k, name in enumerate(joint_names):
            spec = self.joints[name]
            parts = spec.get("mix", [dict(spec, w=1.0)])
            total = sum(p.get("w", 1.0) for p in parts)
            out[k] = sum(p.get("w", 1.0) * rig.bone_point(matrices, p["bone"], float(p.get("at", 0.0)))
                         for p in parts) / total
        return out
