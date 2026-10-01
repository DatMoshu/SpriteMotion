"""Contact sheets: source frames, renders, silhouette differences and joint overlays."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ..poses.skeleton import Skeleton
from ..sprites.dataset import Dataset
from ..sprites.images import alpha_mask, load_rgba
from .compare import load_render

BACKGROUND = (21, 27, 35, 255)


def _hex(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def draw_pose(image: Image.Image, pose: dict, skeleton: Skeleton, scale: float, offset=(0, 0)) -> None:
    draw = ImageDraw.Draw(image)
    joints = pose["joints"]

    def at(name):
        j = joints[name]
        return (offset[0] + (j["x"] + 0.5) * scale, offset[1] + (j["y"] + 0.5) * scale)

    for a, b, inferred in skeleton.edges():
        if a in joints and b in joints:
            color = (255, 228, 94) if inferred else _hex(skeleton.color(a))
            draw.line([at(a), at(b)], fill=color, width=1 if inferred else 2)
    for name in joints:
        x, y = at(name)
        draw.ellipse([x - 2.5, y - 2.5, x + 2.5, y + 2.5], outline=_hex(skeleton.color(name)), fill=(17, 22, 28))


def difference_image(source: np.ndarray, render: np.ndarray) -> np.ndarray:
    """Green: both. Red: source only (render missing it). Blue: render only."""
    sm, rm = alpha_mask(source, 127), alpha_mask(render, 127)
    out = np.zeros(source.shape, dtype=np.uint8)
    out[sm & rm] = (70, 200, 110, 255)
    out[sm & ~rm] = (235, 70, 70, 255)
    out[~sm & rm] = (70, 120, 240, 255)
    return out


def _crop_box(dataset: Dataset, records: list[dict], margin: int = 6) -> tuple[int, int, int, int]:
    boxes = [r["bounds"] for r in records if r.get("bounds")]
    if not boxes:
        return 0, 0, dataset.width, dataset.height
    b = np.array(boxes)
    return (max(0, int(b[:, 0].min()) - margin), max(0, int(b[:, 1].min()) - margin),
            min(dataset.width, int(b[:, 2].max()) + margin), min(dataset.height, int(b[:, 3].max()) + margin))


def contact_sheet(dataset: Dataset, sequence: str, out: Path, renders: Path | None = None,
                  poses: dict | None = None, skeleton: Skeleton | None = None, scale: int = 2) -> Path:
    """One row per direction; per frame a source tile (with optional joints), render tile and diff tile."""
    seq = dataset.sequence(sequence)
    records = [r for _, r in dataset.frames(sequence)]
    x0, y0, x1, y1 = _crop_box(dataset, records)
    tile_w, tile_h = (x1 - x0) * scale, (y1 - y0) * scale
    columns = 3 if renders else 1
    directions = [d["id"] for d in dataset.directions]
    sheet = Image.new("RGBA", (seq["frame_count"] * columns * (tile_w + 4) + 4, len(directions) * (tile_h + 4) + 4),
                      BACKGROUND)
    for row, direction in enumerate(directions):
        for frame in range(seq["frame_count"]):
            try:
                record = dataset.frame(sequence, direction, frame)
            except KeyError:
                continue
            source = load_rgba(dataset.image_path(record))
            tiles = [source]
            if renders:
                render = load_render(dataset, renders, sequence, direction, frame)
                render = np.zeros_like(source) if render is None else render
                tiles += [render, difference_image(source, render)]
            for column, tile in enumerate(tiles):
                crop = Image.fromarray(tile[y0:y1, x0:x1], "RGBA").resize((tile_w, tile_h), Image.NEAREST)
                x = 4 + (frame * columns + column) * (tile_w + 4)
                y = 4 + row * (tile_h + 4)
                sheet.alpha_composite(crop, (x, y))
                if column == 0 and poses and skeleton and (direction, frame) in poses:
                    draw_pose(sheet, poses[(direction, frame)], skeleton, scale, (x - x0 * scale, y - y0 * scale))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
