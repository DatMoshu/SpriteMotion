"""Move annotations between a bundled set (in the repo) and a dataset (in the workspace).

apply:   bundle -> dataset. Only poses whose frame_id and fingerprint match the
         extracted frames are applied; everything else is reported, not guessed.
promote: dataset corrections -> bundle, after review, so they can be shared.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..jsonio import write_json
from ..poses.annotations import AnnotationSet, match_to_dataset
from ..poses.skeleton import Skeleton
from ..sprites.dataset import Dataset


@dataclass
class ApplyReport:
    sequences: dict = field(default_factory=dict)

    @property
    def mismatched(self) -> int:
        return sum(len(v.get(layer, {}).get("mismatched", [])) for v in self.sequences.values()
                   for layer in ("estimate", "correction"))

    def to_dict(self) -> dict:
        totals = {"applied": 0, "mismatched": 0, "unknown_frame": 0, "invalid": 0}
        for entry in self.sequences.values():
            for layer in ("estimate", "correction"):
                for key in totals:
                    value = entry.get(layer, {}).get(key, 0)
                    totals[key] += value if isinstance(value, int) else len(value)
        return {"totals": totals, "sequences": self.sequences}


def _filtered(source: AnnotationSet, dataset: Dataset, skeleton: Skeleton) -> tuple[AnnotationSet, dict]:
    report = match_to_dataset(source, dataset, skeleton)
    kept = AnnotationSet({k: v for k, v in source.data.items() if k != "poses"} | {"poses": []})
    kept._reindex()
    for key in report.matched:
        kept.put(source.poses[key])
    return kept, {"applied": len(report.matched),
                  "mismatched": [list(k) for k in report.mismatched],
                  "unknown_frame": [list(k) for k in report.unknown_frame],
                  "invalid": [[list(k), msg] for k, msg in report.invalid]}


def apply_bundle(dataset: Dataset, bundle: Path, overwrite_corrections: bool = False) -> ApplyReport:
    skeleton = Skeleton.load(dataset.skeleton_path)
    result = ApplyReport()
    sequence_ids = {s["id"] for s in dataset.sequences}
    for layer, folder in (("estimate", "estimates"), ("correction", "corrections")):
        for path in sorted((Path(bundle) / folder).glob("*.json")):
            source = AnnotationSet.load(path)
            if source.data["dataset_id"] != dataset.dataset_id:
                raise ValueError(f"{path} is for dataset {source.data['dataset_id']!r}, not {dataset.dataset_id!r}.")
            if source.sequence not in sequence_ids:
                result.sequences.setdefault(source.sequence, {})[layer] = {"skipped": "sequence not extracted"}
                continue
            kept, entry = _filtered(source, dataset, skeleton)
            target = dataset.annotation_path(layer, source.sequence)
            if layer == "correction" and target.exists() and not overwrite_corrections:
                entry = {"skipped": "local corrections exist; use --overwrite-corrections to replace (a .bak is kept)",
                         "available": entry["applied"]}
            elif len(kept):
                kept.save(target, backup=target.exists())
            result.sequences.setdefault(source.sequence, {})[layer] = entry
    write_json(dataset.root / "annotations" / "apply-report.json", result.to_dict())
    return result


def promote_corrections(dataset: Dataset, bundle: Path, sequences: list[str] | None = None) -> dict:
    """Copy reviewed workspace corrections into the bundle (fingerprints must match the dataset)."""
    skeleton = Skeleton.load(dataset.skeleton_path)
    out = {}
    for path in sorted(dataset.annotation_dir("correction").glob("*.json")):
        if path.name.endswith(".autosave.json"):
            continue
        source = AnnotationSet.load(path)
        if sequences and source.sequence not in sequences:
            continue
        report = match_to_dataset(source, dataset, skeleton)
        if not report.ok:
            out[source.sequence] = {"refused": report.summary()}
            continue
        target = Path(bundle) / "corrections" / path.name
        if target.exists():
            shutil.copy2(target, target.with_name(target.name + ".bak"))
        source.save(target)
        approved = sum(1 for p in source.poses.values() if p.get("review", {}).get("status") == "approved")
        out[source.sequence] = {"promoted": len(source), "approved": approved, "file": str(target)}
    return out
