"""Generate the redistributable sample character: sprites, annotations, rig and ground truth.

Everything here is procedural (our own capsule figure), so it can ship with the
repository. It exists to prove the common layer works with no game adapter and
nothing borrowed from any game: a different canvas, four directions with no
mirroring, a camera tilted 30 degrees, a 13-joint left/right skeleton and a
12-bone rig. Because the true 3D poses are known, fits can be scored exactly.

    python examples/sample-character/make_sample.py [--out DIR]

Writes (default: next to this script):
  dataset.json, skeleton.json, frames/<seq>/d<dir>_f<frame>.png
  annotations/estimates/<seq>.json   truth + 1px noise, method "estimator" (independent)
  annotations/corrections/wave.json  exact truth for the south and east views, approved
  rig/sample-rig.json, rig/sample-mapping.json
  truth/<seq>.pose-solution.json     the poses the sprites were drawn from
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

if importlib.util.find_spec("spritemotion") is None:
    _init = REPO / "common" / "__init__.py"
    _spec = importlib.util.spec_from_file_location("spritemotion", _init, submodule_search_locations=[str(_init.parent)])
    sys.modules["spritemotion"] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(sys.modules["spritemotion"])

import numpy as np  # noqa: E402

from spritemotion.fitting.camera import AffineOrthographicCamera, direction_rotations  # noqa: E402
from spritemotion.fitting.mapping import RigMapping  # noqa: E402
from spritemotion.fitting.rig import Bone, Rig, basis_matrix, quat_from_rotvec  # noqa: E402
from spritemotion.jsonio import write_json  # noqa: E402
from spritemotion.poses.annotations import AnnotationSet  # noqa: E402
from spritemotion.sprites.dataset import Dataset, frame_id  # noqa: E402
from spritemotion.sprites.images import fingerprint, opaque_bounds, save_png  # noqa: E402

DATASET_ID = "examples/sample-character"
WIDTH, HEIGHT, ANCHOR = 160, 192, (80, 170)
SCALE, TILT = 70.0, math.radians(30)
CAMERA = [[SCALE, 0.0, 0.0], [0.0, -SCALE * math.sin(TILT), -SCALE * math.cos(TILT)]]
DIRECTIONS = [{"id": 0, "name": "south", "facing": [0, -1]}, {"id": 1, "name": "east", "facing": [1, 0]},
              {"id": 2, "name": "north", "facing": [0, 1]}, {"id": 3, "name": "west", "facing": [-1, 0]}]
SEQUENCES = [("wave", "Wave (right hand)", 6), ("walk", "Walk in place", 6)]
NOISE_PX = 1.0

# name, parent, head, tail, draw radius, colour
BONES = [
    ("hips", None, (0, 0, 0.95), (0, 0, 1.10), 0.12, (70, 80, 140)),
    ("spine", "hips", (0, 0, 1.10), (0, 0, 1.45), 0.13, (60, 100, 170)),
    ("neck", "spine", (0, 0, 1.45), (0, 0, 1.55), 0.05, (225, 185, 150)),
    ("head", "neck", (0, 0, 1.55), (0, 0, 1.78), 0.11, (235, 195, 160)),
    ("upper_arm.L", "spine", (0.20, 0, 1.42), (0.22, 0, 1.12), 0.045, (60, 100, 170)),
    ("forearm.L", "upper_arm.L", (0.22, 0, 1.12), (0.23, 0, 0.86), 0.04, (225, 185, 150)),
    ("upper_arm.R", "spine", (-0.20, 0, 1.42), (-0.22, 0, 1.12), 0.045, (60, 100, 170)),
    ("forearm.R", "upper_arm.R", (-0.22, 0, 1.12), (-0.23, 0, 0.86), 0.04, (225, 185, 150)),
    ("thigh.L", "hips", (0.10, 0, 0.95), (0.10, 0, 0.52), 0.065, (95, 75, 55)),
    ("shin.L", "thigh.L", (0.10, 0, 0.52), (0.10, 0, 0.08), 0.055, (95, 75, 55)),
    ("thigh.R", "hips", (-0.10, 0, 0.95), (-0.10, 0, 0.52), 0.065, (95, 75, 55)),
    ("shin.R", "thigh.R", (-0.10, 0, 0.52), (-0.10, 0, 0.08), 0.055, (95, 75, 55)),
]
JOINTS = {  # skeleton joint -> point on the rig (the mapping file says the same)
    "head": {"bone": "head", "at": 0.5}, "neck": {"bone": "neck", "at": 0}, "pelvis": {"bone": "hips", "at": 0},
    "left_shoulder": {"bone": "upper_arm.L", "at": 0}, "left_elbow": {"bone": "forearm.L", "at": 0},
    "left_hand": {"bone": "forearm.L", "at": 1},
    "right_shoulder": {"bone": "upper_arm.R", "at": 0}, "right_elbow": {"bone": "forearm.R", "at": 0},
    "right_hand": {"bone": "forearm.R", "at": 1},
    "left_knee": {"bone": "shin.L", "at": 0}, "left_foot": {"bone": "shin.L", "at": 1},
    "right_knee": {"bone": "shin.R", "at": 0}, "right_foot": {"bone": "shin.R", "at": 1},
}


def rest_matrix(head, tail) -> np.ndarray:
    """Blender-style rest matrix: bone along local +y, roll chosen so local x is as close to world x as possible."""
    head, tail = np.asarray(head, float), np.asarray(tail, float)
    y = (tail - head) / np.linalg.norm(tail - head)
    ref = np.array([1.0, 0, 0]) if abs(y[0]) < 0.9 else np.array([0, 1.0, 0])
    x = ref - ref.dot(y) * y
    x /= np.linalg.norm(x)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x, y, np.cross(x, y), head
    return m


def build_rig() -> Rig:
    names = [b[0] for b in BONES]
    return Rig([Bone(n, names.index(p) if p else -1, rest_matrix(h, t), float(np.linalg.norm(np.subtract(t, h))))
                for n, p, h, t, _, _ in BONES], name="sample-rig")


def true_pose(sequence: str, f: int, count: int) -> dict[str, dict]:
    """Local basis per bone (rotation vector in bone space, degrees) for one frame."""
    t = 2 * math.pi * f / count
    r = {}
    if sequence == "wave":
        r["upper_arm.R"] = (0, 0, 145 + 8 * math.sin(t))     # abduct the right arm overhead
        r["forearm.R"] = (0, 0, 35 * math.sin(t))             # wave at the elbow
        r["upper_arm.L"] = (0, 0, -8)
        r["spine"] = (0, 0, 5 * math.sin(t))
        r["head"] = (10 * math.sin(t + 1), 0, 0)
        loc = (0, 0, 0)
    else:
        swing = 28 * math.sin(t)
        r["thigh.L"], r["thigh.R"] = (-swing, 0, 0), (swing, 0, 0)
        r["shin.L"] = (max(0.0, 40 * math.sin(t + 1.2)), 0, 0)
        r["shin.R"] = (max(0.0, -40 * math.sin(t + 1.2)), 0, 0)
        r["upper_arm.L"], r["upper_arm.R"] = (swing * 0.8, 0, -6), (-swing * 0.8, 0, 6)
        r["forearm.L"], r["forearm.R"] = (-20, 0, 0), (-20, 0, 0)
        r["spine"] = (4, 8 * math.sin(t), 0)
        loc = (0, 0.03 * abs(math.cos(t)), 0)   # hips bob (the hips' local y is world up)
    bones = {n: {"rotation_quaternion": quat_from_rotvec(np.radians(v)).round(6).tolist()} for n, v in r.items()}
    bones.setdefault("hips", {"rotation_quaternion": [1.0, 0.0, 0.0, 0.0]})["location"] = list(loc)
    return bones


def to_basis(bones: dict) -> dict[str, np.ndarray]:
    return {n: basis_matrix(np.asarray(b["rotation_quaternion"]), np.asarray(b["location"]) if "location" in b else None)
            for n, b in bones.items()}


def draw(rig: Rig, matrices, camera: AffineOrthographicCamera, rotation: np.ndarray) -> np.ndarray:
    """Capsule figure, far parts first. Radii are scaled by the camera's horizontal scale."""
    from PIL import Image, ImageDraw  # lazy: build_blend.py reads BONES from Blender's Python, which lacks Pillow
    toward_viewer = camera.view_direction()
    parts = []
    for name, _, _, _, radius, colour in BONES:
        a, b = (rotation @ rig.bone_point(matrices, name, at) for at in (0.0, 1.0))
        depth = float(((a + b) / 2) @ toward_viewer)
        parts.append((depth, name, camera.project(a), camera.project(b), radius * SCALE, colour))
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    for _, name, a, b, radius, colour in sorted(parts, key=lambda p: p[0]):
        fill = colour + (255,)
        if name == "head":
            c = (a + b) / 2
            pen.ellipse([c[0] - radius, c[1] - radius * 1.15, c[0] + radius, c[1] + radius * 1.15], fill=fill)
            continue
        pen.line([tuple(a), tuple(b)], fill=fill, width=max(1, round(2 * radius)))
        for p in (a, b):
            pen.ellipse([p[0] - radius, p[1] - radius, p[0] + radius, p[1] + radius], fill=fill)
    return np.array(image)


