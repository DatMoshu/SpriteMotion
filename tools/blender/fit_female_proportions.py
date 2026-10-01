"""Fit the female comparison proportions, retaining source meshes and bind pose."""
from pathlib import Path
import math,json
import bpy,numpy as np
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'workspace/ultima-online/female-locomotion'
scene=bpy.context.scene;rig=bpy.data.objects['Female_Rig']
meshes=[o for o in scene.objects if o.type=='MESH']
def update():bpy.context.view_layer.update()
def head(n):return rig.pose.bones[n].matrix.translation.copy()
def aim(a,b,target):
    pb=rig.pose.bones[a];m=pb.matrix.copy();p=m.translation.copy()
    q=(head(b)-p).rotation_difference(target-p)
    pb.matrix=Matrix.Translation(p)@q.to_matrix().to_4x4()@Matrix.Translation(-p)@m;update()
def floor():
    dg=bpy.context.evaluated_depsgraph_get();low=1e6
    for obj in meshes:
        ev=obj.evaluated_get(dg);v=np.empty(len(ev.data.vertices)*3);ev.data.vertices.foreach_get('co',v)
        m=np.array(ev.matrix_world);p=v.reshape(-1,3)@m[:3,:3].T+m[:3,3];low=min(low,float(p[:,2].min()))
    return low
for track in rig.animation_data.nla_tracks:track.mute=True
report={'head_scale':1.12,'shoulder_width_added_m':.04,'thigh_length_m':.461,'shin_length_m':.453,'clips':{}}
for name,duration in [('Idle',60),('Walk',30),('Run',20)]:
    action=bpy.data.actions['SM_Female_'+name];rig.animation_data.action=action;rig.animation_data.action_slot=action.slots[0]
    # Read all source poses before writing any keys, preserving existing interpolation.
    source=[]
    for f in range(1,duration+2):
        scene.frame_set(f);update();source.append({p.name:p.matrix_basis.copy() for p in rig.pose.bones})
    lows=[];first=None;lastq={}
    for f,pose in enumerate(source,1):
        scene.frame_set(f)
        for p in rig.pose.bones:p.matrix_basis=pose[p.name]
        update()
        rig.pose.bones['head'].scale*=1.12;update()
        for side,sign in [('l',1),('r',-1)]:
            pb=rig.pose.bones['upperarm_'+side];m=pb.matrix.copy();m.translation.x+=sign*.02;pb.matrix=m;update()
            a,b,c=['thigh_'+side,'calf_'+side,'foot_'+side]
            hip,knee,ankle=head(a),head(b),head(c);old_thigh=rig.pose.bones[a].matrix.copy()
            extras={n:rig.pose.bones[n].matrix.copy() for n in ['LegPlate_'+side.upper(),'Hip_'+side.upper()]}
            foot_rotation=rig.pose.bones[c].matrix.to_quaternion()
            l1=(knee-hip).length;l2=(ankle-knee).length
            target=ankle.copy();target.x=hip.x*.85+(ankle.x-hip.x)*.5
            if name=='Idle':target.y=hip.y+.065
            axis=target-hip;distance=max(abs(l1-l2)+.0001,min(axis.length,l1+l2-.0001));axis.normalize()
            pole=Vector((0,-1,0));pole-=axis*pole.dot(axis);pole.normalize()
            along=(l1*l1-l2*l2+distance*distance)/(2*distance)
            bend=hip+axis*along+pole*math.sqrt(max(0,l1*l1-along*along))
            aim(a,b,bend);aim(b,c,hip+axis*distance)
            pb=rig.pose.bones[c];pb.matrix=Matrix.Translation(head(c))@foot_rotation.to_matrix().to_4x4();update()
            delta=rig.pose.bones[a].matrix@old_thigh.inverted()
            for n,m in extras.items():rig.pose.bones[n].matrix=delta@m
            update()
        low=floor()
        if name!='Run' or low<.055:
            pb=rig.pose.bones['pelvis'];m=pb.matrix.copy();m.translation.z+=.001-low;pb.matrix=m;update()
        lows.append(floor())
        if f==1:first={p.name:p.matrix_basis.copy() for p in rig.pose.bones}
        if f==duration+1:
            for p in rig.pose.bones:p.matrix_basis=first[p.name]
            update()
        for pb in rig.pose.bones:
            if pb.name in lastq and pb.rotation_quaternion.dot(lastq[pb.name])<0:pb.rotation_quaternion.negate()
            lastq[pb.name]=pb.rotation_quaternion.copy()
            for prop in ['location','rotation_quaternion','scale']:pb.keyframe_insert(prop,frame=f,group=pb.name)
    report['clips'][name]={'min_floor_m':min(lows),'checked_frames':len(lows)}
    assert min(lows)>-.001
# Grayscale albedo and neutral illumination, in both final Blender and WebGL.
for im in bpy.data.images:
    if im.source=='FILE' and '_D.' in im.name:
        pixels=np.empty(len(im.pixels),np.float32);im.pixels.foreach_get(pixels);p=pixels.reshape(-1,4)
        lum=p[:,:3]@np.array([.2126,.7152,.0722]);p[:,:3]=lum[:,None]
        im.pixels.foreach_set(pixels);im.update();im.pack()
for obj in scene.objects:
    if obj.type=='LIGHT':obj.data.color=(1,1,1)
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.45,.45,.45,1)
rig.animation_data.action=None
for track in rig.animation_data.nla_tracks:track.mute=False
scene.frame_set(1);bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'UO_Female_Fitted.blend'),compress=True)
(OUT/'proportion-fit.json').write_text(json.dumps(report,indent=2));print(report)
