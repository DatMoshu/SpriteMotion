"""Repository-level checks: bundled data validates, publishes nothing it must not, and matches a local client.

The last test needs the user's own Ultima Online client: set SPRITEMOTION_UO_SOURCE
to the folder holding anim.mul / anim.idx.
"""
import os
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from spritemotion.jsonio import read_json
from spritemotion.pipeline.cli import main as cli
from spritemotion.pipeline.status import dataset_status, validate_repository
from spritemotion.sprites.dataset import Dataset

from conftest import REPO, UO

ABSOLUTE_PATH = re.compile(r"(?<![\w/])[A-Za-z]:[\\/](?:Users|_repos|Games)", re.IGNORECASE)


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    return [REPO / line for line in out.splitlines() if line]


def test_bundled_data_validates():
    assert validate_repository() == []


def test_bundled_uo_annotations_keep_the_approved_corrections():
    corrections = read_json(UO / "annotations" / "body-400" / "corrections" / "action-022.json")
    approved = [(p["direction"], p["frame"]) for p in corrections["poses"] if p["review"]["status"] == "approved"]
    assert approved == [(3, f) for f in range(6)]          # the six reviewed SE death_forward poses
    estimates = read_json(UO / "annotations" / "body-400" / "estimates" / "action-001.json")
    assert {p["provenance"]["method"] for p in estimates["poses"]} <= {"rig_projection", "mirrored"}
    assert not any(p["provenance"]["independent"] for p in estimates["poses"])


def test_no_game_assets_or_local_paths_are_published():
    files = tracked_files()
    starter = REPO / 'examples/cc0-starter'
    approved = json.loads((starter / 'provenance.json').read_text())['files']
    model = REPO / 'third_party/UO_Model3D_v13'
    model_approved = json.loads((model / 'provenance.json').read_text())['files']
    for path in files:
        rel = path.relative_to(REPO).as_posix()
        assert not rel.startswith("workspace/") or rel == "workspace/README.md", rel
        if path.parent == starter and path.name in approved:
            assert path.suffix == '.glb'
            data = path.read_bytes()                      # a git-lfs pointer carries the sha256 of the real file
            pointer = re.search(rb'^oid sha256:([0-9a-f]{64})$', data, re.MULTILINE) if data.startswith(b'version https://git-lfs') else None
            digest = pointer.group(1).decode() if pointer else hashlib.sha256(data).hexdigest()
            assert digest == approved[path.name]['sha256'], rel
        elif rel.startswith('third_party/UO_Model3D_v13/') and rel.removeprefix('third_party/UO_Model3D_v13/') in model_approved:
            data = path.read_bytes()                      # a git-lfs pointer carries the sha256 of the real file
            pointer = re.search(rb'^oid sha256:([0-9a-f]{64})$', data, re.MULTILINE) if data.startswith(b'version https://git-lfs') else None
            digest = pointer.group(1).decode() if pointer else hashlib.sha256(data).hexdigest()
            assert digest == model_approved[rel.removeprefix('third_party/UO_Model3D_v13/')], rel
        else:
            assert path.suffix.lower() not in {".mul", ".uop", ".idx", ".blend", ".fbx", ".glb"}, rel
        if rel.startswith('third_party/UO_Model3D_v13/'):
            assert path.suffix.lower() not in {".vd", ".mul", ".uop", ".idx", ".pkl"}, f"client-derived or unsafe file: {rel}"
            assert not {'client', 'extract'} & set(path.parts), rel
        if rel.startswith("games/") and path.suffix.lower() in {".png", ".bmp", ".gif"}:
            pytest.fail(f"image under games/ (game art must never be committed): {rel}")
        if path.suffix.lower() in {".py", ".gd", ".json", ".md", ".bat", ".toml", ".cfg", ".godot", ".tscn",
                                  ".html", ".js", ".mjs", ".css", ".yaml", ".yml", ".txt", ".sh"} \
                and path.exists() and path.stat().st_size < 2_000_000:
            text = path.read_text(encoding="utf-8", errors="replace")
            match = ABSOLUTE_PATH.search(text)
            assert match is None, f"{rel} contains a machine-specific path: {match.group(0) if match else ''}"


