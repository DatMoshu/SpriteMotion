"""Find the Blender executable (standard library only, so tools run it by path or as `spritemotion.blender`).

Order: SPRITEMOTION_BLENDER, the newest tools/blender-runtime build, `blender` on PATH, then the newest
`Blender Foundation/Blender */blender.exe` under %ProgramFiles% (read from the environment, never a literal path).
"""
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MISSING = ('Blender not found. Set SPRITEMOTION_BLENDER to the blender executable (Blender 4.2 or newer), '
           'or unpack a build into tools/blender-runtime/<version>/.')


def _version_key(path):
    return tuple(int(n) for n in re.findall(r'\d+', path.parent.name))


def _newest(paths):
    paths = sorted(paths, key=_version_key)
    return str(paths[-1]) if paths else None


def find_blender(root=None, environ=None):
    """Return the path to Blender, or raise RuntimeError naming SPRITEMOTION_BLENDER and tools/blender-runtime."""
    root = Path(root) if root else ROOT
    environ = os.environ if environ is None else environ
    exe = environ.get('SPRITEMOTION_BLENDER')
    if not exe:
        runtime = root / 'tools/blender-runtime'
        exe = _newest([*runtime.glob('*/blender.exe'), *runtime.glob('*/blender')])
    exe = exe or shutil.which('blender')
    if not exe:
        program_files = environ.get('ProgramFiles')
        if program_files:
            exe = _newest(Path(program_files, 'Blender Foundation').glob('Blender */blender.exe'))
    if not exe:
        raise RuntimeError(MISSING)
    return exe
