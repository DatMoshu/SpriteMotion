"""Read a SpriteMotion transfer artifact: a finished export another tool imports.

Standard library only (no numpy, no Pillow). The format is described in docs/transfer-artifact.md and
common/schemas/transfer-artifact.schema.json. ``read(directory)`` returns a ``TransferArtifact`` or raises
``TransferError`` with a message that names the file or field at fault.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import schemas
from .jsonio import read_json

MANIFEST = "transfer.json"
KIND = "spritemotion.transfer-artifact"
CANVAS = (256, 256)
ANCHOR = (128, 192)
MIRROR_MAP = {5: 3, 6: 2, 7: 1}
STORED_DIRECTIONS = (0, 1, 2, 3, 4)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class TransferError(ValueError):
    """The artifact is malformed, incomplete or fails verification."""


@dataclass(frozen=True)
class Crop:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def mirrored(self) -> "Crop":
        """The crop after a horizontal flip about the anchor column (canvas x = 128)."""
        return Crop(2 * ANCHOR[0] - self.right, self.top, 2 * ANCHOR[0] - self.left, self.bottom)


def centre(crop: Crop) -> tuple[int, int]:
    """Sprite centre for a crop: (128 - left, 192 - bottom). Either value can be negative."""
    return ANCHOR[0] - crop.left, ANCHOR[1] - crop.bottom


@dataclass(frozen=True)
class Frame:
    action: int
    direction: int          # stored direction, 0-4
    index: int
    path: Path | None       # absolute path of the PNG; None for an empty frame
    sha256: str | None
    crop: Crop | None       # None for an empty frame

    @property
    def empty(self) -> bool:
        return self.crop is None

    @property
    def centre(self) -> tuple[int, int] | None:
        return None if self.crop is None else centre(self.crop)


@dataclass(frozen=True)
class ResolvedFrame:
    """A frame as seen for a requested direction (0-7)."""
    frame: Frame
    direction: int          # the direction that was asked for
    mirrored: bool          # True when the stored pixels must be flipped horizontally about x = 128

    @property
    def crop(self) -> Crop | None:
        if self.frame.crop is None:
            return None
        return self.frame.crop.mirrored() if self.mirrored else self.frame.crop

    @property
    def centre(self) -> tuple[int, int] | None:
        crop = self.crop
        return None if crop is None else centre(crop)


class TransferArtifact:
    def __init__(self, root: Path, manifest: dict, frames: list[Frame]):
        self.root = root
        self.manifest = manifest
        self.frames = frames
        self._by_key = {(f.action, f.direction, f.index): f for f in frames}
        self.mirror_map = {int(k): v for k, v in manifest["animation"]["mirror_map"].items()}

    @property
    def identity(self) -> dict:
        return self.manifest["identity"]

    @property
    def actions(self) -> list[int]:
        return [a["action"] for a in self.manifest["animation"]["actions"]]

    def frame_count(self, action: int) -> int:
        for entry in self.manifest["animation"]["actions"]:
            if entry["action"] == action:
                return entry["frame_count"]
        raise KeyError(f"No action {action} in this artifact.")

    def frame(self, action: int, direction: int, index: int) -> Frame:
        """The stored frame for a stored direction (0-4)."""
        try:
            return self._by_key[(action, direction, index)]
        except KeyError:
            raise KeyError(f"No stored frame for action {action}, direction {direction}, index {index}.") from None

    def resolve(self, action: int, direction: int, index: int) -> ResolvedFrame:
        """The frame for any facing 0-7; directions 5-7 come from the mirror map."""
        if direction in self.mirror_map:
            return ResolvedFrame(self.frame(action, self.mirror_map[direction], index), direction, True)
        return ResolvedFrame(self.frame(action, direction, index), direction, False)


def read(directory: str | Path) -> TransferArtifact:
    root = Path(directory)
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        raise TransferError(f"No {MANIFEST} in {root}.")
    try:
        manifest = read_json(manifest_path)
    except ValueError as error:
        raise TransferError(f"{MANIFEST} is not valid JSON: {error}") from error
    if not isinstance(manifest, dict):
        raise TransferError(f"{MANIFEST} is not a JSON object.")
    if manifest.get("schema") != KIND:
        raise TransferError(f"{MANIFEST}: expected schema {KIND!r}, found {manifest.get('schema')!r}.")
    if manifest.get("schema_version") != 1:
        raise TransferError(f"{MANIFEST}: unsupported schema_version {manifest.get('schema_version')!r}.")
    # The reader's own checks run first so their messages are specific; jsonschema, when present, checks the rest.
    _check_structure(manifest)
    frames = _read_frames(root, manifest)
    errors = schemas.validate(manifest, KIND)
    if errors:
        raise TransferError(f"{MANIFEST} does not match its schema: " + "; ".join(errors[:5]))
    return TransferArtifact(root, manifest, frames)


def _check_structure(manifest: dict) -> None:
    for section in ("identity", "animation", "pixels", "frames"):
        if section not in manifest:
            raise TransferError(f"{MANIFEST}: missing section {section!r}.")
    animation, pixels = manifest["animation"], manifest["pixels"]
    mirror = animation.get("mirror_map") if isinstance(animation, dict) else None
    if not isinstance(mirror, dict) or {str(k): v for k, v in mirror.items()} != {str(k): v for k, v in MIRROR_MAP.items()}:
        raise TransferError(f"animation.mirror_map must be exactly {MIRROR_MAP}, found {mirror!r}.")
    if not isinstance(pixels, dict):
        raise TransferError("pixels must be an object.")
    canvas, anchor = pixels.get("canvas"), pixels.get("anchor")
    if not isinstance(canvas, dict) or (canvas.get("width"), canvas.get("height")) != CANVAS:
        raise TransferError(f"pixels.canvas must be {CANVAS[0]}x{CANVAS[1]}, found {canvas!r}.")
    if not isinstance(anchor, dict) or (anchor.get("x"), anchor.get("y")) != ANCHOR:
        raise TransferError(f"pixels.anchor must be {ANCHOR}, found {anchor!r}.")
    if not isinstance(animation.get("actions"), list) or not animation["actions"] or not isinstance(manifest["frames"], list):
        raise TransferError("animation.actions and frames must be non-empty lists.")


def safe_path(root: Path, rel: Any, what: str) -> Path:
    """Resolve a manifest path inside root; reject absolute paths, traversal and escapes."""
    if not isinstance(rel, str) or not rel:
        raise TransferError(f"{what}: path must be a non-empty string.")
    if rel.startswith("/") or "\\" in rel or (len(rel) > 1 and rel[1] == ":"):
        raise TransferError(f"{what}: path {rel!r} is absolute or uses backslashes; use a relative forward-slash path.")
    if any(part in ("..", "") for part in rel.split("/")):
        raise TransferError(f"{what}: path {rel!r} leaves the artifact directory or has an empty segment.")
    root_resolved = root.resolve()
    target = (root / rel).resolve()
    if root_resolved != target and root_resolved not in target.parents:
        raise TransferError(f"{what}: path {rel!r} resolves outside the artifact directory.")
    return target


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from the PNG header (the IHDR chunk), without decoding."""
    with open(path, "rb") as handle:
        head = handle.read(24)
    if len(head) < 24 or head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        raise TransferError(f"{path.name} is not a PNG file.")
    return struct.unpack(">II", head[16:24])


