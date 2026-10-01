"""Decode mobile animation frames from anim.mul / anim.idx and AnimationFrame*.uop.

Layout (see ClassicUO AnimationsLoader and UOFiddler Ultima/Animations.cs):
  anim.idx : 12-byte entries (int32 offset, int32 length, int32 extra); -1 offset = missing
  entry    : 256 x uint16 palette (RGB555), uint32 frame count, frame count x uint32
             offsets (relative to the end of the palette)
  frame    : int16 center_x, int16 center_y, uint16 width, uint16 height, then runs of
             uint32 header [x:10 signed | y:10 signed | run length:12] followed by
             `run` palette indices, terminated by 0x7FFF7FFF.
             Run coordinates are relative to (center_x, center_y + height).

UOP (AnimationFrame<n>.uop, container in uo_uop.py) holds one bin per body and
action group with all five stored directions; each frame there has its own
palette followed by the same sprite encoding, and palette colour 0 is transparent.

Source selection follows the client: a body is drawn from UOP when mobtypes.txt
gives it the UseUopAnimation flag (0x10000) and AnimationFrame files exist,
otherwise from anim.mul. AnimationSequence.uop may redirect an action to another
group. On the MUL side only anim.mul (file 1) is read: anim2-5.mul and
Body.def / Bodyconv.def substitutions are not resolved, so a body that needs them
fails loudly instead of being guessed.
"""
from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uo_uop import FRAME_NAME, MAX_DIRECTIONS, USE_UOP_ANIMATION, UopFile, uop_hash  # noqa: E402

END_OF_FRAME = 0x7FFF7FFF
MAX_ACTIONS = 80                     # the client's action limit for UOP bodies
SOURCE_MODES = ("auto", "mul", "uop")


@dataclass
class Frame:
    center_x: int
    center_y: int
    width: int
    height: int
    rgba: np.ndarray        # (height, width, 4) uint8, unhued source colors
    indices: np.ndarray     # (height, width) palette indices, -1 where transparent

    @property
    def empty(self) -> bool:
        return self.width == 0 or self.height == 0


def empty_frame(center_x: int = 0, center_y: int = 0) -> Frame:
    return Frame(center_x, center_y, 0, 0, np.zeros((0, 0, 4), dtype=np.uint8), np.zeros((0, 0), dtype=np.int16))


def actions_for_body(body: int) -> tuple[int, int]:
    """(first idx entry, action count) for a body in anim.mul."""
    if body < 200:
        return body * 110, 22
    if body < 400:
        return 22000 + (body - 200) * 65, 13
    return 35000 + (body - 400) * 175, 35


def rgb555_to_rgba(color: int) -> tuple[int, int, int, int]:
    r, g, b = (color >> 10) & 31, (color >> 5) & 31, color & 31
    return (r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2), 255


