"""Resolve the paths in a Fit Lab `lab-items.json` against the checkout that reads it.

A lab folder lives in ignored `workspace/` and gets copied between checkouts and worktrees, so the catalog must not
pin the absolute paths of the checkout that wrote it. New catalogs carry a `root` field and store `mapping` and every
item `files` entry relative to it:

    "root": "repo"      relative to the repository (the cc0 starter pack)
    "root": "sidecar"   relative to SPRITEMOTION_SIDECAR (licensed packs, never in git)

A catalog without `root` is the legacy form with absolute paths: it still loads. If such a path is outside this
checkout and the same file exists inside it (under the repo or the sidecar), this checkout's file is used and one
warning is logged. Standard library only: runs inside Blender's Python and by path, like fit_rules.py.
"""
import json
import logging
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOTS = ('repo', 'sidecar')
log = logging.getLogger('fit-lab')


def sidecar():
    return Path(os.environ.get('SPRITEMOTION_SIDECAR', REPO.parent / 'SpriteMotion-Sidecar'))


def root_dir(root):
    if root == 'repo': return REPO
    if root == 'sidecar': return sidecar()
    raise ValueError(f"lab-items.json root must be one of {ROOTS}, not {root!r}.")


def relative(path, root):
    """Path as a catalog stores it: forward slashes, relative to `root`. Raises if it is not inside."""
    return Path(path).resolve().relative_to(root_dir(root).resolve()).as_posix()


def _inside(path, base):
    try: Path(path).resolve().relative_to(base.resolve()); return True
    except ValueError: return False


def _legacy(value, warned):
    path = Path(value)
    if any(_inside(path, base) for base in (REPO, sidecar())): return str(path)
    parts = path.parts[1:] if path.anchor else path.parts
    for base in (REPO, sidecar()):
        for i in range(len(parts)):  # longest suffix first: the shared relative part of both checkouts
            candidate = base.joinpath(*parts[i:])
            if candidate.is_file():
                if not warned:
                    log.warning('lab-items.json names %s outside this checkout; using %s instead.', path, candidate)
                    warned.append(True)
                return str(candidate)
    return str(path)


def resolve(catalog):
    """Copy of a catalog with `mapping` and item `files` absolute for this checkout."""
    out = json.loads(json.dumps(catalog))
    root = out.get('root')
    if root is None:
        warned = []
        if out.get('mapping'): out['mapping'] = _legacy(out['mapping'], warned)
        for item in out.get('items', []): item['files'] = [_legacy(f, warned) for f in item.get('files', [])]
        return out
    base = root_dir(root)
    def join(value):
        if Path(value).anchor or '..' in Path(value).parts:
            raise ValueError(f'lab-items.json with a root needs relative paths inside it, got {value!r}.')
        return str(base / value)
    if out.get('mapping'): out['mapping'] = join(out['mapping'])
    for item in out.get('items', []): item['files'] = [join(f) for f in item.get('files', [])]
    return out


def load(path):
    return resolve(json.loads(Path(path).read_text(encoding='utf-8')))
