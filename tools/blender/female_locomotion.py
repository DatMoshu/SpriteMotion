"""Retarget the new mask-guided armature onto the supplied Unreal-style female rig.

blender -b --factory-startup <female base> --python tools/blender/female_locomotion.py
  -- [--pilot] [--no-render]
Uses child joint heads, not FBX bone tails. Keeps bind pose, weights and mesh intact.
"""
from pathlib import Path
import sys, json, math, argparse, hashlib
import bpy
import numpy as np
from mathutils import Vector, Matrix, Quaternion, Euler
sys.path.insert(0,str(Path(__file__).resolve().parent))
import smblender as SM
from spritemotion.fitting.camera import AffineOrthographicCamera, direction_rotations
from spritemotion.rendering.ortho import blender_camera_params

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'workspace/ultima-online/female-locomotion'
MOTION=json.loads((OUT/'motion-targets.json').read_text())
parser=argparse.ArgumentParser();parser.add_argument('--pilot',action='store_true');parser.add_argument('--no-render',action='store_true')
args=SM.parse_args(parser)
scene=bpy.context.scene
rig=bpy.data.objects['Female_Rig']
meshes=[o for o in scene.objects if o.type=='MESH']
rest={b.name:b.matrix_local.copy() for b in rig.data.bones}
resthead={n:m.translation.copy() for n,m in rest.items()}
idle={n:Vector(v) for n,v in MOTION['actions']['Idle']['frames'][0].items()}
rig.animation_data_clear()
for o in meshes:o.animation_data_clear()
rig.show_in_front=True
for p in rig.pose.bones:p.rotation_mode='QUATERNION'


def update():bpy.context.view_layer.update()


def head(n):return rig.pose.bones[n].matrix.translation.copy()


def aim(bone,child,direction,factor=1.):
    current=head(child)-head(bone)
    if current.length<1e-6 or direction.length<1e-6:return
    rotation=current.rotation_difference(direction)
    if factor<1:rotation=Quaternion().slerp(rotation,factor)
    pb=rig.pose.bones[bone];m=pb.matrix.copy();loc=m.translation.copy()
    pb.matrix=Matrix.Translation(loc) @ rotation.to_matrix().to_4x4() @ Matrix.Translation(-loc) @ m
    update()


def mesh_bounds():
    dg=bpy.context.evaluated_depsgraph_get();arrays=[]
    for obj in meshes:
        ev=obj.evaluated_get(dg);v=np.empty(len(ev.data.vertices)*3,dtype=np.float32);ev.data.vertices.foreach_get('co',v);v=v.reshape(-1,3)
        m=np.array(ev.matrix_world);arrays.append(v@m[:3,:3].T+m[:3,3])
    pts=np.concatenate(arrays)
    if not np.isfinite(pts).all():raise RuntimeError('Non-finite mesh coordinates')
    return pts.min(0),pts.max(0)


def reset():
    for p in rig.pose.bones:p.matrix_basis=Matrix.Identity(4)
    update()


def orient_root(j):
    lateral=j['leg_A_hip']-j['leg_B_hip'];lateral.z*=.3;lateral.normalize()
    up=j['neck']-j['pelvis'];up.normalize();up=Vector((up.x*.30,up.y*.30,1)).normalized()
    forward=up.cross(lateral).normalized();lateral=forward.cross(up).normalized()
    rot=Matrix((lateral,forward,up)).transposed().to_quaternion()
    bob=(j['pelvis'].z-idle['pelvis'].z)*1.10
    location=resthead['pelvis']+Vector(((j['pelvis'].x-idle['pelvis'].x)*.65,(j['pelvis'].y-idle['pelvis'].y)*.65,bob-.035))
    rig.pose.bones['pelvis'].matrix=Matrix.Translation(location) @ (rot @ rest['pelvis'].to_quaternion()).to_matrix().to_4x4()
    update()
    # Distribute torso lean rather than rotating around imported bone tail axes.
    aim('spine_01','neck_01',j['neck']-j['pelvis'],.70)
    aim('neck_01','head',j['head']-j['neck'],.50)