def palette_colors(data: bytes, position: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """(256x4 RGBA colours, 256 raw RGB555 values) of a 512-byte palette."""
    raw = struct.unpack_from("<256H", data, position)
    return np.array([rgb555_to_rgba(c) for c in raw], dtype=np.uint8), np.array(raw, dtype=np.uint16)


class AnimMul:
    def __init__(self, folder: Path):
        folder = Path(folder)
        self.idx_path, self.mul_path = folder / "anim.idx", folder / "anim.mul"
        missing = [p.name for p in (self.idx_path, self.mul_path) if not p.exists()]
        if missing:
            raise FileNotFoundError(f"{folder} has no {', '.join(missing)}.")
        self.idx = self.idx_path.read_bytes()

    def entry(self, index: int) -> bytes | None:
        if (index + 1) * 12 > len(self.idx):
            return None
        offset, length, _ = struct.unpack_from("<iii", self.idx, index * 12)
        if offset < 0 or length <= 0:
            return None
        with self.mul_path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(length)
        if len(data) != length:
            raise ValueError(f"anim.mul entry {index} is truncated.")
        return data

    def sequence(self, body: int, action: int, stored_direction: int) -> list[Frame] | None:
        first, count = actions_for_body(body)
        if not 0 <= action < count or not 0 <= stored_direction < 5:
            raise ValueError(f"Body {body} has actions 0-{count - 1} and stored directions 0-4.")
        data = self.entry(first + action * 5 + stored_direction)
        return None if data is None else decode_entry(data)


def decode_entry(data: bytes) -> list[Frame]:
    colors, _ = palette_colors(data)
    (count,) = struct.unpack_from("<I", data, 512)
    if not 0 < count < 1000:
        raise ValueError(f"Implausible frame count {count}.")
    offsets = struct.unpack_from(f"<{count}I", data, 516)
    return [decode_frame(data, 512 + offset, colors) for offset in offsets]


def decode_frame(data: bytes, position: int, colors: np.ndarray, allow_empty: bool = False,
                 transparent: np.ndarray | None = None) -> Frame:
    """One sprite at `position`. `transparent` flags palette indices drawn as transparent (UOP: colour 0)."""
    cx, cy, width, height = struct.unpack_from("<hhHH", data, position)
    position += 8
    if width <= 0 or height <= 0:
        if allow_empty:
            return empty_frame(cx, cy)
        raise ValueError("Empty animation frame.")
    indices = np.full((height, width), -1, dtype=np.int16)
    while True:
        (header,) = struct.unpack_from("<I", data, position)
        position += 4
        if header == END_OF_FRAME:
            break
        run = header & 0xFFF
        x = (header >> 22) & 0x3FF
        y = (header >> 12) & 0x3FF
        if x & 0x200:
            x -= 0x400
        if y & 0x200:
            y -= 0x400
        x += cx
        y += cy + height
        if not (0 <= y < height and 0 <= x and x + run <= width):
            raise ValueError(f"Run at ({x}, {y}) x{run} leaves the {width}x{height} frame.")
        indices[y, x:x + run] = np.frombuffer(data, dtype=np.uint8, count=run, offset=position)
        position += run
    if transparent is not None:
        hidden = indices >= 0
        hidden[hidden] = transparent[indices[hidden]]
        indices[hidden] = -1
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    opaque = indices >= 0
    rgba[opaque] = colors[indices[opaque]]
    return Frame(cx, cy, width, height, rgba, indices)


def decode_uop_bin(data: bytes, equipment: bool = False) -> list[list[Frame]]:
    """An AnimationFrame bin -> frames per stored direction (0-4), laid out as the client does.

    Frame ids run 1..n through the five directions; a gap in the ids is a missing
    (empty) frame. Frames per direction = round(total / 5), at least 10 for equipment
    bodies, and frame id k belongs to direction (k - 1) // per_direction.
    """
    if data[:4] != b"AMOU":
        raise ValueError(f"Not a UOP animation bin (magic {data[:4]!r}).")
    count, table = struct.unpack_from("<iI", data, 32)
    if not 0 < count < 5000:
        raise ValueError(f"Implausible UOP frame count {count}.")
    ids: list[tuple[int, int | None]] = []
    last = 1
    for i in range(count):
        start = table + 16 * i
        _group, frame_id, _unknown, pixel_offset = struct.unpack_from("<HHQI", data, start)
        while frame_id - last > 1:          # fill the gap with missing frames
            last += 1
            ids.append((last, None))
        ids.append((frame_id, start + pixel_offset))
        last = frame_id
    per_direction = round(len(ids) / MAX_DIRECTIONS)   # banker's rounding, like the client's Math.Round
    if equipment:
        per_direction = max(10, per_direction)
    if per_direction <= 0:
        raise ValueError("UOP bin has too few frames for five directions.")
    directions = [[empty_frame() for _ in range(per_direction)] for _ in range(MAX_DIRECTIONS)]
    for frame_id, position in ids:
        direction, index = divmod(frame_id - 1, per_direction)
        if direction >= MAX_DIRECTIONS:
            break
        if position is None:
            continue
        colors, raw = palette_colors(data, position)
        directions[direction][index] = decode_frame(data, position + 512, colors, allow_empty=True,
                                                    transparent=raw == 0)
    return directions


MOB_TYPES = ("monster", "sea_monster", "animal", "human", "equipment")


def read_mobtypes(path: Path) -> dict[int, tuple[str, int]]:
    """mobtypes.txt -> {body: (type, hex flags)}. A later line for the same body wins, as in the client."""
    result: dict[int, tuple[str, int]] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="latin-1").splitlines():
        line = line.split("#", 1)[0].strip()
        parts = line.split()
        if len(parts) < 3 or not parts[0].isdigit() or parts[1].lower() not in MOB_TYPES:
            continue
        try:
            result[int(parts[0])] = (parts[1].lower(), int(parts[2], 16))
        except ValueError:
            continue
    return result


