"""Locations for generated local payloads, independent of a checkout."""
from pathlib import Path
import os
import hashlib


def work_root() -> Path:
    """Environment override, then the fleet shared work area (portable off Windows)."""
    default = 'D:/_agentShared/work/spritemotion' if os.name == 'nt' else '~/.cache/spritemotion'
    return Path(os.environ.get('SPRITEMOTION_WORK_ROOT') or default).expanduser().resolve()


def content_home() -> Path:
    return Path(os.environ.get('SPRITEMOTION_CONTENT_HOME') or work_root() / 'content-studio').expanduser().resolve()


def checkout_venv(checkout: Path) -> Path:
    """Separate editable installs even for checkouts with the same folder name."""
    identity = str(checkout.resolve())
    if os.name == 'nt': identity = identity.casefold()
    key = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]
    return work_root() / 'venvs' / key
