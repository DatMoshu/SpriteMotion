"""Apply browser local-joint quaternions as pose keys; save a separate scene."""
from pathlib import Path
import sys,json,argparse,importlib.util
import bpy
from mathutils import Matrix,Vector,Quaternion
sys.path.insert(0,str(Path(__file__).resolve().parent))
import smblender as SM

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'workspace/ultima-online/female-locomotion'
p=argparse.ArgumentParser();p.add_argument('--edits',required=True);p.add_argument('--output',required=True);args=SM.parse_args(p)
spec=importlib.util.spec_from_file_location('editor_server',ROOT/'games/ultima-online/region-masks/pose_editor_server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
data=json.loads((OUT/'editor/scene.json').read_text())
doc=server.validate(json.loads(Path(args.edits).read_text()),data)
output=Path(args.output).resolve()
assert output!=(OUT/'UO_Female_Idle_Walk_Run.blend').resolve(),'Must export to a separate scene'
assert output!=(OUT/data.get('sourceBlend','UO_Female_Idle_Walk_Run.blend')).resolve(),'Must preserve the active source scene'
rig=bpy.data.objects['Female_Rig'];scene=bpy.context.scene
for track in rig.animation_data.nla_tracks:track.mute=True
errors=[]
for key,changes in sorted(doc['edits'].items()):
    name,index=key.split(':');index=int(index);clip=data['clips'][name];base=clip['frames'][index]
    action=bpy.data.actions['SM_Female_'+name];rig.animation_data.action=action;rig.animation_data.action_slot=action.slots[0]
    frame=1+index*clip['step'];scene.frame_set(frame);bpy.context.view_layer.update()
    # Traverse parents before children. The browser skeleton stores parent-local
    # posed transforms, whereas Blender keys basis transforms relative to rest.
    for i,b in enumerate(data['bones']):
        bone=b['name']
        if bone not in changes:continue
        pb=rig.pose.bones[bone];v=base[i];q=changes[bone]
        old_basis=pb.rotation_quaternion.copy()
        local=Matrix.LocRotScale(Vector(v['p']),Quaternion((q[3],q[0],q[1],q[2])),Vector(v['s']))
        desired=pb.parent.matrix@local if pb.parent else local
        pb.matrix=desired;bpy.context.view_layer.update()
        errors.append(max(abs(pb.matrix[r][c]-desired[r][c]) for r in range(4) for c in range(4)))
        # Match source quaternion hemisphere for stable interpolation.
        if pb.rotation_quaternion.dot(old_basis)<0:pb.rotation_quaternion.negate()
        pb.keyframe_insert('rotation_quaternion',frame=frame,group=bone)
        if index==0:pb.keyframe_insert('rotation_quaternion',frame=1+len(clip['frames'])*clip['step'],group=bone)
    for _,fc in SM.fcurve_owners(action):
        for k in fc.keyframe_points:k.interpolation='LINEAR'
assert max(errors,default=0)<1e-4,errors
# Evaluate the inserted keys again, verifying every joint including descendants.
evaluated_error=0.;loop_error=0.
for key,changes in doc['edits'].items():
    name,index=key.split(':');index=int(index);clip=data['clips'][name]
    action=bpy.data.actions['SM_Female_'+name];rig.animation_data.action=action;rig.animation_data.action_slot=action.slots[0]
    scene.frame_set(-1);scene.frame_set(1+index*clip['step']);bpy.context.view_layer.update()
    expected=[]
    for i,b in enumerate(data['bones']):
        v=clip['frames'][index][i];q=changes.get(b['name'],v['q'])
        m=Matrix.LocRotScale(Vector(v['p']),Quaternion((q[3],*q[:3])),Vector(v['s']))
        if b['parent']>=0:m=expected[b['parent']]@m
        expected.append(m)
        actual=rig.pose.bones[b['name']].matrix
        evaluated_error=max(evaluated_error,max(abs(actual[r][c]-m[r][c]) for r in range(4) for c in range(4)))
    scene.frame_set(1);bpy.context.view_layer.update();start=[pb.matrix.copy() for pb in rig.pose.bones]
    scene.frame_set(1+len(clip['frames'])*clip['step']);bpy.context.view_layer.update()
    loop_error=max(loop_error,max(abs(pb.matrix[r][c]-m[r][c]) for pb,m in zip(rig.pose.bones,start) for r in range(4) for c in range(4)))
assert evaluated_error<1e-4,evaluated_error
assert loop_error<1e-4,loop_error
rig.animation_data.action=None
for track in rig.animation_data.nla_tracks:track.mute=False
scene.frame_set(1)
rig['editor_edits']=json.dumps(doc)
bpy.ops.wm.save_as_mainfile(filepath=str(output),compress=True)
(output.parent/'verification.json').write_text(json.dumps({'edited_frames':len(doc['edits']),'max_pose_matrix_error':max(errors,default=0),'evaluated_pose_error':evaluated_error,'loop_matrix_error':loop_error,'source_preserved':True},indent=2))
print('EDITED_SCENE',output,flush=True)
