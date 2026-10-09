"""Crash-safe JSON writes: unique temp files, and the target is never missing."""
import os

import pytest

from spritemotion import jsonio


def test_write_leaves_no_temp_files_and_round_trips(tmp_path):
    target = tmp_path / "data.json"
    jsonio.write_json(target, {"a": 1})
    assert jsonio.read_json(target) == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["data.json"]


def test_a_stale_fixed_name_tmp_file_is_not_touched(tmp_path):
    target = tmp_path / "data.json"
    stale = tmp_path / "data.json.tmp"
    stale.write_text("another writer", encoding="utf-8")
    jsonio.write_json(target, {"a": 1})
    assert stale.read_text(encoding="utf-8") == "another writer"


def test_target_exists_at_every_replace_with_backup(tmp_path, monkeypatch):
    target = tmp_path / "data.json"
    jsonio.write_json(target, {"v": 1})
    seen = []
    real = os.replace

    def spy(src, dst):
        seen.append(target.exists())
        return real(src, dst)

    monkeypatch.setattr(jsonio.os, "replace", spy)
    jsonio.write_json(target, {"v": 2}, backup=True)
    assert seen and all(seen)
    assert jsonio.read_json(target) == {"v": 2}
    assert jsonio.read_json(tmp_path / "data.json.bak") == {"v": 1}


def test_a_failed_write_keeps_the_old_file_and_cleans_up(tmp_path):
    target = tmp_path / "data.json"
    jsonio.write_json(target, {"v": 1})
    with pytest.raises(ValueError):
        jsonio.write_json(target, {"v": float("nan")}, backup=True)
    assert jsonio.read_json(target) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["data.json"]
