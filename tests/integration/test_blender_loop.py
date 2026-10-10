"""The full reconstruction loop through real Blender, on the sample character.

build .blend -> export rig -> fit -> key in Blender -> render every view -> compare silhouettes.
Skipped when Blender is not found; set SPRITEMOTION_BLENDER to its executable.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from spritemotion.jsonio import read_json
from spritemotion.pipeline.cli import main as cli

from conftest import REPO, SAMPLE, blender_exe, requires_blender


BLENDER = blender_exe()


def blender(*args, blend: Path | None = None) -> str:
    command = [BLENDER, "-b", "--factory-startup"] + ([str(blend)] if blend else []) + ["--python", *map(str, args)]
    done = subprocess.run(command, capture_output=True, text=True, timeout=600)
    assert "Traceback" not in done.stdout + done.stderr, done.stdout[-3000:] + done.stderr[-3000:]
    return done.stdout


@requires_blender
def test_blender_smoke(tmp_path):
    out = blender(REPO / "tools" / "blender" / "tests" / "smoke_test.py", "--", "--out", tmp_path)
    assert "6/6 Blender checks passed" in out, out[-2000:]


@requires_blender
def test_sample_loop(tmp_path):
    mapping = SAMPLE / "rig" / "sample-mapping.json"
    blend, rig, fit = tmp_path / "sample.blend", tmp_path / "rig.json", tmp_path / "fit.json"
    blender(SAMPLE / "build_blend.py", "--", "--out", blend)
    blender(REPO / "tools" / "blender" / "export_rig.py", "--", "--out", rig, blend=blend)
    assert cli(["fit", str(SAMPLE), "--sequence", "wave", "--rig", str(rig), "--mapping", str(mapping),
                "--out", str(fit)]) == 0
    posed = tmp_path / "wave.blend"
    blender(REPO / "tools" / "blender" / "apply_solution.py", "--", "--solution", fit, "--action", "wave",
            "--mapping", mapping, "--dataset", SAMPLE, "--report", tmp_path / "apply.json", "--save", posed, blend=blend)
    applied = read_json(tmp_path / "apply.json")
    assert applied["max_fk_delta"] < 1e-4
    assert applied["mean_px"] < 1.5
    blender(REPO / "tools" / "blender" / "render_views.py", "--", "--dataset", SAMPLE, "--sequence", "wave",
            "--out", tmp_path / "renders", blend=posed)
    assert cli(["compare", str(SAMPLE), "--renders", str(tmp_path / "renders"), "--sequences", "wave",
                "--out", str(tmp_path / "compare.json")]) == 0
    summary = read_json(tmp_path / "compare.json")["summary"]
    assert summary["missing_renders"] == 0
    assert min(summary["by_direction"].values()) > 0.85


@requires_blender
def test_rekeying_keeps_earlier_passes(tmp_path):
    """A second pass saved over the same scene keeps the first as a file version and as an action."""
    from spritemotion.pipeline import versions
    mapping = SAMPLE / "rig" / "sample-mapping.json"
    blend = tmp_path / "sample.blend"
    blender(SAMPLE / "build_blend.py", "--", "--out", blend)
    for truth in ("wave", "walk"):
        blender(REPO / "tools" / "blender" / "apply_solution.py", "--",
                "--solution", SAMPLE / "truth" / f"{truth}.pose-solution.json", "--action", "fit_wave",
                "--mapping", mapping, "--save", blend, blend=blend)
    history = versions.load_history(blend)["versions"]
    assert len(history) == 3              # the file build_blend made, pass 1, pass 2
    assert versions.version_file(blend, 2).exists()
    assert history[-1]["actions"]["fit_wave"]["previous_kept_as"] == "fit_wave.v001"
    lister = tmp_path / "list_actions.py"
    lister.write_text("import bpy\n"
                      "print('ACTIONS', sorted(a.name for a in bpy.data.actions if a.name.startswith('fit_')))\n")
    out = blender(lister, blend=blend)
    assert "ACTIONS ['fit_wave', 'fit_wave.v001']" in out


CHECK_SCRIPTS = sorted(Path(__file__).parent.glob("blender_*_check.py"))


@pytest.mark.parametrize("script", CHECK_SCRIPTS, ids=lambda path: path.stem)
@requires_blender
def test_blender_check_script(script):
    """Every tests/integration/blender_*_check.py is a Blender script that exits non-zero when an assert fails."""
    done = subprocess.run([BLENDER, "--background", "--factory-startup", "--python-exit-code", "1",
                           "--python", str(script)], capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]
