"""Shim: the fit rules live in common/fit_rules.py (spritemotion.fit_rules).

Loaded by path so it also works inside Blender's Python, where `spritemotion` is not installed.
"""
import importlib.util
from pathlib import Path

REAL = Path(__file__).resolve().parents[2] / 'common' / 'fit_rules.py'
_spec = importlib.util.spec_from_file_location('_spritemotion_fit_rules', REAL)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
resolve = _module.resolve
stored_direction = _module.stored_direction