def leg_ik(side,chain,j):
    thigh,calf,foot='thigh_'+side,'calf_'+side,'foot_'+side
    hip=head(thigh)
    l1=(resthead[calf]-resthead[thigh]).length;l2=(resthead[foot]-resthead[calf]).length
    pref='leg_'+chain+'_'
    source_length=(idle[pref+'knee']-idle[pref+'hip']).length+(idle[pref+'ankle']-idle[pref+'knee']).length
    scale=(l1+l2)/source_length
    target=resthead[foot]+(j[pref+'ankle']-idle[pref+'ankle'])*scale
    target.z=max(resthead[foot].z-.012,target.z)
    v=target-hip;dist=max(abs(l1-l2)+.005,min(v.length,l1+l2-.002));axis=v.normalized();target=hip+axis*dist
    # Source knee supplies the bend plane; reject a backward knee when views disagree.
    source_axis=(j[pref+'ankle']-j[pref+'hip']).normalized()
    source_pole=j[pref+'knee']-j[pref+'hip'];source_pole-=source_axis*source_pole.dot(source_axis)
    # Reconstruct the bend direction in source proportions first. Projecting a
    # long source thigh onto a wider target stance can incorrectly flip knees inward.
    if source_pole.length>1e-5:source_pole.normalize()
    pole=Vector((max(-.12,min(.12,source_pole.x*.15)),-1,0))
    pole-=axis*pole.dot(axis)
    pole.normalize()
    along=(l1*l1-l2*l2+dist*dist)/(2*dist)
    height=math.sqrt(max(0,l1*l1-along*along))
    knee=hip+axis*along+pole*height
    aim(thigh,calf,knee-hip)
    aim(calf,foot,target-head(calf))
    # Keep soles controlled; source toe positions guide modest yaw and swing pitch.
    source=j[pref+'toe']-j[pref+'ankle'];base=idle[pref+'toe']-idle[pref+'ankle']
    yaw=max(-.25,min(.25,math.atan2(source.x,max(.05,-source.y))))
    pitch=max(-.40,min(.40,-math.atan2(source.z,max(.05,math.hypot(source.x,source.y)))+math.atan2(base.z,max(.05,math.hypot(base.x,base.y)))))
    pb=rig.pose.bones[foot]
    pb.matrix=Matrix.Translation(pb.matrix.translation) @ (Euler((pitch,0,yaw),'XYZ').to_quaternion() @ rest[foot].to_quaternion()).to_matrix().to_4x4()
    update()