def skeleton_doc() -> dict:
    side = lambda s, parts: [f"{s}_{p}" for p in parts]  # noqa: E731
    return {
        "schema": "spritemotion.skeleton", "schema_version": 1, "id": "stick-13", "title": "Sample stick figure, 13 joints",
        "description": "Anatomical left/right names: this sample's views never hide which side a limb is.",
        "joints": [{"name": n, "label": n.replace("_", " ").capitalize()} for n in JOINTS],
        "chains": [
            {"name": "spine", "label": "Spine", "color": "#ffd166", "joints": ["head", "neck", "pelvis"]},
            {"name": "left_arm", "label": "Left arm", "color": "#06d6a0", "joints": side("left", ["shoulder", "elbow", "hand"])},
            {"name": "right_arm", "label": "Right arm", "color": "#ef476f", "joints": side("right", ["shoulder", "elbow", "hand"])},
            {"name": "left_leg", "label": "Left leg", "color": "#118ab2", "joints": ["pelvis", "left_knee", "left_foot"]},
            {"name": "right_leg", "label": "Right leg", "color": "#f78c6b", "joints": ["pelvis", "right_knee", "right_foot"]},
        ],
        "inferred_connections": [["neck", "left_shoulder"], ["neck", "right_shoulder"]],
        "symmetric_pairs": [[f"left_{p}", f"right_{p}"] for p in ("shoulder", "elbow", "hand", "knee", "foot")],
    }


