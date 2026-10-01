"""The interface a game adapter implements.

An adapter turns a user's local game installation into a normalized dataset:
canvas-sized RGBA frames plus a manifest (see schemas/sprite-sequence.schema.json).
Adapters live in games/<game>/ and are loaded by file path from game.json, so
the shared layer never imports game code by name.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class GameAdapter(ABC):
    def __init__(self, game_dir: Path, game: dict):
        self.game_dir = Path(game_dir)
        self.game = game

    def character(self, character_id: str) -> dict:
        for item in self.game["characters"]:
            if item["id"] == character_id:
                return item
        known = ", ".join(c["id"] for c in self.game["characters"])
        raise KeyError(f"Unknown character {character_id!r}; known: {known}")

    @abstractmethod
    def extract(self, source: Path, character_id: str, out_dir: Path, sequences: list[str] | None = None) -> Path:
        """Extract frames for one character into out_dir and return the dataset manifest path."""
