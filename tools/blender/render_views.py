"""Render a model from every sprite direction with the dataset's camera, for silhouette comparison.

    blender -b model.blend --python tools/blender/render_views.py -- --dataset DATASET --sequence SEQ --out RENDERS
        [--frames 0,1,2] [--directions 3,4] [--armature NAME] [--action NAME] [--turn-object NAME] [--camera CAMERA.json]
        [--model-forward 0,-1] [--frame-start 1] [--frame-step 1] [--keep-render-settings]

Writes RENDERS/<sequence>/d<direction>_f<frame>.png (the layout `spritemotion compare`
and `spritemotion sheet --renders` read). Each direction is the model turned about
world z at the ground origin, exactly as the fitter models it; the object that is
turned (the armature by default) is restored afterwards. Mirrored-only views
(e.g. UO's N/NE/E) are not rendered: the game draws them by flipping their
partner, and compare/sheet do the same with the partner's render. By default renders are
flat, unlit, transparent Workbench silhouettes at the canvas size.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smblender as sb  # noqa: E402

import bpy  # noqa: E402


def silhouette_settings(scene):
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "FLAT"
    shading.color_type = "SINGLE"
    shading.single_color = (0.8, 0.8, 0.8)
    shading.show_object_outline = False
    shading.show_cavity = False
    scene.render.film_transparent = True
    scene.render.filter_size = 0.0  # hard edges: one render pixel = one sprite pixel
    scene.view_settings.view_transform = "Standard"
    settings = scene.render.image_settings
    settings.file_format = "PNG"
    settings.color_mode = "RGBA"
    settings.color_depth = "8"


def character_objects(armature) -> set:
    """The armature, everything parented under it, and every mesh it deforms."""
    keep = {armature}
    stack = [armature]
    while stack:
        for child in stack.pop().children:
            if child not in keep:
                keep.add(child)
                stack.append(child)
    for obj in bpy.context.scene.objects:
        if any(m.type == "ARMATURE" and m.object == armature for m in getattr(obj, "modifiers", ())):
            keep.add(obj)
    return keep


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--sequence", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--frames", help="comma-separated source frames (default: all)")
    parser.add_argument("--directions", help="comma-separated direction ids (default: every stored direction "
                                             "with a facing; mirrored-only views are flipped from their partner)")
    parser.add_argument("--armature")
    parser.add_argument("--action", help="action to render, e.g. fit_action-022 or an earlier fit_action-022.v001 "
                                         "(default: the armature's current action)")
    parser.add_argument("--turn-object", help="object turned per direction (default: the armature)")
    parser.add_argument("--camera", help="camera JSON overriding the dataset's")
    parser.add_argument("--model-forward", default="0,-1")
    parser.add_argument("--frame-start", type=int, default=1)
    parser.add_argument("--frame-step", type=int, default=1)
    parser.add_argument("--all-objects", action="store_true",
                        help="render every renderable object (default: only the character: the armature, its "
                             "children and the meshes it deforms, so stages and backdrops stay out of the silhouette)")
    parser.add_argument("--keep-render-settings", action="store_true",
                        help="use the scene's engine and look instead of flat silhouettes")
    args = sb.parse_args(parser)

    from spritemotion.fitting.camera import direction_rotations
    from spritemotion.rendering.compare import render_path
    from spritemotion.rendering.ortho import blender_camera_params
    from spritemotion.sprites.dataset import Dataset

    dataset = Dataset.load(args.dataset)
    sequence = next((s for s in dataset.sequences if s["id"] == args.sequence), None)
    if sequence is None:
        raise SystemExit(f"{args.sequence} is not in the dataset.")
    scene = bpy.context.scene
    camera = sb.dataset_camera(dataset, args.camera)
    sb.setup_camera(scene, blender_camera_params(camera, dataset.width, dataset.height))
    if not args.keep_render_settings:
        silhouette_settings(scene)

    if args.action:
        action = bpy.data.actions.get(args.action)
        if action is None:
            raise SystemExit(f"No action named {args.action!r}; actions: {sorted(a.name for a in bpy.data.actions)}")
        sb.armature(args.armature).animation_data_create().action = action
    turn = bpy.data.objects.get(args.turn_object) if args.turn_object else sb.armature(args.armature)
    if turn is None:
        raise SystemExit(f"No object named {args.turn_object!r}.")
    rotations = direction_rotations(dataset.directions, tuple(float(v) for v in args.model_forward.split(",")))
    mirrored = {d: dataset.mirror_source(d) for d in rotations if dataset.mirror_source(d) is not None}
    if args.directions:
        directions = [int(v) for v in args.directions.split(",")]
        asked = [d for d in directions if d in mirrored]
        if asked:
            raise SystemExit(f"Directions {asked} are mirrored-only views; render their partners "
                             f"{[mirrored[d] for d in asked]} instead (compare and sheet flip them).")
    else:
        directions = sorted(d for d in rotations if d not in mirrored)
    frames = [int(v) for v in args.frames.split(",")] if args.frames else list(range(sequence["frame_count"]))
    unknown = [d for d in directions if d not in rotations]
    if unknown:
        raise SystemExit(f"Directions without a facing vector: {unknown}")

    hidden = []
    if not args.all_objects:
        keep = character_objects(sb.armature(args.armature))
        hidden = [o for o in scene.objects if o not in keep and not o.hide_render]
        for o in hidden:
            o.hide_render = True
        if not any(o.type == "MESH" for o in keep):
            raise SystemExit("The armature deforms no mesh and has no mesh children; pass --all-objects.")
    original = turn.matrix_world.copy()
    count = 0
    try:
        for d in directions:
            turn.matrix_world = sb.rotation_about_z(rotations[d]) @ original
            for f in frames:
                scene.frame_set(sb.blender_frame(f, args.frame_start, args.frame_step))
                path = render_path(Path(args.out), args.sequence, d, f)
                path.parent.mkdir(parents=True, exist_ok=True)
                scene.render.filepath = str(path.resolve())
                bpy.ops.render.render(write_still=True)
                count += 1
    finally:
        turn.matrix_world = original
        for o in hidden:
            o.hide_render = False
    print(f"Rendered {count} views to {Path(args.out) / args.sequence}")


if __name__ == "__main__":
    main()
