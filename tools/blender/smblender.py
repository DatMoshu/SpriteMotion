"""Shared helpers for the SpriteMotion Blender scripts (run inside Blender's Python).

Every script is run headless the same way:

    blender -b <file.blend> --python tools/blender/<script>.py -- <script arguments>

The scripts import the repository's `spritemotion` package directly from
common/, so nothing has to be installed into Blender. Only numpy is needed,
and Blender ships it.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def bootstrap():
    """Make `import spritemotion` resolve to <repo>/common."""
    if "spritemotion" not in sys.modules:
        init = REPO_ROOT / "common" / "__init__.py"
        spec = importlib.util.spec_from_file_location("spritemotion", init,
                                                      submodule_search_locations=[str(init.parent)])
        module = importlib.util.module_from_spec(spec)
        sys.modules["spritemotion"] = module
        spec.loader.exec_module(module)
    return sys.modules["spritemotion"]


bootstrap()

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402


def parse_args(parser: argparse.ArgumentParser):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def armature(name: str | None = None):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "ARMATURE":
            raise SystemExit(f"No armature object named {name!r}.")
        return obj
    found = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    if len(found) != 1:
        raise SystemExit(f"Pass --armature; the scene has {len(found)} armatures: {[o.name for o in found]}.")
    return found[0]


def to_np(matrix) -> np.ndarray:
    return np.array([list(row) for row in matrix], dtype=float)


def rig_from_armature(obj):
    from spritemotion.fitting.rig import Rig
    bones = obj.data.bones
    ordered, seen = [], set()

    def visit(bone):
        if bone.name in seen:
            return
        if bone.parent:
            visit(bone.parent)
        seen.add(bone.name)
        ordered.append(bone)

    for bone in bones:
        visit(bone)
    return Rig.from_dict({
        "schema": "spritemotion.rig", "name": obj.name, "matrix_world": to_np(obj.matrix_world).tolist(),
        "bones": [{"name": b.name, "parent": b.parent.name if b.parent else None,
                   "matrix_local": to_np(b.matrix_local).tolist(), "length": b.length} for b in ordered]})


def get_basis(pose_bone) -> tuple[list[float], list[float]]:
    """(rotation quaternion wxyz, location) of a pose bone's local basis, whatever its rotation mode."""
    basis = pose_bone.matrix_basis
    return list(basis.to_quaternion()), list(basis.to_translation())


def set_basis(pose_bone, quaternion, location=None, key_frame: int | None = None):
    q = Quaternion(quaternion)
    mode = pose_bone.rotation_mode
    if mode == "QUATERNION":
        pose_bone.rotation_quaternion = q
    elif mode == "AXIS_ANGLE":
        axis, angle = q.to_axis_angle()
        pose_bone.rotation_axis_angle = (angle, *axis)
    else:
        pose_bone.rotation_euler = q.to_euler(mode, pose_bone.rotation_euler)
    if location is not None:
        pose_bone.location = Vector(location)
    if key_frame is not None:
        path = {"QUATERNION": "rotation_quaternion", "AXIS_ANGLE": "rotation_axis_angle"}.get(mode, "rotation_euler")
        pose_bone.keyframe_insert(path, frame=key_frame, group=pose_bone.name)
        if location is not None:
            pose_bone.keyframe_insert("location", frame=key_frame, group=pose_bone.name)


def blender_frame(source_frame: int, start: int, step: int) -> int:
    return start + source_frame * step


def setup_camera(scene, params: dict, name: str = "SpriteMotion Camera"):
    """Create or update an orthographic camera from rendering.ortho.blender_camera_params()."""
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        scene.collection.objects.link(cam)
    rotation = Matrix([list(r) for r in params["rotation"]])
    cam.matrix_world = Matrix.Translation(Vector(params["location"])) @ rotation.to_4x4()
    data = cam.data
    data.type = "ORTHO"
    data.ortho_scale = params["ortho_scale"]
    data.sensor_fit = params["sensor_fit"]
    data.shift_x = data.shift_y = 0.0
    data.clip_start, data.clip_end = params["clip_start"], params["clip_end"]
    render = scene.render
    render.resolution_x, render.resolution_y = params["resolution"]
    render.resolution_percentage = 100
    render.pixel_aspect_x, render.pixel_aspect_y = params["pixel_aspect_x"], params["pixel_aspect_y"]
    scene.camera = cam
    return cam


def dataset_camera(dataset, override: str | None = None):
    from spritemotion.fitting.camera import AffineOrthographicCamera
    from spritemotion.jsonio import read_json
    data = read_json(override) if override else dataset.data["camera"]
    return AffineOrthographicCamera.from_dict(data, dataset.canvas.get("anchor"))


def rotation_about_z(matrix3: np.ndarray) -> Matrix:
    return Matrix([list(r) for r in matrix3]).to_4x4()


def fcurve_owners(action) -> list:
    """(collection, fcurve) for every F-curve of an action: action.fcurves before
    Blender's slotted actions, the channelbags of its layers after (5.x)."""
    legacy = getattr(action, "fcurves", None)
    if legacy is not None and not getattr(action, "layers", None):
        return [(legacy, fc) for fc in legacy]
    out = []
    for layer in getattr(action, "layers", ()):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", ()):
                out.extend((bag.fcurves, fc) for fc in bag.fcurves)
    if not out and legacy is not None:
        out = [(legacy, fc) for fc in legacy]
    return out


def clear_bone_transform_curves(action, bones) -> int:
    """Remove the rotation/location F-curves of the named bones (so re-keying leaves no stale in-between keys)."""
    removed = 0
    for owner, fc in fcurve_owners(action):
        path = fc.data_path
        if path.startswith('pose.bones["') and path.split('"')[1] in bones and \
                path.rsplit(".", 1)[-1] in ("rotation_quaternion", "rotation_euler", "rotation_axis_angle", "location"):
            owner.remove(fc)
            removed += 1
    return removed


def new_versioned_action(obj, name: str, copy_from=None):
    """Give obj a fresh action called `name`, keeping any existing one as `name.vNNN`.

    Earlier passes stay in the file (with a fake user so Blender never drops
    them) and can be compared or reassigned from the Action editor. With
    copy_from (an action), the new action starts as a copy of it, so channels
    a fit does not touch (IK/FK switches, helper bones, custom properties)
    keep that animation's values.
    Returns (new action, name the previous action was kept under or None).
    """
    kept = None
    old = bpy.data.actions.get(name)
    if old is not None:
        taken = {a.name for a in bpy.data.actions}
        n = 1
        while f"{name}.v{n:03d}" in taken:
            n += 1
        kept = f"{name}.v{n:03d}"
        old.name = kept
        old.use_fake_user = True
    if copy_from is not None:
        action = copy_from.copy()
        action.name = name
    else:
        action = bpy.data.actions.new(name)
    action.use_fake_user = True
    data = obj.animation_data_create()
    data.action = action
    slots = getattr(action, "slots", None)       # Blender 4.4+: bind the copied slot, not a new one
    if slots and getattr(data, "action_slot", None) is None:
        data.action_slot = slots[0]
    return action, kept


def save_versioned(path, made_by: str, metrics: dict | None = None, note: str = "",
                   actions: dict | None = None) -> dict:
    """Save the open file to `path`, archiving whatever was there first (see spritemotion.pipeline.versions)."""
    from spritemotion.pipeline import versions
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    versions.archive_current(path)
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    entry = versions.record_save(path, made_by, metrics, note, actions)
    print(f"Saved {path} as version {entry['version']} (history: {versions.versions_dir(path).name}/)")
    return entry
