"""The transfer-artifact reader and its synthetic fixture (tests/fixtures/transfer, made by tools/transfer-fixture)."""
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from spritemotion import schemas, transfer
from spritemotion.transfer import Crop, TransferError

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests/fixtures/transfer"
KIND = "spritemotion.transfer-artifact"


@pytest.fixture
def artifact_dir(tmp_path):
    target = tmp_path / "artifact"
    shutil.copytree(FIXTURE, target)
    return target


def edit_manifest(directory, change):
    path = directory / "transfer.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    change(manifest)
    path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def frame_entry(manifest, action, direction, index):
    return next(f for f in manifest["frames"] if (f["action"], f["direction"], f["index"]) == (action, direction, index))


def test_valid_fixture_reads_and_validates_against_the_schema():
    pytest.importorskip("jsonschema")
    manifest = json.loads((FIXTURE / "transfer.json").read_text(encoding="utf-8"))
    assert schemas.validate(manifest, KIND, required=True) == []
    artifact = transfer.read(FIXTURE)
    assert artifact.actions == [0, 4]
    assert len(artifact.frames) == 25
    assert artifact.identity["item_id"] == "synthetic-flag"
    assert artifact.frame_count(4) == 3


def test_frames_are_found_by_action_direction_index():
    artifact = transfer.read(FIXTURE)
    frame = artifact.frame(4, 3, 2)
    assert (frame.action, frame.direction, frame.index) == (4, 3, 2)
    assert frame.path.is_file() and not frame.empty
    assert transfer.png_size(frame.path) == (frame.crop.width, frame.crop.height)
    with pytest.raises(KeyError):
        artifact.frame(4, 5, 0)          # 5 is mirrored, never stored
    with pytest.raises(KeyError):
        artifact.frame(9, 0, 0)


def test_mirrored_directions_resolve_through_the_map():
    artifact = transfer.read(FIXTURE)
    for shown, stored in {5: 3, 6: 2, 7: 1}.items():
        resolved = artifact.resolve(0, shown, 1)
        assert resolved.mirrored and resolved.frame is artifact.frame(0, stored, 1)
    straight = artifact.resolve(0, 2, 1)
    assert not straight.mirrored and straight.crop == straight.frame.crop


def test_centre_maths_on_the_asymmetric_sprite():
    artifact = transfer.read(FIXTURE)
    frame = artifact.frame(0, 0, 0)
    assert frame.crop == Crop(104, 100, 128, 190)
    assert transfer.centre(frame.crop) == (24, 2) == frame.centre
    # the crop is not square, so a swapped formula would give something else
    assert frame.crop.width != frame.crop.height
    assert transfer.centre(Crop(100, 60, 124, 190)) == (28, 2)
    # a mirrored sprite flips about x = 128, so the centre moves from 128 - left to right - 128
    resolved = artifact.resolve(0, 7, 0)             # mirror of stored direction 1
    original = artifact.frame(0, 1, 0).crop
    assert resolved.crop == Crop(256 - original.right, original.top, 256 - original.left, original.bottom)
    assert resolved.centre == (original.right - 128, 192 - original.bottom)


def test_negative_centre_and_empty_frame():
    artifact = transfer.read(FIXTURE)
    negative = artifact.frame(4, 4, 0)
    assert negative.centre == (-22, -12)
    empty = artifact.frame(4, 2, 1)
    assert empty.empty and empty.path is None and empty.centre is None
    assert artifact.resolve(4, 6, 1).centre is None


def test_absolute_path_is_rejected(artifact_dir):
    for bad in ("/etc/passwd", "C:/Windows/x.png", "C:\\x.png"):
        edit_manifest(artifact_dir, lambda m, bad=bad: frame_entry(m, 0, 0, 0).update(png=bad))
        with pytest.raises(TransferError, match="absolute"):
            transfer.read(artifact_dir)


