import copy

import pytest

from spritemotion.poses.annotations import (AnnotationSet, corrections_from_poses, effective_poses, is_meaningful_correction,
                                            match_to_dataset, mirror_pose, normalize_pose)
from spritemotion.poses.skeleton import Skeleton
from spritemotion.sprites.dataset import Dataset

from conftest import SAMPLE


def pose(direction=0, frame=0, x=10.0, status="unreviewed", method="estimator", independent=True):
    return {"frame_id": f"d/s/d{direction}/f{frame:02d}", "direction": direction, "frame": frame,
            "source_fingerprint": "sha256:x", "provenance": {"method": method, "independent": independent},
            "review": {"status": status}, "joints": {"a": {"x": x, "y": 5.0}, "b": {"x": x + 1, "y": 6.0}}}


def layer(name, *poses):
    result = AnnotationSet.new("d", "s", "sk", name)
    for p in poses:
        result.put(copy.deepcopy(p))
    return result


def test_corrections_win_over_estimates():
    merged = effective_poses(layer("estimate", pose(0, 0), pose(0, 1)), layer("correction", pose(0, 1, x=20)))
    assert merged[(0, 0)][0] == "estimate"
    assert merged[(0, 1)] == ("correction", merged[(0, 1)][1]) and merged[(0, 1)][1]["joints"]["a"]["x"] == 20


def test_godot_floats_are_normalised():
    p = pose()
    p["direction"], p["frame"] = 3.0, 5.0
    assert normalize_pose(p)["direction"] == 3 and isinstance(p["frame"], int)


def test_meaningful_corrections_only():
    base = pose()
    assert not is_meaningful_correction(copy.deepcopy(base), base)
    assert is_meaningful_correction(pose(x=10.5), base)
    assert is_meaningful_correction(pose(status="approved"), base)
    noted = pose()
    noted["review"]["notes"] = "left arm hidden"
    assert is_meaningful_correction(noted, base)
    kept = corrections_from_poses([copy.deepcopy(base), pose(0, 0, x=12)], layer("estimate", base),
                                  layer("estimate"))
    assert len(kept) == 1 and kept.layer == "correction"


def test_mirror_pose_keeps_chain_names_and_dependence():
    projected = pose(method="rig_projection", independent=False)
    mirrored = mirror_pose(projected, 127.5, 7, "fid", "sha256:y")
    assert mirrored["joints"]["a"]["x"] == 245.0
    assert mirrored["provenance"] == {"method": "mirrored", "independent": False, "source_method": "rig_projection",
                                      "mirrored_from": 0}
    swapped = mirror_pose(projected, 127.5, 7, "fid", "sha256:y", swap={"a": "b", "b": "a"})
    assert swapped["joints"]["b"]["x"] == 245.0


def test_match_reports_changed_pixels(tmp_path):
    dataset = Dataset.load(SAMPLE)
    skeleton = Skeleton.load(dataset.skeleton_path)
    estimates = AnnotationSet.load(dataset.annotation_path("estimate", "wave"))
    assert match_to_dataset(estimates, dataset, skeleton).ok
    estimates.get(1, 2)["source_fingerprint"] = "sha256:" + "0" * 64
    report = match_to_dataset(estimates, dataset, skeleton)
    assert report.mismatched == [(1, 2)] and not report.ok


def test_unknown_layer_rejected():
    with pytest.raises(ValueError):
        AnnotationSet.new("d", "s", "sk", "guess")
