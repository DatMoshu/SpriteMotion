"""Rebuild distributable CC0 sources using only Quaternius sources, never the UO model.

blender -b --factory-startup --python prepare_blender.py -- <extracted-standard-pack> <output>
Original supplement geometry is dedicated to CC0-1.0; see supplement-license.txt.
"""
import hashlib
import json
import math
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

SOURCE, OUT = map(Path, sys.argv[sys.argv.index('--') + 1:])
OUT.mkdir(parents=True, exist_ok=True)
ROOT = Path(__file__).resolve().parents[2]
FBX = SOURCE / 'Exports/FBX (Unity)/Modular Parts'
COLORS = {'leather': (.25,.12,.045,1), 'cloth': (.08,.23,.28,1),
          'metal': (.48,.55,.59,1), 'gold': (.85,.56,.12,1), 'hair': (.12,.055,.025,1)}


def material(name):
    mat = bpy.data.materials.get('Starter '+name) or bpy.data.materials.new('Starter '+name)
    mat.diffuse_color = COLORS[name]
    mat.use_nodes = True
    mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = COLORS[name]
    return mat


def base(filename='Male_Ranger_Arms.fbx'):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str((FBX/filename).resolve()))
    rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    rig.animation_data_clear()
    rig.data.pose_position = 'REST'
    for o in list(bpy.data.objects):
        if o.type == 'MESH':
            # These source parts include exposed skin; remove it from equipment assets.
            bm = bmesh.new(); bm.from_mesh(o.data)
            remove = [f for f in bm.faces if 'Regular' in o.data.materials[f.material_index].name]
            bmesh.ops.delete(bm, geom=remove, context='FACES')
            loose = [v for v in bm.verts if not v.link_faces]
            bmesh.ops.delete(bm, geom=loose, context='VERTS')
            bm.to_mesh(o.data); bm.free()
            if not o.data.polygons:
                bpy.data.objects.remove(o, do_unlink=True)
                continue
            for mat in o.data.materials:
                if not mat or not mat.use_nodes: continue
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        name = Path(node.image.filepath.replace('\\','/')).name
                        matches = list(SOURCE.rglob(name))
                        if matches:
                            node.image.filepath = str(matches[0].resolve()); node.image.reload(); node.image.pack()
    return rig


def head(rig, name):
    return rig.matrix_world @ rig.data.bones[name].head_local


def finish_object(o, rig, bone, color):
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.vertex_groups.new(name=bone).add(list(range(len(o.data.vertices))),1,'REPLACE')
    o.parent = rig
    o.matrix_parent_inverse = rig.matrix_world.inverted()
    mod = o.modifiers.new('Source rig','ARMATURE'); mod.object = rig
    o.data.materials.append(material(color))
    return o


def sphere(rig, bone, center, size, color='leather'):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, location=center)
    o=bpy.context.object; o.scale=size
    return finish_object(o,rig,bone,color)


def box(rig, bone, center, size, color='leather'):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center)
    o=bpy.context.object; o.scale=size
    bevel=o.modifiers.new('Rounded edges','BEVEL'); bevel.width=.015; bevel.segments=2
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    return finish_object(o,rig,bone,color)


def torus(rig,bone,center,radius,thickness,color='gold',scale=(1,1,1),rotation=(0,0,0)):
    bpy.ops.mesh.primitive_torus_add(major_segments=24,minor_segments=8,location=center,
                                  major_radius=radius,minor_radius=thickness,rotation=rotation)
    o=bpy.context.object;o.scale=scale
    return finish_object(o,rig,bone,color)


