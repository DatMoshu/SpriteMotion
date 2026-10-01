"""Migrate UO Roto / UO Armature Lab pose data into SpriteMotion annotation sets.

    python migrate_uo_roto.py --roto "<UO Roto folder>" --dataset <extracted body-400 dataset> [--out <bundle>]

Legacy format (per action, data/actions/action_NNN.json + corrections/action_NNN.json):
  frames[] {direction, frame, joints[{id, name, x, y, confidence, status}], user_confirmed,
            user_notes, mirrored_from, estimate_method, registration_scale, sprite, source_placement}

Nothing is guessed: every legacy pose is tied to the extracted frame only after
its sprite's silhouette and its recorded placement are checked against that
frame; the frame's fingerprint is then written into the annotation. Estimates
and user corrections go to separate layers, and rig projections are marked
independent=false. A verification pass rebuilds every effective legacy pose
from the new files and fails on any difference.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from spritemotion.jsonio import read_json, write_json
from spritemotion.poses import AnnotationSet, Skeleton, effective_poses
from spritemotion.sprites import Dataset, alpha_mask, load_rgba

LEGACY_JOINT_STATUS = {"user corrected": "corrected", "mirrored user correction": "mirrored_correction"}
TOLERANCE = 1e-3


def sequence_id(action: int) -> str:
    return f"action-{action:03d}"


def integral(value):
    return int(value) if isinstance(value, float) and value.is_integer() else value


def legacy_frames(doc: dict) -> dict:
    return {(int(r["direction"]), int(r["frame"])): r for r in doc["frames"]}


def joints_of(record: dict, names: list[str], layer: str, digits: int | None) -> dict:
    by_name = {j["name"]: j for j in record["joints"]}
    ids = sorted(int(j["id"]) for j in record["joints"])
    if [by_name[n]["name"] for n in names] != names or ids != list(range(1, len(names) + 1)):
        raise ValueError(f"Unexpected joint set in direction {record['direction']} frame {record['frame']}.")
    result = {}
    for name in names:
        j = by_name[name]
        x, y = float(j["x"]), float(j["y"])
        if digits is not None:
            x, y = round(x, digits), round(y, digits)
        status = LEGACY_JOINT_STATUS.get(j.get("status", ""), "estimate") if layer == "correction" else "estimate"
        result[name] = {"x": x, "y": y, "confidence": float(j.get("confidence", 0.5)), "visibility": "unknown",
                        "status": status}
    return result


def baseline_provenance(action: int, record: dict, doc: dict) -> dict:
    manual = action == 22
    method = "manual" if manual else "rig_projection"
    if record.get("mirrored_from") is not None:
        return {"method": "mirrored", "independent": manual, "source_method": method,
                "mirrored_from": int(record["mirrored_from"]),
                "detail": "Exact mirror (x' = 255 - x) of the stored-direction pose; chain IDs preserved."}
    provenance = {"method": method, "independent": manual, "detail": doc["method"]}
    if not manual:
        provenance["detail"] = (f"{record.get('estimate_method', 'rig projection')}: {doc['method']}")
        if "registration_scale" in record:
            provenance["parameters"] = {"registration_scale": record["registration_scale"]}
    return provenance


def check_frame(dataset: Dataset, roto: Path, sid: str, record: dict) -> dict:
    d, f = int(record["direction"]), int(record["frame"])
    target = dataset.frame(sid, d, f)
    legacy_mask = alpha_mask(load_rgba(roto / record["sprite"]))
    if not np.array_equal(legacy_mask, alpha_mask(load_rgba(dataset.image_path(target)))):
        raise ValueError(f"{sid} d{d} f{f}: legacy sprite silhouette differs from the extracted frame.")
    placement = record.get("source_placement")
    if placement:
        center = placement["encoded_center"]
        if ([center["x"], center["y"]] != target["source"]["center"] or placement["encoded_size"] != target["source"]["size"]
                or placement["stored_direction"] != target["source"]["stored_direction"]
                or bool(placement["mirrored"]) != target["source"]["mirrored"]):
            raise ValueError(f"{sid} d{d} f{f}: legacy placement metadata differs from the extracted frame.")
    return target


def migrate(roto: Path, dataset: Dataset, out: Path) -> dict:
    skeleton = Skeleton.load(dataset.skeleton_path)
    names = skeleton.joint_names
    catalog = read_json(roto / "data" / "catalog.json")
    report = {"source": f"UO Roto ({roto.name})", "dataset_id": dataset.dataset_id, "actions": [], "checks": {}}
    for entry in catalog:
        action, sid = int(entry["id"]), sequence_id(int(entry["id"]))
        doc = read_json(roto / entry["file"])
        if int(doc["body"]) != 400 or int(doc["action"]) != action:
            raise ValueError(f"{entry['file']} does not describe body 400 action {action}.")
        estimates = AnnotationSet.new(dataset.dataset_id, sid, skeleton.id, "estimate",
                                      limb_identity=doc["limb_identity"],
                                      migrated_from={"tool": "UO Roto", "file": entry["file"]})
        for (d, f), record in sorted(legacy_frames(doc).items()):
            target = check_frame(dataset, roto, sid, record)
            estimates.put({"frame_id": target["frame_id"], "direction": d, "frame": f,
                           "source_fingerprint": target["fingerprint"],
                           "provenance": baseline_provenance(action, record, doc),
                           "review": {"status": "unreviewed"},
                           "joints": joints_of(record, names, "estimate", 4)})
        estimates.save(out / "estimates" / f"{sid}.json")

        corrections_path = roto / "corrections" / f"action_{action:03d}.json"
        kept = 0
        if corrections_path.exists():
            legacy = read_json(corrections_path)
            if integral(legacy["action"]) != action:
                raise ValueError(f"{corrections_path} is for action {legacy['action']}.")
            corrections = AnnotationSet.new(dataset.dataset_id, sid, skeleton.id, "correction",
                                            limb_identity=legacy.get("limb_identity", doc["limb_identity"]),
                                            editor=legacy.get("editor", "UO Roto"),
                                            saved_at_utc=legacy.get("saved_at_utc", ""),
                                            migrated_from={"tool": "UO Roto", "file": f"corrections/{corrections_path.name}"})
            for (d, f), record in sorted(legacy_frames(legacy).items()):
                base = estimates.get(d, f)
                joints = joints_of(record, names, "correction", None)
                moved = any(abs(joints[n]["x"] - base["joints"][n]["x"]) > TOLERANCE or
                            abs(joints[n]["y"] - base["joints"][n]["y"]) > TOLERANCE for n in names)
                approved = bool(record.get("user_confirmed", False))
                notes = str(record.get("user_notes", "")).strip()
                if not (moved or approved or notes):
                    continue
                review = {"status": "approved" if approved else ("in_progress" if moved else "unreviewed")}
                if notes:
                    review["notes"] = notes
                if legacy.get("saved_at_utc"):
                    review["updated_at"] = legacy["saved_at_utc"] + "Z"
                provenance = {"method": "manual", "independent": approved or base["provenance"]["independent"],
                              "source_method": base["provenance"]["method"],
                              "detail": "Person-corrected in UO Roto on top of the estimate."}
                corrections.put({"frame_id": base["frame_id"], "direction": d, "frame": f,
                                 "source_fingerprint": base["source_fingerprint"], "provenance": provenance,
                                 "review": review, "joints": joints})
                kept += 1
            if kept:
                corrections.save(out / "corrections" / f"{sid}.json")
        report["actions"].append({"sequence": sid, "name": entry["name"], "estimates": len(estimates),
                                  "corrections": kept})
    report["checks"] = verify(roto, out, catalog, names)
    write_json(out / "MIGRATION.json", report)
    return report


def verify(roto: Path, out: Path, catalog: list, names: list[str]) -> dict:
    """Rebuild the effective legacy pose for every frame and compare to the new layers."""
    compared = approved = 0
    worst = 0.0
    for entry in catalog:
        action, sid = int(entry["id"]), sequence_id(int(entry["id"]))
        legacy = legacy_frames(read_json(roto / entry["file"]))
        corrections_path = roto / "corrections" / f"action_{action:03d}.json"
        legacy_corrections = legacy_frames(read_json(corrections_path)) if corrections_path.exists() else {}
        est = AnnotationSet.load(out / "estimates" / f"{sid}.json")
        corr_path = out / "corrections" / f"{sid}.json"
        merged = effective_poses(est, AnnotationSet.load(corr_path) if corr_path.exists() else None)
        if set(merged) != set(legacy):
            raise AssertionError(f"{sid}: pose set differs after migration.")
        for key, record in legacy.items():
            expected = legacy_corrections.get(key, record)
            got = merged[key][1]
            for j in expected["joints"]:
                delta = max(abs(float(j["x"]) - got["joints"][j["name"]]["x"]),
                            abs(float(j["y"]) - got["joints"][j["name"]]["y"]))
                worst = max(worst, delta)
                if delta > TOLERANCE:
                    raise AssertionError(f"{sid} {key} {j['name']}: moved by {delta} during migration.")
            if bool(expected.get("user_confirmed", False)) != (got.get("review", {}).get("status") == "approved"):
                raise AssertionError(f"{sid} {key}: approval flag lost.")
            if str(expected.get("user_notes", "")).strip() != got.get("review", {}).get("notes", ""):
                raise AssertionError(f"{sid} {key}: notes lost.")
            approved += got.get("review", {}).get("status") == "approved"
            compared += 1
    return {"poses_compared": compared, "approved": approved, "max_coordinate_delta": worst,
            "tolerance": TOLERANCE, "passed": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--roto", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "annotations" / "body-400")
    args = parser.parse_args(argv)
    report = migrate(args.roto, Dataset.load(args.dataset), args.out)
    print(json.dumps(report["checks"]))
    print("\n".join(f"{a['sequence']} {a['name']}: {a['estimates']} estimates, {a['corrections']} corrections"
                    for a in report["actions"] if a["corrections"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
