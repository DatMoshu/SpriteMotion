"""2D annotation skeletons: named joints and drawn connectivity."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..jsonio import read_json
from ..schemas import SchemaError, validate


@dataclass
class Skeleton:
    data: dict
    path: Path | None = None

    @classmethod
    def load(cls, path: str | Path) -> "Skeleton":
        data = read_json(path)
        skeleton = cls(data, Path(path))
        skeleton.check()
        return skeleton

    def check(self) -> None:
        errors = validate(self.data, "spritemotion.skeleton")
        names = self.joint_names
        if len(set(names)) != len(names):
            errors.append("Joint names must be unique.")
        known = set(names)
        for chain in self.data.get("chains", []):
            errors += [f"Chain {chain['name']} uses unknown joint {j!r}." for j in chain["joints"] if j not in known]
        for key in ("inferred_connections", "symmetric_pairs"):
            for pair in self.data.get(key, []):
                errors += [f"{key} uses unknown joint {j!r}." for j in pair if j not in known]
        if errors:
            raise SchemaError(f"{self.path or 'skeleton'}: " + "; ".join(errors[:5]))

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def joint_names(self) -> list[str]:
        return [j["name"] for j in self.data["joints"]]

    @property
    def chains(self) -> list[dict]:
        return self.data.get("chains", [])

    def edges(self) -> list[tuple[str, str, bool]]:
        """(joint_a, joint_b, inferred) for every drawn connection."""
        result = []
        for chain in self.chains:
            joints = chain["joints"]
            result += [(a, b, False) for a, b in zip(joints, joints[1:])]
        result += [(a, b, True) for a, b in self.data.get("inferred_connections", [])]
        return result

    def color(self, joint: str) -> str:
        for chain in self.chains:
            if joint in chain["joints"]:
                return chain.get("color", "#ffffff")
        return "#ffffff"

    def swap_map(self) -> dict[str, str]:
        result = {}
        for a, b in self.data.get("symmetric_pairs", []):
            result[a], result[b] = b, a
        return result
