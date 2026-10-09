"""JSON reading and crash-safe writing."""
from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _clean(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Refusing to write a non-finite number to JSON.")
        return value
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def dumps(value: Any, indent: int | None = 1) -> str:
    return json.dumps(_clean(value), indent=indent, ensure_ascii=False) + "\n"


def write_json(path: str | Path, value: Any, indent: int | None = 1, backup: bool = False) -> Path:
    """Write via a temporary file and atomic replace; optionally keep the previous file as .bak."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = dumps(value, indent)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False)
    temp = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if backup and path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))   # the target itself is never moved away
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return path
