"""Run inside Blender. Preserve the canonical rig and evaluate its native scale inheritance."""
import ast
import importlib.util
import json
import math
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector, Euler

spec = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
backend, job = Path(spec['backend']), Path(spec['job'])
bpy.ops.wm.open_mainfile(filepath=str(backend / 'model/UO_Body_0x190.blend'), load_ui=False, use_scripts=False)
bpy.context.preferences.filepaths.save_version = 0
rig, body = bpy.data.objects['UO_Rig'], bpy.data.objects['UO_Body']
# The rig was 108/112 bones (twist, toe, skirt and cloak chains) and is 54 since 2026-10-09: check the bones this file
# and the mappings use by name, not a count.
NEEDED_BONES = ('pelvis', 'spine', 'chest', 'neck', 'head', 'clavicle.L', 'clavicle.R', 'upper_arm.L', 'upper_arm.R',
                'forearm.L', 'forearm.R', 'hand.L', 'hand.R', 'thigh.L', 'thigh.R', 'shin.L', 'shin.R', 'foot.L', 'foot.R',
                'shield.L')
missing_bones = [name for name in NEEDED_BONES if name not in rig.data.bones]
if missing_bones or body.data.shape_keys:
    raise ValueError(f'Expected the UO_Model3D rig without corrective shape keys; missing bones: {missing_bones}')
rig.animation_data.action = None
rig['uo_direction'] = 0
rig.rotation_euler = (0, 0, 0)
rig.data.pose_position = 'REST'
bpy.context.view_layer.update()
# Remove only example clothing from this new in-memory scene, never from the original .blend.
col = bpy.data.collections.get('Clothing')
if col:
    for ob in list(col.all_objects):
        bpy.data.objects.remove(ob, do_unlink=True)
else:
    col = bpy.data.collections.new('Clothing')
    bpy.context.scene.collection.children.link(col)

def execute_external(name, overrides=None, injected=None):
    """Replace reviewed script settings structurally; no prompt text is executable code."""
    path = backend / 'pipeline' / name
    tree = ast.parse(path.read_text(encoding='utf-8'))
    if name == 'render_uo_layer.py':
        class Blocks(ast.NodeTransformer):
            def visit_For(self, node):
                self.generic_visit(node)
                if isinstance(node.target, ast.Name) and node.target.id == 'd' and ast.unparse(node.iter) == 'range(5)':
                    node.body[:0] = ast.parse('if _selected_blocks is not None and (a,d) not in _selected_blocks: continue').body
                    for index, child in enumerate(node.body):
                        if isinstance(child, ast.Expr) and ast.unparse(child) == 'rig.update_tag()':
                            node.body.insert(index+1, ast.parse('_fit_pose(a,d,globals())').body[0])
                            break
                return node
        tree = Blocks().visit(tree)
        # The 2026-10 renderer has its own 256x256 CANVAS with anchor (128,192); only older ones are padded here.
        native = any(isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'CANVAS' for n in tree.body)
        # Pad the native viewport, without changing pixels/metre or perspective.
        # Keep compressed source image decoding at its original 136x120 dimensions.
        class Canvas(ast.NodeTransformer):
            def visit_Constant(self, node):
                if type(node.value) is int and node.value in (120,136):
                    return ast.copy_location(ast.Constant(256),node)
                return node
        for node in [] if native else tree.body:
            if isinstance(node,ast.FunctionDef) and node.name in ('raster','body_occlusion'):
                Canvas().visit(node)
            if isinstance(node,ast.Assign):
                targets=ast.unparse(node.targets[0])
                if 'sc.render.resolution_x' in targets:
                    Canvas().visit(node)
            # Metadata written at the bottom of the reference renderer.
            if isinstance(node,ast.With) and 'meta.json' in ast.unparse(node):
                Canvas().visit(node)
            if isinstance(node,ast.If) and 'uo_horse_masks.json' in ast.unparse(node.test):
                for child in ast.walk(node):
                    if isinstance(child,ast.Assign) and any(isinstance(t,ast.Subscript) and
                        isinstance(t.value,ast.Name) and t.value.id=='HORSE_MASKS' for t in child.targets):
                        child.value=ast.parse('np.pad(bits.reshape(120,136).astype(bool), ((106,30),(60,60)))',mode='eval').body
        for node in [] if native else tree.body:
            if isinstance(node,ast.FunctionDef) and node.name=='original':
                for child in ast.walk(node):
                    if isinstance(child,ast.Return) and isinstance(child.value,ast.Call):
                        child.value=ast.parse('np.pad(np.frombuffer(zlib.decompress(base64.b64decode(v)), np.uint8).reshape(120,136,4), ((106,30),(60,60),(0,0)))',mode='eval').body
    overrides = overrides or {}
    replaced = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key in overrides:
                node.value = ast.parse(repr(overrides[key]), mode='eval').body
                replaced.add(key)
            if key == 'writer' and injected and 'writer' in injected:
                node.value = ast.Name(id='_external_writer', ctx=ast.Load())
    if replaced != set(overrides):
        raise ValueError(f'Backend settings changed: {set(overrides) - replaced}')
    env = {'__name__': '__main__', '__file__': str(path)}
    if injected:
        env.update(injected)
        env['_external_writer'] = injected.get('writer')
    exec(compile(ast.fix_missing_locations(tree), str(path), 'exec'), env)

