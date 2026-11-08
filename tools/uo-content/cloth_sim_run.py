"""Run uo_cloth_sim.py inside Blender (it was written for a Python with bpy as a module, which the venv does not have).

    blender -b --factory-startup --python-exit-code 1 --python cloth_sim_run.py -- <uo_cloth_sim.py> <item.blend> [its args...]

uo_cloth_sim reads sys.argv[1:] as <item.blend> [args]: this sets sys.argv to that and calls its main(). Only --jobs 1:
its parallel mode starts sys.executable, which inside Blender is not Blender.
"""
import importlib.util
import sys

argv = sys.argv[sys.argv.index('--') + 1:]
script, rest = argv[0], argv[1:]
if '--jobs' in rest:
    raise SystemExit('cloth_sim_run: --jobs is not supported inside Blender')
sys.argv = [script] + rest
spec = importlib.util.spec_from_file_location('uo_cloth_sim', script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.main()
