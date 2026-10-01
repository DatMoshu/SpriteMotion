import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
import uo_vd_writer
import vd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools' / 'vd'))
import vdtool  # noqa: E402

ANCHOR = (128, 192)
# Colours that survive the 15-bit round trip exactly.
COLOURS = [uo_vd_writer.c15_to_rgb(c).tolist() for c in (0x7C00, 0x03E0, 0x001F, 0x4210, 0x0001)]


def synthetic_frame(shift):
    """A small multi-colour figure standing on the anchor, with a hole and a stray pixel."""
    im = np.zeros((256, 256, 4), np.uint8)
    for i, rgb in enumerate(COLOURS):
        im[150 + 8 * i:158 + 8 * i, 120 + shift:136 + shift] = rgb + [255]
    im[160:164, 126 + shift:130 + shift] = 0
    im[100, 200] = COLOURS[0] + [255]
    return im


def placed(frame, rgba):
    """Put a decoded frame back on a 256 px canvas by its centre."""
    out = np.zeros((256, 256, 4), np.uint8)
    x0, y0 = ANCHOR[0] - frame['cx'], ANCHOR[1] - frame['cy'] - frame['h']
    out[y0:y0 + frame['h'], x0:x0 + frame['w']] = rgba[:frame['h'], :frame['w']]
    return out


class VdRoundTripTests(unittest.TestCase):
    def test_writer_reader_round_trip(self):
        blocks = {(0, 0): [synthetic_frame(0), synthetic_frame(3)], (4, 2): [synthetic_frame(-5)]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.vd'
            uo_vd_writer.write_vd(path, blocks, anim_type=2, anchor=ANCHOR)
            anim_type, actions, anims = vd.read_vd(path)
            self.assertEqual((anim_type, actions), (2, 35))
            self.assertEqual(sorted(anims), sorted(blocks))
            for key, frames in blocks.items():
                self.assertEqual(len(anims[key]), len(frames))
                for original, decoded in zip(frames, anims[key]):
                    back = placed(decoded, decoded['img'])
                    np.testing.assert_array_equal(back[..., 3] > 0, original[..., 3] >= 128)   # alpha is on/off
                    np.testing.assert_array_equal(back, original)                             # pixels and anchor
            # vdtool decodes the same file to the same frames.
            vt_type, vt_blocks = vdtool.read_vd(str(path))
            self.assertEqual(vt_type, 2)
            for b in vt_blocks:
                frames = blocks.get((b['action'], b['dir']), [])
                self.assertEqual(len(b['frames']), len(frames))
                for original, f in zip(frames, b['frames']):
                    np.testing.assert_array_equal(placed(f, vdtool.frame_rgba(f, b['palette'])), original)

    def test_empty_frame_is_one_transparent_pixel(self):
        crop, cx, cy = uo_vd_writer.crop_frame(np.zeros((256, 256, 4), np.uint8), *ANCHOR)
        self.assertEqual((crop.shape, crop[..., 3].max(), cx, cy), ((1, 1, 4), 0, 0, -1))


if __name__ == '__main__':
    unittest.main()
