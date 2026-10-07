"""SpriteMotion shared layer.

Everything in this package is game-independent: it knows about canvases,
frames, skeletons, pose annotations, projections and rigs, but nothing about
any particular game's files, body IDs, camera or direction conventions. Those
live in games/<game>/ and reach this code through data (profiles, manifests).
"""
from pathlib import Path

__version__ = "0.1.0"

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
