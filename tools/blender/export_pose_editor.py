"""Export the intact Blender skin and sampled poses for the local WebGL editor."""
from pathlib import Path
import sys, json, hashlib
import bpy, numpy as np
from mathutils import Matrix
sys.path.insert(0, str(Path(__file__).resolve().parent))
import smblender
from spritemotion.fitting.camera import direction_rotations

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'workspace/ultima-online/female-locomotion'
DEST = OUT / 'editor'
DEST.mkdir(exist_ok=True)
rig = bpy.data.objects['Female_Rig']
scene = bpy.context.scene
motion = json.loads((OUT/'motion-targets.json').read_text())
bones = list(rig.data.bones)
indices = {b.name:i for i,b in enumerate(bones)}
def flat(m): return np.array(m).T.reshape(-1).tolist()
def trs(m):
    p,q,s=m.decompose()
    return {'p':list(p),'q':[q.x,q.y,q.z,q.w],'s':list(s)}
data={'version':1,'bones':[], 'meshes':[], 'materials':[], 'clips':{},
      'camera':motion['camera'], 'anchor':[128,192], 'crop':[80,108,96,96]}
for b in bones:
    local=b.parent.matrix_local.inverted()@b.matrix_local if b.parent else b.matrix_local
    data['bones'].append({'name':b.name,'parent':indices[b.parent.name] if b.parent else -1,
                          'inverse':flat(b.matrix_local.inverted()),**trs(local)})
materials=list(bpy.data.materials)
for i,mat in enumerate(materials):
    shader=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
    image=None
    if shader and shader.inputs['Base Color'].is_linked:
        node=shader.inputs['Base Color'].links[0].from_node
        if node.type=='TEX_IMAGE':image=node.image
    texture=None
    if image:
        texture=f'texture-{i}.png'
        # Save the image itself in sRGB, independent of scene display transforms.
        old_format=image.file_format;image.file_format='PNG'
        image.filepath_raw=str(DEST/texture);image.save();image.file_format=old_format
    data['materials'].append({'name':mat.name,'texture':texture,
                             'color':list(shader.inputs['Base Color'].default_value) if shader else [1,1,1,1]})
chunks=[];offset=0
def array(values,dtype,size):
    global offset
    a=np.asarray(values,dtype=dtype);raw=a.tobytes()
    record={'offset':offset,'length':a.size,'type':dtype,'size':size}
    chunks.append(raw);offset+=len(raw)
    padding=(-offset)%4
    if padding:chunks.append(bytes(padding));offset+=padding
    return record
for obj in sorted((o for o in scene.objects if o.type=='MESH'),key=lambda o:o.name):
    mesh=obj.data;mesh.calc_loop_triangles()
    transform=rig.matrix_world.inverted()@obj.matrix_world
    normalmat=transform.to_3x3().inverted().transposed()
    positions=[list(transform@v.co) for v in mesh.vertices]
    weights=[];joints=[]
    for v in mesh.vertices:
        influences=[(indices[obj.vertex_groups[g.group].name],g.weight) for g in v.groups
                    if obj.vertex_groups[g.group].name in indices and g.weight>1e-7]
        assert len(influences)<=8,(obj.name,v.index,influences)
        total=sum(w for _,w in influences)
        assert total>0,(obj.name,v.index)
        influences += [(0,0)]*(8-len(influences))
        joints.append([i for i,w in influences]);weights.append([w/total for i,w in influences])
    # Split triangle corners to retain original UV seams and corner normals.
    pos=[];normal=[];uv=[];ji=[];we=[];groups=[]
    for material in range(len(obj.material_slots)):
        start=len(pos)
        for tri in mesh.loop_triangles:
            if tri.material_index!=material:continue
            for vi,li in zip(tri.vertices,tri.loops):
                pos.append(positions[vi]);normal.append(list((normalmat@mesh.corner_normals[li].vector).normalized()))
                uv.append(list(mesh.uv_layers.active.data[li].uv) if mesh.uv_layers.active else [0,0])
                ji.append(joints[vi]);we.append(weights[vi])
        groups.append({'start':start,'count':len(pos)-start,'material':materials.index(obj.material_slots[material].material)})
    data['meshes'].append({'name':obj.name,'groups':groups,
        'attributes':{k:array(v,t,s) for k,v,t,s in [('position',pos,'float32',3),('normal',normal,'float32',3),
        ('uv',uv,'float32',2),('skinIndex',[v[:4] for v in ji],'uint16',4),('skinWeight',[v[:4] for v in we],'float32',4),
        ('skinIndex2',[v[4:] for v in ji],'uint16',4),('skinWeight2',[v[4:] for v in we],'float32',4)]}})
(DEST/'mesh.bin').write_bytes(b''.join(chunks))
for track in rig.animation_data.nla_tracks:track.mute=True
rig.matrix_world=Matrix.Identity(4)
for name,clip in motion['actions'].items():
    action=bpy.data.actions['SM_Female_'+name]
    rig.animation_data.action=action;rig.animation_data.action_slot=action.slots[0]
    frames=[]
    for f in range(len(clip['frames'])):
        scene.frame_set(1+f*clip['source_frame_step']);bpy.context.view_layer.update()
        frames.append([trs(p.parent.matrix.inverted()@p.matrix if p.parent else p.matrix) for p in rig.pose.bones])
    data['clips'][name]={'step':clip['source_frame_step'],'frames':frames}
rots=direction_rotations(json.loads((ROOT/'games/ultima-online/profiles/body-401.json').read_text())['directions'])
data['directions']={str(d):flat(Matrix(rots[d].tolist()).to_4x4()) for d in range(3,8)}
data['sourceBlend']=Path(bpy.data.filepath).name
data['assetId']=hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest()
(DEST/'scene.json').write_text(json.dumps(data,separators=(',',':')))
print('EXPORTED',len(bones),'bones',len(data['meshes']),'meshes',offset,'bytes',flush=True)
