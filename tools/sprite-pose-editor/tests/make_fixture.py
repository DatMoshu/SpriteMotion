"""Write the tiny synthetic dataset used by the editor tests.

Our own procedurally drawn art (a stick figure on a 48x64 canvas), so it is
redistributable. Four directions with two mirror pairs (E<->W, NE<->NW),
two sequences (3 and 2 frames), a six-joint skeleton, a partial estimates
layer and a corrections layer holding one approved pose.

    python tools/sprite-pose-editor/tests/make_fixture.py
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _import_spritemotion():
    try:
        import spritemotion  # noqa: F401
        return
    except ImportError:
        pass
    spec = importlib.util.spec_from_file_location(
        "spritemotion", REPO / "common" / "__init__.py", submodule_search_locations=[str(REPO / "common")])
    module = importlib.util.module_from_spec(spec)
    sys.modules["spritemotion"] = module
    spec.loader.exec_module(module)


_import_spritemotion()

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from spritemotion.jsonio import write_json  # noqa: E402
from spritemotion.sprites.images import fingerprint, mirror_canvas, opaque_bounds  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures" / "tiny"
WIDTH, HEIGHT = 48, 64
AXIS = (WIDTH - 1) / 2
DATASET_ID = "fixture/tiny"
JOINTS = ["head", "neck", "pelvis", "hand", "foot_a", "foot_b"]
DIRECTIONS = [
    {"id": 0, "name": "E", "mirror_of": 2, "stored": True},
    {"id": 1, "name": "NE", "mirror_of": 3, "stored": True},
    {"id": 2, "name": "W", "mirror_of": 0, "stored": False},
    {"id": 3, "name": "NW", "mirror_of": 1, "stored": False},
]
SEQUENCES = [("wave", "Wave", 3), ("hop", "Hop", 2)]


def pose_points(sequence: str, direction: int, frame: int) -> dict[str, tuple[float, float]]:
    """Ground-truth joints for stored directions (0, 1); mirrored views are derived."""
    lean = 3.0 if direction == 1 else 0.0
    lift = 4.0 * frame if sequence == "hop" else 0.0
    swing = math.sin(frame * 1.3) * 6.0 if sequence == "wave" else 2.0
    head = (22 + lean, 12 - lift)
    neck = (22 + lean * 0.8, 20 - lift)
    pelvis = (22.0, 38 - lift)
    hand = (32 + swing * 0.5, 22 - swing - lift)
    foot_a = (17.0, 58 - lift)
    foot_b = (27.0, 58 - lift)
    return dict(zip(JOINTS, (head, neck, pelvis, hand, foot_a, foot_b)))


def draw(points: dict[str, tuple[float, float]], tint: tuple[int, int, int]) -> np.ndarray:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    color = tint + (255,)
    for a, b in [("neck", "pelvis"), ("neck", "hand"), ("pelvis", "foot_a"), ("pelvis", "foot_b")]:
        pen.line([points[a], points[b]], fill=color, width=3)
    hx, hy = points["head"]
    pen.ellipse([hx - 5, hy - 5, hx + 5, hy + 5], fill=color)
    return np.array(image)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    skeleton = {
        "schema": "spritemotion.skeleton", "schema_version": 1, "id": "tiny-6", "title": "Tiny six-joint test skeleton",
        "joints": [{"name": n, "label": n.replace("_", " ").title()} for n in JOINTS],
        "chains": [
            {"name": "spine", "label": "Spine", "color": "#ffe45e", "joints": ["head", "neck", "pelvis"]},
            {"name": "arm", "label": "Arm", "color": "#28d9ff", "joints": ["neck", "hand"]},
            {"name": "leg_a", "label": "Leg A", "color": "#78ff6b", "joints": ["pelvis", "foot_a"]},
        ],
        "inferred_connections": [["pelvis", "foot_b"]],
        "symmetric_pairs": [["foot_a", "foot_b"]],
    }
    write_json(OUT / "skeleton.json", skeleton)

    sequences, truth = [], {}
    for seq_id, name, count in SEQUENCES:
        frames = []
        for d in DIRECTIONS:
            for f in range(count):
                stored = d["id"] if d["stored"] else d["mirror_of"]
                points = pose_points(seq_id, stored, f)
                tint = (200, 150 + 30 * f, 120) if seq_id == "wave" else (120, 170, 220 - 30 * f)
                canvas = draw(points, tint)
                if not d["stored"]:
                    canvas = mirror_canvas(canvas, AXIS)
                    points = {k: (2 * AXIS - x, y) for k, (x, y) in points.items()}
                rel = f"frames/{seq_id}/d{d['id']}_f{f:02d}.png"
                (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(canvas, "RGBA").save(OUT / rel)
                record = {"frame_id": f"{DATASET_ID}/{seq_id}/d{d['id']}/f{f:02d}", "direction": d["id"], "frame": f,
                          "image": rel, "fingerprint": fingerprint(canvas), "bounds": opaque_bounds(canvas)}
                if not d["stored"]:
                    record["mirrored_from"] = d["mirror_of"]
                frames.append(record)
                truth[(seq_id, d["id"], f)] = (record, points)
        sequences.append({"id": seq_id, "name": name, "index": len(sequences), "frame_count": count,
                          "frame_duration_ms": 150, "frames": frames})

    manifest = {
        "schema": "spritemotion.dataset", "schema_version": 1, "dataset_id": DATASET_ID,
        "title": "Tiny editor fixture", "game": "fixture", "character": "stick",
        "created_by": "tools/sprite-pose-editor/tests/make_fixture.py",
        "canvas": {"width": WIDTH, "height": HEIGHT, "anchor": [22, 58], "mirror_axis_x": AXIS},
        "directions": DIRECTIONS, "skeleton": "skeleton.json",
        "annotations": {"estimates": "annotations/estimates", "corrections": "annotations/corrections"},
        "sequences": sequences,
    }
    write_json(OUT / "dataset.json", manifest)

    def pose(seq_id: str, d: int, f: int, jitter: float, **extra) -> dict:
        record, points = truth[(seq_id, d, f)]
        return {"frame_id": record["frame_id"], "direction": d, "frame": f, "source_fingerprint": record["fingerprint"],
                "provenance": extra.pop("provenance"), "review": extra.pop("review", {"status": "unreviewed"}),
                "joints": {n: {"x": round(x + jitter, 3), "y": round(y - jitter, 3), "confidence": 0.5, "status": "estimate"}
                           for n, (x, y) in points.items()}}

    projection = {"method": "rig_projection", "independent": False, "detail": "Synthetic test estimate."}
    base = {"schema": "spritemotion.pose-annotations", "schema_version": 1, "dataset_id": DATASET_ID,
            "skeleton": "tiny-6", "coordinate_space": "canvas-px"}
    # Wave: every pose except direction 3 frame 2 (left missing on purpose). Hop: no estimates at all.
    wave = [pose("wave", d["id"], f, 1.5, provenance=dict(projection))
            for d in DIRECTIONS for f in range(3) if not (d["id"] == 3 and f == 2)]
    write_json(OUT / "annotations/estimates/wave.json", {**base, "sequence": "wave", "layer": "estimate", "poses": wave})
    approved = pose("wave", 0, 1, 0.0, provenance={"method": "manual", "independent": True, "source_method": "rig_projection"},
                    review={"status": "approved", "notes": "Fixture approval.", "updated_at": "2026-09-25T00:00:00Z"})
    for joint in approved["joints"].values():
        joint["status"] = "corrected"
    write_json(OUT / "annotations/corrections/wave.json",
               {**base, "sequence": "wave", "layer": "correction", "poses": [approved]})
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
