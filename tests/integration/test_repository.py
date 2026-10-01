"""Repository-level checks: bundled data validates, publishes nothing it must not, and matches a local client.

The last test needs the user's own Ultima Online client: set SPRITEMOTION_UO_SOURCE
to the folder holding anim.mul / anim.idx.
"""
import os
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
    for path in files:
        rel = path.relative_to(REPO).as_posix()
        assert not rel.startswith("workspace/") or rel == "workspace/README.md", rel
        assert path.suffix.lower() not in {".mul", ".uop", ".idx", ".blend", ".fbx", ".glb"}, rel
        if rel.startswith("games/") and path.suffix.lower() in {".png", ".bmp", ".gif"}:
            pytest.fail(f"image under games/ (game art must never be committed): {rel}")
        if path.suffix.lower() in {".py", ".gd", ".json", ".md", ".bat", ".toml", ".cfg", ".godot", ".tscn",
                                  ".html", ".js", ".css", ".yaml", ".yml", ".txt"} \
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
