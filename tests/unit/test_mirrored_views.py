"""Mirrored-only views (UO's N/NE/E) are the partner view flipped, not another camera angle.

The sample is turned into a game that stores east and draws west by flipping
it: west's art becomes east's art mirrored, west's annotations east's mirrored,
and west is marked `stored: false, mirror_of: 1`.
"""
import numpy as np

from spritemotion.fitting.mapping import RigMapping
from spritemotion.fitting.rig import Rig
from spritemotion.pipeline.fitjob import fit_sequence, read_solution, select_targets
from spritemotion.poses.annotations import AnnotationSet, effective_poses, load_layer, mirror_pose
from spritemotion.poses.skeleton import Skeleton
from spritemotion.rendering.compare import compare_dataset, render_path
from spritemotion.sprites.dataset import Dataset
from spritemotion.sprites.images import fingerprint, load_rgba, mirror_canvas, save_png

EAST, WEST = 1, 3


def make_mirror_game(root, drop_east_annotations: bool) -> Dataset:
    dataset = Dataset.load(root)
    west = dataset.direction(WEST)
    west.update(stored=False, mirror_of=EAST)
    for sequence, record in dataset.frames():
        if record["direction"] == WEST:
            east = dataset.frame(sequence, EAST, record["frame"])
            image = mirror_canvas(load_rgba(dataset.image_path(east)), dataset.mirror_axis_x)
            save_png(dataset.image_path(record), image)
            record["fingerprint"] = fingerprint(image)
            record["mirrored_from"] = EAST
    dataset.save()
    dataset = Dataset.load(root)
    for layer in ("estimate", "correction"):
        for sequence in ("wave", "walk"):
            path = dataset.annotation_path(layer, sequence)
            if not path.exists():
                continue
            annotations = AnnotationSet.load(path)
            for (direction, frame), pose in list(annotations.poses.items()):
                if direction == WEST:
                    annotations.remove(WEST, frame)
            for (direction, frame), pose in list(annotations.poses.items()):
                if direction == EAST:
                    record = dataset.frame(sequence, WEST, frame)
                    annotations.put(mirror_pose(pose, dataset.mirror_axis_x, WEST, record["frame_id"],
                                                record["fingerprint"]))
                    if drop_east_annotations:
                        annotations.remove(EAST, frame)
            annotations.save()
    return dataset


def test_mirrored_pose_is_flipped_into_its_partner(sample_copy):
    dataset = make_mirror_game(sample_copy, drop_east_annotations=True)
    names = Skeleton.load(dataset.skeleton_path).joint_names
    merged = effective_poses(load_layer(dataset, "estimate", "wave"), load_layer(dataset, "correction", "wave"))
    targets, report = select_targets(dataset, "wave", names, mode="independent")
    assert [d for d, f, p in report["mirrored_into_partner"]] == [WEST] * 6
    assert all(p == EAST for _, _, p in report["mirrored_into_partner"])
    for frame, views in targets.items():
        assert sorted(v.direction for v in views) == [0, EAST, 2]
        west = next(v for v in views if v.direction == EAST)
        pose = merged[(WEST, frame)][1]
        expected = [2 * dataset.mirror_axis_x - pose["joints"][n]["x"] for n in names]
        assert np.allclose(west.points[:, 0], expected)


def test_partner_annotation_wins_over_its_mirror(sample_copy):
    dataset = make_mirror_game(sample_copy, drop_east_annotations=False)
    names = Skeleton.load(dataset.skeleton_path).joint_names
    targets, report = select_targets(dataset, "wave", names, mode="independent")
    assert len(report["skipped_mirrored_view"]) == 6 and not report["mirrored_into_partner"]
    assert all(sorted(v.direction for v in views) == [0, EAST, 2] for views in targets.values())


def test_fit_through_a_mirrored_view_recovers_the_pose(sample_copy, tmp_path):
    dataset = make_mirror_game(sample_copy, drop_east_annotations=True)
    rig = Rig.load(sample_copy / "rig" / "sample-rig.json")
    mapping = RigMapping.load(sample_copy / "rig" / "sample-mapping.json")
    names = Skeleton.load(dataset.skeleton_path).joint_names
    out = tmp_path / "wave.json"
    fit_sequence(dataset, "wave", rig, mapping, out, mode="independent")
    fitted, truth = read_solution(out), read_solution(sample_copy / "truth" / "wave.pose-solution.json")
    for frame in fitted:
        error = np.linalg.norm(mapping.joint_positions(rig, rig.pose_matrices(fitted[frame]), names)
                               - mapping.joint_positions(rig, rig.pose_matrices(truth[frame]), names), axis=1)
        assert error.mean() < 0.03, f"frame {frame}: {error.mean():.3f}"


def test_compare_flips_the_partner_render(sample_copy, tmp_path):
    dataset = make_mirror_game(sample_copy, drop_east_annotations=True)
    renders = tmp_path / "renders"
    for sequence, record in dataset.frames("wave"):
        if record["direction"] != WEST:           # stored views only, as render_views does
            path = render_path(renders, sequence, record["direction"], record["frame"])
            path.parent.mkdir(parents=True, exist_ok=True)
            save_png(path, load_rgba(dataset.image_path(record)))
    summary = compare_dataset(dataset, renders, ["wave"])["summary"]
    assert summary["missing_renders"] == 0
    assert summary["by_direction"][str(WEST)] == 1.0
