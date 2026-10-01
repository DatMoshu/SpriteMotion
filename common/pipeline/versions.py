"""Version history for scene files (.blend or anything else saved repeatedly).

Every save through `save_with_history` keeps what was there before:

    model.blend                     the current version
    model.versions/history.json     one entry per version: when, what made it, its metrics
    model.versions/model.v001.blend earlier versions, copied before they were replaced

so an animation that was better before a pass can be compared and restored.
Plain file operations only: usable from Blender's Python and from the CLI.
"""
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..jsonio import read_json, write_json

HISTORY = "history.json"


def versions_dir(path: str | Path) -> Path:
    path = Path(path)
    return path.with_name(f"{path.stem}.versions")


def version_file(path: str | Path, version: int) -> Path:
    path = Path(path)
    return versions_dir(path) / f"{path.stem}.v{version:03d}{path.suffix}"


def load_history(path: str | Path) -> dict:
    file = versions_dir(path) / HISTORY
    if file.exists():
        return read_json(file)
    return {"schema": "spritemotion.file-history", "schema_version": 1, "file": Path(path).name, "versions": []}


def _save_history(path: str | Path, history: dict) -> None:
    folder = versions_dir(path)
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder / HISTORY, history)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_version(path: str | Path) -> dict | None:
    versions = load_history(path)["versions"]
    return versions[-1] if versions else None


def archive_current(path: str | Path) -> dict | None:
    """Copy the file as it is now into the versions folder, before it gets replaced.

    A file with no history yet (made before versioning, or by another tool) is
    recorded as version 1. Returns the history entry of the archived version.
    """
    path = Path(path)
    if not path.exists():
        return None
    history = load_history(path)
    sha = _sha256(path)
    entry = history["versions"][-1] if history["versions"] else None
    if entry is None or entry.get("sha256") != sha:
        # the file changed outside this history (saved by hand in Blender, or pre-dates it)
        entry = {"version": len(history["versions"]) + 1, "saved_at": _now(), "sha256": sha,
                 "made_by": "external save (not recorded)", "metrics": {}}
        history["versions"].append(entry)
    target = version_file(path, entry["version"])
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    entry["archived"] = target.name
    _save_history(path, history)
    return entry


def record_save(path: str | Path, made_by: str, metrics: dict | None = None, note: str = "",
                actions: dict | None = None) -> dict:
    """Record the file just written at `path` as the next version."""
    path = Path(path)
    history = load_history(path)
    entry = {"version": len(history["versions"]) + 1, "saved_at": _now(), "sha256": _sha256(path),
             "made_by": made_by, "metrics": dict(metrics or {})}
    if note:
        entry["note"] = note
    if actions:
        entry["actions"] = actions
    history["versions"].append(entry)
    _save_history(path, history)
    return entry


def attach_metrics(path: str | Path, metrics: dict, version: int | None = None) -> dict:
    """Add metrics (e.g. a compare summary) to a version, the current one by default."""
    history = load_history(path)
    if not history["versions"]:
        raise ValueError(f"{path} has no recorded versions.")
    entry = history["versions"][-1] if version is None else _find(history, version)
    entry.setdefault("metrics", {}).update(metrics)
    _save_history(path, history)
    return entry


def _find(history: dict, version: int) -> dict:
    for entry in history["versions"]:
        if entry["version"] == version:
            return entry
    raise KeyError(f"No version {version}; known: {[e['version'] for e in history['versions']]}")


def restore(path: str | Path, version: int) -> dict:
    """Make an earlier version current again. The version being replaced is archived first."""
    path = Path(path)
    history = load_history(path)
    source_entry = _find(history, version)
    source = version_file(path, version)
    if not source.exists():
        if source_entry is history["versions"][-1] and path.exists():
            return source_entry     # already current
        raise FileNotFoundError(f"Version {version} was never archived ({source.name} missing).")
    archive_current(path)
    shutil.copy2(source, path)
    return record_save(path, f"restore of v{version:03d}", source_entry.get("metrics"),
                       note=f"restored from version {version}")