@pytest.mark.skipif(not os.environ.get("SPRITEMOTION_UO_SOURCE"), reason="set SPRITEMOTION_UO_SOURCE to a UO client")
def test_uo_extraction_matches_every_bundled_pose(tmp_path):
    out = tmp_path / "body-400"
    assert cli(["extract", "--game", "ultima-online", "--character", "body-400",
                "--source", os.environ["SPRITEMOTION_UO_SOURCE"], "--out", str(out)]) == 0
    status = dataset_status(Dataset.load(out))["totals"]
    assert status["annotated"] == status["frames"] == 1680
    assert status["approved"] == 6 and status["fingerprint_mismatches"] == 0


def test_agent_routers_match_claude_sources():
    result = subprocess.run([sys.executable, str(REPO / "tools" / "agents" / "run.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


# ---- launchers: the DirectorDeck Run panel lists every .bat (rem line), and each has a .sh twin ----------------------

LAUNCHER_DIR = REPO / "launchers"
LAUNCHER_EXEMPT: set[str] = set()
COMMON_BAT = 'call "%~dp0..\\_shared\\common.bat" || exit /b 1'


def launcher_names() -> list[str]:
    names = sorted(p.relative_to(LAUNCHER_DIR).with_suffix("").as_posix() for p in LAUNCHER_DIR.glob("*/*.bat")
                   if p.parent.name != "_shared")
    return [n for n in names if n not in LAUNCHER_EXEMPT]


def bat_lines(name: str) -> list[str]:
    data = (LAUNCHER_DIR / f"{name}.bat").read_bytes()
    assert b"\n" not in data.replace(b"\r\n", b""), f"{name}.bat must use CRLF line endings only"
    return data.decode("utf-8").split("\r\n")


def bat_header(name: str) -> tuple[str, list[str]]:
    """The one-sentence rem line and the lines after it (after an optional `rem args:` line)."""
    lines = bat_lines(name)
    assert lines[0].lower() == "@echo off", f"{name}.bat: the first line must be @echo off"
    rest = [line for line in lines[1:] if line.strip()]
    assert rest[0].startswith("rem ") and not rest[0].startswith("rem args:"), \
        f"{name}.bat: the first line after @echo off must be a one-sentence rem saying what it does"
    assert rest[0].endswith("."), f"{name}.bat: the rem line is one sentence ending in a full stop"
    after = rest[1:]
    if after and after[0].startswith("rem args:"):
        after = after[1:]
    return rest[0][4:], after


def test_launchers_follow_the_run_panel_rule():
    names = launcher_names()
    assert len(names) >= 30
    for name in names:
        desc, after = bat_header(name)
        assert len(desc) <= 240, f"{name}.bat: shorten the rem line"
        assert after[0] == COMMON_BAT, f"{name}.bat: call _shared\\common.bat right after the rem lines"
        text = "\r\n".join(bat_lines(name))
        assert not re.search(r"^\s*pause\b", text, re.IGNORECASE | re.MULTILINE), f"{name}.bat reads stdin (pause)"
        assert not re.search(r"set\s+/p", text, re.IGNORECASE), f"{name}.bat reads stdin (set /p)"
        assert not re.search(r"\bchoice\b", text, re.IGNORECASE), f"{name}.bat reads stdin (choice)"


def test_every_launcher_has_a_shell_twin():
    names = launcher_names()
    sh_names = sorted(p.relative_to(LAUNCHER_DIR).with_suffix("").as_posix() for p in LAUNCHER_DIR.glob("*/*.sh")
                      if p.parent.name != "_shared")
    assert [n for n in sh_names if n not in LAUNCHER_EXEMPT] == names, "each launcher .bat needs a .sh with the same name"
    modes = {}
    listing = subprocess.run(["git", "ls-files", "-s", "--", "launchers"], cwd=REPO, capture_output=True, text=True).stdout
    for line in listing.splitlines():
        meta, path = line.split("\t")
        modes[path] = meta.split()[0]
    for name in names:
        data = (LAUNCHER_DIR / f"{name}.sh").read_bytes()
        assert b"\r" not in data, f"{name}.sh must use LF line endings"
        lines = data.decode("utf-8").split("\n")
        assert lines[0] == "#!/usr/bin/env bash", name
        assert lines[1] == "# " + bat_header(name)[0].replace("\\", "/"), f"{name}.sh: description must match the .bat rem line"
        assert "set -euo pipefail" in lines, name
        assert any(line.endswith('/../_shared/common.sh"') for line in lines), f"{name}.sh: source _shared/common.sh"
        if modes:  # an export without git metadata cannot say
            assert modes.get(f"launchers/{name}.sh") in (None, "100755"), f"{name}.sh needs the executable bit in git"
    for shared in ("common.sh", "config.sh"):
        assert b"\r" not in (LAUNCHER_DIR / "_shared" / shared).read_bytes(), shared


def test_gitattributes_keep_bat_crlf_and_sh_lf():
    attributes = (REPO / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "*.bat text eol=crlf" in attributes
    assert "*.sh text eol=lf" in attributes


def test_launcher_readme_lists_every_launcher_with_its_description():
    readme = (LAUNCHER_DIR / "README.md").read_text(encoding="utf-8")
    for name in launcher_names():
        assert f"`{name}`" in readme, f"launchers/README.md does not list {name}"
        assert bat_header(name)[0] in readme, f"launchers/README.md has a stale description for {name}"


# `[\\/]` is a backslash or a slash in a regex class; `[\/]` is the slash only. A .py file holds backslash paths
# doubled ('C:\\Windows'), so one or more separators are matched.
HARDCODED_TOOL_PATH = re.compile(r"Program Files|Windows[\\/]+Fonts|[A-Za-z]:[\\/]+Windows|[A-Za-z]:[\\/]+[^'\"\n]*blender", re.IGNORECASE)


def test_hardcoded_tool_path_pattern_matches_both_separators():
    """Lines are source text as a .py file holds them: backslashes doubled, or in a raw string."""
    hits = [
        r"font = 'C:\\Windows\\Fonts\\arial.ttf'",
        r"font = r'C:\Windows\Fonts'",
        "font = 'C:/Windows/Fonts'",
        r"exe = 'D:\\tools\\blender.exe'",
        "exe = 'D:/tools/blender.exe'",
        r"base = 'C:\\Program Files\\x'",
    ]
    misses = ["font = Path(windir, 'Fonts')", "exe = find_blender(ROOT)"]
    print(HARDCODED_TOOL_PATH.pattern)
    assert [line for line in hits if not HARDCODED_TOOL_PATH.search(line)] == []
    assert [line for line in misses if HARDCODED_TOOL_PATH.search(line)] == []


def test_code_has_no_hardcoded_windows_font_or_blender_paths():
    """Fonts come from %WINDIR% and Blender from spritemotion.blender.find_blender; docs, launchers and tests may name paths."""
    offenders = []
    for path in tracked_files():
        rel = path.relative_to(REPO).as_posix()
        if path.suffix not in {".py", ".js", ".mjs"} or rel.startswith(("tests/", "third_party/", "workspace/", "launchers/", "docs/")):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if HARDCODED_TOOL_PATH.search(line):
                offenders.append(f"{rel}:{number}: {line.strip()[:100]}")
    assert offenders == []


def test_every_test_that_starts_blender_is_marked_requires_blender():
    """A machine without Blender must skip those tests with a reason, not fail them (see the CI note in ci.yml)."""
    for path in sorted((REPO / "tests").rglob("test_*.py")):
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        if path.name == Path(__file__).name or "--factory-startup" not in text:
            continue
        tests = len(re.findall(r"^def test_", text, re.MULTILINE))
        marked = len(re.findall(r"^@requires_blender\ndef test_", text, re.MULTILINE))
        assert tests == marked, f"{path.name}: {tests - marked} test(s) start Blender without @requires_blender"
