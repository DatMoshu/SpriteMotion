"""VD offset range checks, clipped reads and CLI usage errors, on synthetic data only."""
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'vd'))
sys.path.insert(0, str(ROOT / 'games' / 'ultima-online' / 'outfit-lab'))
import uo_vd_writer  # noqa: E402
import vd  # noqa: E402
import vdtool  # noqa: E402


def idx_frame(h, w):
    idx = np.full((h, w), -1, np.int16)
    idx[:, :] = 1
    return idx


def test_vdtool_encode_rejects_out_of_range_offset():
    with pytest.raises(ValueError, match='10-bit'):
        vdtool.encode_frame(idx_frame(2, 4), 600, 0)
    with pytest.raises(ValueError, match='10-bit'):
        vdtool.encode_frame(idx_frame(2, 4), 0, -600)


def test_vdtool_encode_accepts_boundary_offsets():
    vdtool.encode_frame(idx_frame(1, 1), 512, 0)    # dx = -512
    vdtool.encode_frame(idx_frame(1, 1), -511, 0)   # dx = 511


def test_writer_encode_rejects_out_of_range_offset():
    with pytest.raises(ValueError, match='10-bit'):
        uo_vd_writer.encode_frame(idx_frame(2, 4), 600, 0)
    uo_vd_writer.encode_frame(idx_frame(1, 1), 512, 0)


def test_vd_reader_clips_runs_outside_declared_size(tmp_path):
    # One 2x2 frame whose runs fall left of, below and past the right edge of the frame.
    cx, cy, w, h = 0, 0, 2, 2
    frame = struct.pack('<hhHH', cx, cy, w, h)
    xb, yb = cx - 0x200, cy + h - 0x200
    for x, y, n in ((-1, 0, 2), (1, 1, 3), (0, 5, 1)):
        hdr = (((x - xb) & 0x3FF) << 22) | (((y - yb) & 0x3FF) << 12) | n
        frame += struct.pack('<I', hdr ^ ((0x200 << 22) | (0x200 << 12))) + bytes([1]) * n
    frame += struct.pack('<I', 0x7FFF7FFF)
    pal = struct.pack('<256H', *([0x7FFF] * 256))
    data = struct.pack('<i', 1) + struct.pack('<i', 8) + frame
    off = 4 + 12 * 35 * 5
    index = struct.pack('<iii', off, len(pal) + len(data), 0) + struct.pack('<iii', -1, -1, -1) * (35 * 5 - 1)
    blob = struct.pack('<hh', 0, 2) + index + pal + data
    path = tmp_path / 'clip.vd'
    path.write_bytes(blob)
    _, _, anims = vd.read_vd(str(path))
    img = anims[(0, 0)][0]['img']
    assert img.shape[:2] == (2, 2)
    assert img[0, 0, 3] == 255 and img[0, 1, 3] == 0     # left run clipped to x=0
    assert img[1, 1, 3] == 255 and img[1, 0, 3] == 0     # no wraparound to the right edge


@pytest.mark.parametrize('cmd', ['extract', 'pack', 'verify'])
def test_vdtool_missing_args_is_usage_error(cmd, capsys):
    assert vdtool.main(['vdtool.py', cmd, 'only-one']) == 2
    assert 'usage' in capsys.readouterr().out
