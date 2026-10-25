"""Locations for generated local payloads, independent of a checkout."""
from pathlib import Path
import os
import hashlib


def external_path(path: Path, checkout: Path | None = None) -> Path:
    """Reject physical output/environment locations inside any Git checkout."""
    path = Path(path).expanduser().resolve()
    checkout = (checkout or Path(__file__).resolve().parents[1]).resolve()
    if path == checkout or checkout in path.parents:
        raise ValueError('Generated storage must be outside the checkout. Set SPRITEMOTION_WORK_ROOT / SPRITEMOTION_CONTENT_HOME.')
    for parent in (path, *path.parents):
        if (parent / '.git').exists():
            raise ValueError('Generated storage must be outside every Git checkout: ' + str(path))
    return path


def work_root() -> Path:
    """Environment override, then the fleet shared work area (portable off Windows)."""
    default = 'D:/_agentShared/work/spritemotion' if os.name == 'nt' else '~/.cache/spritemotion'
    return external_path(Path(os.environ.get('SPRITEMOTION_WORK_ROOT') or default))


def content_home() -> Path:
    return external_path(Path(os.environ.get('SPRITEMOTION_CONTENT_HOME') or work_root() / 'content-studio'))


def backend_home() -> Path:
    """One external canonical input installation, shared by all checkouts."""
    return external_path(Path(os.environ.get('SPRITEMOTION_BACKEND') or work_root() / 'inputs/canonical-model'))


def checkout_venv(checkout: Path) -> Path:
    """Separate editable installs even for checkouts with the same folder name."""
    identity = str(checkout.resolve())
    if os.name == 'nt': identity = identity.casefold()
    key = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]
    return work_root() / 'venvs' / key
