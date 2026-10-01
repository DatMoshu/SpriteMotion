"""UOP animation support against synthetic in-memory containers (no game files needed)."""
import struct
import zlib

import numpy as np
import pytest

from spritemotion.pipeline.games import load_adapter
from spritemotion.sprites.dataset import Dataset

from conftest import UO, load_module
from test_uo_adapter import encode_frame, figure

uo_uop = load_module(UO / "extraction" / "uo_uop.py", "uo_uop")
uo_anim = load_module(UO / "extraction" / "uo_anim.py", "uo_anim_uop_test")


# --- writers (the inverse of the readers under test) -------------------------------------------

def bwt_encode(plain: bytes) -> bytes:
    """Produce a buffer that the client's BWT stage decodes to `plain` (byte 0 must not occur)."""
    assert plain and 0 not in plain
    counts = [0] * 256
    for b in plain:
        counts[b] += 1
    positions = {s: [i for i, b in enumerate(plain) if b == s] for s in set(plain)}
    first_seen = list(dict.fromkeys(plain))
    segments = {s: [first_seen.index(s)] for s in first_seen}          # initial slot
    for t, val in enumerate(plain):
        later = [p for p in positions[val] if p > t]
        if not later:
            continue
        nxt = later[0]
        others = [s for s in first_seen if s != val and any(p > t for p in positions[s])]
        segments[val].append(sum(1 for s in others if min(p for p in positions[s] if p > t) < nxt))
    order = sorted(first_seen, key=lambda s: (-counts[s], s))
    stage2 = struct.pack("<256i", *counts) + bytes(b for s in order for b in segments[s])
    # stage 1: move-to-front over the table rotated to start at `first`; T[0] == table[first]
    first = 0
    assert stage2[0] == (2 * first) & 0xFF
    table = [(first + k) & 0xFF for k in range(256)]
    indices = []
    for value in stage2[1:]:
        k = table.index(value)
        indices.append(k)
        table.insert(0, table.pop(k))
    return bytes(4) + bytes([first]) + bytes(indices) + b"\0"


def make_uop(files: dict[str, tuple[bytes, int]], per_table: int = 2) -> bytes:
    """A UOP container holding name -> (payload, compression flag), `per_table` entries per table."""
    names = list(files)
    blobs, entries = bytearray(), []
    for name in names:
        payload, flag = files[name]
        stored = payload
        if flag == 1:
            stored = zlib.compress(payload)
        elif flag == 3:
            payload = bwt_encode(payload)
            stored = zlib.compress(payload)
        entries.append((name, len(blobs), stored, payload, flag))
        blobs += stored
    tables = [entries[i:i + per_table] for i in range(0, len(entries), per_table)]
    header_size = 28
    table_size = lambda t: 12 + 34 * len(t)                             # noqa: E731
    table_offsets, position = [], header_size
    for t in tables:
        table_offsets.append(position)
        position += table_size(t)
    data_start = position
    out = bytearray(struct.pack("<IIIqIi", uo_uop.UOP_MAGIC, 5, 0, table_offsets[0], per_table, len(entries)))
    for k, t in enumerate(tables):
        nxt = table_offsets[k + 1] if k + 1 < len(tables) else 0
        out += struct.pack("<iq", len(t), nxt)
        for name, offset, stored, payload, flag in t:
            out += struct.pack("<qiiiQIh", data_start + offset, 0, len(stored), len(payload),
                               uo_uop.uop_hash(name), 0, flag)
    return bytes(out + blobs)


PALETTE = [(i * 0x421) & 0x7FFF for i in range(256)]
PALETTE[5] = 0          # colour 0: transparent in UOP frames


def make_bin(frames: dict[int, np.ndarray], group: int = 0) -> bytes:
    """AnimationFrame bin with the given frame ids (1-based) -> pixel index arrays."""
    ids = sorted(frames)
    table = 40
    pixels = [struct.pack("<256H", *PALETTE) + encode_frame(frames[i], 5, -2) for i in ids]
    out = bytearray(b"AMOU" + struct.pack("<I", 1) + bytes(24) + struct.pack("<iI", len(ids), table))
    position = table + 16 * len(ids)
    for k, i in enumerate(ids):
        record_start = table + 16 * k
        out += struct.pack("<HHQI", group, i, 0, position - record_start)
        position += len(pixels[k])
    return bytes(out + b"".join(pixels))


def frame_name(body, group):
    return uo_uop.FRAME_NAME.format(body=body, group=group)


# --- tests ---------------------------------------------------------------------------------------

def test_hash_matches_the_client():
    # values pinned from a real client, whose AnimationFrame3.uop table contains the first name
    assert uo_uop.uop_hash("build/animationlegacyframe/000666/00.bin") == 0x412B5F8D4D40D2D1
    assert uo_uop.uop_hash("abcdefghijkl") == 0x75B50EC04012F87B     # length a multiple of 12
    assert uo_uop.uop_hash("") == 0xDEADBEEF00000000


