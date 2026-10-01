"""Compare rendered frames against source sprites.

Renders are expected at <renders>/<sequence>/d<direction>_f<frame:02>.png on
the dataset canvas (same size and anchor). Mirrored-only views (see
Dataset.mirror_source) need no render of their own: they are compared against
the partner's render flipped, exactly as the game draws them. Metrics are
silhouette overlaps: useful for spotting regressions, not a percentage of "done".
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..sprites.dataset import Dataset
from ..sprites.images import alpha_mask, load_rgba, mirror_canvas


def render_path(renders: Path, sequence: str, direction: int, frame: int) -> Path:
    return Path(renders) / sequence / f"d{direction}_f{frame:02d}.png"


def load_render(dataset: Dataset, renders: Path, sequence: str, direction: int, frame: int) -> np.ndarray | None:
    """The render for a view, or for a mirrored-only view its partner's render flipped. None when missing."""
    path = render_path(renders, sequence, direction, frame)
    if path.exists():
        return load_rgba(path)
    partner = dataset.mirror_source(direction)
    if partner is not None:
        path = render_path(renders, sequence, partner, frame)
        if path.exists():
            return mirror_canvas(load_rgba(path), dataset.mirror_axis_x)
    return None


@dataclass
class FrameMetrics:
    sequence: str
    direction: int
    frame: int
    iou: float
    source_pixels: int
    render_pixels: int
    rgb_mae: float | None

    def to_dict(self) -> dict:
        return {"sequence": self.sequence, "direction": self.direction, "frame": self.frame,
                "iou": round(self.iou, 5), "source_pixels": self.source_pixels,
                "render_pixels": self.render_pixels,
                "rgb_mae": None if self.rgb_mae is None else round(self.rgb_mae, 3)}


def silhouette_iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 1.0


def compare_frame(source: np.ndarray, render: np.ndarray, threshold: int = 127) -> tuple[float, int, int, float | None]:
    if source.shape != render.shape:
        raise ValueError(f"Render size {render.shape[:2]} differs from source {source.shape[:2]}.")
    sm, rm = alpha_mask(source, threshold), alpha_mask(render, threshold)
    both = sm & rm
    mae = float(np.abs(source[both, :3].astype(int) - render[both, :3].astype(int)).mean()) if both.any() else None
    return silhouette_iou(sm, rm), int(sm.sum()), int(rm.sum()), mae


def compare_dataset(dataset: Dataset, renders: Path, sequences: list[str] | None = None) -> dict:
    frames, missing = [], []
    for sequence, record in dataset.frames():
        if sequences and sequence not in sequences:
            continue
        render = load_render(dataset, renders, sequence, record["direction"], record["frame"])
        if render is None:
            missing.append(record["frame_id"])
            continue
        iou, sp, rp, mae = compare_frame(load_rgba(dataset.image_path(record)), render)
        frames.append(FrameMetrics(sequence, record["direction"], record["frame"], iou, sp, rp, mae))
    summary: dict = {"frames": len(frames), "missing_renders": len(missing)}
    if frames:
        summary["mean_iou"] = round(float(np.mean([f.iou for f in frames])), 5)
        by_sequence: dict[str, list[float]] = {}
        by_direction: dict[int, list[float]] = {}
        for f in frames:
            by_sequence.setdefault(f.sequence, []).append(f.iou)
            by_direction.setdefault(f.direction, []).append(f.iou)
        summary["by_sequence"] = {k: round(float(np.mean(v)), 5) for k, v in by_sequence.items()}
        summary["by_direction"] = {str(k): round(float(np.mean(v)), 5) for k, v in sorted(by_direction.items())}
    return {"dataset_id": dataset.dataset_id, "renders": str(renders), "summary": summary,
            "note": "Silhouette IoU measures shape overlap only; it is not a completion percentage.",
            "missing": missing[:50], "frame_metrics": [f.to_dict() for f in frames]}