def curl_grip(side):
    """Close fingers toward the palm in anatomical hand space, with thumb opposition."""
    hand='hand_'+side
    # The imported right pinky_01 pivot is at middle_02, not its mirrored knuckle.
    # Use the intact left knuckle span as the anatomical reference for both hands.
    across=resthead['pinky_01_l']-resthead['index_01_l']
    if side=='r':across.x=-across.x
    knuckle_across=across.copy()
    forward=resthead['middle_03_'+side]-resthead['middle_01_'+side]
    inward=Vector((-1 if side=='l' else 1,0,0))
    if across.cross(forward).dot(inward)<0:across=-across
    delta=rig.pose.bones[hand].matrix @ rest[hand].inverted()
    axis=(delta.to_3x3()@across).normalized()
    for finger,first_angle in [('index',95),('middle',95),('ring',95),('pinky',95)]:
        for digit,angle in [(1,first_angle),(2,50),(3,25)]:
            pb=rig.pose.bones[f'{finger}_{digit:02}_{side}'];m=pb.matrix.copy();loc=m.translation.copy()
            if finger=='pinky' and digit==1 and side=='r':
                pivot=resthead['pinky_01_l'].copy();pivot.x=-pivot.x
                loc=delta@pivot
            pb.matrix=Matrix.Translation(loc) @ Matrix.Rotation(math.radians(angle),4,axis) @ Matrix.Translation(-loc) @ m
            update()
        # Steer the distal pad into the palm rather than letting the long stylized
        # fingertips overshoot toward the wrist when the hand closes.
        n=f'{finger}_03_{side}';pb=rig.pose.bones[n]
        palm=delta @ (resthead[hand]*.35+resthead['middle_01_'+side]*.65)
        rest_direction=resthead[n]-resthead[f'{finger}_02_{side}']
        current=(pb.matrix @ rest[n].inverted()).to_3x3() @ rest_direction
        turn=current.rotation_difference(palm-pb.matrix.translation)
        if turn.angle>math.radians(85):turn=Quaternion().slerp(turn,math.radians(85)/turn.angle)
        m=pb.matrix.copy();loc=m.translation.copy()
        pb.matrix=Matrix.Translation(loc) @ turn.to_matrix().to_4x4() @ Matrix.Translation(-loc) @ m
        update()
    # Abduct the thumb outside the index side, then bend it down. A target inside
    # the finger mass makes the distal thumb poke through the folded fingers.
    outside=(delta.to_3x3() @ -knuckle_across).normalized()
    down=(delta.to_3x3() @ (resthead['middle_01_'+side]-resthead[hand])).normalized()
    aim('thumb_01_'+side,'thumb_02_'+side,outside*.95+down*.15)
    aim('thumb_02_'+side,'thumb_03_'+side,down*.85+outside*.45)
    n='thumb_03_'+side;pb=rig.pose.bones[n]
    current=(pb.matrix @ rest[n].inverted()).to_3x3() @ (resthead[n]-resthead['thumb_02_'+side])
    turn=current.rotation_difference(down-outside*.10)
    m=pb.matrix.copy();loc=m.translation.copy()
    pb.matrix=Matrix.Translation(loc) @ turn.to_matrix().to_4x4() @ Matrix.Translation(-loc) @ m
    update()


def apply_pose(j,clip_name):
    reset();orient_root(j)
    for side,chain in [('l','A'),('r','B')]:
        pref='arm_'+chain+'_'
        aim('upperarm_'+side,'lowerarm_'+side,j[pref+'elbow']-j[pref+'shoulder'])
        aim('lowerarm_'+side,'hand_'+side,j[pref+'wrist']-j[pref+'elbow'])
        # Her hips are wider than the motion-source model; keep a low fist clear
        # of the thigh instead of letting the closed fingers disappear into it.
        wrist=head('hand_'+side)
        if wrist.z<1.20 and wrist.y>-.20:
            clearance=Vector((.07 if side=='l' else -.07,0,0))
            aim('upperarm_'+side,'lowerarm_'+side,j[pref+'elbow']-j[pref+'shoulder']+clearance)
            aim('lowerarm_'+side,'hand_'+side,j[pref+'wrist']-j[pref+'elbow'])
        aim('hand_'+side,'middle_01_'+side,j[pref+'hand']-j[pref+'wrist'],.65)
        curl_grip(side)
        leg_ik(side,chain,j)
        # Imported thigh accessories are parented to pelvis, not to the leg.
        # Drive their rest-relative transform with thigh; retain every bind matrix.
        for extra in ['LegPlate_'+side.upper(),'Hip_'+side.upper()]:
            if extra in rest:
                rig.pose.bones[extra].matrix=rig.pose.bones['thigh_'+side].matrix @ rest['thigh_'+side].inverted() @ rest[extra]
        update()
    lo,hi=mesh_bounds()
    grounded=clip_name!='Run' or float(lo[2])<.055
    lift=.001-float(lo[2]) if grounded else max(0.,.001-float(lo[2]))
    if abs(lift)>1e-7:
        m=rig.pose.bones['pelvis'].matrix.copy();m.translation.z+=lift;rig.pose.bones['pelvis'].matrix=m;update()
    lo,hi=mesh_bounds()
    return {'floor_min_m':float(lo[2]),'height_m':float(hi[2]-lo[2]),'floor_lift_m':lift,'width_m':float(hi[0]-lo[0])}


