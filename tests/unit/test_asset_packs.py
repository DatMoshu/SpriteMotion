"""Asset-pack mappings and equipment slots: the format validates and every reference resolves.

A local sidecar's mappings (licensed packs that never enter the repository) are checked too when
SPRITEMOTION_SIDECAR points at it.
"""
import os
from pathlib import Path

import pytest

from spritemotion.jsonio import read_json
from spritemotion.schemas import validate

from conftest import REPO, UO

SLOTS = UO / "equipment" / "layers.json"
EXAMPLES = sorted((REPO / "examples" / "asset-pack").glob("*.json"))
SIDECAR = os.environ.get("SPRITEMOTION_SIDECAR")
LOCAL = sorted(Path(SIDECAR).glob("packs/*/asset-pack.json")) if SIDECAR else []


def test_uo_layers_validate_and_are_unique():
    slots = read_json(SLOTS)
    assert validate(slots, "spritemotion.equipment-slots", required=True) == []
    ids = [layer["id"] for layer in slots["layers"]]
    assert len(ids) == len(set(ids))
    assert {layer["name"] for layer in slots["layers"]} >= {"OneHanded", "TwoHanded", "Helm", "Cloak", "Arms"}


@pytest.mark.parametrize("path", EXAMPLES + LOCAL, ids=lambda p: p.parent.name + "/" + p.name)
def test_asset_pack_mapping(path):
    pack = read_json(path)
    assert validate(pack, "spritemotion.asset-pack", required=True) == []
    layers = {layer["id"] for layer in read_json(REPO / pack["slots"])["layers"]}
    bones = pack["bones"]
    for name, bone in bones.items():
        assert bone["parent"] is None or bone["parent"] in bones, name
        if "end" in bone:
            assert "target" in bone and (bone["end"] is None or bone["end"] in bones), name
        if "follows" in bone:
            assert "end" in bones[bone["follows"]] and bones[bone["follows"]]["target"] == bone["target"], name
    assert any(bone.get("end") is not None or "end" in bone for bone in bones.values())
    codes = {part["code"]: part for part in pack["parts"]}
    for part in pack["parts"]:
        assert part.get("uo_layer") is None or part["uo_layer"] in layers, part["code"]
        assert set(part.get("alternatives", [])) <= layers, part["code"]
        assert part.get("pair") is None or part["pair"] in codes, part["code"]
        assert (part["status"] in ("uo", "merge")) == (part.get("uo_layer") is not None), part["code"]
        if part["status"] == "extra":          # a pair is one item: either half may describe the slot
            assert "candidate_slot" in part or "candidate_slot" in codes.get(part.get("pair"), {}), part["code"]
    assert set(pack.get("uncovered_layers", [])) <= layers