def _verify_file(root: Path, ref: Any, what: str) -> Path:
    if not isinstance(ref, dict):
        raise TransferError(f"{what}: expected an object with path and sha256.")
    path = safe_path(root, ref.get("path"), what)
    if not path.is_file():
        raise TransferError(f"{what}: file {ref.get('path')!r} is missing.")
    expected = ref.get("sha256")
    if not isinstance(expected, str) or sha256_of(path) != expected:
        raise TransferError(f"{what}: sha256 mismatch for {ref.get('path')!r}.")
    return path


def _read_frames(root: Path, manifest: dict) -> list[Frame]:
    actions = {}
    for entry in manifest["animation"]["actions"]:
        action = entry.get("action")
        if not isinstance(action, int) or action in actions:
            raise TransferError(f"animation.actions: duplicate or invalid action {action!r}.")
        directions = entry.get("directions")
        if not isinstance(directions, list) or not directions or any(d not in STORED_DIRECTIONS for d in directions):
            raise TransferError(f"action {action}: directions must be a list drawn from 0-4 (5-7 are mirrored).")
        if not isinstance(entry.get("frame_count"), int) or entry["frame_count"] < 1:
            raise TransferError(f"action {action}: frame_count must be a positive integer.")
        actions[action] = entry

    # Files other than frames: checked when declared.
    for label, ref in (("reproducibility.fit", manifest.get("reproducibility", {}).get("fit")),
                       ("equipment.item_art", manifest.get("equipment", {}).get("item_art")),
                       ("acceptance.validation_report", manifest.get("acceptance", {}).get("validation_report"))):
        if ref is not None:
            _verify_file(root, ref, label)

    frames: list[Frame] = []
    seen: set[tuple[int, int, int]] = set()
    for number, item in enumerate(manifest["frames"]):
        what = f"frames[{number}]"
        if not isinstance(item, dict):
            raise TransferError(f"{what}: not an object.")
        try:
            action, direction, index = item["action"], item["direction"], item["index"]
        except KeyError as error:
            raise TransferError(f"{what}: missing {error.args[0]!r}.") from None
        if action not in actions:
            raise TransferError(f"{what}: action {action} is not declared in animation.actions.")
        entry = actions[action]
        if direction not in entry["directions"]:
            raise TransferError(f"{what}: direction {direction} is not a stored direction of action {action} "
                                f"(5-7 are mirrored, never stored).")
        if not isinstance(index, int) or not 0 <= index < entry["frame_count"]:
            raise TransferError(f"{what}: index {index!r} is outside 0..{entry['frame_count'] - 1} for action {action}.")
        key = (action, direction, index)
        if key in seen:
            raise TransferError(f"{what}: duplicate frame {key}.")
        seen.add(key)
        if item.get("empty") is True:
            if any(k in item for k in ("png", "sha256", "crop", "centre")):
                raise TransferError(f"{what}: an empty frame carries no png, sha256, crop or centre.")
            frames.append(Frame(action, direction, index, None, None, None))
            continue
        if item.get("empty") is not False:
            raise TransferError(f"{what}: 'empty' must be true or false.")
        path = _verify_file(root, {"path": item.get("png"), "sha256": item.get("sha256")}, what)
        crop = _read_crop(item.get("crop"), what)
        width, height = png_size(path)
        if (width, height) != (crop.width, crop.height):
            raise TransferError(f"{what}: PNG is {width}x{height} but the crop is {crop.width}x{crop.height}.")
        stated = item.get("centre")
        if stated is not None and (stated.get("x"), stated.get("y")) != centre(crop):
            raise TransferError(f"{what}: centre {stated} does not match the crop (expected {centre(crop)}).")
        frames.append(Frame(action, direction, index, path, item["sha256"], crop))

    missing = [(a, d, i) for a, entry in actions.items() for d in entry["directions"]
               for i in range(entry["frame_count"]) if (a, d, i) not in seen]
    if missing:
        raise TransferError(f"frames: {len(missing)} declared frame(s) missing, first {missing[0]} (action, direction, index).")
    return frames


def _read_crop(raw: Any, what: str) -> Crop:
    if not isinstance(raw, dict):
        raise TransferError(f"{what}: crop must be an object with left, top, right, bottom.")
    try:
        values = [raw[k] for k in ("left", "top", "right", "bottom")]
    except KeyError as error:
        raise TransferError(f"{what}: crop is missing {error.args[0]!r}.") from None
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        raise TransferError(f"{what}: crop values must be integers.")
    crop = Crop(*values)
    if not (0 <= crop.left < crop.right <= CANVAS[0] and 0 <= crop.top < crop.bottom <= CANVAS[1]):
        raise TransferError(f"{what}: crop {values} is empty or outside the {CANVAS[0]}x{CANVAS[1]} canvas.")
    return crop
