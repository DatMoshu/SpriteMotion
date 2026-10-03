"""Blender: export the canonical UO body and fitted asset-pack items as glTF for the fit lab.

    blender -b --factory-startup --python export_blender.py -- <lab-items.json> <out dir> [--force]

body.glb   UO_Body skinned to UO_Rig, every UO action sampled at the UO frames (scene frame 1 + 3i).
items/     one .glb per item: the pack parts fitted by pack_fit (no lab adjustments: the lab applies those live),
           skinned to the same rig, with the pack palette.
manifest.json  camera, directions, actions and the item list (merged with an earlier export).
"""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from reference import write_reference
sys.path.insert(0, str(REPO / 'tools' / 'uo-content'))
import pack_fit  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
items_doc = json.loads(Path(argv[0]).read_text(encoding='utf-8'))
OUT = Path(argv[1]); FORCE = '--force' in argv
(OUT / 'items').mkdir(parents=True, exist_ok=True)
MODEL = Path(items_doc.get('model', REPO / 'workspace/ultima-online/canonical-model/model/UO_Body_0x190.blend'))
STEP = 3

bpy.ops.wm.open_mainfile(filepath=str(MODEL), load_ui=False, use_scripts=False)
original = bpy.data.texts.get('uo_original_frames.json')
if original:
    write_reference(json.loads(original.as_string()), OUT)
    print('FITLAB original sprite reference exported', flush=True)
rig, body = bpy.data.objects['UO_Rig'], bpy.data.objects['UO_Body']
cam = bpy.data.objects['UO_Camera']
CAMERA = {'matrix_world': [list(r) for r in cam.matrix_world], 'ortho_scale': cam.data.ortho_scale}
# The direction is a driver on the rig's Z rotation (-d*pi/4); the lab applies it, so export facing the camera.
rig.driver_remove('rotation_euler', 2)
rig.rotation_euler = (0, 0, 0); rig['uo_direction'] = 0
for o in list(bpy.data.objects):
    if o not in (rig, body): bpy.data.objects.remove(o, do_unlink=True)
acts = sorted((a for a in bpy.data.actions if 'uo_action' in a), key=lambda a: int(a['uo_action']))
scene = bpy.context.scene
manifest_path = OUT / 'manifest.json'
manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
manifest.update({
    'model': MODEL.name, 'rig': 'uo-model3d-v13', 'fps': scene.render.fps, 'frame_step': STEP,
    'camera': {**CAMERA,
               'resolution': [scene.render.resolution_x, scene.render.resolution_y], 'px_per_m': 36,
               'anchor_px': [68, 86], 'up': 'Z'},
    'directions': {'stored': 5, 'rotation_z_deg_per_step': -45, 'mirrored': {'5': 3, '6': 2, '7': 1}},
    'actions': [{'id': int(a['uo_action']), 'name': a.name, 'frames': int(a['uo_frames'])} for a in acts],
    'pack': items_doc.get('pack'), 'mapping': items_doc.get('mapping'),
})


def select_only(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects: o.hide_set(False); o.select_set(True)
    bpy.context.view_layer.objects.active = rig


def export(path, objects, animations):
    select_only(objects)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True, export_skins=True,
                              export_def_bones=False, export_animations=animations, export_morph=False,
                              export_materials='EXPORT' if not animations else 'NONE', export_yup=True,
                              **({'export_animation_mode': 'ACTIONS', 'export_force_sampling': True,
                                  'export_frame_step': STEP, 'export_anim_slide_to_zero': False} if animations else {}))


if FORCE or not (OUT / 'body.glb').exists():
    rig.animation_data.action = acts[0]
    for a in acts: a.use_fake_user = True
    export(OUT / 'body.glb', [rig, body], True)
    print('FITLAB body exported', flush=True)

pack = pack_fit.load_pack(items_doc['mapping'])
known = {i['id']: i for i in manifest.get('items', [])}
rig.animation_data.action = None
for n, item in enumerate(items_doc['items']):
    target = OUT / 'items' / f"{item['id']}.glb"
    if target.exists() and not FORCE and item['id'] in known:
        continue
    objects = pack_fit.import_fitted({'source_files': item['files'], 'palette': item.get('palette'),
                                      'pack_part': item['part']}, rig, pack, body)
    pack_fit.bind(objects, rig, False)
    totals = {}
    for o in objects:
        names = {g.index: g.name for g in o.vertex_groups}
        for v in o.data.vertices:
            for g in v.groups: totals[names[g.group]] = totals.get(names[g.group], 0) + g.weight
    export(target, [rig] + objects, False)
    known[item['id']] = {k: item[k] for k in ('id', 'slot', 'part', 'family') if k in item} | {
        'file': f"items/{item['id']}.glb", 'dominant_bone': max(totals, key=totals.get),
        'vertices': sum(len(o.data.vertices) for o in objects)}
    for o in objects:
        mesh = o.data; bpy.data.objects.remove(o, do_unlink=True); bpy.data.meshes.remove(mesh)
    for block in (bpy.data.materials, bpy.data.images):
        for x in list(block):
            if x.users == 0: block.remove(x)
    print(f"FITLAB item {n + 1}/{len(items_doc['items'])} {item['id']}", flush=True)
    manifest['items'] = sorted(known.values(), key=lambda i: (i.get('slot', ''), i['id']))
    manifest_path.write_text(json.dumps(manifest, indent=1))
manifest['items'] = sorted(known.values(), key=lambda i: (i.get('slot', ''), i['id']))
manifest_path.write_text(json.dumps(manifest, indent=1))
print('FITLAB done', len(manifest['items']), 'items', flush=True)