def cloth(rig, robe=False, skirt=False):
    # Open, original cloth panels; no surface is sampled from a character mesh.
    verts=[];faces=[];rows=9;cols=25
    for row in range(rows):
        t=row/(rows-1)
        for col in range(cols):
            a=2*math.pi*col/(cols-1)
            if robe or skirt:
                z=(1.47 if robe else 1.0)*(1-t)+(.20 if robe else .53)*t
                radius=(.22 if robe else .20)+(.09*t)
                verts.append((radius*math.cos(a),radius*.7*math.sin(a)-.025,z))
            else:
                a=math.pi*.18+math.pi*.64*col/(cols-1)
                verts.append(((.25+.1*t)*math.cos(a),-(.14+.07*t)*math.sin(a)-.06,1.48-.94*t))
    for row in range(rows-1):
        for col in range(cols-1):
            i=row*cols+col; faces.append((i,i+1,i+cols+1,i+cols))
    mesh=bpy.data.meshes.new('Original cloth');mesh.from_pydata(verts,[],faces);mesh.update()
    o=bpy.data.objects.new('Original cloth',mesh);bpy.context.collection.objects.link(o)
    for name in ('spine_03','pelvis','thigh_l','thigh_r'):o.vertex_groups.new(name=name)
    for v in mesh.vertices:
        z=v.co.z
        weights={'spine_03':max(0,min(1,(z-1.0)/.35)), 'pelvis':1}
        weights['pelvis']=1-weights['spine_03']
        for name,w in weights.items():
            if w:o.vertex_groups[name].add([v.index],w,'REPLACE')
    o.parent=rig;o.matrix_parent_inverse=rig.matrix_world.inverted()
    mod=o.modifiers.new('Source rig','ARMATURE');mod.object=rig
    o.data.materials.append(material('cloth'))
    solid=o.modifiers.new('Cloth thickness','SOLIDIFY');solid.thickness=.008
    return o


def supplement(name, rig):
    for o in list(bpy.data.objects):
        if o.type=='MESH':bpy.data.objects.remove(o,do_unlink=True)
    h=head(rig,'Head');p=head(rig,'pelvis');n=head(rig,'neck_01')
    if name in ('starter-sword','starter-shield'):
        source='weapon-sword' if name=='starter-sword' else 'shield-round'
        before=set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str((OUT/(source+'.glb')).resolve()))
        imported=set(bpy.data.objects)-before
        meshes=[o for o in imported if o.type=='MESH']
        points=[o.matrix_world@v.co for o in meshes for v in o.data.vertices]
        lo=Vector(tuple(min(v[i] for v in points) for i in range(3)))
        hi=Vector(tuple(max(v[i] for v in points) for i in range(3)))
        center=(lo+hi)/2; scale=(.85 if name=='starter-sword' else .55)/max(hi-lo)
        bone='hand_r' if name=='starter-sword' else 'hand_l'
        for o in meshes:
            world=o.matrix_world.copy()
            for v in o.data.vertices:v.co=(world@v.co-center)*scale+head(rig,bone)
            o.parent=rig;o.matrix_parent_inverse=rig.matrix_world.inverted();o.matrix_basis=Matrix.Identity(4)
            o.vertex_groups.clear();o.vertex_groups.new(name=bone).add(list(range(len(o.data.vertices))),1,'REPLACE')
            mod=o.modifiers.new('Source rig','ARMATURE');mod.object=rig
        for o in imported:
            if o not in meshes:bpy.data.objects.remove(o,do_unlink=True)
    elif name=='gorget':torus(rig,'neck_01',n+Vector((0,0,.02)),.105,.027,'metal',scale=(1,.85,1.5))
    elif name=='belt':
        torus(rig,'pelvis',p+Vector((0,0,.05)),.19,.024,'leather',scale=(1,.66,1.6))
        box(rig,'pelvis',p+Vector((0,.145,.05)),(.065,.02,.06),'gold')
    elif name=='hair':
        sphere(rig,'Head',h+Vector((0,-.018,.115)),(.11,.115,.09),'hair')
        for x in (-.085,0,.085):sphere(rig,'Head',h+Vector((x,-.07,.02)),(.04,.06,.09),'hair')
    elif name=='beard':
        sphere(rig,'Head',h+Vector((0,.105,-.06)),(.087,.035,.10),'hair')
    elif name=='mask':
        for x in (-.05,.05):torus(rig,'Head',h+Vector((x,.106,.055)),.038,.012,'metal',rotation=(math.pi/2,0,0))
        box(rig,'Head',h+Vector((0,.11,.055)),(.032,.02,.014),'metal')
    elif name=='backpack':
        c=head(rig,'spine_03');box(rig,'spine_03',c+Vector((0,-.18,-.07)),(.32,.16,.40))
        box(rig,'spine_03',c+Vector((0,-.275,-.16)),(.23,.05,.12))
        for x in (-.115,.115):torus(rig,'spine_03',c+Vector((x,-.02,.015)),.12,.015,'leather',scale=(1,1,1.45),rotation=(0,math.pi/2,0))
    elif name in ('cloak','robe','skirt'):cloth(rig,robe=name=='robe',skirt=name=='skirt')
    elif name=='gloves':
        for side,sign in (('l',-1),('r',1)):
            c=head(rig,'hand_'+side)
            sphere(rig,'hand_'+side,c+Vector((sign*.065,0,-.007)),(.09,.055,.04),'metal')
            sphere(rig,'hand_'+side,c+Vector((sign*.045,.045,-.025)),(.045,.028,.026),'metal')
    elif name=='ring':torus(rig,'hand_l',head(rig,'index_01_l'),.013,.004)
    elif name=='bracelet':torus(rig,'hand_l',head(rig,'hand_l'),.038,.009,rotation=(0,math.pi/2,0))
    elif name=='earrings':
        for x in (-.12,.12):torus(rig,'Head',h+Vector((x,0,.03)),.026,.006,rotation=(math.pi/2,0,0))
    elif name=='talisman':
        c=head(rig,'spine_03')+Vector((0,.16,.035))
        sphere(rig,'spine_03',c,(.035,.012,.05),'gold')
        torus(rig,'neck_01',n+Vector((0,0,-.015)),.11,.005,scale=(1,1,1))