def read_group_replacements(sequence: UopFile) -> dict[int, dict[int, int]]:
    """AnimationSequence.uop -> {body: {action: replacement group}} (records whose frame count is 0)."""
    result: dict[int, dict[int, int]] = {}
    for name_hash in sequence.entries:
        data = sequence.read(name_hash)
        if len(data) < 56:
            continue
        (body,) = struct.unpack_from("<I", data, 0)
        (replaces,) = struct.unpack_from("<i", data, 52)
        mapping: dict[int, int] = {}
        if replaces not in (48, 68):         # the client skips entries with these counts
            position = 56
            for _ in range(max(0, replaces)):
                if position + 12 > len(data):
                    break
                old, frames, new = struct.unpack_from("<iIi", data, position)
                if frames == 0:
                    mapping[old] = new
                position += 12 + 60
        if mapping:
            result[body] = mapping
    return result


class UOAnimations:
    """Animation data of one client folder, taking each body from MUL or UOP like the client.

    mode "auto" follows the client (UOP when mobtypes.txt flags the body), "mul" and
    "uop" force one source and fail when it is missing.
    """

    def __init__(self, folder: Path, mode: str = "auto"):
        if mode not in SOURCE_MODES:
            raise ValueError(f"Animation source must be one of {', '.join(SOURCE_MODES)}, not {mode!r}.")
        self.folder, self.mode = Path(folder), mode
        has_mul = (self.folder / "anim.mul").exists() and (self.folder / "anim.idx").exists()
        self.mul = AnimMul(self.folder) if has_mul else None
        self.uop = [UopFile(p) for n in range(1, 11) if (p := self.folder / f"AnimationFrame{n}.uop").exists()]
        if self.mul is None and not self.uop:
            raise FileNotFoundError(f"{self.folder} has neither anim.mul/anim.idx nor AnimationFrame*.uop.")
        self.mobtypes = read_mobtypes(self.folder / "mobtypes.txt")
        sequence = self.folder / "AnimationSequence.uop"
        self.replacements = read_group_replacements(UopFile(sequence)) if self.uop and sequence.exists() else {}
        self._cached: tuple[tuple[int, int], object] | None = None

    def uses_uop(self, body: int) -> bool:
        """The client's rule: UOP when the body has the UseUopAnimation flag and UOP files exist."""
        return bool(self.uop) and bool(self.mobtypes.get(body, ("", 0))[1] & USE_UOP_ANIMATION)

    def source_for(self, body: int) -> str:
        """'mul' or 'uop' for this body under the current mode; raises if that source is missing."""
        source = self.mode if self.mode != "auto" else ("uop" if self.uses_uop(body) else "mul")
        if source == "mul" and self.mul is None:
            raise FileNotFoundError(f"{self.folder} has no anim.mul/anim.idx (needed for body {body}).")
        if source == "uop" and not self.uop:
            raise FileNotFoundError(f"{self.folder} has no AnimationFrame*.uop (needed for body {body}).")
        return source

    def action_count(self, body: int) -> int:
        return MAX_ACTIONS if self.source_for(body) == "uop" else actions_for_body(body)[1]

    def group_for(self, body: int, action: int) -> int:
        """UOP group drawn for an action after AnimationSequence replacements."""
        return self.replacements.get(body, {}).get(action, action)

    def uop_bodies(self) -> list[int]:
        """Bodies with at least one group in the AnimationFrame files (scans all names; slow-ish)."""
        present = set().union(*(f.entries.keys() for f in self.uop)) if self.uop else set()
        return [body for body in range(4096)
                if any(uop_hash(FRAME_NAME.format(body=body, group=g)) in present for g in range(MAX_ACTIONS))]

    def _uop_group(self, body: int, action: int):
        key = (body, action)
        if self._cached is None or self._cached[0] != key:    # one group at a time keeps memory flat
            group = self.group_for(body, action)
            found = None
            if 0 <= group < MAX_ACTIONS:
                name = FRAME_NAME.format(body=body, group=group)
                name_hash = uop_hash(name)
                container = next((f for f in self.uop if name_hash in f), None)
                if container is not None:
                    equipment = self.mobtypes.get(body, ("", 0))[0] == "equipment"
                    found = (decode_uop_bin(container.read(name_hash), equipment),
                             {"file": container.path.name, "group": group})
            self._cached = (key, found)
        return self._cached[1]

    def sequence(self, body: int, action: int, stored_direction: int) -> tuple[list[Frame] | None, dict]:
        """Frames of one stored direction and their source file info; (None, {}) when absent."""
        if not 0 <= stored_direction < MAX_DIRECTIONS:
            raise ValueError("Stored directions are 0-4.")
        if self.source_for(body) == "mul":
            if not 0 <= action < actions_for_body(body)[1]:
                return None, {}
            frames = self.mul.sequence(body, action, stored_direction)
            return frames, {"file": "anim.mul"}
        found = self._uop_group(body, action)
        if found is None:
            return None, {}
        directions, info = found
        return directions[stored_direction], dict(info)
