"""End to end on the procedural sample: generate -> validate -> fit -> score against the true 3D poses."""
import numpy as np
import pytest

from spritemotion.fitting.mapping import RigMapping
from spritemotion.fitting.rig import Rig
from spritemotion.pipeline.cli import main as cli
from spritemotion.pipeline.fitjob import fit_sequence, read_solution
from spritemotion.poses.annotations import AnnotationSet
from spritemotion.poses.skeleton import Skeleton
from spritemotion.sprites.dataset import Dataset

from conftest import SAMPLE, load_module

make_sample = load_module(SAMPLE / "make_sample.py", "make_sample_test")


def world_joints(dataset_dir, solution_path, frame):
    rig = Rig.load(dataset_dir / "rig" / "sample-rig.json")
    mapping = RigMapping.load(dataset_dir / "rig" / "sample-mapping.json")
    names = Skeleton.load(dataset_dir / "skeleton.json").joint_names
    return mapping.joint_positions(rig, rig.pose_matrices(read_solution(solution_path)[frame]), names)


def test_generator_reproduces_committed_sample(tmp_path):
    make_sample.main(["--out", str(tmp_path / "gen")])
    fresh, committed = Dataset.load(tmp_path / "gen"), Dataset.load(SAMPLE)
    assert [r["fingerprint"] for _, r in fresh.frames()] == [r["fingerprint"] for _, r in committed.frames()]
    for sid in ("wave", "walk"):
        assert (AnnotationSet.load(fresh.annotation_path("estimate", sid)).data["poses"]
                == AnnotationSet.load(committed.annotation_path("estimate", sid)).data["poses"])


def test_sample_validates():
    assert cli(["validate", str(SAMPLE)]) == 0


@pytest.mark.parametrize("mode, tolerance", [("approved", 0.02), ("independent", 0.02)])
def test_fit_recovers_true_poses(sample_copy, tmp_path, mode, tolerance):
    dataset = Dataset.load(sample_copy)
    out = tmp_path / f"wave-{mode}.json"
    solution = fit_sequence(dataset, "wave", Rig.load(sample_copy / "rig" / "sample-rig.json"),
                            RigMapping.load(sample_copy / "rig" / "sample-mapping.json"), out, mode=mode)
    views = 2 if mode == "approved" else 4
    assert all(len(f["report"]["views"]) == views for f in solution["frames"])
    for frame in solution["frames"]:
        # targets carry 1px noise in independent mode (expected mean residual ~1.25px)
        assert max(v["mean_px"] for v in frame["report"]["views"].values()) < (0.6 if mode == "approved" else 2.5)
        error = np.linalg.norm(world_joints(sample_copy, out, frame["frame"])
                               - world_joints(sample_copy, sample_copy / "truth" / "wave.pose-solution.json",
                                              frame["frame"]), axis=1)
        assert error.mean() < tolerance, f"frame {frame['frame']}: mean 3D joint error {error.mean():.3f}"


def test_fit_refuses_rig_projections_as_evidence(sample_copy, tmp_path):
    """A rig projection must not validate a fit of the same rig unless explicitly allowed."""
    dataset = Dataset.load(sample_copy)
    estimates = AnnotationSet.load(dataset.annotation_path("estimate", "walk"))
    for p in estimates.data["poses"]:
        p["provenance"] = {"method": "rig_projection", "independent": False}
    estimates.save()
    rig = Rig.load(sample_copy / "rig" / "sample-rig.json")
    mapping = RigMapping.load(sample_copy / "rig" / "sample-mapping.json")
    with pytest.raises(ValueError, match="dependent"):
        fit_sequence(dataset, "walk", rig, mapping, tmp_path / "walk.json", mode="all")
    solution = fit_sequence(dataset, "walk", rig, mapping, tmp_path / "walk.json", mode="all", allow_dependent=True)
    assert len(solution["target_selection"]["used"]) == 24


def test_changed_sprite_is_not_fitted(sample_copy, tmp_path):
    dataset = Dataset.load(sample_copy)
    record = dataset.frame("wave", 1, 3)
    record["fingerprint"] = "sha256:" + "f" * 64      # as if the art had been redrawn
    dataset.save()
    dataset = Dataset.load(sample_copy)
    solution = fit_sequence(dataset, "wave", Rig.load(sample_copy / "rig" / "sample-rig.json"),
                            RigMapping.load(sample_copy / "rig" / "sample-mapping.json"), tmp_path / "w.json")
    assert solution["target_selection"]["skipped_mismatch"] == [[1, 3]]


def test_cli_loop(sample_copy, tmp_path):
    rig, mapping = sample_copy / "rig" / "sample-rig.json", sample_copy / "rig" / "sample-mapping.json"
    assert cli(["status", str(sample_copy)]) == 0
    assert cli(["fit", str(sample_copy), "--sequence", "wave", "--rig", str(rig), "--mapping", str(mapping),
                "--out", str(tmp_path / "fit.json"), "--frames", "0,1"]) == 0
    assert cli(["estimate-rig", str(sample_copy), "--sequence", "walk", "--rig", str(rig), "--mapping", str(mapping),
                "--poses", str(sample_copy / "truth" / "walk.pose-solution.json")]) == 0
    walk = AnnotationSet.load(Dataset.load(sample_copy).annotation_path("estimate", "walk"))
    assert len(walk) == 24   # existing estimator poses are kept, not replaced by projections
    assert cli(["sheet", str(sample_copy), "--sequence", "wave", "--out", str(tmp_path / "sheet.png")]) == 0