def material(name, color, image=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    look = nt.nodes.new('ShaderNodeGroup')
    look.node_tree = bpy.data.node_groups['UO_Look']
    rgb = tuple(int(color[i:i+2],16)/255 for i in (1,3,5))
    # Input hex is sRGB; the shader consumes linear color.
    rgb = tuple(c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in rgb)
    look.inputs['Albedo'].default_value = (*rgb, 1)
    nt.links.new(look.outputs['Shader'], out.inputs['Surface'])
    if image:
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(str(image), check_existing=True)
        tex.image.pack()
        nt.links.new(tex.outputs['Color'], look.inputs['Albedo'])
    return mat

mat = material('SpriteMotion item', spec['color'], spec.get('asset') if spec['input_kind']=='image' else None)

def bounds(objects):
    points = np.array([tuple(o.matrix_world @ Vector(c)) for o in objects for c in o.bound_box])
    return points.min(0), points.max(0)

def region_bounds(names):
    groups = {g.index:g.name for g in body.vertex_groups}
    points = [body.matrix_world @ v.co for v in body.data.vertices
        if sum(g.weight for g in v.groups if groups[g.group] in names) > .45]
    p = np.array(points)
    return p.min(0), p.max(0)

def shell(part):
    # A fitted template is explicit geometry, not a claimed reconstruction of an image.
    sets = {'helm':['head'], 'chest':['chest','spine','clavicle.L','clavicle.R'],
        'arms':['upper_arm.L','upper_arm.R','forearm.L','forearm.R'],
        'gloves':['hand.L','hand.R'], 'legs':['pelvis','thigh.L','thigh.R','shin.L','shin.R'],
        'boots':['foot.L','foot.R','shin.L','shin.R']}
    names = sets.get(part, ['chest','spine','pelvis','thigh.L','thigh.R','upper_arm.L','upper_arm.R'])
    if part in ('cloak','skirt','robe'):
        template = bpy.data.objects.get('UO_Template_Cloak' if part=='cloak' else 'UO_Template_Skirt')
        if template and part != 'robe':
            ob = template.copy(); ob.data = template.data.copy()
            bpy.context.scene.collection.objects.link(ob)
            ob.hide_render = False; ob.hide_viewport = False; ob.hide_set(False)
            ob.modifiers.clear(); ob.vertex_groups.clear(); ob.parent = None
            return [ob]
    groups = {g.index:g.name for g in body.vertex_groups}
    keep = {v.index for v in body.data.vertices if sum(g.weight for g in v.groups
        if groups[g.group] in names or (part=='gloves' and groups[g.group].startswith('finger'))) > .45}
    if part == 'helm':
        lo, hi = region_bounds(['head'])
        # Open face toward -Y. Keep crown, back and side guards.
        keep = {i for i in keep if body.data.vertices[i].co.z > lo[2]+.65*(hi[2]-lo[2]) or
            body.data.vertices[i].co.y > (lo[1]+hi[1])/2 or
            abs(body.data.vertices[i].co.x-(lo[0]+hi[0])/2) > .36*(hi[0]-lo[0])}
    faces = [list(p.vertices) for p in body.data.polygons if all(i in keep for i in p.vertices)]
    used = sorted({i for f in faces for i in f})
    mapping = {v:i for i,v in enumerate(used)}
    vertices = [body.matrix_world @ (body.data.vertices[i].co + body.data.vertices[i].normal*.018) for i in used]
    me = bpy.data.meshes.new('Item shell')
    me.from_pydata(vertices, [], [[mapping[i] for i in f] for f in faces]); me.update()
    ob = bpy.data.objects.new('Item shell', me)
    bpy.context.scene.collection.objects.link(ob)
    solid = ob.modifiers.new('Metal thickness', 'SOLIDIFY'); solid.thickness=.008
    for p in me.polygons: p.use_smooth=True
    return [ob]

def cube(name, location, scale):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    ob = bpy.context.object; ob.name=name; ob.scale=scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return ob

# Where a held item sits and how long the auto fit makes it (fraction of a metre). The weapon parts ride on the weapon
# bones after the bind (uo_bind_item.py); before it they start at the hand that holds them.
HOLD_BONE = {'weapon':'hand.R','weapon1h':'hand.R','axe2h':'hand.L','polearm':'hand.L','shield':'shield.L','bow':'hand.L','quiver':'chest'}
HOLD_SIZE = {'weapon':.85,'weapon1h':.85,'axe2h':1.1,'polearm':1.6,'shield':.55,'bow':.75,'quiver':.45}

def starter(part):
    if part not in HOLD_BONE:
        obs = shell(part)
        if part=='helm' and any(w in spec['prompt'].lower() for w in ['crest','crested']):
            lo,hi=region_bounds(['head'])
            obs.append(cube('Helmet crest', ((lo[0]+hi[0])/2,(lo[1]+hi[1])/2,hi[2]+.055), (.028,.23,.11)))
        return obs
    bone = rig.data.bones[HOLD_BONE[part]]
    center = rig.matrix_world @ bone.head_local
    if part in ('weapon','weapon1h','axe2h','polearm'):
        # Model along rest-bone Y, with grip at the hand.
        obs=[cube('Blade',(0,.40,0),(.065,.65,.018)), cube('Guard',(0,.075,0),(.19,.025,.045)),
             cube('Grip',(0,0,0),(.036,.15,.036))]
    elif part=='shield':
        obs=[cube('Shield',(0,.05,0),(.42,.035,.55))]
    elif part=='quiver':
        obs=[cube('Quiver',(0,0,0),(.16,.14,.42))]
    else:
        bpy.ops.mesh.primitive_torus_add(major_radius=.32, minor_radius=.022, major_segments=32, minor_segments=6)
        obs=[bpy.context.object]; obs[0].scale=(.55,1,1)
    for o in obs:
        o.matrix_world=rig.matrix_world @ bone.matrix_local @ o.matrix_world
    return obs

def import_asset(path):
    before=set(bpy.data.objects)
    ext=path.suffix.lower()
    if ext in ('.glb','.gltf'): bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext=='.fbx': bpy.ops.import_scene.fbx(filepath=str(path))
    elif ext=='.obj': bpy.ops.wm.obj_import(filepath=str(path))
    elif ext=='.stl': bpy.ops.wm.stl_import(filepath=str(path))
    elif ext=='.blend':
        with bpy.data.libraries.load(str(path), link=False) as (src,dst): dst.objects=src.objects
        for o in dst.objects:
            if o: bpy.context.scene.collection.objects.link(o)
    imported=set(bpy.data.objects)-before
    meshes=[o for o in imported if o.type=='MESH']
    if not meshes: raise ValueError('No mesh found in supplied asset.')
    dg=bpy.context.evaluated_depsgraph_get()
    # Flatten an imported asset's current shape before binding it to the canonical rig.
    copies=[]
    for o in meshes:
        ev=o.evaluated_get(dg)
        me=bpy.data.meshes.new_from_object(ev, depsgraph=dg)
        new=bpy.data.objects.new('Item_'+o.name,me)
        bpy.context.scene.collection.objects.link(new)
        new.matrix_world=o.matrix_world.copy(); copies.append(new)
        sk=o.data.shape_keys
        if spec.get('bow_draw') and sk and len(sk.key_blocks)>1 and len(me.vertices)==len(o.data.vertices):
            # bow_draw drives shape keys of the item: keep them over the flattened shape (same topology, relative to the basis)
            n=len(me.vertices); flat=np.empty(n*3,np.float32); me.vertices.foreach_get('co',flat)
            base=np.empty(n*3,np.float32); sk.key_blocks[0].data.foreach_get('co',base)
            new.shape_key_add(name='Basis',from_mix=False)
            for k in sk.key_blocks[1:]:
                co=np.empty(n*3,np.float32); k.data.foreach_get('co',co)
                new.shape_key_add(name=k.name,from_mix=False).data.foreach_set('co',flat+co-base)
    for o in imported: bpy.data.objects.remove(o,do_unlink=True)
    return copies

part=spec['part']
sys.path.insert(0,str(Path(__file__).parent))
from fit_runtime import BlockFit, resolve
extra_fit = {'offset':[spec['offset_'+a] for a in 'xyz'], 'rotate':[spec['rotate_'+a] for a in 'xyz'], 'scale':spec['scale']}
initial_fit = None
mapping_fit = {}
if spec.get('pack_mapping'):
    # A third-party asset pack: its mapping (docs/asset-packs.md) drives the rest-pose fit.
    sys.path.insert(0,str(Path(__file__).parent))
    import pack_fit
    pack=pack_fit.load_pack(spec['pack_mapping'])
    objects=pack_fit.import_fitted(spec,rig,pack,body)
    # The mapping's (lab-tuned) part settings are the defaults; explicit job settings add on top.
    fit=next((p for p in pack['parts'] if p['code']==spec.get('pack_part')),{})
    mapping_fit = fit
    fit = resolve(spec.get('fit_adjustments', {'parts':{},'items':{}}), fit,
                  spec.get('fit_item', {'id':'','slot':part,'part':spec.get('pack_part','')}))
    initial_fit = fit
    spec.setdefault('rigid', fit['bind'] == 'rigid')
    for i,a in enumerate('xyz'):
        spec['offset_'+a]=spec.get('offset_'+a,0)+fit.get('offset',[0,0,0])[i]
        spec['rotate_'+a]=spec.get('rotate_'+a,0)+fit.get('rotate',[0,0,0])[i]
    spec['scale']=spec.get('scale',1)*fit.get('scale',1)
else:
    objects = import_asset(Path(spec['asset'])) if spec['input_kind']=='model' else starter(part)
if spec.get('mount_source_origin'):
    mount=rig.matrix_world @ rig.data.bones['hand.R'].matrix_local
    align=Matrix.Rotation(math.pi if spec.get('weapon_forward')=='-Y' else -math.pi/2,4,'Z' if spec.get('weapon_forward')=='-Y' else 'X')
    for ob in objects: ob.matrix_world=mount @ align @ ob.matrix_world
    for image in list(bpy.data.images):
        if image.source=='FILE' and not image.packed_file and image.filepath and not Path(bpy.path.abspath(image.filepath)).exists(): bpy.data.images.remove(image)
bpy.context.view_layer.update()
rotation=Euler(tuple(math.radians(spec['rotate_'+a]) for a in 'xyz')).to_matrix().to_4x4()
lo,hi=bounds(objects); center=Vector((lo+hi)/2)
fit_center = center.copy()
depth_scale = initial_fit.get('depth_scale',1) if initial_fit is not None else 1
depth_matrix = Matrix.Diagonal(Vector((1,depth_scale,1,1)))
for o in objects: o.matrix_world=Matrix.Translation(center) @ rotation @ depth_matrix @ Matrix.Translation(-center) @ o.matrix_world
bpy.context.view_layer.update()
lo,hi=bounds(objects); center=Vector((lo+hi)/2)
if initial_fit is not None: center = fit_center.copy()
target=center.copy(); factor=1.
if spec['input_kind']=='model' and spec['fit']=='auto':
    regions={'helm':['head'],'chest':['chest','spine'],'arms':['upper_arm.L','upper_arm.R','forearm.L','forearm.R'],
        'gloves':['hand.L','hand.R'],'legs':['thigh.L','thigh.R','shin.L','shin.R'],
        'boots':['foot.L','foot.R'],'robe':['chest','pelvis','thigh.L','thigh.R'],
        'cloak':['chest','pelvis','thigh.L','thigh.R'],'skirt':['pelvis','thigh.L','thigh.R']}
    if part in regions:
        tlo,thi=region_bounds(regions[part]); target=Vector((tlo+thi)/2)
        # Uniform fit preserves the supplied model's proportions.
        factor=float(max((thi-tlo)*1.15)/max(hi-lo))
    else:
        bone=rig.data.bones[HOLD_BONE[part]]
        target=rig.matrix_world @ bone.head_local
        factor=HOLD_SIZE[part]/max(hi-lo)
offset=Vector(tuple(spec['offset_'+a] for a in 'xyz'))
for o in objects:
    o.matrix_world=Matrix.Translation(target+offset) @ Matrix.Scale(factor*spec['scale'],4) @ Matrix.Translation(-center) @ o.matrix_world
    for c in list(o.users_collection): c.objects.unlink(o)
    col.objects.link(o)
    o.hide_render=False; o.hide_viewport=False; o.hide_set(False)
    if spec['input_kind']!='model' or not o.data.materials:
        o.data.materials.clear(); o.data.materials.append(mat)
    else:
        # Preserve imported base-color images/values while using the reference UO lighting.
        for slot in o.material_slots:
            old=slot.material
            if not old or not old.use_nodes: slot.material=mat; continue
            principled=next((n for n in old.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
            if not principled: continue
            if spec.get('weapon_material_colors') is not None:
                colors=spec['weapon_material_colors']; key=old.name.rsplit('.',1)[0] if old.name.rsplit('.',1)[-1].isdigit() else old.name
                color=colors.get(key,next(iter(colors.values()),[.22,.24,.26,1.]))
                socket=principled.inputs['Base Color']
                for link in list(socket.links): old.node_tree.links.remove(link)
                socket.default_value=color
            converted=old.copy(); slot.material=converted; nt=converted.node_tree
            src=next(n for n in nt.nodes if n.type=='BSDF_PRINCIPLED').inputs['Base Color']
            group=nt.nodes.new('ShaderNodeGroup'); group.node_tree=bpy.data.node_groups['UO_Look']
            group.inputs['Albedo'].default_value=src.default_value
            if src.is_linked: nt.links.new(src.links[0].from_socket,group.inputs['Albedo'])
            out=next((n for n in nt.nodes if n.type=='OUTPUT_MATERIAL'),None) or nt.nodes.new('ShaderNodeOutputMaterial')
            nt.links.new(group.outputs['Shader'],out.inputs['Surface'])
    if spec['input_kind']=='image' and not o.data.uv_layers:
        bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active=o
        bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.uv.smart_project(); bpy.ops.object.mode_set(mode='OBJECT')
# Optional per-build weapon calibration (spec "weapon_motion": {bone: entry of weapon_motion.json}): replaces the entry
# of that bone and re-keys the weapon bones (uo_weapon_bones.py, embedded in the .blend) before the bind. Used for bows:
# the stock bow.L class is fitted on the bow and both crossbows together and turns the bow flat at the release of
# attack_bow; a class fitted on the bows alone follows them.
if spec.get('weapon_motion'):
    wm_text=bpy.data.texts['weapon_motion.json']; wm=json.loads(wm_text.as_string())
    for bone_name, entry in spec['weapon_motion'].items():
        if bone_name not in wm: raise ValueError('weapon_motion: unknown weapon bone %s' % bone_name)
        wm[bone_name]=entry
    wm_text.from_string(json.dumps(wm))
    exec(compile(bpy.data.texts['uo_weapon_bones.py'].as_string(),'uo_weapon_bones.py','exec'),{'__name__':'uo_weapon_bones'})
    print('weapon_motion override:', ', '.join(spec['weapon_motion']), flush=True)
bpy.ops.object.select_all(action='DESELECT')
for o in objects: o.select_set(True)
bpy.context.view_layer.objects.active=objects[0]
if spec.get('mount_source_origin'):
    sys.path.insert(0,str(Path(__file__).parent))
    import pack_fit
    for ob in objects:
        ob.vertex_groups.clear();ob.vertex_groups.new(name='hand.R').add(list(range(len(ob.data.vertices))),1.,'REPLACE')
    pack_fit.bind(objects,rig,True)
elif spec.get('pack_mapping'):
    pack_fit.bind(objects,rig,spec.get('rigid',False))
else:
    execute_external('uo_bind_item.py', {'PART': 'hat' if part=='helm' else part})
rig.data.pose_position='POSE'
# Optional bow draw (spec "bow_draw": {"weights": {action: [0..1 per frame]}, "orient": {action: [frames]}, "hand": "hand.R",
# "bone": "bow.L"}): the item
# brings the shape keys "draw" (limbs bent at full draw, weight 1) and "string_x/y/z" (the middle of the string moved 1 m
# along the mesh's local X/Y/Z). Per action frame the rig gets the draw weight and the offset from the nock to the drawing
# hand in the bow's rest frame (zero where the weight is 0), keyed as custom properties of the rig in every UO action, and
# drivers read them: the limbs bend and the string follows the fingers in the draw of attack_bow.
if spec.get('bow_draw'):
    bd=spec['bow_draw']; wbone=rig.pose.bones[bd.get('bone','bow.L')]; hbone=rig.pose.bones[bd.get('hand','hand.R')]
    names=('draw','string_x','string_y','string_z')
    keyed=[o for o in objects if o.data.shape_keys and all(n in o.data.shape_keys.key_blocks for n in names)]
    if not keyed: raise ValueError('bow_draw: no item object has the shape keys '+', '.join(names))
    for o0 in keyed:                                  # the string: the object whose string_x moves vertices
        kb=o0.data.shape_keys.key_blocks
        moved=[i for i,(a,b) in enumerate(zip(kb[0].data,kb['string_x'].data)) if (a.co-b.co).length>1e-6]
        if moved: break
    else: raise ValueError('bow_draw: the shape key string_x moves no vertex')
    nock=o0.matrix_world @ (sum((kb[0].data[i].co for i in moved),Vector())/len(moved))
    to_local=o0.matrix_world.to_3x3().inverted()
    for n in names: rig['bow_'+n]=0.0
    sc=bpy.context.scene; ndraw=0
    # "orient": {action: [frames]}: in these frames the bow turns about its own axis (the class dir) until the string side
    # faces the drawing hand, as the original bows do (the bow's plane holds the draw); the class has no roll.
    if bd.get('orient'):
        kp=kb['draw']; disp=[(b.co-a.co) for a,b in zip(kb[0].data,kp.data) if (b.co-a.co).length>1e-6]
        pull_rest=(o0.matrix_world.to_3x3() @ (sum(disp,Vector())/len(disp))).normalized()
        d_b=Vector(json.loads(bpy.data.texts['weapon_motion.json'].as_string())[wbone.name]['dir']).normalized()
        a_b=(rig.matrix_world @ wbone.bone.matrix_local).to_3x3().inverted() @ pull_rest
        a_b=(a_b-d_b*a_b.dot(d_b)).normalized(); nrot=0
        for act in [x for x in bpy.data.actions if 'uo_action' in x]:
            rig.animation_data.action=act
            for i in bd['orient'].get(str(int(act['uo_action'])),[]):
                sc.frame_set(1+3*i)
                h=(rig.matrix_world @ wbone.matrix).inverted() @ (rig.matrix_world @ hbone.tail)
                hp=(h-d_b*h.dot(d_b)).normalized()
                phi=math.atan2(d_b.dot(a_b.cross(hp)),a_b.dot(hp))
                wbone.rotation_quaternion=wbone.rotation_quaternion @ Quaternion(d_b,phi)
                wbone.keyframe_insert('rotation_quaternion',frame=1+3*i,group=wbone.name); nrot+=1
        print('bow_draw: bow turned to the hand in %d frames' % nrot, flush=True)
    for act in [a for a in bpy.data.actions if 'uo_action' in a]:
        rig.animation_data.action=act; w=bd['weights'].get(str(int(act['uo_action'])),[])
        for i in range(int(act['uo_frames'])):
            sc.frame_set(1+3*i); wi=float(w[i]) if i<len(w) else 0.
            dl=Vector()
            if wi>0:
                Mp=rig.matrix_world @ wbone.matrix; Mr=rig.matrix_world @ wbone.bone.matrix_local
                dl=to_local @ (Mr @ Mp.inverted() @ (rig.matrix_world @ hbone.tail) - nock); ndraw+=1
            for n,v in zip(names,(wi,dl.x,dl.y,dl.z)):
                rig['bow_'+n]=v; rig.keyframe_insert('["bow_%s"]'%n,frame=1+3*i,group='bow_draw')
    for o in keyed:
        for n in names:
            k=o.data.shape_keys.key_blocks[n]; k.slider_min=-5.; k.slider_max=5.
            drv=k.driver_add('value').driver; drv.type='AVERAGE'
            var=drv.variables.new(); var.type='SINGLE_PROP'; var.targets[0].id=rig; var.targets[0].data_path='["bow_%s"]'%n
    print('bow_draw: %d drawn frames, %d objects, nock %s' % (ndraw,len(keyed),tuple(round(c,3) for c in nock)), flush=True)
acts=sorted((a for a in bpy.data.actions if 'uo_action' in a), key=lambda a:int(a['uo_action']))
rig.animation_data.action=next(a for a in acts if int(a['uo_action'])==4)
bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()
camera=bpy.data.objects['UO_Camera']
camera.data.ortho_scale *= 256/136
camera.location += camera.rotation_euler.to_matrix() @ Vector((0,38/36,0))
bpy.context.scene.render.resolution_x=256
bpy.context.scene.render.resolution_y=256
report={'model':'UO_Model3D','bones':len(rig.data.bones),'shape_keys':0,
    'actions':{str(int(a['uo_action'])):int(a['uo_frames']) for a in acts},'frame_start':1,'frame_step':3,
    'camera':'UO_Camera','render_canvas':[256,256],'anchor':[128,192],
    'inherit_scale':{b.name:b.inherit_scale for b in rig.data.bones if b.inherit_scale!='FULL'},
    'item_objects':[o.name for o in objects], 'auto_fit_scale':float(factor),
    'placement_note':'Automatic placement is a starting fit. Inspect all facings; adjust rotation/scale/offset or supply a prepositioned model.'}
(job/'scene-report.json').write_text(json.dumps(report,indent=2))
if 'uo_original_frames.json' in bpy.data.texts:       # the stripped public .blend has no client frames
    (job/'original-frames.json').write_text(bpy.data.texts['uo_original_frames.json'].as_string())
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(job/'item.blend'))
# Optional cloth simulation of a loose garment (spec "cloth_sim": true or {key: value} of uo_cloth_sim.py): the hem swings and
# drags instead of only being pushed out of the legs frame by frame. It runs on the saved item.blend in a separate Blender
# (uo_cloth_sim opens the file itself) and writes job/cloth_sim.npz, which render_uo_layer.py adds to the leg push (CLOTH_SIM).
if spec.get('cloth_sim') and part in ('robe', 'skirt'):
    import subprocess, time
    # uo_cloth_sim reads the evaluated mesh vertex by vertex: a modifier that adds vertices (the procedural shell's
    # Solidify) makes it fail deep inside Blender ("Array length mismatch"). Refuse it here with the reason.
    dg = bpy.context.evaluated_depsgraph_get()
    grown = [o.name for o in objects if len(o.evaluated_get(dg).data.vertices) != len(o.data.vertices)]
    if grown:
        raise ValueError('cloth_sim needs meshes whose modifiers keep the vertex count (%s changes it; the procedural '
                         '%s template has a Solidify): supply a model.' % (', '.join(grown), part))
    sim_cfg =spec['cloth_sim'] if isinstance(spec['cloth_sim'], dict) else {}
    sim_acts = [a.name for a in acts if int(a['uo_action']) in spec['actions'] and not 23 <= int(a['uo_action']) <= 29]
    cmd = [bpy.app.binary_path, '-b', '--factory-startup', '--python-exit-code', '1',
           '--python', str(Path(__file__).resolve().parent / 'cloth_sim_run.py'), '--',
           str(backend / 'pipeline/uo_cloth_sim.py'), str(job / 'item.blend'),
           '--actions', ','.join(sim_acts), '--out', str(job / 'cloth_sim.npz')] + [f'{k}={v}' for k, v in sim_cfg.items()]
    t0 = time.time()
    sim = subprocess.run(cmd, capture_output=True, text=True)
    (job / 'cloth_sim.log').write_text(sim.stdout + sim.stderr, encoding='utf-8')
    if sim.returncode != 0 or not (job / 'cloth_sim.npz').exists():
        raise RuntimeError('cloth simulation failed; see cloth_sim.log')
    print('cloth_sim: %d actions in %.0f s -> %s' % (len(sim_acts), time.time() - t0, job / 'cloth_sim.npz'), flush=True)
module_spec=importlib.util.spec_from_file_location('external_vd_writer',backend/'pipeline/uo_vd_writer.py')
writer=importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(writer)
block_fit = BlockFit(spec,rig,body,objects,mapping_fit,initial_fit,fit_center,extra_fit)
execute_external('render_uo_layer.py', {
    'ONLY':[a.name for a in acts if int(a['uo_action']) in spec['actions']],
    'OUT_DIR':str(job/'render')+'/', 'VD_FILE':str(job/'%s.vd'),
    'ANCHOR':(128,192),
    'BODY_GAP':0.0 if spec.get('rigid') or part in ('helm','weapon','weapon1h','axe2h','polearm','shield','bow','quiver') else .006,
    'DESPECKLE':0, 'FILL_HOLES':0, 'MIN_PIECE':0,
}, {'writer':writer, '_fit_pose':block_fit,
    '_selected_blocks':set(map(tuple,spec['blocks'])) if 'blocks' in spec else None})
report['fit_blocks'] = block_fit.report
report['hidden_body_faces'] = next(iter(block_fit.report.values()))['hidden_body_faces'] if block_fit.report else 0
(job/'scene-report.json').write_text(json.dumps(report,indent=2))
(job/'clothing.vd').replace(job/'item.vd')
