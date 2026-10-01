"""Headless checks for the add-on's UO frame renderer.

    blender -b --factory-startup --python games/ultima-online/blender/tests/render_frames_test.py [-- --out DIR]

A skinned one-bone model carries a small marker cube off the ground origin. For both camera presets and all five
stored rows, the rendered marker must land where the SpriteMotion camera (canvas = anchor + M @ world) puts it,
the cropped frames' ClassicUO centres must reproduce the full-canvas position, and the overlay's pixels per unit
must equal the camera matrix's row norms. Exit code 0 when everything passes.
"""
import json
import math
import os
import sys
import tempfile

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import spritemotion_sheet_reference as addon  # noqa: E402

MARKER = (0.35, -0.2, 1.1)     # marker centre in model space (model faces -Y), world units = tiles
MARKER_SIZE = 0.08
failures = []


def check(ok, what):
    print(("PASS " if ok else "FAIL ") + what, flush=True)
    if not ok:
        failures.append(what)


def build_scene():
    scene = bpy.context.scene      # run with --factory-startup: clear the default cube, camera and light
    for o in list(scene.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    arm_data = bpy.data.armatures.new("Rig")
    arm = bpy.data.objects.new("Rig", arm_data)
    scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    bone = arm_data.edit_bones.new("root")
    bone.head, bone.tail = (0, 0, 0), (0, 0, 1)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.mesh.primitive_cube_add(size=MARKER_SIZE, location=MARKER)
    cube = bpy.context.active_object
    cube.name = "Marker"
    group = cube.vertex_groups.new(name="root")
    group.add(range(len(cube.data.vertices)), 1.0, "REPLACE")
    cube.parent = arm
    cube.modifiers.new("Armature", "ARMATURE").object = arm
    # a stage object that must stay out of the render
    bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, -0.01))
    bpy.context.active_object.name = "Stage"
    # UO_idle: one static key; UO_walk: the bone rises 0.5 over frames 1..11 (loop sampling never reaches 11)
    arm.animation_data_create()
    for name, keys in (("UO_idle", [(1, 0.0)]), ("UO_walk", [(1, 0.0), (11, 0.5)])):
        act = bpy.data.actions.new(name)
        arm.animation_data.action = act
        if hasattr(arm.animation_data, "action_slot") and getattr(act, "slots", None) is not None \
                and len(act.slots) == 0:
            pass
        pb = arm.pose.bones["root"]
        for frame, z in keys:
            pb.location = (0, z, 0)      # bone y = world z for this upright bone
            pb.keyframe_insert("location", frame=frame)
        for fc in addon._action_fcurves(act):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
        act.use_fake_user = True
    pb.location = (0, 0, 0)
    arm.animation_data.action = None
    return scene, arm


def centroid(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    a = np.flipud(px.reshape(h, w, 4))[..., 3]
    ys, xs = np.nonzero(a > 0.5)
    return (xs.mean(), ys.mean()) if len(xs) else None


def expected(matrix, anchor, facing, lift=0.0):
    yaw = addon.facing_yaw(facing)
    c, s = math.cos(yaw), math.sin(yaw)
    x, y, z = MARKER
    world = np.array([c * x - s * y, s * x + c * y, z + lift])
    return np.asarray(anchor, dtype=float) + np.asarray(matrix, dtype=float) @ world


def run(out_root):
    scene, arm = build_scene()
    s = scene.spritemotion_render
    s.model, s.look, s.body, s.actions = arm, "SILHOUETTE", 400, "0,4"
    for preset in ("GROUND_GRID", "DEPTH_0447"):
        s.camera = preset
        s.output_dir = os.path.join(out_root, preset)
        n, problems = addon.render_uo_frames(scene, s, log=print)
        check(n == 5 * (10 + 1), f"{preset}: 55 frames rendered (got {n})")
        check(not problems, f"{preset}: no problems {problems}")
        matrix = addon.CAMERA_PRESETS[preset][1]
        cam = scene.camera
        px = addon.camera_px(cam)
        check(np.allclose(px, [np.linalg.norm(matrix[0]), np.linalg.norm(matrix[1])]),
              f"{preset}: overlay px/unit {px} = camera row norms")
        worst = 0.0
        for d, (name, facing) in enumerate(addon.STORED_ROWS):
            for a, f, lift in ((4, 0, 0.0), (0, 0, 0.0), (0, 5, 0.25)):
                got = centroid(os.path.join(s.output_dir, "canvas", f"a{a:02d}_d{d}_f{f:02d}.png"))
                want = expected(matrix, (128, 192), facing, lift)
                err = float(np.hypot(*(np.asarray(got) - want))) if got else 1e9
                worst = max(worst, err)
            side = json.load(open(os.path.join(s.output_dir, "body_0400", f"a00_d{d}.json")))
            fr = side["frames"][5]
            png = os.path.join(s.output_dir, "body_0400", fr["png"])
            c = centroid(png)
            # ClassicUO: the crop's top-left sits at anchor - (center_x, height + center_y)
            full = (128 - fr["center_x"] + c[0], 192 - (fr["height"] + fr["center_y"]) + c[1])
            want = expected(matrix, (128, 192), facing, 0.25)
            check(math.hypot(full[0] - want[0], full[1] - want[1]) < 0.75 and len(side["frames"]) == 10
                  and side["direction"] == d and side["action"] == 0,
                  f"{preset} row {d} {name}: uopack centre places the crop at {tuple(round(float(v), 2) for v in full)}, expected {tuple(round(float(v), 2) for v in want)}")
        check(worst < 0.75, f"{preset}: marker within 0.75 px of the projection in every row (worst {worst:.3f})")
        manifest = json.load(open(os.path.join(s.output_dir, "render.json")))
        check(manifest["camera_matrix"] == matrix and manifest["anchor"] == [128, 192],
              f"{preset}: render.json records the camera")
    check(bpy.data.objects["Stage"].hide_render is False, "stage visibility restored")
    check(abs(arm.rotation_euler.z) < 1e-9 and arm.animation_data.action is None, "model turn and action restored")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[argv.index("--out") + 1] if "--out" in argv else tempfile.mkdtemp(prefix="sm_uo_render_")
    addon.register()
    try:
        run(out)
    finally:
        addon.unregister()
    print(f"{len(failures)} failure(s); renders in {out}", flush=True)
    sys.exit(1 if failures else 0)


main()
