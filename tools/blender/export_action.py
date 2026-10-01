"""Export an armature action as a spritemotion.pose-solution (seed poses for fitting).

Source frame f is read at Blender frame start + f * step.

    blender -b model.blend --python tools/blender/export_action.py -- --frames 12 --out seed.json
        [--armature NAME] [--action NAME] [--frame-start 1] [--frame-step 1] [--mapping MAPPING --swap-sides]

With --mapping only the bones the fitter moves are written (the root with its location).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smblender as sb  # noqa: E402

import bpy  # noqa: E402

from spritemotion.jsonio import write_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--frames", type=int, required=True, help="number of source frames")
    parser.add_argument("--armature")
    parser.add_argument("--action", help="action to assign before sampling (default: the current one)")
    parser.add_argument("--frame-start", type=int, default=1)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--mapping")
    parser.add_argument("--swap-sides", action="store_true")
    parser.add_argument("--sequence", default="")
    parser.add_argument("--dataset-id", default="")
    args = sb.parse_args(parser)

    obj = sb.armature(args.armature)
    if args.action:
        action = bpy.data.actions.get(args.action)
        if action is None:
            raise SystemExit(f"No action named {args.action!r}.")
        obj.animation_data_create().action = action
    bones = [pb.name for pb in obj.pose.bones]
    root = None
    if args.mapping:
        from spritemotion.fitting.mapping import RigMapping
        mapping = RigMapping.load(args.mapping, args.swap_sides)
        bones, root = mapping.fit_bones, mapping.root_bone
        missing = [b for b in bones if b not in obj.pose.bones]
        if missing:
            raise SystemExit(f"Armature lacks mapped bones: {missing}")

    scene = bpy.context.scene
    frames = []
    for f in range(args.frames):
        scene.frame_set(sb.blender_frame(f, args.frame_start, args.frame_step))
        entry = {}
        for name in bones:
            q, loc = sb.get_basis(obj.pose.bones[name])
            entry[name] = {"rotation_quaternion": [round(v, 6) for v in q]}
            if root is None or name == root:
                entry[name]["location"] = [round(v, 6) for v in loc]
        frames.append({"frame": f, "bones": entry})
    anim = obj.animation_data
    action = anim.action.name if anim and anim.action else None
    write_json(args.out, {"schema": "spritemotion.pose-solution", "schema_version": 1,
                          "dataset_id": args.dataset_id, "sequence": args.sequence, "rig": obj.name,
                          "source": {"tool": "export_action.py", "action": action, "frame_start": args.frame_start,
                                     "frame_step": args.frame_step},
                          "frames": frames})
    print(f"Wrote {args.out}: {len(frames)} frames, {len(bones)} bones, action {action}")


if __name__ == "__main__":
    main()
