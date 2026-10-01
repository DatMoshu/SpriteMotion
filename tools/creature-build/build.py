"""Reshape a CC4 base into a creature: per-bone length/thickness, uniform scale, optional second head.

    blender -b --factory-startup --python tools/creature-build/build.py -- --config games/ultima-online/models/ettin-build.json
        --save workspace/ultima-online/ettin/Ettin_Base.blend

Config (JSON): base_fbx, armature, scale, head_extend_cm, bones {"CC_Base_{side}_Thigh": {"length": 1.1,
"thickness": 1.6}, ...} ({side} expands to L and R), optional second_head {bone, offset_m}.

Steps: import the FBX; extend the head bone tail (FBX stores no tails); scale the armature object; pose-scale each
listed bone (Y = length, X/Z = thickness; listed children ignore the parent's scale so factors don't compound,
twist/share helpers inherit theirs); bake the deformed meshes and apply the pose as the new rest pose. For a second
head, the head region of the body (vertices weighted to the head bone hierarchy) and the eye/teeth/tongue meshes are
copied onto a new bone beside the head, weighted to it with the remainder blended into the upper neck; then both
heads are moved apart by offset_m (head A to +X, anatomical left) and baked the same way.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HEAD_EXTRAS = ("CC_Base_Eye", "CC_Base_Teeth", "CC_Base_Tongue", "CC_Base_EyeOcclusion", "CC_Base_TearLine")


def args_after_dashes():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--save", required=True)
    return p.parse_args(argv)


def meshes(arm):
    return [o for o in bpy.data.objects if o.type == "MESH" and any(
        m.type == "ARMATURE" and m.object == arm for m in o.modifiers)]


def set_active(obj):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def bake_pose_as_rest(arm):
    """Apply every mesh's armature modifier (the posed shape), make the pose the rest pose, re-add the modifiers."""
    bpy.context.view_layer.update()
    for obj in meshes(arm):
        if obj.data.shape_keys:
            set_active(obj)
            bpy.ops.object.shape_key_remove(all=True)
        mod = next(m for m in obj.modifiers if m.type == "ARMATURE" and m.object == arm)
        name = mod.name
        set_active(obj)
        bpy.ops.object.modifier_move_to_index(modifier=name, index=0)
        bpy.ops.object.modifier_apply(modifier=name)
        new = obj.modifiers.new(name, "ARMATURE")
        new.object = arm
        new.use_vertex_groups = True
    set_active(arm)
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def expand(bones_cfg, arm):
    out = {}
    for pattern, f in bones_cfg.items():
        for side in (("L", "R") if "{side}" in pattern else ("",)):
            name = pattern.replace("{side}", side)
            if name in arm.pose.bones:
                out[name] = f
    return out


def head_hierarchy(arm, root="CC_Base_Head"):
    names, stack = set(), [arm.data.bones[root]]
    while stack:
        b = stack.pop()
        names.add(b.name)
        stack += list(b.children)
    return names


def second_head(arm, cfg):
    bone_b = cfg["bone"]
    head_names = head_hierarchy(arm)
    body = bpy.data.objects["CC_Base_Body"]
    # 1. copy the head region of the body
    set_active(body)
    bpy.ops.object.duplicate()
    copy = bpy.context.active_object
    copy.name = "Ettin_HeadB_Body"
    groups = {g.index: g.name for g in copy.vertex_groups}
    weight = {}
    for v in copy.data.vertices:
        weight[v.index] = sum(g.weight for g in v.groups if groups.get(g.group) in head_names)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for v in copy.data.vertices:
        v.select = weight[v.index] < 0.05
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.delete(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")
    kept = {}
    for v in copy.data.vertices:
        kept[v.index] = min(1.0, sum(g.weight for g in v.groups if groups.get(g.group) in head_names))
    copy.vertex_groups.clear()
    gb, gn = copy.vertex_groups.new(name=bone_b), copy.vertex_groups.new(name="CC_Base_NeckTwist02")
    for i, w in kept.items():
        gb.add([i], w, "REPLACE")
        if w < 1.0:
            gn.add([i], 1.0 - w, "REPLACE")
    # 2. copy eyes, teeth, tongue rigidly onto head B
    for name in HEAD_EXTRAS:
        src = bpy.data.objects.get(name)
        if src is None:
            continue
        set_active(src)
        bpy.ops.object.duplicate()
        dup = bpy.context.active_object
        dup.name = name + "_B"
        dup.vertex_groups.clear()
        g = dup.vertex_groups.new(name=bone_b)
        g.add([v.index for v in dup.data.vertices], 1.0, "REPLACE")
    # 3. the new bone, a copy of the head bone
    set_active(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    src = eb["CC_Base_Head"]
    nb = eb.new(bone_b)
    nb.head, nb.tail, nb.roll = src.head.copy(), src.tail.copy(), src.roll
    nb.parent = src.parent
    nb.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")
    # 4. move the heads apart in pose space and bake
    offset = cfg["offset_m"] / arm.matrix_world.to_scale().x
    bpy.ops.object.mode_set(mode="POSE")
    for name, sign in (("CC_Base_Head", 1.0), (bone_b, -1.0)):
        pb = arm.pose.bones[name]
        pb.matrix = Matrix.Translation(Vector((sign * offset, 0.0, 0.0))) @ pb.matrix
        bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode="OBJECT")
    bake_pose_as_rest(arm)


def main():
    args = args_after_dashes()
    cfg = json.loads(Path(args.config).read_text())
    root = Path(args.config).resolve()
    while not (root / "pyproject.toml").exists() and root.parent != root:
        root = root.parent
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(root / cfg["base_fbx"]), automatic_bone_orientation=False)
    arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    arm.name = cfg["armature"]
    if arm.animation_data:
        arm.animation_data.action = None
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)
    # head bone tail (FBX stores none)
    set_active(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    hb = arm.data.edit_bones["CC_Base_Head"]
    hb.tail = hb.head + (hb.tail - hb.head).normalized() * (cfg["head_extend_cm"] / 100.0 / arm.matrix_world.to_scale().z)
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.scale = arm.scale * cfg["scale"]
    bpy.context.view_layer.update()
    # proportions
    factors = expand(cfg["bones"], arm)
    for name in factors:
        arm.data.bones[name].inherit_scale = "NONE"
    for name, f in factors.items():
        pb = arm.pose.bones[name]
        pb.scale = (f["thickness"], f["length"], f["thickness"])
    bake_pose_as_rest(arm)
    for name in factors:
        arm.data.bones[name].inherit_scale = "FULL"
    if cfg.get("second_head"):
        second_head(arm, cfg["second_head"])
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
    body = bpy.data.objects["CC_Base_Body"]
    top = max((body.matrix_world @ v.co).z for v in body.data.vertices)
    lo = min((body.matrix_world @ v.co).z for v in body.data.vertices)
    arm.location.z -= lo          # shortened legs lift the body; stand it back on the ground
    bpy.context.view_layer.update()
    arm["spritemotion_build"] = json.dumps(cfg)
    print(f"Built {arm.name}: height {top - lo:.3f} m, feet moved from z {lo:.3f} to 0")
    Path(args.save).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()))
    print(f"Saved {args.save}")


if __name__ == "__main__":
    main()
