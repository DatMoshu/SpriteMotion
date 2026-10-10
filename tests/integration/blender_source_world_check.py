"""Run with Blender --background --factory-startup --python <this file>. No external assets needed."""
from pathlib import Path
import math
import sys
import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/uo-content'))
from pack_fit import source_world

# An FBX armature carries the 0.01 unit scale and the Y-up rotation; its skinned mesh sits under it with identity
# local transforms. matrix_world can read back as identity right after import (the Elven Warriors hair), so the
# world matrix has to come from the parent chain.
arm = bpy.data.objects.new('Armature', None)
bpy.context.collection.objects.link(arm)
arm.matrix_basis = Matrix.Rotation(math.pi/2, 4, 'X') @ Matrix.Scale(.01, 4)
mesh = bpy.data.objects.new('Mesh', bpy.data.meshes.new('Mesh'))
bpy.context.collection.objects.link(mesh)
mesh.parent = arm
mesh.matrix_parent_inverse = Matrix.Identity(4)
mesh.matrix_world = Matrix.Identity(4)           # the stale value
want = arm.matrix_basis
got = source_world(mesh)
assert all(abs(got[i][j]-want[i][j]) < 1e-9 for i in range(4) for j in range(4)), 'World must come from the parent chain'
assert source_world(arm) == arm.matrix_basis
print('PASS: imported mesh world matrix from the parent chain')
