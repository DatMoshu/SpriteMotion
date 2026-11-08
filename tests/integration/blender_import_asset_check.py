"""A skinned GLB keeps its real mesh but excludes imported bone-display geometry."""
import ast
from pathlib import Path
import tempfile

import bpy
from mathutils import Vector
import numpy as np


root = Path(__file__).resolve().parents[2]
tree = ast.parse((root / 'tools/uo-content/blender_build.py').read_text(encoding='utf-8'))
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'import_asset')
exec(compile(ast.Module(body=[function], type_ignores=[]), 'import_asset', 'exec'))

with tempfile.TemporaryDirectory() as temp:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.object.armature_add()
    rig = bpy.context.object
    bpy.ops.mesh.primitive_cube_add(size=0.25, location=(0, 0, 2))
    mesh = bpy.context.object
    # A legitimate mesh may itself be named Icosphere; filtering by name is wrong.
    mesh.name = 'Icosphere'
    mesh.vertex_groups.new(name=rig.data.bones[0].name).add(list(range(8)), 1, 'REPLACE')
    mesh.modifiers.new('Skin', 'ARMATURE').object = rig
    mesh.parent = rig
    path = Path(temp) / 'skinned.glb'
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = import_asset(path)
    assert len(objects) == 1, [obj.name for obj in objects]
    points = np.array([tuple(objects[0].matrix_world @ vertex.co) for vertex in objects[0].data.vertices])
    np.testing.assert_allclose(points.min(axis=0), [-0.125, -0.125, 1.875], atol=1e-5)
    np.testing.assert_allclose(points.max(axis=0), [0.125, 0.125, 2.125], atol=1e-5)
    assert set(bpy.data.objects) == set(objects)
print('Skinned GLB imports only supplied geometry; fit bounds preserved.')
