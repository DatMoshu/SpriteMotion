"""The UO adapter against a synthetic anim.mul/anim.idx (no game files needed)."""
import struct

import numpy as np
import pytest

from spritemotion.pipeline.annotate import apply_bundle
from spritemotion.pipeline.games import load_adapter
from spritemotion.sprites.dataset import Dataset
from spritemotion.sprites.images import load_rgba, mirror_canvas

from conftest import UO, load_module

uo_anim = load_module(UO / "extraction" / "uo_anim.py", "uo_anim_test")


def encode_frame(pixels: np.ndarray, cx: int, cy: int) -> bytes:
    """pixels: (h, w) palette indices, -1 transparent."""
    h, w = pixels.shape
    out = bytearray(struct.pack("<hhHH", cx, cy, w, h))
    for y in range(h):
        x = 0
        while x < w:
            if pixels[y, x] < 0:
                x += 1
                continue
            start = x
            while x < w and pixels[y, x] >= 0:
                x += 1
            rx, ry = (start - cx) & 0x3FF, (y - cy - h) & 0x3FF
            out += struct.pack("<I", (rx << 22) | (ry << 12) | (x - start))
            out += bytes(int(v) for v in pixels[y, start:x])
    out += struct.pack("<I", uo_anim.END_OF_FRAME)
    return bytes(out)


def encode_entry(frames: list[tuple[np.ndarray, int, int]]) -> bytes:
    palette = struct.pack("<256H", *[(i * 0x421) & 0x7FFF for i in range(256)])
    bodies = [encode_frame(*f) for f in frames]
    header = 4 + 4 * len(bodies)
    offsets, position = [], header
    for body in bodies:
        offsets.append(position)
        position += len(body)
    return palette + struct.pack("<I", len(bodies)) + struct.pack(f"<{len(bodies)}I", *offsets) + b"".join(bodies)


def figure(seed: int, h=30, w=12) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pixels = np.full((h, w), -1)
    pixels[2:h - 1, 3:w - 3] = rng.integers(1, 255, (h - 3, w - 6))
    pixels[5, 0:3] = 7  # an asymmetric arm so mirroring is visible
    return pixels


@pytest.fixture
def fake_client(tmp_path):
    """anim.idx/mul holding body 400, action 0, stored directions 0-4, two frames each."""
    first, _ = uo_anim.actions_for_body(400)
    entries = {first + s: encode_entry([(figure(10 * s + f), 6, 4 + f) for f in range(2)]) for s in range(5)}
    idx, mul = bytearray(), bytearray()
    for index in range(first + 5):
        if index in entries:
            idx += struct.pack("<iii", len(mul), len(entries[index]), 0)
            mul += entries[index]
        else:
            idx += struct.pack("<iii", -1, 0, 0)
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "anim.idx").write_bytes(bytes(idx))
    (tmp_path / "client" / "anim.mul").write_bytes(bytes(mul))
    return tmp_path / "client"


def test_decoder_round_trip():
    pixels = figure(1)
    [frame] = uo_anim.decode_entry(encode_entry([(pixels, 6, -3)]))
    assert (frame.center_x, frame.center_y, frame.width, frame.height) == (6, -3, 12, 30)
    assert np.array_equal(frame.indices, pixels)


def test_extract_places_and_mirrors(fake_client, tmp_path):
    manifest = load_adapter("ultima-online").extract(fake_client, "body-400", tmp_path / "ds")
    dataset = Dataset.load(manifest)
    [sequence] = dataset.sequences
    assert sequence["id"] == "action-000" and sequence["frame_count"] == 2
    assert len(sequence["frames"]) == 16
    record = dataset.frame("action-000", 3, 1)   # SE, stored index 0, not mirrored
    assert record["source"]["stored_direction"] == 0 and not record["source"]["mirrored"]
    # the frame's ground origin lands on the anchor: offset = anchor - (cx, cy + h)
    assert record["source"]["offset"] == [128 - 6, 192 - (4 + 1) - 30]
    # N (0) is the mirror of W (6): both come from stored index 3
    north, west = (load_rgba(dataset.image_path(dataset.frame("action-000", d, 0))) for d in (0, 6))
    assert np.array_equal(north, mirror_canvas(west, dataset.mirror_axis_x))


def test_bundled_annotations_refuse_different_pixels(fake_client, tmp_path):
    dataset = Dataset.load(load_adapter("ultima-online").extract(fake_client, "body-400", tmp_path / "ds"))
    report = apply_bundle(dataset, UO / "annotations" / "body-400").to_dict()
    assert report["totals"]["applied"] == 0
    assert report["totals"]["mismatched"] == 16      # every action-000 pose was drawn on other pixels
    assert not dataset.annotation_path("estimate", "action-000").exists()


def test_missing_client_files_fail_loudly(tmp_path):
    with pytest.raises(FileNotFoundError, match="anim.mul"):
        uo_anim.AnimMul(tmp_path)
