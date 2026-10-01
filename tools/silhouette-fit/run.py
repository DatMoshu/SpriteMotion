"""Silhouette-constrained full pass: mask-snapped joint targets, then a fit that keeps bones inside the sprite.

    python tools/silhouette-fit/run.py prep --dataset DATASET --poses POSE_DIR [--corrections DIR] --out WORK
    python tools/silhouette-fit/run.py fit  --dataset WORK --rig RIG.json --mapping MAPPING.json --camera CAMERA.json
                                            --out SOLUTIONS_DIR [--sequences action-000,...] [--jobs 12]

prep copies DATASET (dataset.json, skeleton.json, frames/) to WORK and writes one estimate layer per sequence
from POSE_DIR (reviews reset to unreviewed when they come from another dataset; spritemotion.pose-annotations files of any dataset with the same sequences and frame layout;
fingerprints and frame ids are rewritten to DATASET's). Every joint that falls outside the frame's silhouette
(alpha > 0, eroded by 1 px) is moved to the nearest pixel inside it. --corrections is copied unchanged, and only
when its fingerprints match DATASET (approved human poses stay exactly as reviewed).

fit runs spritemotion's PoseFitter per sequence with one extra residual: the projected joints and points along
every skeleton edge are penalised by their distance outside the sprite silhouette of each view. Output is one
spritemotion.pose-solution per sequence plus fit-summary.json.

With --skin SKIN.npz (blender_pass.py skin) the model itself is matched to the sprite: sampled mesh vertices are
skinned in numpy and penalised for landing outside the silhouette, and sampled sprite pixels are penalised for being
far from any projected vertex (coverage). Every frame of a sequence is then fitted, including frames with no joint
marks (silhouette only), in all stored views. --seed SOLUTION uses that solution's first frame as the pose the prior
pulls toward (e.g. a fitted idle), instead of the rest pose.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from multiprocessing import Pool
from pathlib import Path

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):  # one BLAS thread per worker
    os.environ.setdefault(_var, "1")

import numpy as np  # noqa: E402
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from spritemotion.fitting.camera import direction_rotations  # noqa: E402
from spritemotion.fitting.fit import FitSettings, PoseFitter, ViewTarget  # noqa: E402
from spritemotion.fitting.mapping import RigMapping  # noqa: E402
from spritemotion.fitting.rig import Rig  # noqa: E402
from spritemotion.jsonio import read_json, write_json  # noqa: E402
from spritemotion.pipeline.fitjob import dataset_camera, read_solution, select_targets  # noqa: E402
from spritemotion.poses.skeleton import Skeleton  # noqa: E402
from spritemotion.sprites.dataset import Dataset  # noqa: E402

SAMPLES = (0.2, 0.4, 0.6, 0.8)


def silhouette(path: Path, mirror: bool = False) -> np.ndarray:
    mask = np.array(Image.open(path).convert("RGBA"))[:, :, 3] > 0
    return mask[:, ::-1] if mirror else mask


POSE_KEYS = {"frame_id", "direction", "frame", "source_fingerprint", "provenance", "review", "joints"}
SCHEMA_METHODS = {"manual", "mirrored", "rig_projection", "estimator", "interpolated", "imported"}


def normalise(pose: dict) -> None:
    """Fold experiment-only fields (e.g. the Astra mask pass) into provenance.detail so the layer validates."""
    dropped = {k: pose.pop(k) for k in list(pose) if k not in POSE_KEYS and k != "support"}
    pose.pop("support", None)
    provenance = pose.setdefault("provenance", {"method": "estimator", "independent": False})
    extra = {k: provenance.pop(k) for k in list(provenance) if k not in
             {"method", "independent", "source_method", "mirrored_from", "detail", "estimator", "parameters"}}
    if provenance.get("method") not in SCHEMA_METHODS:
        extra["original_method"] = provenance["method"]
        provenance["method"] = "estimator"
        provenance["estimator"] = extra["original_method"]
    extra.update({f"pose.{k}": v for k, v in dropped.items()})
    if extra:
        provenance["detail"] = (provenance.get("detail", "") + " | " + json.dumps(extra)).strip(" |")


# ---- prep ----
def prep(args) -> None:
    source = Path(args.dataset)
    work = Path(args.out)
    work.mkdir(parents=True, exist_ok=True)
    for name in ("dataset.json", "skeleton.json"):
        shutil.copy2(source / name, work / name)
    if not (work / "frames").exists():
        shutil.copytree(source / "frames", work / "frames")
    dataset = Dataset.load(work)
    (work / "annotations" / "estimates").mkdir(parents=True, exist_ok=True)
    stats = {"moved": 0, "joints": 0, "max_move_px": 0.0, "by_sequence": {}}
    for path in sorted(Path(args.poses).glob("action-*.json")):
        layer = read_json(path)
        sequence = layer["sequence"]
        foreign = layer.get("dataset_id") != dataset.dataset_id
        layer["dataset_id"] = dataset.dataset_id
        layer.pop("experiment", None)
        moved = 0
        for pose in layer["poses"]:
            normalise(pose)
            if foreign:  # a review of another body's drawing does not carry over
                pose["review"] = {"status": "unreviewed"}
            record = dataset.frame(sequence, pose["direction"], pose["frame"])
            pose["frame_id"], pose["source_fingerprint"] = record["frame_id"], record["fingerprint"]
            mask = silhouette(work / record["image"])
            inner = ndimage.binary_erosion(mask)
            if not inner.any():
                inner = mask
            _, (iy, ix) = ndimage.distance_transform_edt(~inner, return_indices=True)
            for joint in pose["joints"].values():
                stats["joints"] += 1
                px = int(np.clip(np.floor(joint["x"]), 0, mask.shape[1] - 1))
                py = int(np.clip(np.floor(joint["y"]), 0, mask.shape[0] - 1))
                if inner[py, px]:
                    continue
                nx, ny = ix[py, px] + 0.5, iy[py, px] + 0.5
                move = float(np.hypot(nx - joint["x"], ny - joint["y"]))
                joint["x"], joint["y"] = float(nx), float(ny)
                if move > 3.0:
                    joint["confidence"] = round(float(joint.get("confidence", 0.5)) * 0.7, 3)
                moved += 1
                stats["max_move_px"] = max(stats["max_move_px"], move)
            provenance = pose.setdefault("provenance", {})
            provenance["detail"] = (provenance.get("detail", "") +
                                    " | silhouette-fit prep: joints outside the eroded sprite silhouette moved to the "
                                    "nearest inside pixel.").strip(" |")
        stats["moved"] += moved
        stats["by_sequence"][sequence] = moved
        write_json(work / "annotations" / "estimates" / f"{sequence}.json", layer)
    if args.corrections:
        (work / "annotations" / "corrections").mkdir(parents=True, exist_ok=True)
        for path in sorted(Path(args.corrections).glob("action-*.json")):
            layer = read_json(path)
            ok = all(dataset.frame(layer["sequence"], p["direction"], p["frame"])["fingerprint"] ==
                     p["source_fingerprint"] for p in layer["poses"])
            if ok:
                shutil.copy2(path, work / "annotations" / "corrections" / path.name)
            print(f"corrections {path.name}: {'copied' if ok else 'skipped (fingerprints differ)'}")
    write_json(work / "prep-report.json", stats)
    print(f"prep: {stats['moved']} of {stats['joints']} joints moved inside the silhouette "
          f"(max {stats['max_move_px']:.1f}px) -> {work}")


# ---- fit ----
class SilhouetteFitter(PoseFitter):
    def __init__(self, *a, edges, mask_weight, skin=None, coverage_weight=0.0, **k):
        super().__init__(*a, **k)
        self.edges = np.array(edges)
        self.mask_weight = mask_weight
        self.fields: dict[int, np.ndarray] = {}
        self.cover: dict[int, np.ndarray] = {}
        self.coverage_weight = coverage_weight
        self.skin = None
        if skin is not None:
            names = [str(n) for n in skin["bones"]]
            to_rig = np.array([self.rig.index[n] for n in names])
            bone_index = to_rig[skin["bone_index"]]
            used = sorted(set(bone_index.ravel().tolist()))
            self.skin = {"rest": np.c_[skin["rest"], np.ones(len(skin["rest"]))], "weight": skin["weight"],
                         "slot": np.searchsorted(used, bone_index), "used": used,
                         "rest_inv": np.array([np.linalg.inv(self.rig.bones[i].rest) for i in used]),
                         "chain": self.rig.chain_to_root([self.rig.bones[i].name for i in used] + self.fit_bones)}

    def posed_vertices(self, basis: dict) -> np.ndarray:
        k = self.skin
        matrices = self.rig.pose_matrices(basis, k["chain"])
        skinning = np.array([matrices[i] for i in k["used"]]) @ k["rest_inv"]          # (B, 4, 4)
        out = np.zeros_like(k["rest"])
        for c in range(k["slot"].shape[1]):
            out += k["weight"][:, c, None] * np.einsum("nij,nj->ni", skinning[k["slot"][:, c]], k["rest"])
        return (out @ self.rig.world.T)[:, :3]

    def sample_points(self, joints: np.ndarray) -> np.ndarray:
        a, b = joints[self.edges[:, 0]], joints[self.edges[:, 1]]
        inner = [a + t * (b - a) for t in SAMPLES]
        return np.concatenate([joints] + inner)

    def outside(self, points2d: np.ndarray, field: np.ndarray) -> np.ndarray:
        return ndimage.map_coordinates(field, [points2d[:, 1] - 0.5, points2d[:, 0] - 0.5], order=1,
                                       mode="nearest")

    def _residual(self, x, seed, targets, previous):
        base = super()._residual(x, seed, targets, previous)
        if not self.fields:
            return base
        basis = self.basis(x, seed)
        points = self.sample_points(self.joints_world(basis))
        extra = [self.mask_weight * self.outside(self.project(points, t.direction), self.fields[t.direction])
                 for t in targets if t.direction in self.fields]
        if self.skin is not None:
            verts = self.posed_vertices(basis)
            n = len(verts)
            for t in targets:
                if t.direction not in self.fields:
                    continue
                projected = self.project(verts, t.direction)
                extra.append(self.mask_weight * np.sqrt(20.0 / n) * self.outside(projected, self.fields[t.direction]))
                if self.coverage_weight and t.direction in self.cover:
                    pixels = self.cover[t.direction]
                    gap, _ = cKDTree(projected).query(pixels)
                    extra.append(self.coverage_weight * np.sqrt(20.0 / len(pixels)) * np.maximum(gap - 1.0, 0.0))
        return np.concatenate([base] + extra)


def fit_one(job: dict) -> dict:
    started = time.time()
    dataset = Dataset.load(job["dataset"])
    sequence = job["sequence"]
    names = Skeleton.load(dataset.skeleton_path).joint_names
    skeleton = read_json(dataset.skeleton_path)
    index = {n: i for i, n in enumerate(names)}
    edges = [(index[c["joints"][i]], index[c["joints"][i + 1]]) for c in skeleton["chains"]
             for i in range(len(c["joints"]) - 1)] + [(index[a], index[b]) for a, b in skeleton["inferred_connections"]]
    rig = Rig.load(job["rig"])
    mapping = RigMapping.load(job["mapping"], job["swap_sides"])
    camera_data = read_json(job["camera"]) if job["camera"] else None
    projection = dataset_camera(dataset, camera_data)
    settings = FitSettings(floor_joints=list(names), max_iterations=job["iterations"], prior_weight=job["prior_weight"],
                           root_limit=job["root_limit"])
    skin = dict(np.load(job["skin"])) if job.get("skin") else None
    fitter = SilhouetteFitter(rig, mapping, projection, names, direction_rotations(dataset.directions, (0.0, -1.0)),
                              settings, edges=edges, mask_weight=job["mask_weight"], skin=skin,
                              coverage_weight=job.get("coverage_weight", 0.0))
    try:
        targets, selection = select_targets(dataset, sequence, names, "all", allow_dependent=True)
    except Exception:
        targets, selection = {}, {"mode": "all", "used": [], "mirrored_into_partner": []}
    if skin is not None:  # every frame, every stored view; frames without marks are fitted to the silhouette alone
        stored = [d["id"] for d in dataset.directions if dataset.mirror_source(d["id"]) is None]
        count = next(s["frame_count"] for s in dataset.sequences if s["id"] == sequence)
        for frame in range(count):
            have = {t.direction for t in targets.get(frame, [])}
            targets.setdefault(frame, []).extend(ViewTarget(d, np.full((len(names), 2), np.nan), np.zeros(len(names)))
                                                 for d in stored if d not in have)
    seed = next(iter(read_solution(job["seed"]).values())) if job.get("seed") else None
    rng = np.random.default_rng(0)
    mirrored = {(partner, frame): d for d, frame, partner in selection["mirrored_into_partner"]}
    solution = {"schema": "spritemotion.pose-solution", "schema_version": 1, "dataset_id": dataset.dataset_id,
                "sequence": sequence, "rig": rig.name, "camera": projection.to_dict(), "target_selection": selection,
                "settings": {**vars(settings), "mask_weight": job["mask_weight"], "edge_samples": list(SAMPLES),
                             "coverage_weight": job.get("coverage_weight", 0.0), "skin": job.get("skin"),
                             "seed": job.get("seed"), "method": "silhouette-fit"}, "frames": []}
    previous, px_err, outside = None, [], []
    for frame in sorted(targets):
        fitter.fields, fitter.cover = {}, {}
        for t in targets[frame]:
            src = mirrored.get((t.direction, frame))
            record = dataset.frame(sequence, src if src is not None else t.direction, frame)
            mask = silhouette(Path(job["dataset"]) / record["image"], mirror=src is not None)
            fitter.fields[t.direction] = ndimage.distance_transform_edt(~mask).astype(float)
            ys, xs = np.nonzero(mask)
            pick = rng.choice(len(xs), size=min(200, len(xs)), replace=False)
            fitter.cover[t.direction] = np.c_[xs[pick] + 0.5, ys[pick] + 0.5]
        fit = fitter.fit_frame(frame, targets[frame], seed, previous)
        previous = fit.x
        report = fit.report(names)
        points = fitter.sample_points(fitter.joints_world(fitter.basis(fit.x, seed or {})))
        report["outside_px"] = {str(t.direction): float(np.mean(fitter.outside(fitter.project(points, t.direction),
                                                                                fitter.fields[t.direction])))
                                for t in targets[frame]}
        solution["frames"].append({"frame": frame, "bones": fit.bones, "report": report})
        px_err += [v["mean_px"] for v in report["views"].values() if v["mean_px"] is not None]
        outside += list(report["outside_px"].values())
    write_json(Path(job["out"]) / f"{sequence}.json", solution)
    return {"sequence": sequence, "frames": len(targets), "mean_joint_px": float(np.mean(px_err)) if px_err else None,
            "mean_outside_px": float(np.mean(outside)), "seconds": round(time.time() - started, 1)}


def fit(args) -> None:
    dataset = Dataset.load(args.dataset)
    sequences = args.sequences.split(",") if args.sequences else [s["id"] for s in dataset.data["sequences"]]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [{"dataset": args.dataset, "sequence": s, "rig": args.rig, "mapping": args.mapping, "camera": args.camera,
             "swap_sides": args.swap_sides, "mask_weight": args.mask_weight, "iterations": args.iterations,
             "prior_weight": args.prior_weight, "root_limit": args.root_limit, "skin": args.skin,
             "coverage_weight": args.coverage_weight, "seed": args.seed,
             "out": str(out)} for s in sequences]
    results = []
    with Pool(args.jobs) as pool:
        for r in pool.imap_unordered(fit_one, jobs):
            results.append(r)
            joints = "-" if r["mean_joint_px"] is None else f"{r['mean_joint_px']:.2f}px"
            print(f"{r['sequence']}: {r['frames']} frames, joints {joints}, "
                  f"outside {r['mean_outside_px']:.3f}px, {r['seconds']}s", flush=True)
    summary_path = out / "fit-summary.json"
    if summary_path.exists():  # a resumed or partial run keeps the sequences fitted earlier
        done = {r["sequence"] for r in results}
        results += [r for r in read_json(summary_path)["sequences"] if r["sequence"] not in done]
    results.sort(key=lambda r: r["sequence"])
    write_json(out / "fit-summary.json", {"dataset": args.dataset, "rig": args.rig, "mapping": args.mapping,
                                          "camera": args.camera, "mask_weight": args.mask_weight,
                                          "sequences": results})


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prep")
    p.add_argument("--dataset", required=True)
    p.add_argument("--poses", required=True)
    p.add_argument("--corrections")
    p.add_argument("--out", required=True)
    f = sub.add_parser("fit")
    f.add_argument("--dataset", required=True)
    f.add_argument("--rig", required=True)
    f.add_argument("--mapping", required=True)
    f.add_argument("--camera")
    f.add_argument("--swap-sides", action="store_true")
    f.add_argument("--out", required=True)
    f.add_argument("--sequences")
    f.add_argument("--mask-weight", type=float, default=1.0)
    f.add_argument("--iterations", type=int, default=60)
    f.add_argument("--prior-weight", type=float, default=4.0, help="pull toward the rest pose (FitSettings default 4)")
    f.add_argument("--root-limit", type=float, default=1.0, help="max root offset per frame, world units")
    f.add_argument("--jobs", type=int, default=12)
    f.add_argument("--skin", help="blender_pass.py skin samples: fit the mesh to the silhouette, every frame")
    f.add_argument("--coverage-weight", type=float, default=1.0, help="with --skin: pull the model over sprite pixels")
    f.add_argument("--seed", help="pose solution whose first frame the prior pulls toward (default: rest pose)")
    args = parser.parse_args()
    {"prep": prep, "fit": fit}[args.command](args)


if __name__ == "__main__":
    main()
