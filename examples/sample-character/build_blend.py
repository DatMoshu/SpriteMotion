"""Build the sample character's .blend: an armature from rig/sample-rig.json with capsule meshes on its bones.

    blender -b --factory-startup --python examples/sample-character/build_blend.py -- --out workspace/sample/sample.blend

The capsules use the radii make_sample.py drew the sprites with, so renders of
this model are directly comparable with the sample frames.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "tools" / "blender"))
import smblender as sb  # noqa: E402

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from spritemotion.fitting.rig import Rig  # noqa: E402


def sample_bones():
    """(name, radius) per bone, read from make_sample.py without running its main()."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_sample_defs", HERE / "make_sample.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {b[0]: b[4] for b in module.BONES}


def build_armature(rig: Rig):
    data = bpy.data.armatures.new(rig.name)
    obj = bpy.data.objects.new(rig.name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    for bone in rig.bones:
        edit = data.edit_bones.new(bone.name)
        rest = Matrix([list(r) for r in bone.rest])
        edit.head = rest.to_translation()
        edit.tail = rest @ Vector((0, bone.length, 0))
        edit.align_roll(rest.to_3x3() @ Vector((0, 0, 1)))
        if bone.parent >= 0:
            edit.parent = data.edit_bones[rig.bones[bone.parent].name]
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.matrix_world = Matrix([list(r) for r in rig.world])
    for pb in obj.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return obj


def add_capsule(armature, bone_name: str, radius: float, length: float):
    head = bone_name == "head"
    if head:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=32, ring_count=16)
        mesh = bpy.context.active_object
        mesh.scale = (1, 1.15, 1)  # make_sample draws the head as an ellipse 1.15x taller
        offset = Vector((0, length / 2, 0))
    else:
        bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, vertices=24)
        mesh = bpy.context.active_object
        mesh.rotation_euler = (1.5707963, 0, 0)  # cylinder along the bone's +y
        offset = Vector((0, length / 2, 0))
        for end in (0.0, length):
            bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=24, ring_count=12)
            cap = bpy.context.active_object
            cap.location = (0, 0, end - length / 2)  # the cylinder runs along its local z
            cap.parent = mesh
    mesh.name = f"capsule.{bone_name}"
    mesh.location = offset
    for obj in [mesh, *mesh.children]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    # bone parenting: the child's space is the bone's tail frame, so shift back by the bone length
    mesh.parent = armature
    mesh.parent_type = "BONE"
    mesh.parent_bone = bone_name
    mesh.location = offset - Vector((0, length, 0))
    return mesh


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    args = sb.parse_args(parser)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    rig = Rig.load(HERE / "rig" / "sample-rig.json")
    armature = build_armature(rig)
    radii = sample_bones()
    for bone in rig.bones:
        add_capsule(armature, bone.name, radii[bone.name], bone.length)
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
