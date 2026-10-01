"""Verify saved female clips and export projected armature overlays for local review."""
from pathlib import Path
import sys,json,hashlib
import bpy,numpy as np
from mathutils import Matrix,Vector
from bpy_extras.object_utils import world_to_camera_view
sys.path.insert(0,str(Path(__file__).resolve().parent));import smblender as SM
from spritemotion.fitting.camera import direction_rotations

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/ultima-online/female-locomotion'
FILE=OUT/'UO_Female_Idle_Walk_Run.blend'
targets=json.loads((OUT/'motion-targets.json').read_text())
names=json.loads((ROOT/'games/ultima-online/skeletons/humanoid-20.json').read_text())['joints']


def signature():
    rig=bpy.data.objects['Female_Rig']
    bones={b.name:np.array(b.matrix_local).round(5).tolist() for b in rig.data.bones}
    h=hashlib.sha256()
    for obj in sorted((o for o in bpy.data.objects if o.type=='MESH'),key=lambda o:o.name):
        h.update(obj.name.encode())
        for v in obj.data.vertices:
            h.update(np.array(v.co,dtype=np.float32).tobytes())
            for g in v.groups:h.update(f'{g.group}:{g.weight:.7f};'.encode())
    return bones,h.hexdigest()


def bounds(meshes):
    dg=bpy.context.evaluated_depsgraph_get();allpts=[]
    for obj in meshes:
        ev=obj.evaluated_get(dg);v=np.empty(len(ev.data.vertices)*3,dtype=np.float32);ev.data.vertices.foreach_get('co',v)
        m=np.array(ev.matrix_world);allpts.append(v.reshape(-1,3)@m[:3,:3].T+m[:3,3])
    p=np.concatenate(allpts);assert np.isfinite(p).all()
    return p.min(0),p.max(0)


def joint_positions(rig):
    p=rig.pose.bones
    mapping={'neck':'neck_01','chest':'spine_02','pelvis':'pelvis'}
    for chain,side in [('A','l'),('B','r')]:
        for label,bone in [('shoulder','upperarm'),('elbow','lowerarm'),('wrist','hand'),('hand','middle_01')]:mapping[f'arm_{chain}_{label}']=bone+'_'+side
        for label,bone in [('hip','thigh'),('knee','calf'),('ankle','foot'),('toe','ball')]:mapping[f'leg_{chain}_{label}']=bone+'_'+side
    result={n:rig.matrix_world@p[b].matrix.translation for n,b in mapping.items()}
    headrest=rig.data.bones['head'].matrix_local
    result['head']=rig.matrix_world@p['head'].matrix@headrest.inverted()@(headrest.translation+Vector((0,0,.06)))
    return result


def main():
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'source/UOCharacter2_Female_Base.blend'));original=signature()
    bpy.ops.wm.open_mainfile(filepath=str(FILE));current=signature()
    assert original==current,'Bind pose, geometry or weights changed'
    scene=bpy.context.scene;rig=bpy.data.objects['Female_Rig'];meshes=[o for o in scene.objects if o.type=='MESH']
    for t in rig.animation_data.nla_tracks:t.mute=True
    report={'bind_mesh_weights_unchanged':True,'clips':{},'texture_images_packed':all(im.packed_file for im in bpy.data.images if im.source=='FILE')}
    overlays={};M=np.array(targets['camera']['matrix']);anchor=np.array([128,192])
    rots=direction_rotations(json.loads((ROOT/'games/ultima-online/profiles/body-401.json').read_text())['directions'])
    for name,clip in targets['actions'].items():
        action=bpy.data.actions['SM_Female_'+name];rig.animation_data.action=action;rig.animation_data.action_slot=action.slots[0]
        rig.matrix_world=Matrix.Identity(4)
        duration=len(clip['frames'])*clip['source_frame_step'];floors=[];corrections=[];heights=[];loop=[];max_length_error=0.
        for frame in range(1,duration+2):
            scene.frame_set(frame);bpy.context.view_layer.update()
            lo,hi=bounds(meshes)
            # Clear small interpolation penetrations without modifying source poses.
            if lo[2]<-.0005:
                pb=rig.pose.bones['pelvis'];m=pb.matrix.copy();m.translation.z+=.001-float(lo[2]);pb.matrix=m
                pb.keyframe_insert('location',frame=frame,group='pelvis');bpy.context.view_layer.update();corrections.append(frame)
                lo,hi=bounds(meshes)
            floors.append(float(lo[2]));heights.append(float(hi[2]-lo[2]))
            if frame in (1,duration+1):loop.append(np.array([rig.pose.bones[b.name].matrix for b in rig.data.bones]))
            for side in ('l','r'):
                for a,b in [('upperarm','lowerarm'),('lowerarm','hand'),('thigh','calf'),('calf','foot')]:
                    a+='_'+side;b+='_'+side
                    current=(rig.pose.bones[a].matrix.translation-rig.pose.bones[b].matrix.translation).length
                    rest=(rig.data.bones[a].head_local-rig.data.bones[b].head_local).length
                    max_length_error=max(max_length_error,abs(current-rest))
        looperror=float(np.max(np.abs(loop[0]-loop[1])))
        assert looperror<1e-4,(name,looperror)
        assert min(floors)>-.001,(name,min(floors))
        assert max_length_error<1e-4,(name,max_length_error)
        report['clips'][name]={'duration_frames':duration,'checked_frames':duration+1,'loop_matrix_error':looperror,
                               'min_floor_m':min(floors),'max_floor_m':max(floors),'max_limb_length_error_m':max_length_error,
                               'interpolation_floor_corrections':corrections,'height_range_m':[min(heights),max(heights)]}
        overlays[name]=[]
        for f in range(len(clip['frames'])):
            scene.frame_set(1+f*clip['source_frame_step']);bpy.context.view_layer.update();pts=joint_positions(rig)
            scene.render.resolution_x=512;scene.render.resolution_y=640;scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1
            beauty={}
            for n,p in pts.items():
                v=world_to_camera_view(scene,bpy.data.objects['SM_Review_Camera'],p);beauty[n]=[float(v.x*512),float((1-v.y)*640)]
            uo={str(d):{n:(np.array(p)@rots[d].T@M.T+anchor).tolist() for n,p in pts.items()} for d in range(3,8)}
            overlays[name].append({'beauty':beauty,'uo':uo})
    rig.animation_data.action=None
    for t in rig.animation_data.nla_tracks:t.mute=False
    scene.frame_set(1);scene.camera=bpy.data.objects['SM_Review_Camera']
    bpy.ops.wm.save_as_mainfile(filepath=str(FILE),compress=True)
    (OUT/'verification.json').write_text(json.dumps(report,indent=2));(OUT/'projected-rig.json').write_text(json.dumps(overlays))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
