"""Locate game folders and load their adapters by file path."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .. import REPO_ROOT
from ..jsonio import read_json
from ..schemas import SchemaError, validate
from ..sprites.adapter import GameAdapter

GAMES_DIR = REPO_ROOT / "games"


def game_dir(game_id: str) -> Path:
    path = GAMES_DIR / game_id
    if not (path / "game.json").exists():
        known = ", ".join(sorted(p.name for p in GAMES_DIR.iterdir() if (p / "game.json").exists()))
        raise SchemaError(f"No game {game_id!r} in {GAMES_DIR}; known: {known}")
    return path


def load_game(game_id: str) -> tuple[Path, dict]:
    path = game_dir(game_id)
    game = read_json(path / "game.json")
    errors = validate(game, "spritemotion.game")
    if errors:
        raise SchemaError(f"{path / 'game.json'}: " + "; ".join(errors))
    return path, game


def character(game: dict, character_id: str) -> dict:
    for item in game["characters"]:
        if item["id"] == character_id:
            return item
    raise SchemaError(f"Game {game['id']!r} has no character {character_id!r}.")


def load_adapter(game_id: str) -> GameAdapter:
    path, game = load_game(game_id)
    module_path = path / game["adapter"]["module"]
    name = f"spritemotion_game_{game_id.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise SchemaError(f"Cannot load adapter module {module_path}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    adapter_class = getattr(module, game["adapter"]["class"])
    adapter = adapter_class(path, game)
    if not isinstance(adapter, GameAdapter):
        raise SchemaError(f"{adapter_class.__name__} does not implement GameAdapter.")
    return adapter


def annotation_bundle(game_id: str, character_id: str) -> Path | None:
    path, game = load_game(game_id)
    folder = character(game, character_id).get("annotations")
    return path / folder if folder else None
