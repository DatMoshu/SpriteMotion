"""Blender side of `run.py body`: render the bare canonical body for the outfit compositor's base layer."""
import ast
import sys
from pathlib import Path
import bpy

args = sys.argv[sys.argv.index('--')+1:]
backend, out, only = Path(args[0]), args[1], args[2].split(',')
path = backend/'pipeline'/'render_uo_layer.py'
tree = ast.parse(path.read_text(encoding='utf-8'))
overrides = {'LAYER': 'body', 'ONLY': only, 'OUT_DIR': out, 'WRITE_VD': False, 'ANCHOR': (128, 192)}
for node in tree.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in overrides:
        node.value = ast.parse(repr(overrides[node.targets[0].id]), mode='eval').body
exec(compile(tree, str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)})
