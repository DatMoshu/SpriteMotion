"""Check exported WebGL skin against evaluated Blender geometry at all 21 poses."""
from pathlib import Path
import sys,json
import bpy,numpy as np
from mathutils import Matrix,Vector,Quaternion
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'workspace/ultima-online/female-locomotion'
data=json.loads((OUT/'editor/scene.json').read_text());blob=(OUT/'editor/mesh.bin').read_bytes()
rig=bpy.data.objects['Female_Rig'];scene=bpy.context.scene
for t in rig.animation_data.nla_tracks:t.mute=True
def arr(a):return np.frombuffer(blob,dtype=a['type'],offset=a['offset'],count=a['length']).reshape(-1,a['size'])
skin=[]
for m in data['meshes']:
    a={n:arr(v) for n,v in m['attributes'].items()};obj=bpy.data.objects[m['name']];obj.data.calc_loop_triangles()
    corners=[]
    for group in range(len(obj.material_slots)):
        for tri in obj.data.loop_triangles:
            if tri.material_index==group:corners.extend(tri.vertices)
    skin.append((obj,a,np.array(corners)))
inverse=np.array([np.array(b['inverse']).reshape(4,4).T for b in data['bones']])
max_joint=0;max_vertex=0;checked=0
for name,clip in data['clips'].items():
    action=bpy.data.actions['SM_Female_'+name];rig.animation_data.action=action;rig.animation_data.action_slot=action.slots[0]
    for f,pose in enumerate(clip['frames']):
        scene.frame_set(1+f*clip['step']);bpy.context.view_layer.update()
        matrices=[]
        for i,local in enumerate(pose):
            q=local['q'];m=Matrix.LocRotScale(Vector(local['p']),Quaternion((q[3],*q[:3])),Vector(local['s']))
            if data['bones'][i]['parent']>=0:m=matrices[data['bones'][i]['parent']]@m
            matrices.append(m)
            actual=rig.pose.bones[data['bones'][i]['name']].matrix
            max_joint=max(max_joint,float(np.max(np.abs(np.array(actual)-np.array(m)))))
        deform=np.array(matrices)@inverse
        dg=bpy.context.evaluated_depsgraph_get()
        for obj,a,corners in skin:
            positions=np.column_stack([a['position'],np.ones(len(corners))]);result=np.zeros((len(corners),4))
            for suffix in ('','2'):
                for channel in range(4):
                    mat=deform[a['skinIndex'+suffix][:,channel]]
                    result+=np.einsum('nij,nj->ni',mat,positions)*a['skinWeight'+suffix][:,channel,None]
            ev=obj.evaluated_get(dg);v=np.array([v.co for v in ev.data.vertices])[corners]
            v=v@np.array(ev.matrix_world)[:3,:3].T+np.array(ev.matrix_world)[:3,3]
            max_vertex=max(max_vertex,float(np.max(np.linalg.norm(result[:,:3]-v,axis=1))))
        checked+=1
assert max_joint<1e-4,max_joint
assert max_vertex<1e-4,max_vertex
report={'sampled_poses':checked,'max_joint_matrix_error':max_joint,'max_skinned_vertex_error_m':max_vertex,'all_skin_weights_preserved':True}
(OUT/'editor/skin-verification.json').write_text(json.dumps(report,indent=2));print(report)
