"""Blender side of the silhouette-fit full pass: build a fresh scene, key every solution, render every view.

    blender -b --factory-startup --python tools/silhouette-fit/blender_pass.py -- build
        --fbx MODEL.fbx --armature NAME [--head-bone CC_Base_Head --head-extend-cm 21.45] --save SCENE.blend
    blender -b --factory-startup SCENE.blend --python tools/silhouette-fit/blender_pass.py -- key
        --solutions DIR --dataset DATASET --mapping MAPPING --camera CAMERA.json --armature NAME [--frame-step 4]
    blender -b --factory-startup SCENE.blend --python tools/silhouette-fit/blender_pass.py -- render
        --dataset DATASET --camera CAMERA.json --armature NAME --out RENDERS [--frame-step 4]

key: one action per solution, named <sequence>_<name> (e.g. action-000_walk), keyed with apply_solution's
pose-space keying and measured against the dataset's effective annotations (keyed-report.json next to the
solutions). The scene is saved with spritemotion's version history. render: render_views for every keyed action
(--shaded: studio-lit textures instead of flat silhouettes).

    blender -b --factory-startup SCENE.blend --python tools/silhouette-fit/blender_pass.py -- skin
        --armature NAME --out SKIN.npz [--count 1500]
    blender -b --factory-startup SCENE.blend --python tools/silhouette-fit/blender_pass.py -- hands
        [--state fist] [--states hand-states.json] [--frame-step 4]

hands: keys a hand pose on the finger bones of every keyed action (constant over the action) and stores it on the
action as spritemotion_hand_A / _B. --states is {"<sequence>": {"A": state, "B": state}} (e.g. exported from the
hand review page) and overrides --state per action and hand. States: fist, grip, relaxed, open.
CC4 finger bones curl about local Z (+ on L, - on R); the thumb tucks about local X (-) on both sides.
"""
import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

TOOLS = Path(__file__).resolve().parents[1] / "blender"
sys.path.insert(0, str(TOOLS))
import smblender as sb  # noqa: E402

import bpy  # noqa: E402


def build(args):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=args.fbx, automatic_bone_orientation=False)
    arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    arm.name = args.armature
    if arm.animation_data:
        arm.animation_data.action = None
    for action in list(bpy.data.actions):          # the FBX bind-pose take
        bpy.data.actions.remove(action)
    if args.head_extend_cm:
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        bone = arm.data.edit_bones[args.head_bone]
        direction = (bone.tail - bone.head).normalized()
        bone.tail = bone.head + direction * (args.head_extend_cm / 100.0 / arm.matrix_world.to_scale().z)
        bpy.ops.object.mode_set(mode="OBJECT")
        print(f"{args.head_bone} tail extended to {arm.data.bones[args.head_bone].length:.2f} armature units")
    arm["spritemotion_source_fbx"] = args.fbx
    sb.save_versioned(args.save, f"silhouette-fit build from {Path(args.fbx).name}")


def key(args):
    import apply_solution
    from spritemotion.jsonio import read_json, write_json
    from spritemotion.sprites.dataset import Dataset
    names = {s["id"]: s["name"] for s in Dataset.load(args.dataset).sequences}
    obj = sb.armature(args.armature)
    reports, keyed = {}, {}
    for path in sorted(Path(args.solutions).glob("action-*.json")):
        solution = read_json(path)
        sequence = solution["sequence"]
        action_name = f"{sequence}_{names.get(sequence, '')}".rstrip("_")
        action, _ = sb.new_versioned_action(obj, action_name)
        action["spritemotion_sequence"] = sequence
        action["spritemotion_solution"] = path.name
        ns = SimpleNamespace(solution=str(path), frame_start=1, frame_step=args.frame_step, mapping=args.mapping,
                             swap_sides=False, dataset=args.dataset, camera=args.camera, model_forward="0,-1")
        apply_solution.key_pose_space(obj, solution, ns)
        count = len(solution["frames"])
        action.frame_range = (1, 1 + (count - 1) * args.frame_step) if count > 1 else (1, 2)
        report = apply_solution.measure(obj, solution, ns)
        reports[sequence] = {k: report.get(k) for k in ("mean_px", "max_px", "views", "max_fk_delta")}
        keyed[action_name] = {"solution": path.name, "sequence": sequence}
        print(f"{action_name}: {count} frames, keyed reprojection {report.get('mean_px', float('nan')):.2f}px "
              f"(max {report.get('max_px', float('nan')):.2f})", flush=True)
    obj.animation_data.action = None
    write_json(Path(args.solutions) / "keyed-report.json", reports)
    sb.save_versioned(bpy.data.filepath, f"silhouette-fit key {len(keyed)} actions", actions=keyed)


HAND_POSES = {  # degrees per segment 1..3: fingers about Z, thumb about X
    "fist": ((80, 95, 70), (20, 35, 45)),
    "grip": ((60, 75, 55), (15, 25, 30)),
    "relaxed": ((20, 25, 15), (5, 10, 10)),
    "open": ((0, 0, 0), (0, 0, 0)),
}


def pose_hand(obj, side, state, frame):
    import math
    fingers, thumb = HAND_POSES[state]
    sign = 1.0 if side == "L" else -1.0
    for name in ("Index", "Mid", "Ring", "Pinky"):
        for k, deg in zip((1, 2, 3), fingers):
            pb = obj.pose.bones.get(f"CC_Base_{side}_{name}{k}")
            if pb is None:
                continue
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = (0.0, 0.0, math.radians(deg) * sign)
            pb.keyframe_insert("rotation_euler", frame=frame, group=pb.name)
    for k, deg in zip((1, 2, 3), thumb):
        pb = obj.pose.bones.get(f"CC_Base_{side}_Thumb{k}")
        if pb is None:
            continue
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (-math.radians(deg), 0.0, 0.0)
        pb.keyframe_insert("rotation_euler", frame=frame, group=pb.name)