def key_pose(frame,last_quats):
    for pb in rig.pose.bones:
        q=pb.rotation_quaternion.copy()
        if pb.name in last_quats and q.dot(last_quats[pb.name])<0:q.negate();pb.rotation_quaternion=q
        last_quats[pb.name]=q.copy()
        pb.keyframe_insert('rotation_quaternion',frame=frame,group=pb.name)
        pb.keyframe_insert('location',frame=frame,group=pb.name)
        pb.keyframe_insert('scale',frame=frame,group=pb.name)


def setup_stage():
    scene.cycles.samples=16
    scene.render.engine='CYCLES'
    prefs=bpy.context.preferences.addons['cycles'].preferences
    try:
        prefs.compute_device_type='OPTIX';prefs.get_devices()
        for dev in prefs.devices:dev.use=dev.type!='CPU'
        if any(d.use for d in prefs.devices):scene.cycles.device='GPU'
    except Exception:scene.cycles.device='CPU'
    scene.cycles.use_denoising=True
    scene.render.use_persistent_data=True
    scene.render.film_transparent=True
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
    scene.render.fps=30
    scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.35,.42,.55,1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.55
    for name,loc,power,size,color in [('SM_Key',(3,-4,6),650,4,(1,.90,.80)),('SM_Fill',(-4,-2,3),450,3,(.75,.85,1)),('SM_Rim',(1,3,4),700,3,(1,.95,.88))]:
        obj=bpy.data.objects.new(name,bpy.data.lights.new(name,'AREA'));scene.collection.objects.link(obj)
        obj.location=loc;obj.rotation_euler=(Vector((0,0,1))-obj.location).to_track_quat('-Z','Y').to_euler()
        obj.data.energy=power;obj.data.shape='DISK';obj.data.size=size;obj.data.color=color
    camera=AffineOrthographicCamera(np.array(MOTION['camera']['matrix']),np.array([128,192]))
    uo=SM.setup_camera(scene,blender_camera_params(camera,256,256),'SM_UO_Camera')
    uo.data.show_background_images=True
    bg=uo.data.background_images.new()
    bg.image=bpy.data.images.load(str(OUT/'references/idle_d3_f00.png'))
    bg.alpha=.35;bg.display_depth='BACK';bg.frame_method='FIT'
    beauty=bpy.data.objects.new('SM_Review_Camera',bpy.data.cameras.new('SM_Review_Camera'));scene.collection.objects.link(beauty)
    beauty.data.type='ORTHO';beauty.data.ortho_scale=2.18
    beauty.location=(3,-6,3.0);beauty.rotation_euler=(Vector((0,0,.92))-beauty.location).to_track_quat('-Z','Y').to_euler()
    return uo,beauty


def set_action(action):
    rig.animation_data.action=action
    if action.slots:rig.animation_data.action_slot=action.slots[0]


def render_clip(name,action,uo,beauty):
    clip=MOTION['actions'][name];count=len(clip['frames']);step=clip['source_frame_step']
    folder=OUT/'renders'/name.lower();folder.mkdir(parents=True,exist_ok=True)
    set_action(action)
    dirs=json.loads((ROOT/'games/ultima-online/profiles/body-401.json').read_text())['directions'];rots=direction_rotations(dirs)
    details=[]
    indices=[0] if args.pilot else list(range(count))
    for f in indices:
        scene.frame_set(1+f*step);rig.matrix_world=Matrix.Identity(4);update()
        scene.camera=beauty;scene.render.resolution_x=512;scene.render.resolution_y=640;scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1
        scene.render.filepath=str(folder/f'beauty_f{f:02}.png');bpy.ops.render.render(write_still=True)
        for d in ([3] if args.pilot else [3,4,5,6,7]):
            rig.matrix_world=Matrix(rots[d].tolist()).to_4x4();update()
            scene.camera=uo;params=blender_camera_params(AffineOrthographicCamera(np.array(MOTION['camera']['matrix']),np.array([128,192])),256,256)
            SM.setup_camera(scene,params,'SM_UO_Camera')
            scene.render.filepath=str(folder/f'd{d}_f{f:02}.png');bpy.ops.render.render(write_still=True)
        rig.matrix_world=Matrix.Identity(4);update()
    return details


