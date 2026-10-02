"""Blender block hook: resolve fits from immutable rest geometry and rebuild occlusion."""
import math
from pathlib import Path
import sys

import bpy
from mathutils import Euler, Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fit-lab'))
from fit_rules import resolve


def transform(fit, center):
    return (Matrix.Translation(center + Vector(fit['offset'])) @
            Euler(tuple(math.radians(v) for v in fit['rotate']), 'XYZ').to_matrix().to_4x4() @
            Matrix.Scale(fit['scale'], 4) @ Matrix.Translation(-center))


class BlockFit:
    def __init__(self, spec, rig, body, objects, mapping, initial, center, extra):
        self.spec, self.rig, self.body, self.objects = spec, rig, body, objects
        self.mapping, self.initial, self.center, self.extra = mapping, initial, center, extra
        self.matrices = [o.matrix_basis.copy() for o in objects]
        self.original_body = body.data.copy()
        self.report = {}

    def with_extra(self, fit):
        return {**fit, 'offset':[a+b for a,b in zip(fit['offset'],self.extra['offset'])],
                'rotate':[a+b for a,b in zip(fit['rotate'],self.extra['rotate'])], 'scale':fit['scale']*self.extra['scale']}

    def __call__(self, action, direction, env):
        env['fix_clear']()
        env['FIX_CACHE'].clear()
        item = self.spec.get('fit_item', {'id':'', 'slot':self.spec['part'], 'part':self.spec.get('pack_part','')})
        fit = resolve(self.spec.get('fit_adjustments', {'parts':{},'items':{}}), self.mapping, item, action, direction)
        mode = self.spec.get('occlusion', fit['occlusion'])
        old_pose, old_dir = self.rig.data.pose_position, self.rig.get('uo_direction',0)
        self.rig.data.pose_position='REST'; self.rig['uo_direction']=0; self.rig.update_tag()
        bpy.context.view_layer.update()
        if self.initial is not None:
            delta = transform(self.with_extra(fit), self.center) @ transform(self.with_extra(self.initial), self.center).inverted()
            for obj, original in zip(self.objects,self.matrices): obj.matrix_basis = delta @ original
        old = self.body.data; self.body.data = self.original_body.copy()
        if old.users == 0: bpy.data.meshes.remove(old)
        bpy.context.view_layer.update()
        hidden = 0
        hide = self.spec.get('hide_body') or fit['hide_body']
        if hide.get('enabled') and mode == 'clothing':
            import pack_fit
            hidden = pack_fit.hide_body_under(self.body,self.objects,hide.get('outward',.02),hide.get('inward',.01))
        self.rig.data.pose_position=old_pose; self.rig['uo_direction']=old_dir; self.rig.update_tag()
        bpy.context.view_layer.update()
        torso = {'pelvis','spine','chest','neck','clavicle'}
        bones = set(env['OCCLUDERS'])
        if mode == 'body': bones |= torso
        elif mode == 'none': bones = set()
        # Hidden body faces change the triangle count, so every cached triangle mask is rebuilt.
        mask = env['body_part_mask']
        env['OCCLUDER_TRIS'] = mask(bones)
        if 'HIDER_TRIS' in env:
            # Newer renderer: the holdout has its own mask, without the parts the item is skinned to.
            # An attachment is hidden by the torso even when it is bound to it.
            env['HIDER_TRIS'] = mask(bones - env.get('WORN', set()) | (torso if mode == 'body' else set()))
            if env.get('TORSO_TRIS') is not None: env['TORSO_TRIS'] = mask(torso)
        self.report[f'{action},{direction}'] = {'fit':fit, 'occlusion':mode, 'hidden_body_faces':hidden}