def test_table_chain_and_compression(tmp_path):
    files = {f"entry/{k}.bin": (bytes([k + 1]) * (50 + k), k % 2) for k in range(5)}
    path = tmp_path / "t.uop"
    path.write_bytes(make_uop(files, per_table=2))                       # 3 tables in a chain
    uop = uo_uop.UopFile(path)
    assert len(uop.entries) == 5
    for name, (payload, _) in files.items():
        assert uop.read(uo_uop.uop_hash(name)) == payload


def test_bwt_round_trip(tmp_path):
    plain = b"gargoyle wings beat the air; abracadabra " * 7 + bytes(range(1, 256))
    assert uo_uop.bwt_decompress(bwt_encode(plain)) == plain
    path = tmp_path / "b.uop"
    path.write_bytes(make_uop({"x.bin": (plain, 3)}))
    assert uo_uop.UopFile(path).read(uo_uop.uop_hash("x.bin")) == plain


def test_unsupported_compression_fails_loudly(tmp_path):
    path = tmp_path / "u.uop"
    path.write_bytes(make_uop({"x.bin": (b"abc", 2)}))
    with pytest.raises(ValueError, match="unsupported UOP compression type 2"):
        uo_uop.UopFile(path).read(uo_uop.uop_hash("x.bin"))


def test_bin_directions_gaps_and_transparency():
    pixels = figure(3)
    pixels[10, 4] = 5                                         # a colour-0 pixel
    frames = {i: figure(i) for i in range(1, 11) if i != 4}   # 2 per direction, id 4 missing
    frames[1] = pixels
    directions = uo_anim.decode_uop_bin(make_bin(frames))
    assert [len(d) for d in directions] == [2] * 5
    assert directions[1][1].empty                             # id 4 -> direction 1, frame 1
    expected = figure(10)
    expected[expected == 5] = -1                              # colour 0 is transparent
    assert np.array_equal(directions[4][1].indices, expected)
    first = directions[0][0]
    assert (first.center_x, first.center_y) == (5, -2)
    assert first.indices[10, 4] == -1 and first.rgba[10, 4, 3] == 0
    assert directions[0][0].rgba[5, 0, 3] == 255


def uop_client(tmp_path, mobtypes: str, with_mul: bool = True):
    folder = tmp_path / "client"
    folder.mkdir(parents=True)
    files = {frame_name(666, 0): (make_bin({i: figure(i) for i in range(1, 11)}), 1),
             frame_name(666, 7): (make_bin({i: figure(20 + i) for i in range(1, 16)}, 7), 1)}
    (folder / "AnimationFrame1.uop").write_bytes(make_uop(files))
    record = struct.pack("<iIi", 3, 0, 7) + bytes(60)          # action 3 -> group 7
    sequence = struct.pack("<I", 666) + bytes(48) + struct.pack("<i", 1) + record
    (folder / "AnimationSequence.uop").write_bytes(make_uop({"seq/666.bin": (sequence, 1)}))
    (folder / "mobtypes.txt").write_text(mobtypes)
    if with_mul:
        (folder / "anim.idx").write_bytes(b"")
        (folder / "anim.mul").write_bytes(b"")
    return folder


def test_source_selection_follows_mobtypes(tmp_path):
    folder = uop_client(tmp_path, "# comment\n666 EQUIPMENT 0\n666 HUMAN 10000 # later line wins\n400 HUMAN 20000\n")
    anims = uo_anim.UOAnimations(folder)
    assert anims.source_for(666) == "uop" and anims.source_for(400) == "mul"
    assert uo_anim.UOAnimations(folder, "mul").source_for(666) == "mul"
    frames, info = anims.sequence(666, 0, 2)
    assert len(frames) == 2 and info == {"file": "AnimationFrame1.uop", "group": 0}
    frames, info = anims.sequence(666, 3, 0)                  # replaced by AnimationSequence
    assert info["group"] == 7 and len(frames) == 3
    assert anims.sequence(666, 5, 0) == (None, {})
    flipped = uo_anim.UOAnimations(uop_client(tmp_path / "b", "666 HUMAN 10000\n666 HUMAN 0\n"))
    assert flipped.source_for(666) == "mul"


def test_forced_sources_fail_loudly(tmp_path):
    folder = uop_client(tmp_path, "", with_mul=False)
    with pytest.raises(FileNotFoundError, match="anim.mul"):
        uo_anim.UOAnimations(folder).source_for(666)          # no UOP flag -> MUL, which is absent
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError, match="AnimationFrame"):
        uo_anim.UOAnimations(tmp_path / "empty", "uop")
    with pytest.raises(ValueError, match="auto"):
        uo_anim.UOAnimations(folder, "best")


def test_adapter_extracts_uop_body(tmp_path):
    folder = uop_client(tmp_path, "666 HUMAN 10000\n", with_mul=False)
    manifest = load_adapter("ultima-online").extract(folder, "body-666", tmp_path / "ds",
                                                     sequences=["action-000", "action-003"])
    dataset = Dataset.load(manifest)
    assert [s["id"] for s in dataset.sequences] == ["action-000", "action-003"]
    assert [s["frame_count"] for s in dataset.sequences] == [2, 3]
    record = dataset.frame("action-003", 3, 0)
    assert record["source"]["file"] == "AnimationFrame1.uop" and record["source"]["group"] == 7
    assert record["source"]["offset"] == [128 - 5, 224 + 2 - 30]
