"""Asset-pack rest-pose adapter, driven by a spritemotion.asset-pack mapping. Runs inside Blender, never edits sources.

The mapping's aligned bones (those with an 'end') carry the fit: each chain is rotated onto its target-rig bone and
scaled to its length; keep_orientation bones (spine, head) are only moved. Every other bone, including a part's
dynamic bones, follows its nearest aligned ancestor. Format: docs/asset-packs.md.
"""
import json
from pathlib import Path
import bpy
from mathutils import Matrix, Vector


def load_pack(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def import_fitted(spec, rig, pack):
    bones = pack['bones']
    aligned = {name: b for name, b in bones.items() if 'end' in b}
    mapping = {name: b['target'] for name, b in aligned.items()}
    keep = {name for name, b in aligned.items() if b.get('keep_orientation')}
    fit = pack.get('fit', {})
    low, high = fit.get('scale_clamp', [.5, 1.8])
    missing_end = Vector(fit.get('missing_end_offset', [0, -.07, 0]))
    result = []
    for filename in spec['source_files']:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=filename)
        imported = set(bpy.data.objects)-before
        arm = next(o for o in imported if o.type == 'ARMATURE')
        arm.data.pose_position = 'REST'

        def resolve(name):
            bone = arm.data.bones.get(name)
            while bone and bone.name not in mapping: bone = bone.parent
            return bone.name if bone else pack.get('root_bone', next(iter(mapping)))
        transforms = {}
        for source, target in mapping.items():
            if source not in arm.data.bones: continue
            start = arm.matrix_world@arm.data.bones[source].head_local
            endname = aligned[source]['end']
            endpoint = (arm.matrix_world@arm.data.bones[endname].head_local) if endname and endname in arm.data.bones else start+missing_end
            dest = rig.data.bones[target]
            a = endpoint-start; b = dest.tail_local-dest.head_local
            # Keep torso/head vertical orientation; FBX bone roll is unrelated to anatomy.
            if source in keep:
                rotation = Matrix.Identity(4); scale = 1.0
            else:
                rotation = a.rotation_difference(b).to_matrix().to_4x4()
                scale = max(low, min(high, b.length/a.length))
            transforms[source] = Matrix.Translation(dest.head_local)@rotation@Matrix.Scale(scale, 4)@Matrix.Translation(-start)
        for ob in [o for o in imported if o.type == 'MESH']:
            # The base shape is the input; source morphs use the old coordinate system.
            if ob.data.shape_keys: ob.shape_key_clear()
            groups = {g.index: resolve(g.name) for g in ob.vertex_groups}
            weights = []
            for v in ob.data.vertices:
                w = {}
                for g in v.groups:
                    key = groups[g.group]; w[key] = w.get(key, 0)+g.weight
                total = sum(w.values())
                if total <= 0: raise ValueError(f'Unweighted {pack["id"]} vertex: {ob.name}')
                point = ob.matrix_world@v.co
                v.co = sum((transforms[k]@point*(x/total) for k, x in w.items()), Vector())
                merged = {}
                for k, x in w.items(): merged[mapping[k]] = merged.get(mapping[k], 0)+x/total
                weights.append(merged)
            ob.parent = None; ob.matrix_parent_inverse = Matrix.Identity(4); ob.matrix_world = Matrix.Identity(4)
            ob.modifiers.clear(); ob.vertex_groups.clear()
            for name in sorted({n for w in weights for n in w}): ob.vertex_groups.new(name=name)
            for i, w in enumerate(weights):
                for name, value in w.items(): ob.vertex_groups[name].add([i], value, 'REPLACE')
            if spec.get('palette'):
                # Source UVs index the pack's palette texture; pack it into the editable scene.
                mat = bpy.data.materials.new(f'{pack["title"]} palette'); mat.use_nodes = True
                nt = mat.node_tree; tex = nt.nodes.new('ShaderNodeTexImage')
                tex.image = bpy.data.images.load(spec['palette'], check_existing=True); tex.image.pack(); tex.interpolation = 'Closest'
                principled = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
                nt.links.new(tex.outputs['Color'], principled.inputs['Base Color'])
                ob.data.materials.clear(); ob.data.materials.append(mat)
            result.append(ob)
        for ob in imported:
            if ob not in result: bpy.data.objects.remove(ob, do_unlink=True)
    # FBXs keep stale author-machine texture references; the packed palette replaces them.
    for image in list(bpy.data.images):
        if image.source == 'FILE' and not image.packed_file and image.filepath and not Path(bpy.path.abspath(image.filepath)).exists():
            bpy.data.images.remove(image)
    return result


def bind(objects, rig, rigid=False):
    if rigid:
        for o in objects:
            totals = {g.index: 0. for g in o.vertex_groups}
            for v in o.data.vertices:
                for g in v.groups: totals[g.group] += g.weight
            anchor = o.vertex_groups[max(totals, key=totals.get)].name
            o.vertex_groups.clear()
            o.vertex_groups.new(name=anchor).add(list(range(len(o.data.vertices))), 1., 'REPLACE')
        # Independent helper bones copy position/rotation only: animated source scale cannot deform metal.
        names = {g.name for o in objects for g in o.vertex_groups}
        bpy.ops.object.select_all(action='DESELECT'); rig.hide_set(False); rig.select_set(True); bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')
        for name in names:
            b = rig.data.edit_bones.new('rigid_'+name); b.matrix = rig.data.edit_bones[name].matrix.copy(); b.length = rig.data.edit_bones[name].length
        bpy.ops.object.mode_set(mode='OBJECT')
        for name in names:
            pb = rig.pose.bones['rigid_'+name]
            for kind in ('COPY_LOCATION', 'COPY_ROTATION'):
                c = pb.constraints.new(kind); c.target = rig; c.subtarget = name; c.target_space = 'POSE'; c.owner_space = 'POSE'
        for o in objects:
            for g in o.vertex_groups: g.name = 'rigid_'+g.name
    for o in objects:
        o.parent = rig; o.matrix_parent_inverse = Matrix.Identity(4); mod = o.modifiers.new('UO equipment animation', 'ARMATURE'); mod.object = rig


def hide_body_under(body, objects, outward=.02, inward=.01):
    """CC4-style hide-under-clothes: delete body faces whose centre, cast along its normal from `inward` inside,
    reaches an item within inward+outward metres (rest pose). Same rule as the fit lab. Returns the face count."""
    import bmesh
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    trees = [(BVHTree.FromObject(o, dg), o.matrix_world.inverted()) for o in objects]   # trees are object-local
    bm = bmesh.new(); bm.from_mesh(body.data)
    M = body.matrix_world; N = M.to_3x3().inverted().transposed()
    doomed = []
    for f in bm.faces:
        c = M @ f.calc_center_median(); n = (N @ f.normal).normalized()
        start = c - n*inward
        if any(t.ray_cast(inv @ start, (inv.to_3x3() @ n).normalized(), inward+outward)[0] is not None for t, inv in trees):
            doomed.append(f)
    bmesh.ops.delete(bm, geom=doomed, context='FACES_ONLY')
    bm.to_mesh(body.data); bm.free(); body.data.update()
    return len(doomed)