def main():
    outputs={};validation=[]
    for name,clip in MOTION['actions'].items():
        action,_=SM.new_versioned_action(rig,'SM_Female_'+name)
        outputs[name]=action;last={};first=None
        for i,j in enumerate(clip['frames']):
            scene.frame_set(1+i*clip['source_frame_step'])
            stats=apply_pose({n:Vector(q) for n,q in j.items()},name)
            if i==0:first={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
            key_pose(1+i*clip['source_frame_step'],last)
            validation.append({'action':name,'source_frame':i,**stats})
        end=1+len(clip['frames'])*clip['source_frame_step']
        for p in rig.pose.bones:p.matrix_basis=first[p.name]
        key_pose(end,last)
        for _,fc in SM.fcurve_owners(action):
            for k in fc.keyframe_points:k.interpolation='LINEAR'
            fc.modifiers.new('CYCLES')
        action['source']='SpriteMotion Astra armature pass, body400, multi-view lift; natural female proportions retained'
        action['source_action']=clip['action_id'];action['loop_frames']=end-1
        print('KEYED',name,len(clip['frames']),'poses',flush=True)
    uo,beauty=setup_stage()
    if not args.no_render:
        for name,action in outputs.items():render_clip(name,action,uo,beauty)
    # An immediately playable reel plus three independent reusable Action clips.
    rig.matrix_world=Matrix.Identity(4);rig.animation_data.action=None
    track=rig.animation_data.nla_tracks.new();track.name='Idle / Walk / Run — review reel'
    start=1
    for name,repeat in [('Idle',1),('Walk',4),('Run',6)]:
        strip=track.strips.new(name,start,outputs[name]);strip.repeat=repeat;strip.blend_type='REPLACE';strip.extrapolation='NOTHING'
        if outputs[name].slots:strip.action_slot=outputs[name].slots[0]
        scene.timeline_markers.new(name,frame=start)
        start=int(strip.frame_end)
    scene.frame_start=1;scene.frame_end=start-1;scene.frame_set(1)
    scene.camera=beauty;scene.render.resolution_x=512;scene.render.resolution_y=640;scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1
    rig['motion_source']='New mask-region armature data (male body 400); not a body401-specific fit'
    rig['clips']='SM_Female_Idle / SM_Female_Walk / SM_Female_Run'
    rig['notes']='Idle holds the single source idle pose. UO-style closed grip in all clips. Walk/run loops close exactly. NLA reel: idle, 4 walks, 6 runs.'
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type=='VIEW_3D':area.spaces.active.region_3d.view_perspective='CAMERA';area.spaces.active.shading.type='MATERIAL'
    bpy.ops.object.select_all(action='DESELECT');rig.select_set(True);bpy.context.view_layer.objects.active=rig
    bpy.ops.file.pack_all()
    output=OUT/('Female_Locomotion_Pilot.blend' if args.pilot else 'UO_Female_Idle_Walk_Run.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(output),compress=True)
    report={'blend':str(output),'bones':len(rig.data.bones),'clips':{n:a.name for n,a in outputs.items()},
            'validation':validation,'textures':[{'name':im.name,'packed':bool(im.packed_file)} for im in bpy.data.images if im.source=='FILE'],
            'retarget':'Connected 3D targets lifted from the new 2D armatures; rotation retarget with two-bone leg IK and mesh-floor clearance. Bind pose and mesh weights unchanged.',
            'timing':'30 fps; walk 30-frame cycle; run 20-frame cycle; static 60-frame idle; authored timing, not recovered MUL playback metadata.',
            'limits':['Male body400 motion transferred to female proportions, not a female sprite fit.','Reprojection agreement does not establish true depth.','No root travel: in-place cycles.']}
    (OUT/'retarget-report.json').write_text(json.dumps(report,indent=2))
    print('COMPLETE',output,flush=True)


if __name__=='__main__':main()
