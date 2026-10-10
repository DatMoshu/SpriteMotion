"""The installable core: schemas ship as package data and the package imports with the standard library only."""
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from spritemotion import __version__, schemas

REPO = Path(__file__).resolve().parents[2]

SCHEMA_NAMES = sorted(p.name for p in schemas.SCHEMA_DIR.glob("*.schema.json"))

STDLIB_ONLY = """
import sys
sys.path.insert(0, {target!r})
import spritemotion, spritemotion.jsonio, spritemotion.schemas as s, spritemotion.transfer as t, spritemotion.fit_rules as fr
assert fr.resolve({{}}, {{}}, {{'id': 'i', 'part': 'p'}})['scale'] == 1
for kind in s.SCHEMA_FILES:
    assert s.load_schema(kind)
for name in {names!r}:
    assert s.load_file(name)
artifact = t.read({fixture!r})
assert len(artifact.frames) == 25 and artifact.frame(4, 4, 0).centre == (-22, -12)
leaked = sorted(m for m in ("numpy", "PIL") if m in sys.modules)
assert not leaked, leaked
print(s.version(), len(s.SCHEMA_FILES))
"""


def test_version_matches_pyproject():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    declared = next(line for line in text.splitlines() if line.startswith("version = "))
    assert declared.split('"')[1] == __version__ == schemas.version()


def test_schema_files_live_only_in_the_package():
    assert SCHEMA_NAMES
    assert not (REPO / "schemas").exists()
    assert set(schemas.SCHEMA_FILES.values()) <= set(SCHEMA_NAMES)


def test_load_file_and_path_reject_other_names():
    assert schemas.load_file("fit-adjustments.schema.json")["type"] == "object"
    assert schemas.path("starter-catalog.schema.json").is_file()
    assert schemas.load_file("fit-lab-view.schema.json")["properties"]["schema"]["const"] == "spritemotion.fit-lab-view"
    for bad in ("../pyproject.toml", "missing.schema.json", "game.json"):
        with pytest.raises((ValueError, FileNotFoundError)):
            schemas.path(bad)


def test_wheel_carries_every_schema_and_core_imports_without_imaging(tmp_path):
    out = tmp_path / "wheel"
    build = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "-w", str(out), str(REPO)],
                           capture_output=True, text=True, cwd=tmp_path)
    if build.returncode:
        pytest.skip("cannot build a wheel here (setuptools missing?): " + build.stderr[-300:])
    wheel = next(out.glob("spritemotion-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata = archive.read(next(n for n in names if n.endswith(".dist-info/METADATA"))).decode()
    for name in SCHEMA_NAMES:
        assert f"spritemotion/schemas/{name}" in names, name
    assert not any(n.startswith("schemas/") for n in names)
    assert "spritemotion/fit_rules.py" in names and "spritemotion/web/fit-rules.mjs" in names
    assert "Requires-Dist: numpy" not in metadata.split("Provides-Extra: imaging")[0]

    # Import from the unpacked wheel, not the checkout, with the standard library only.
    target = tmp_path / "site"
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(target)
    # -S leaves out site-packages, so numpy and Pillow could not be imported even by accident.
    run = subprocess.run([sys.executable, "-I", "-S", "-c", STDLIB_ONLY.format(names=SCHEMA_NAMES, target=str(target),
                                                                        fixture=str(REPO / "tests/fixtures/transfer"))],
                         capture_output=True, text=True, cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    assert run.stdout.split()[0] == __version__