def hands(args):
    import json
    from spritemotion.jsonio import read_json
    states = read_json(args.states) if args.states else {}
    mapping = read_json(args.mapping) if args.mapping else {"sides": {"A": "L", "B": "R"}}
    sides = mapping.get("sides", {"A": "L", "B": "R"})
    obj = sb.armature(args.armature)
    data = obj.animation_data_create()
    done = {}
    for action in sorted(bpy.data.actions, key=lambda a: a.name):
        sequence = action.get("spritemotion_sequence")
        if not sequence:
            continue
        data.action = action
        slots = getattr(action, "slots", None)
        if slots and getattr(data, "action_slot", None) is None:
            data.action_slot = slots[0]
        per = states.get(sequence, {})
        for chain in ("A", "B"):
            state = per.get(chain, args.state)
            if state not in HAND_POSES:
                raise SystemExit(f"{sequence} hand {chain}: unknown state {state!r}; use one of {sorted(HAND_POSES)}")
            pose_hand(obj, sides[chain], state, int(action.frame_range[0]))
            action[f"spritemotion_hand_{chain}"] = state
        done[action.name] = {"A": action["spritemotion_hand_A"], "B": action["spritemotion_hand_B"]}
    data.action = None
    print(json.dumps(done))
    sb.save_versioned(bpy.data.filepath, f"silhouette-fit hands ({args.states or args.state})",
                      actions={k: {"hands": v} for k, v in done.items()})


def skin(args):
    """Sample skinned vertices (armature-space rest positions + top-4 bone weights) for numpy silhouette fitting."""
    import numpy as np
    obj = sb.armature(args.armature)
    bones = [b.name for b in obj.data.bones]
    index = {n: i for i, n in enumerate(bones)}
    to_arm = obj.matrix_world.inverted()
    points, idx, wts = [], [], []
    for mesh in bpy.data.objects:
        if mesh.type != "MESH" or not any(m.type == "ARMATURE" and m.object == obj for m in mesh.modifiers):
            continue
        groups = {g.index: g.name for g in mesh.vertex_groups}
        m = to_arm @ mesh.matrix_world
        for v in mesh.data.vertices:
            ws = sorted(((g.weight, index[groups[g.group]]) for g in v.groups
                         if groups.get(g.group) in index and g.weight > 0), reverse=True)[:4]
            total = sum(w for w, _ in ws)
            if total <= 0:
                continue
            points.append(tuple(m @ v.co))
            idx.append([b for _, b in ws] + [0] * (4 - len(ws)))
            wts.append([w / total for w, _ in ws] + [0.0] * (4 - len(ws)))
    points, idx, wts = np.array(points), np.array(idx), np.array(wts)
    rng = np.random.default_rng(0)
    pick = rng.choice(len(points), size=min(args.count, len(points)), replace=False)
    np.savez(args.out, rest=points[pick], bone_index=idx[pick], weight=wts[pick], bones=np.array(bones))
    print(f"Wrote {args.out}: {len(pick)} of {len(points)} skinned vertices")


def shaded_settings(scene):
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "TEXTURE"
    shading.show_cavity = False
    shading.show_object_outline = False
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    settings = scene.render.image_settings
    settings.file_format, settings.color_mode, settings.color_depth = "PNG", "RGBA", "8"


def render(args):
    import render_views
    for action in sorted(bpy.data.actions, key=lambda a: a.name):
        sequence = action.get("spritemotion_sequence")
        if not sequence:
            continue
        sys.argv = ["blender", "--", "--dataset", args.dataset, "--sequence", sequence, "--action", action.name,
                    "--armature", args.armature, "--camera", args.camera, "--out", args.out,
                    "--frame-start", "1", "--frame-step", str(args.frame_step)]
        if args.shaded:
            shaded_settings(bpy.context.scene)
            sys.argv.append("--keep-render-settings")
        render_views.main()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--fbx", required=True)
    b.add_argument("--armature", required=True)
    b.add_argument("--head-bone", default="CC_Base_Head")
    b.add_argument("--head-extend-cm", type=float)
    b.add_argument("--save", required=True)
    k = sub.add_parser("key")
    r = sub.add_parser("render")
    for p in (k, r):
        p.add_argument("--dataset", required=True)
        p.add_argument("--camera", required=True)
        p.add_argument("--armature", required=True)
        p.add_argument("--frame-step", type=int, default=4)
    k.add_argument("--solutions", required=True)
    k.add_argument("--mapping", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--shaded", action="store_true", help="studio-lit textures instead of flat silhouettes")
    h = sub.add_parser("hands")
    h.add_argument("--armature", required=True)
    h.add_argument("--state", default="fist", choices=sorted(HAND_POSES))
    h.add_argument("--states", help='JSON {"action-000": {"A": "fist", "B": "grip"}, ...}')
    h.add_argument("--mapping", help="rig mapping, for which rig side is chain A (default A -> L)")
    sk = sub.add_parser("skin")
    sk.add_argument("--armature", required=True)
    sk.add_argument("--out", required=True)
    sk.add_argument("--count", type=int, default=1500)
    args = sb.parse_args(parser)
    {"build": build, "key": key, "render": render, "hands": hands, "skin": skin}[args.command](args)


if __name__ == "__main__":
    main()
