# .vd tools

Command-line tools for UOFiddler's `.vd` animation export format. The outfit-lab writes its results
as `.vd` files (`games/ultima-online/outfit-lab/atlas_to_vd.py`). These tools read the originals and
check the results.

| Script | Job |
|---|---|
| `mul2vd.py` | Copy one animation (body or equipment id) out of `anim.idx` + `anim.mul` into a `.vd` file, byte for byte. |
| `vdtool.py` | `info` (actions and frame counts), `extract` (frames to PNG plus `meta.json`), `pack` (PNG folder back to `.vd`), `verify` (compare two `.vd` files frame by frame). |

Requires Python 3.8+, NumPy and Pillow.

```powershell
python tools/vd/mul2vd.py "<your UO client folder>/anim.idx" "<your UO client folder>/anim.mul" <out dir> 400 0x1F3
python tools/vd/vdtool.py info <out dir>/anim_0400.vd
python tools/vd/vdtool.py extract anim_0400.vd frames/          # shared canvas, one anchor
python tools/vd/vdtool.py extract anim_0400.vd frames/ --raw    # original frame sizes, edit pixels only
python tools/vd/vdtool.py pack frames/ new.vd
python tools/vd/vdtool.py verify anim_0400.vd new.vd            # IDENTICAL BYTE FOR BYTE / IMAGE IDENTICAL / DIFFERENCES: n
```

`mul2vd.py` reads only `anim.mul` with the standard index layout (body < 200: 22 actions,
< 400: 13 actions, otherwise 35 actions). Animations that `Bodyconv.def` sends to `anim2`–`anim5.mul`
have to be exported from UOFiddler (Animation Edit → Export to VD). `atlas_to_vd.py` needs the
original `.vd` only for its frame counts.

## Format notes

- Header: `int16` magic `6`, `int16` animation type: `0` high detail (22 actions), `1` low detail
  (13 actions), `2` people and equipment (35 actions).
- Then one index entry per action × 5 stored directions: `int32 offset, int32 length, int32 extra`.
  `-1` means the block is empty.
- Each block holds a 256-entry palette of 15-bit colours (`uint16`, RGB 5-5-5), an `int32` frame
  count, the frame offsets, then the frames. Colour `0x0000` is transparent in the client, so writers
  map pure black to `0x0001`.
- A frame is `int16 cx, int16 cy, uint16 width, uint16 height` and RLE runs. Each run has a `uint32`
  header (10-bit x offset, 10-bit y offset, 12-bit length) followed by palette indices. `0x7FFF7FFF`
  ends the frame.
- One palette per action and direction block, and alpha is on or off. Soft edges, glows and
  photo-like pictures get flattened.

## Origin

Contributed by Levy from his UO_Model3D project and included with his permission.