files={}
source_choices={'boots':'Male_Ranger_Feet_Boots','pants':'Male_Peasant_Legs',
 'shirt':'Male_Peasant_Body','hood':'Male_Ranger_Head_Hood','chest':'Male_Ranger_Body',
 'tunic':'Male_Peasant_Body','arms':'Male_Ranger_Arms','leg-armor':'Male_Ranger_Legs'}
originals=['gorget','hair','belt','mask','beard','cloak','backpack','robe','skirt','gloves','ring','bracelet','earrings','talisman','starter-sword','starter-shield']
bones=None
for name in [*source_choices,*originals]:
    source=source_choices.get(name,'Male_Ranger_Arms')+'.fbx'
    rig=base(source)
    if name in originals:supplement(name,rig)
    if bones is None:
        bones={b.name:{'parent':b.parent.name if b.parent else None} for b in rig.data.bones}
    # CC0 authoring rig faces +Y; canonical fitting space faces -Y.
    rig.matrix_world=Matrix.Rotation(math.pi,4,'Z')@rig.matrix_world
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='SELECT')
    target=OUT/(name+'.glb')
    bpy.ops.export_scene.gltf(filepath=str(target.resolve()),export_format='GLB',export_animations=False,
                              export_skins=True,export_def_bones=False,export_apply=False)
    files[target.name]={'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                       'source':('Original primitive geometry; CC0 Quaternius rig' if name in originals else source),
                       'source_sha256':hashlib.sha256((FBX/source).read_bytes()).hexdigest()}
    if name.startswith('starter-'):
        source='weapon-sword.glb' if name=='starter-sword' else 'shield-round.glb'
        files[target.name].update(source='Kenney '+source+' mounted on CC0 Quaternius rig',
                                  source_sha256=hashlib.sha256((OUT/source).read_bytes()).hexdigest())
(OUT/'source-bones.json').write_text(json.dumps(bones,indent=2)+'\n')
(OUT/'sources.json').write_text(json.dumps(files,indent=2)+'\n')
