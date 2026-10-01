"""Refresh comparison renders and joint overlays from the fitted scene."""
from pathlib import Path
import sys,json,importlib.util
import bpy,numpy as np
from mathutils import Matrix
from bpy_extras.object_utils import world_to_camera_view
sys.path.insert(0,str(Path(__file__).resolve().parent));import smblender as SM
from spritemotion.fitting.camera import direction_rotations,AffineOrthographicCamera
from spritemotion.rendering.ortho import blender_camera_params
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/ultima-online/female-locomotion'
spec=importlib.util.spec_from_file_location('verify',Path(__file__).parent/'verify_female_locomotion.py')
verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)
scene=bpy.context.scene;rig=bpy.data.objects['Female_Rig']
targets=json.loads((OUT/'motion-targets.json').read_text());M=np.array(targets['camera']['matrix']);anchor=np.array([128,192])
rots=direction_rotations(json.loads((ROOT/'games/ultima-online/profiles/body-401.json').read_text())['directions'])
for t in rig.animation_data.nla_tracks:t.mute=True
scene.render.use_persistent_data=True;overlays={}
for name,clip in targets['actions'].items():
    action=bpy.data.actions['SM_Female_'+name];rig.animation_data.action=action;rig.animation_data.action_slot=action.slots[0]
    overlays[name]=[];folder=OUT/'renders'/name.lower()
    for f in range(len(clip['frames'])):
        rig.matrix_world=Matrix.Identity(4);scene.frame_set(1+f*clip['source_frame_step']);bpy.context.view_layer.update()
        pts=verify.joint_positions(rig)
        scene.camera=bpy.data.objects['SM_Review_Camera'];scene.render.resolution_x=512;scene.render.resolution_y=640;scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1
        beauty={}
        for n,p in pts.items():
            v=world_to_camera_view(scene,scene.camera,p);beauty[n]=[float(v.x*512),float((1-v.y)*640)]
        overlays[name].append({'beauty':beauty,'uo':{str(d):{n:(np.array(p)@rots[d].T@M.T+anchor).tolist() for n,p in pts.items()} for d in range(3,8)}})
        scene.render.filepath=str(folder/f'beauty_f{f:02}.png');bpy.ops.render.render(write_still=True)
        for d in range(3,8):
            rig.matrix_world=Matrix(rots[d].tolist()).to_4x4();bpy.context.view_layer.update()
            scene.camera=SM.setup_camera(scene,blender_camera_params(AffineOrthographicCamera(M,anchor),256,256),'SM_UO_Camera')
            scene.render.filepath=str(folder/f'd{d}_f{f:02}.png');bpy.ops.render.render(write_still=True)
(OUT/'projected-rig.json').write_text(json.dumps(overlays))
print('FITTED RENDERS COMPLETE')
