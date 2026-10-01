"""Dataset manifests: the normalized frames an adapter extracted."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from ..jsonio import read_json, write_json
from ..schemas import SchemaError, validate

DATASET_FILE = "dataset.json"


def frame_id(dataset_id: str, sequence: str, direction: int, frame: int) -> str:
    return f"{dataset_id}/{sequence}/d{direction}/f{frame:02d}"


@dataclass
class Dataset:
    path: Path
    data: dict
    _frames: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, path: str | Path, check_schema: bool = True) -> "Dataset":
        path = Path(path)
        if path.is_dir():
            path = path / DATASET_FILE
        data = read_json(path)
        if check_schema:
            errors = validate(data, "spritemotion.dataset")
            if errors:
                raise SchemaError(f"{path}: " + "; ".join(errors[:5]))
        dataset = cls(path, data)
        dataset._index()
        return dataset

    def _index(self) -> None:
        self._frames.clear()
        direction_ids = {d["id"] for d in self.directions}
        for sequence in self.sequences:
            seen = set()
            for record in sequence["frames"]:
                key = (sequence["id"], record["direction"], record["frame"])
                if key in seen:
                    raise SchemaError(f"Duplicate frame {key} in {self.path}.")
                if record["direction"] not in direction_ids:
                    raise SchemaError(f"Frame {record['frame_id']} uses unknown direction {record['direction']}.")
                if record["frame"] >= sequence["frame_count"]:
                    raise SchemaError(f"Frame {record['frame_id']} is outside frame_count {sequence['frame_count']}.")
                expected = frame_id(self.dataset_id, sequence["id"], record["direction"], record["frame"])
                if record["frame_id"] != expected:
                    raise SchemaError(f"Frame id {record['frame_id']!r} should be {expected!r}.")
                seen.add(key)
                self._frames[key] = record

    def save(self, path: str | Path | None = None) -> Path:
        return write_json(path or self.path, self.data)

    @property
    def root(self) -> Path:
        return self.path.parent

    @property
    def dataset_id(self) -> str:
        return self.data["dataset_id"]

    @property
    def canvas(self) -> dict:
        return self.data["canvas"]

    @property
    def width(self) -> int:
        return int(self.canvas["width"])

    @property
    def height(self) -> int:
        return int(self.canvas["height"])

    @property
    def mirror_axis_x(self) -> float:
        return float(self.canvas.get("mirror_axis_x", (self.width - 1) / 2))

    @property
    def directions(self) -> list[dict]:
        return self.data["directions"]

    def direction(self, direction_id: int) -> dict:
        for item in self.directions:
            if item["id"] == direction_id:
                return item
        raise KeyError(direction_id)

    def mirror_source(self, direction_id: int) -> int | None:
        """The stored direction a mirrored-only view is flipped from, or None for a stored view.

        A mirrored view is not another camera angle on the same 3D pose: on screen
        it is the mirror-image character. Fitting, reprojection and rendering
        therefore treat it as its partner view, flipped about mirror_axis_x.
        """
        direction = self.direction(direction_id)
        if direction.get("stored", True) or direction.get("mirror_of") is None:
            return None
        return int(direction["mirror_of"])

    @property
    def sequences(self) -> list[dict]:
        return self.data["sequences"]

    def sequence(self, sequence_id: str) -> dict:
        for item in self.sequences:
            if item["id"] == sequence_id:
                return item
        raise KeyError(sequence_id)

    def frame(self, sequence_id: str, direction: int, frame: int) -> dict:
        return self._frames[(sequence_id, direction, frame)]

    def frames(self, sequence_id: str | None = None) -> Iterator[tuple[str, dict]]:
        for sequence in self.sequences:
            if sequence_id is None or sequence["id"] == sequence_id:
                for record in sequence["frames"]:
                    yield sequence["id"], record

    def image_path(self, record: dict) -> Path:
        return self.root / record["image"]

    @property
    def skeleton_path(self) -> Path:
        return self.root / self.data["skeleton"]

    def annotation_dir(self, layer: str) -> Path:
        key = {"estimate": "estimates", "correction": "corrections"}[layer]
        return self.root / self.data.get("annotations", {}).get(key, f"annotations/{key}")

    def annotation_path(self, layer: str, sequence_id: str) -> Path:
        return self.annotation_dir(layer) / f"{sequence_id}.json"
