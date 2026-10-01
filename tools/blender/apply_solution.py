"""Key a spritemotion.pose-solution onto an armature and measure the keyed result.

    blender -b model.blend --python tools/blender/apply_solution.py -- --solution fit.json --save out.blend
        [--armature NAME] [--action NEW_ACTION_NAME [--copy-from ACTION]] [--frame-start 1] [--frame-step 1]
        [--mapping MAPPING [--swap-sides] [--dataset DATASET [--camera CAMERA.json] [--model-forward 0,-1]]]
        [--report report.json]

Source frame f is keyed at Blender frame start + f * step.

Each fitted bone is keyed so that its pose-space matrix is the one the fitter
solved for, parents first. The rig's own constraints on helper bones (e.g.
Rigify's follow/hinge parents of FK controls) are therefore resolved by
Blender instead of silently moving the result. --copy-from starts the new
action as a copy of an existing one, so channels the fit does not touch
(IK/FK switches, helper bones, properties) keep that animation's values; the
fitted bones' own rotation/location curves are replaced.

With --mapping the joint positions Blender evaluates after keying are compared
with the numpy forward kinematics the fitter uses; a disagreement means the rig
export is stale or the rig has constraints/drivers the fitter does not model.
With --dataset as well, Blender's joints are projected into every annotated
view and compared with the effective annotations: the real reprojection error
of what was keyed, not the solver's own estimate.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smblender as sb  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from spritemotion.jsonio import read_json, write_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--solution", required=True)
    parser.add_argument("--armature")
    parser.add_argument("--action", help="name for a new action (default: key into the current action)")
    parser.add_argument("--copy-from", help="with --action: start the new action as a copy of this action")
    parser.add_argument("--frame-start", type=int, default=1)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--mapping")
    parser.add_argument("--swap-sides", action="store_true")
    parser.add_argument("--dataset")
    parser.add_argument("--camera", help="camera JSON overriding the dataset's")
    parser.add_argument("--model-forward", default="0,-1")
    parser.add_argument("--report")
    parser.add_argument("--save", help="save the .blend here, keeping earlier versions (default: do not save)")
    parser.add_argument("--note", default="", help="note stored with the saved version")
    args = sb.parse_args(parser)

    solution = read_json(args.solution)
    if solution.get("schema") != "spritemotion.pose-solution":
        raise SystemExit(f"{args.solution} is not a spritemotion.pose-solution.")
    obj = sb.armature(args.armature)
    obj.animation_data_create()
    kept = None
    source = None
    if args.copy_from:
        if not args.action:
            raise SystemExit("--copy-from needs --action NAME for the new action.")
        source = bpy.data.actions.get(args.copy_from)
        if source is None:
            raise SystemExit(f"No action named {args.copy_from!r}.")
    if args.action:
        _, kept = sb.new_versioned_action(obj, args.action, source)
        if kept:
            print(f"Previous {args.action!r} kept as {kept!r}")
    if obj.animation_data.action is None:
        raise SystemExit("The armature has no action; pass --action NAME.")
    missing = sorted({b for fr in solution["frames"] for b in fr["bones"] if b not in obj.pose.bones})
    if missing:
        raise SystemExit(f"Armature lacks bones named in the solution: {missing}")

    fitted = sorted({b for fr in solution["frames"] for b in fr["bones"]})
    if source is not None:
        sb.clear_bone_transform_curves(obj.animation_data.action, set(fitted))
    key_pose_space(obj, solution, args)
    print(f"Keyed {len(solution['frames'])} frames into {obj.animation_data.action.name}")

    report = {}
    if args.mapping:
        report = measure(obj, solution, args)
        print(f"Blender vs fitter FK: max {report['max_fk_delta']:.6f} world units")
        if "mean_px" in report:
            print(f"Reprojection of keyed pose vs annotations: mean {report['mean_px']:.2f}px, "
                  f"max {report['max_px']:.2f}px over {report['views']} views")
        if args.report:
            write_json(args.report, report)
            print(f"Wrote {args.report}")
    if args.save:
        action = obj.animation_data.action.name
        metrics = {k: report[k] for k in ("max_fk_delta", "mean_px", "max_px", "views") if k in report}
        metrics = {f"{action}.{k}": v for k, v in metrics.items()}
        actions = {action: {"solution": Path(args.solution).name, "sequence": solution.get("sequence"),
                            **({"previous_kept_as": kept} if kept else {})}}
        sb.save_versioned(args.save, f"apply_solution {Path(args.solution).name} -> {action}", metrics,
                          args.note, actions)


def solver_matrices(rig, entry) -> dict:
    """Armature-space matrices of the pose the fitter solved (identity basis for bones it did not fit)."""
    from spritemotion.fitting.rig import basis_matrix
    return rig.pose_matrices({name: basis_matrix(np.asarray(b["rotation_quaternion"]),
                                                 np.asarray(b["location"]) if "location" in b else None)
                              for name, b in entry["bones"].items()})


def key_pose_space(obj, solution, args) -> None:
    rig = sb.rig_from_armature(obj)
    scene = bpy.context.scene
    for entry in solution["frames"]:
        key = sb.blender_frame(int(entry["frame"]), args.frame_start, args.frame_step)
        scene.frame_set(key)
        target = solver_matrices(rig, entry)
        for bone in rig.bones:                              # parents first
            if bone.name not in entry["bones"]:
                continue
            pb = obj.pose.bones[bone.name]
            pb.matrix = sb.Matrix(target[rig.index[bone.name]].tolist())
            bpy.context.view_layer.update()
            quaternion, location = sb.get_basis(pb)
            keep_location = "location" in entry["bones"][bone.name] or not pb.bone.use_connect
            sb.set_basis(pb, quaternion, location if keep_location else None, key)


def measure(obj, solution, args) -> dict:
    from spritemotion.fitting.camera import direction_rotations
    from spritemotion.fitting.mapping import RigMapping
    mapping = RigMapping.load(args.mapping, args.swap_sides)
    rig = sb.rig_from_armature(obj)

    annotations = camera = rotations = None
    if args.dataset:
        from spritemotion.poses.annotations import effective_poses, load_layer
        from spritemotion.poses.skeleton import Skeleton
        from spritemotion.sprites.dataset import Dataset
        dataset = Dataset.load(args.dataset)
        names = Skeleton.load(dataset.skeleton_path).joint_names
        sequence = solution.get("sequence")
        merged = effective_poses(load_layer(dataset, "estimate", sequence), load_layer(dataset, "correction", sequence))
        annotations = {key: pose for key, (_, pose) in merged.items()}
        camera = sb.dataset_camera(dataset, args.camera)
        rotations = direction_rotations(dataset.directions, tuple(float(v) for v in args.model_forward.split(",")))
    else:
        names = sorted(mapping.joints)

    scene = bpy.context.scene
    frames, worst_fk, errors = [], 0.0, []
    for entry in solution["frames"]:
        f = int(entry["frame"])
        scene.frame_set(sb.blender_frame(f, args.frame_start, args.frame_step))
        blender = mapping.joint_positions(rig, {rig.index[pb.name]: sb.to_np(pb.matrix) for pb in obj.pose.bones},
                                          names)
        numpy_fk = mapping.joint_positions(rig, solver_matrices(rig, entry), names)
        fk_delta = float(np.max(np.linalg.norm(blender - numpy_fk, axis=1)))
        worst_fk = max(worst_fk, fk_delta)
        row = {"frame": f, "max_fk_delta": fk_delta, "views": {}}
        if annotations is not None:
            for (d, frame), pose in sorted(annotations.items()):
                partner = dataset.mirror_source(d)
                view = d if partner is None else partner   # a mirrored-only view is its partner, flipped
                if frame != f or view not in rotations:
                    continue
                projected = camera.project(blender @ rotations[view].T)
                if partner is not None:
                    projected[:, 0] = 2 * dataset.mirror_axis_x - projected[:, 0]
                target = np.array([[pose["joints"][n]["x"], pose["joints"][n]["y"]] for n in names])
                dist = np.linalg.norm(projected - target, axis=1)
                errors.extend(dist.tolist())
                row["views"][str(d)] = {"mean_px": float(dist.mean()), "max_px": float(dist.max()),
                                        "review": pose.get("review", {}).get("status", "unreviewed"),
                                        "method": pose.get("provenance", {}).get("method")}
        frames.append(row)
    report = {"solution": Path(args.solution).name, "rig": obj.name, "max_fk_delta": worst_fk, "frames": frames}
    if errors:
        report.update(mean_px=float(np.mean(errors)), max_px=float(np.max(errors)),
                      views=sum(len(r["views"]) for r in frames))
    return report


if __name__ == "__main__":
    main()
