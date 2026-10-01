"""Schema validation for the four SpriteMotion document types.

jsonschema is optional at runtime: without it only the structural checks in
each loader run. Tests install it and validate every bundled document.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from . import SCHEMA_DIR
from .jsonio import read_json

SCHEMA_FILES = {
    "spritemotion.game": "game.schema.json",
    "spritemotion.dataset": "sprite-sequence.schema.json",
    "spritemotion.skeleton": "skeleton.schema.json",
    "spritemotion.pose-annotations": "pose-annotations.schema.json",
}


class SchemaError(ValueError):
    pass


@lru_cache(maxsize=None)
def load_schema(kind: str) -> dict:
    return read_json(SCHEMA_DIR / SCHEMA_FILES[kind])


def validate(document: Any, kind: str | None = None, required: bool = False) -> list[str]:
    """Return a list of schema errors (empty when valid or when jsonschema is unavailable).

    With required=True a missing jsonschema package is itself an error.
    """
    if not isinstance(document, dict):
        return ["Document is not a JSON object."]
    kind = kind or document.get("schema")
    if kind not in SCHEMA_FILES:
        return [f"Unknown document schema {kind!r}."]
    if document.get("schema") != kind:
        return [f"Expected schema {kind!r}, found {document.get('schema')!r}."]
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema is not installed."] if required else []
    validator = jsonschema.Draft202012Validator(load_schema(kind))
    return [
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    ]


def require_valid(document: Any, kind: str | None = None) -> None:
    errors = validate(document, kind)
    if errors:
        raise SchemaError("; ".join(errors[:5]) + (f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""))