def mapping_doc() -> dict:
    return {"schema": "spritemotion.rig-mapping", "schema_version": 1, "skeleton": "stick-13", "rig": "sample-rig",
            "description": "Maps the sample skeleton onto the sample rig.", "sides": {},
            "joints": JOINTS,
            "fit": {"root_bone": "hips", "bones": [b[0] for b in BONES],
                    "limits_deg": {"default": 170, "spine": 45, "neck": 45, "head": 60}}}


def main(argv=None) -> Path:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=HERE)
    out = parser.parse_args(argv).out
    rig = build_rig()
    camera = AffineOrthographicCamera(np.array(CAMERA), np.array(ANCHOR, dtype=float))
    rotations = direction_rotations(DIRECTIONS, (0.0, -1.0))
    names = list(JOINTS)
    mapping = RigMapping.from_dict(mapping_doc())
    rng = np.random.default_rng(2026)

    write_json(out / "skeleton.json", skeleton_doc())
    rig.save(out / "rig" / "sample-rig.json")
    write_json(out / "rig" / "sample-mapping.json", mapping_doc())

    sequences, truth_points = [], {}
    for sid, title, count in SEQUENCES:
        truth = {"schema": "spritemotion.pose-solution", "schema_version": 1, "dataset_id": DATASET_ID,
                 "sequence": sid, "rig": rig.name, "source": {"tool": "make_sample.py", "ground_truth": True},
                 "frames": []}
        frames = []
        for f in range(count):
            bones = true_pose(sid, f, count)
            truth["frames"].append({"frame": f, "bones": bones})
            matrices = rig.pose_matrices(to_basis(bones))
            joints3d = mapping.joint_positions(rig, matrices, names)
            for d in DIRECTIONS:
                image = draw(rig, matrices, camera, rotations[d["id"]])
                rel = f"frames/{sid}/d{d['id']}_f{f:02d}.png"
                save_png(out / rel, image)
                frames.append({"frame_id": frame_id(DATASET_ID, sid, d["id"], f), "direction": d["id"], "frame": f,
                               "image": rel, "fingerprint": fingerprint(image), "bounds": opaque_bounds(image)})
                truth_points[(sid, d["id"], f)] = camera.project(joints3d @ rotations[d["id"]].T)
        frames.sort(key=lambda r: (r["direction"], r["frame"]))
        sequences.append({"id": sid, "name": title, "index": len(sequences), "frame_count": count,
                          "frame_duration_ms": 120, "frames": frames})
        write_json(out / "truth" / f"{sid}.pose-solution.json", truth)

    write_json(out / "dataset.json", {
        "schema": "spritemotion.dataset", "schema_version": 1, "dataset_id": DATASET_ID,
        "title": "Sample character (procedural)", "game": "examples", "character": "sample-character",
        "created_by": "examples/sample-character/make_sample.py",
        "canvas": {"width": WIDTH, "height": HEIGHT, "anchor": list(ANCHOR), "mirror_axis_x": (WIDTH - 1) / 2},
        "directions": DIRECTIONS,
        "camera": {"type": "affine_orthographic", "matrix": [[round(v, 6) for v in row] for row in CAMERA],
                   "anchor": list(ANCHOR), "notes": "70 px per unit, looking north and 30 degrees down."},
        "skeleton": "skeleton.json",
        "annotations": {"estimates": "annotations/estimates", "corrections": "annotations/corrections"},
        "sequences": sequences,
        "notes": "Procedural art generated by make_sample.py; free to redistribute with this repository.",
    })
    dataset = Dataset.load(out / "dataset.json")

    for sid, _, count in SEQUENCES:
        estimates = AnnotationSet.new(DATASET_ID, sid, "stick-13", "estimate", limb_identity="anatomical")
        corrections = AnnotationSet.new(DATASET_ID, sid, "stick-13", "correction", limb_identity="anatomical")
        for d in DIRECTIONS:
            for f in range(count):
                record = dataset.frame(sid, d["id"], f)
                exact = truth_points[(sid, d["id"], f)]
                noisy = exact + rng.normal(0.0, NOISE_PX, exact.shape)
                base = {"frame_id": record["frame_id"], "direction": d["id"], "frame": f,
                        "source_fingerprint": record["fingerprint"]}
                estimates.put({**base, "provenance": {
                    "method": "estimator", "independent": True, "estimator": "synthetic-noise",
                    "detail": f"Ground truth plus {NOISE_PX:g}px Gaussian noise; stands in for an image-based detector."},
                    "review": {"status": "unreviewed"},
                    "joints": {n: {"x": round(float(x), 3), "y": round(float(y), 3), "confidence": 0.6,
                                   "visibility": "unknown", "status": "estimate"} for n, (x, y) in zip(names, noisy)}})
                if sid == "wave" and d["name"] in ("south", "east"):
                    corrections.put({**base, "provenance": {"method": "manual", "independent": True,
                                                            "source_method": "estimator",
                                                            "detail": "Exact joints, standing in for a person's review."},
                                     "review": {"status": "approved", "reviewer": "make_sample.py",
                                                "updated_at": "2026-09-25T00:00:00Z"},
                                     "joints": {n: {"x": round(float(x), 3), "y": round(float(y), 3), "confidence": 1.0,
                                                    "visibility": "visible", "status": "corrected"}
                                                for n, (x, y) in zip(names, exact)}})
        estimates.save(dataset.annotation_path("estimate", sid))
        if len(corrections):
            corrections.save(dataset.annotation_path("correction", sid))
    print(f"Wrote {out / 'dataset.json'}")
    return out / "dataset.json"


if __name__ == "__main__":
    main()
