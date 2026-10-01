"""Shared test setup: import paths and the procedurally generated sample character."""
from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "examples" / "sample-character"
UO = REPO / "games" / "ultima-online"

if importlib.util.find_spec("spritemotion") is None:  # running without `pip install -e .`
    _init = REPO / "common" / "__init__.py"
    _spec = importlib.util.spec_from_file_location("spritemotion", _init, submodule_search_locations=[str(_init.parent)])
    sys.modules["spritemotion"] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(sys.modules["spritemotion"])


def load_module(path: Path, name: str):
    """Import a script that lives outside the package (game adapters, examples, migrations)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sample_copy(tmp_path) -> Path:
    """A writable copy of the committed sample character dataset."""
    target = tmp_path / "sample"
    shutil.copytree(SAMPLE, target, ignore=shutil.ignore_patterns("*.py", "__pycache__", "README.md"))
    return target
