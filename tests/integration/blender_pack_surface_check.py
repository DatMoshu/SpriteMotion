"""Run with Blender --background --factory-startup --python <this file>. No external assets needed."""
from pathlib import Path
import sys
import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/uo-content'))
from pack_fit import clear_surface

bpy.ops.mesh.primitive_cube_add(size=2)
body = bpy.context.object
rig = bpy.data.objects.new('Target', None)
bpy.context.collection.objects.link(rig)
# The algorithm must use rig space, independently of the body's object transform.
body.matrix_world = Matrix.Translation((2, 0, 0))
rig.matrix_world = Matrix.Translation((2, 0, 0))
mesh = bpy.data.meshes.new('Shell')
mesh.from_pydata([(0.98, 0, 0), (1.1, 0, 0), (0, 0, 0)], [], [])
shell = bpy.data.objects.new('Shell', mesh)
bpy.context.collection.objects.link(shell)
clear_surface([shell], body, rig, .004)
assert abs(mesh.vertices[0].co.x - 1.004) < 1e-5, 'Nearby penetration must clear the body'
assert abs(mesh.vertices[1].co.x - 1.1) < 1e-5, 'Outside geometry must stay unchanged'
assert mesh.vertices[2].co.length < 1e-5, 'Distant geometry must not snap to another body region'
print('PASS: surface clearance, coordinate spaces, outside and distant geometry')
