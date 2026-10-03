"""Blender block hook: resolve fits from immutable rest geometry and rebuild occlusion."""
import math
from pathlib import Path
import sys

import bpy
from mathutils import Euler, Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fit-lab'))
from fit_rules import resolve
from occlusion import BodyHoldout


def transform(fit, center):
    return (Matrix.Translation(center + Vector(fit['offset'])) @
            Euler(tuple(math.radians(v) for v in fit['rotate']), 'XYZ').to_matrix().to_4x4() @
            Matrix.Diagonal(Vector((fit['scale'],fit['scale']*fit.get('depth_scale',1),fit['scale'],1))) @ Matrix.Translation(-center))


def side_weights(obj, vertex):
    weights = [0., 0.]
    total = 0.
    for group in vertex.groups:
        name = obj.vertex_groups[group.group].name
        total += group.weight
        if name.endswith('.L'): weights[0] += group.weight
        if name.endswith('.R'): weights[1] += group.weight
    return [w / total if total else 0. for w in weights]


def apply_side_offsets(geometry, sides):
    offsets = [Vector(sides.get(side, [0, 0, 0])) for side in ('left', 'right')]
    for obj, original, weights in geometry:
        inverse = obj.matrix_world.to_3x3().inverted()
        local = [inverse @ offset for offset in offsets]
        for vertex, rest, pair in zip(obj.data.vertices, original, weights):
            vertex.co = rest + local[0] * pair[0] + local[1] * pair[1]
        obj.data.update()


class BlockFit:
    def __init__(self, spec, rig, body, objects, mapping, initial, center, extra):
        self.spec, self.rig, self.body, self.objects = spec, rig, body, objects
        self.mapping, self.initial, self.center, self.extra = mapping, initial, center, extra
        self.matrices = [o.matrix_basis.copy() for o in objects]
        self.side_geometry = [(o, [v.co.copy() for v in o.data.vertices],
                               [side_weights(o, v) for v in o.data.vertices]) for o in objects]
        self.original_body = body.data.copy()
        self.holdout = BodyHoldout(body, self.original_body, objects)
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
        bpy.context.view_layer.update()
        apply_side_offsets(self.side_geometry, fit.get('sides', {}))
        old = self.body.data; self.body.data = self.original_body.copy()
        if old.users == 0: bpy.data.meshes.remove(old)
        bpy.context.view_layer.update()
        hidden = 0
        hide = self.spec.get('hide_body') or fit['hide_body']
        self.holdout.configure(mode, hide)
        # Final holdout uses the complete body, even when skin is removed from
        # the fitting/push-out mesh below. Never globally exempt a worn region.
        env['body_occlusion'] = lambda free, margin: self.holdout.render(env, free, margin)
        if hide.get('enabled') and mode == 'clothing':
            import pack_fit
            hidden = pack_fit.hide_body_under(self.body,self.objects,hide.get('outward',.02),hide.get('inward',.01))
        self.rig.data.pose_position=old_pose; self.rig['uo_direction']=old_dir; self.rig.update_tag()
        bpy.context.view_layer.update()
        # The deformation solver still uses the fitting mesh and its original
        # collision regions. It never controls visibility of the pristine proxy.
        env['OCCLUDER_TRIS'] = env['body_part_mask'](set(env['OCCLUDERS']))
        self.report[f'{action},{direction}'] = {'fit':fit, 'occlusion':mode, 'hidden_body_faces':hidden}