def test_traversal_is_rejected(artifact_dir):
    outside = artifact_dir.parent / "outside.png"
    shutil.copy(artifact_dir / "frames/a00-d0-f0.png", outside)
    for bad in ("../outside.png", "frames/../../outside.png", "frames//a00-d0-f0.png"):
        edit_manifest(artifact_dir, lambda m, bad=bad: frame_entry(m, 0, 0, 0).update(png=bad))
        with pytest.raises(TransferError, match="leaves the artifact"):
            transfer.read(artifact_dir)


def test_missing_file_is_rejected(artifact_dir):
    (artifact_dir / "frames/a04-d1-f2.png").unlink()
    with pytest.raises(TransferError, match="missing"):
        transfer.read(artifact_dir)


def test_hash_mismatch_is_rejected(artifact_dir):
    target = artifact_dir / "frames/a00-d3-f1.png"
    data = bytearray(target.read_bytes())
    data[-20] ^= 0xFF                                  # same size and header, different bytes
    target.write_bytes(bytes(data))
    with pytest.raises(TransferError, match="sha256 mismatch"):
        transfer.read(artifact_dir)


def test_bad_mirror_map_is_rejected(artifact_dir):
    for bad in ({"5": 3, "6": 1, "7": 1}, {"5": 3, "6": 2}, {"5": 3, "6": 2, "7": 1, "4": 0}):
        edit_manifest(artifact_dir, lambda m, bad=bad: m["animation"].update(mirror_map=bad))
        with pytest.raises(TransferError, match="mirror_map"):
            transfer.read(artifact_dir)


def test_png_size_must_match_the_crop(artifact_dir):
    edit_manifest(artifact_dir, lambda m: frame_entry(m, 0, 0, 0)["crop"].update(right=129))
    with pytest.raises(TransferError, match="crop"):
        transfer.read(artifact_dir)


def test_stated_centre_must_match_the_crop(artifact_dir):
    edit_manifest(artifact_dir, lambda m: frame_entry(m, 0, 0, 0)["centre"].update(x=0))
    with pytest.raises(TransferError, match="centre"):
        transfer.read(artifact_dir)


def test_missing_frame_entry_is_rejected(artifact_dir):
    edit_manifest(artifact_dir, lambda m: m["frames"].remove(frame_entry(m, 0, 1, 0)))
    with pytest.raises(TransferError, match="missing"):
        transfer.read(artifact_dir)


def test_a_mirrored_direction_cannot_be_stored(artifact_dir):
    edit_manifest(artifact_dir, lambda m: frame_entry(m, 0, 4, 0).update(direction=5))
    with pytest.raises(TransferError, match="not a stored direction"):
        transfer.read(artifact_dir)


def test_wrong_kind_and_missing_manifest(artifact_dir, tmp_path):
    edit_manifest(artifact_dir, lambda m: m.update(schema="spritemotion.game"))
    with pytest.raises(TransferError, match="expected schema"):
        transfer.read(artifact_dir)
    with pytest.raises(TransferError, match="transfer.json"):
        transfer.read(tmp_path / "nothing")


def test_schema_rejects_what_the_reader_would_also_reject():
    pytest.importorskip("jsonschema")
    manifest = json.loads((FIXTURE / "transfer.json").read_text(encoding="utf-8"))
    manifest["frames"][0]["png"] = "../x.png"
    manifest["animation"]["mirror_map"]["6"] = 1
    manifest["pixels"]["anchor"]["y"] = 191
    text = " ".join(schemas.validate(manifest, KIND, required=True))
    assert "png" in text and "mirror_map" in text and "anchor" in text


def test_generator_is_deterministic_and_matches_the_committed_fixture(tmp_path):
    spec = importlib.util.spec_from_file_location("transfer_fixture", REPO / "tools/transfer-fixture/run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first, second = module.build(tmp_path / "one"), module.build(tmp_path / "two")

    def digest(root):
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(root.rglob("*")) if p.is_file()}

    assert digest(first) == digest(second) == digest(FIXTURE)
