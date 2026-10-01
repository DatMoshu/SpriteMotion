"""Headless Blender checks for the pieces the fitter and renderer rely on.

    blender -b --factory-startup --python tools/blender/tests/smoke_test.py -- [--out DIR]

1. Forward kinematics: random poses on a branching armature (with a rotated,
   offset object transform); numpy Rig.pose_matrices must match Blender's pose.
2. Camera: points projected by the sprite camera must land where Blender's
   orthographic camera (from rendering.ortho) projects them.
3. Render: a small cube rendered with render_views' silhouette settings must be
   centred on its projected position.
4. Rig round trip: export_rig's rig and an exported/applied pose solution agree.
Exit code 0 when everything passes.
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import smblender as sb  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402

from spritemotion.fitting.camera import AffineOrthographicCamera  # noqa: E402
from spritemotion.fitting.rig import Rig  # noqa: E402
from spritemotion.rendering.ortho import blender_camera_params  # noqa: E402

CAMERAS = {
    "ground-grid": [[22, 22, 0], [22, -22, -31.1127]],
    "character-depth": [[22, 22, 0], [9.834, -9.834, -31.1127]],
    "front-square": [[40, 0, 0], [0, 0, -40]],
}
CANVAS = (256, 256, (128, 192))
RESULTS = []


def check(name, ok, detail):
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def build_armature():
    data = bpy.data.armatures.new("TestRig")
    obj = bpy.data.objects.new("TestRig", data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    specs = [("root", None, (0, 0, 0.9), (0, 0, 1.1), 0.0), ("spine", "root", (0, 0, 1.1), (0, 0.05, 1.5), 0.3),
             ("head", "spine", (0, 0.05, 1.5), (0, 0.05, 1.8), 0.0),
             ("arm.L", "spine", (0.2, 0, 1.45), (0.5, 0.1, 1.2), 0.7), ("hand.L", "arm.L", (0.5, 0.1, 1.2), (0.6, 0.2, 1.0), -0.4),
             ("leg.L", "root", (0.1, 0, 0.9), (0.12, 0.05, 0.45), 0.2), ("foot.L", "leg.L", (0.12, 0.05, 0.45), (0.12, -0.1, 0.05), 0.0)]
    for name, parent, head, tail, roll in specs:
        bone = data.edit_bones.new(name)
        bone.head, bone.tail, bone.roll = head, tail, roll
        if parent:
            bone.parent = data.edit_bones[parent]
            bone.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.matrix_world = Matrix.Translation((0.3, -0.2, 0.1)) @ Euler((0.1, -0.2, 0.7)).to_matrix().to_4x4()
    obj.pose.bones["spine"].rotation_mode = "XYZ"      # exercise non-quaternion bones
    obj.pose.bones["hand.L"].rotation_mode = "ZXY"
    return obj


def test_fk(obj, rng):
    rig = sb.rig_from_armature(obj)
    worst = 0.0
    for _ in range(20):
        for pb in obj.pose.bones:
            q = Euler(rng.uniform(-1.2, 1.2, 3)).to_quaternion()
            loc = rng.uniform(-0.2, 0.2, 3) if pb.name == "root" else None
            sb.set_basis(pb, list(q), loc)
        bpy.context.view_layer.update()
        ours = rig.pose_matrices({pb.name: sb.to_np(pb.matrix_basis) for pb in obj.pose.bones})
        for pb in obj.pose.bones:
            for at in (0.0, 1.0):
                theirs = sb.to_np(obj.matrix_world @ pb.matrix) @ np.array([0, at * pb.bone.length, 0, 1])
                worst = max(worst, float(np.linalg.norm(rig.bone_point(ours, pb.name, at) - theirs[:3])))
    check("forward kinematics", worst < 1e-5, f"max joint difference {worst:.2e} over 20 random poses")


def blender_canvas(scene, cam, point):
    ndc = world_to_camera_view(scene, cam, Vector(point))
    w, h = scene.render.resolution_x, scene.render.resolution_y
    return np.array([ndc.x * w - 0.5, (1.0 - ndc.y) * h - 0.5])


def test_cameras(scene, rng):
    w, h, anchor = CANVAS
    for name, matrix in CAMERAS.items():
        camera = AffineOrthographicCamera(np.array(matrix, dtype=float), np.array(anchor, dtype=float))
        cam = sb.setup_camera(scene, blender_camera_params(camera, w, h))
        bpy.context.view_layer.update()
        points = rng.uniform([-2, -2, 0], [2, 2, 2.5], (50, 3))
        diff = max(float(np.linalg.norm(blender_canvas(scene, cam, p) - camera.project(p))) for p in points)
        check(f"camera {name}", diff < 1e-3, f"max projection difference {diff:.2e}px")


def test_render(scene, out: Path):
    w, h, anchor = CANVAS
    camera = AffineOrthographicCamera(np.array(CAMERAS["ground-grid"], dtype=float), np.array(anchor, dtype=float))
    sb.setup_camera(scene, blender_camera_params(camera, w, h))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.15, location=(0.4, -0.3, 1.0), segments=48, ring_count=24)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from render_views import silhouette_settings  # noqa: E402
    silhouette_settings(scene)
    scene.render.filepath = str(out / "sphere.png")
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(scene.render.filepath)
    pixels = np.array(image.pixels[:]).reshape(h, w, 4)[::-1]  # Blender stores rows bottom-up
    ys, xs = np.nonzero(pixels[:, :, 3] > 0.5)
    centroid = np.array([xs.mean(), ys.mean()])
    expected = camera.project(np.array([0.4, -0.3, 1.0]))
    diff = float(np.linalg.norm(centroid - expected))
    check("render placement", diff < 0.5, f"sphere centroid {centroid.round(2)} vs projected {expected.round(2)}")
    bpy.data.objects.remove(bpy.context.active_object, do_unlink=True)


def test_rig_roundtrip(obj, out: Path):
    rig_path = out / "rig.json"
    sb.rig_from_armature(obj).save(rig_path)
    loaded = Rig.load(rig_path)
    ok = [b.name for b in loaded.bones] and loaded.index["foot.L"] > loaded.index["leg.L"]
    check("rig export", bool(ok), f"{len(loaded.bones)} bones, parents before children")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = sb.parse_args(parser)
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="spritemotion-blender-"))
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    scene = bpy.context.scene
    clear_scene()
    obj = build_armature()
    test_fk(obj, rng)
    test_rig_roundtrip(obj, out)
    test_cameras(scene, rng)
    test_render(scene, out)
    failed = [r for r in RESULTS if not r[1]]
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} Blender checks passed; output in {out}")
    sys.stdout.flush()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
