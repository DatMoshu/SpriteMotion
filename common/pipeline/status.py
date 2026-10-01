"""Coverage and repository validation reports."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..jsonio import read_json
from ..poses.annotations import AnnotationSet, check_pose, effective_poses, load_layer, review_status
from ..poses.skeleton import Skeleton
from ..schemas import validate
from ..sprites.dataset import Dataset
from .games import GAMES_DIR


def dataset_status(dataset: Dataset) -> dict:
    rows = []
    for sequence in dataset.sequences:
        sid = sequence["id"]
        estimates = load_layer(dataset, "estimate", sid)
        corrections = load_layer(dataset, "correction", sid)
        merged = effective_poses(estimates, corrections)
        methods = Counter(pose.get("provenance", {}).get("method", "unknown") for _, pose in merged.values())
        reviews = Counter(review_status(pose) for _, pose in merged.values())
        mismatched = sum(1 for (d, f), (_, pose) in merged.items()
                         if pose["source_fingerprint"] != dataset.frame(sid, d, f)["fingerprint"])
        rows.append({"sequence": sid, "name": sequence["name"], "frames": len(sequence["frames"]),
                     "annotated": len(merged), "corrections": len(corrections) if corrections else 0,
                     "approved": reviews.get("approved", 0), "methods": dict(methods),
                     "fingerprint_mismatches": mismatched})
    totals = {k: sum(r[k] for r in rows) for k in ("frames", "annotated", "corrections", "approved",
                                                   "fingerprint_mismatches")}
    return {"dataset_id": dataset.dataset_id, "totals": totals, "sequences": rows}


def validate_repository(games_dir: Path = GAMES_DIR) -> list[str]:
    """Schema-check every game descriptor, skeleton and bundled annotation file."""
    errors: list[str] = []
    for game_file in sorted(games_dir.glob("*/game.json")):
        game = read_json(game_file)
        errors += [f"{game_file}: {e}" for e in validate(game, "spritemotion.game", required=True)]
        for character in game.get("characters", []):
            skeleton_path = game_file.parent / character["skeleton"]
            try:
                skeleton = Skeleton.load(skeleton_path)
            except Exception as exc:  # noqa: BLE001 - report every broken file
                errors.append(f"{skeleton_path}: {exc}")
                continue
            if not (game_file.parent / character["profile"]).exists():
                errors.append(f"{game_file}: missing profile {character['profile']}")
            bundle = game_file.parent / character.get("annotations", "")
            for path in sorted(bundle.glob("*/*.json")) if character.get("annotations") else []:
                try:
                    annotations = AnnotationSet.load(path)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{path}: {exc}")
                    continue
                expected = "estimate" if path.parent.name == "estimates" else "correction"
                if annotations.layer != expected:
                    errors.append(f"{path}: layer {annotations.layer!r} in folder {path.parent.name!r}")
                if annotations.data["skeleton"] != skeleton.id:
                    errors.append(f"{path}: skeleton {annotations.data['skeleton']!r} != {skeleton.id!r}")
                for key, pose in annotations.poses.items():
                    # Canvas bounds are checked against the dataset at apply time; here only joint sets.
                    issues = [i for i in check_pose(pose, skeleton, 10 ** 9, 10 ** 9)]
                    if issues:
                        errors.append(f"{path} {key}: {'; '.join(issues)}")
    return errors
