# UO conventions used by the adapter

These are the rules `extraction/` follows, with the source of each one. For
file formats, the references are ClassicUO's `AnimationsLoader` and UOFiddler's
`Ultima/Animations.cs`.

## anim.idx / anim.mul

- `anim.idx`: 12-byte entries `(int32 offset, int32 length, int32 extra)`.
  An offset of −1 means the entry is missing.
- Entry index for a body:

  | body | first entry | actions |
  |---|---|---|
  | < 200 (monsters) | body × 110 | 22 |
  | 200–399 (animals) | 22000 + (body − 200) × 65 | 13 |
  | ≥ 400 (people) | 35000 + (body − 400) × 175 | 35 |

  entry = first + action × 5 + stored direction.
- An entry holds a 256-colour RGB555 palette, a frame count, and frame
  offsets relative to the end of the palette.
- A frame holds `int16 center_x, int16 center_y, uint16 width, uint16 height`
  followed by pixel runs. Each run has a 32-bit header
  (x: 10 bits signed, y: 10 bits signed, length: 12 bits) and then `length`
  palette indices. The list ends with `0x7FFF7FFF`. Run coordinates are
  relative to (center_x, center_y + height).
- Pixels not covered by a run are transparent. Frames are extracted **unhued**. Skin and
  clothing hues are applied at draw time by the client and are not part of
  the fingerprint.

## UOP animations (AnimationFrame*.uop)

Newer bodies (gargoyles 666/667, many monsters) ship only in
`AnimationFrame<n>.uop`. The rules follow ClassicUO's `UOFileUop` and
`AnimationsLoader`, reimplemented in `extraction/uo_uop.py` and `uo_anim.py`.

- **Which source a body uses** (`anim_source: "auto"`, the default): UOP when
  `mobtypes.txt` gives the body the `UseUopAnimation` flag (0x10000) and
  AnimationFrame files exist. Otherwise anim.mul is used.
  - The flags are hex, and a later line for the same body overrides an
    earlier one.
  - Bodies 400/401 are `HUMAN 20000`, so they stay on anim.mul.
  - `"mul"` or `"uop"` in the profile, or the `SPRITEMOTION_UO_ANIM_SOURCE`
    environment variable, forces one source.
- **Container:**
  - Header: `u32 magic 0x50594D, u32 version, u32 stamp, i64 first table,
    u32 table size, i32 count`.
  - Tables: `i32 count, i64 next table (0 = last)`, then 34-byte entries
    `i64 offset, i32 header length, i32 compressed, i32 decompressed,
    u64 name hash, u32 data hash, i16 compression`.
  - Data starts at offset + header length.
  - Names are stored only as a 64-bit hash (the client's variant of Jenkins'
    lookup3 `hashlittle2`).
- **Compression:** 0 is none, 1 is zlib, 3 is zlib followed by the client's
  BWT/move-to-front stage. Any other value fails loudly. The tested client
  uses only type 1.
- **Name:** `build/animationlegacyframe/<body:06>/<group:02>.bin`. There is
  one bin per body and action group, holding all five stored directions, and
  up to 80 groups.
  - `AnimationSequence.uop` can redirect an action to another group. These
    are the records with frame count 0; entries with 48 or 68 records are
    skipped, as in the client.
- **Bin:**
  - Header: `"AMOU"`, version, …, `i32 frame count` at byte 32 and
    `u32 table offset` at byte 36.
  - 16-byte records: `u16 group, u16 frame id (1-based), 8 bytes,
    u32 pixel offset` (relative to the record).
  - Each frame: a 512-byte palette, then the anim.mul sprite encoding.
  - **Palette colour 0 is transparent** here (not in anim.mul).
- **Frames to directions:** gaps in the frame ids become empty frames. There
  are round(n / 5) frames per direction (at least 10 for equipment), and frame
  id *k* belongs to stored direction (k − 1) // per-direction. The stored
  directions and mirroring are the same as in anim.mul.
- `source.file` in each frame record names the real file (`anim.mul` or
  `AnimationFrame3.uop`). UOP frames also record `source.group`.
- **Not handled:** `anim2`–`anim5.mul`, `Body.def` / `Bodyconv.def`
  substitutions, and hues.
- **Checked on a real client:** 294 bodies have UOP data, and every entry's
  hash matched a generated name. Gargoyle 666 extracts 52 groups × 80 frames.
  Its frames reach 199 px above the ground origin, hence the taller
  `body-666/667` canvas.

## Placement

ClassicUO draws a mobile with the frame's top-left corner at
(screen_x − center_x, screen_y − (height + center_y)). The ground origin of
the sprite, which is the centre of the tile the mobile stands on, is therefore
at pixel (center_x, height + center_y) from the frame's top-left. The adapter
places every frame so that this pixel lands on the canvas anchor (128, 192).
All 35 body-400 actions, including deaths and weapon reaches, fit on a
256×256 canvas at that anchor.

## Directions and mirroring

`anim.mul` stores five facings. ClassicUO's `GetAnimDirection` maps the eight
UO directions onto them and mirrors three at draw time:

| UO direction | screen | stored | mirrored |
|---|---|---|---|
| 3 SE | down | 0 | no |
| 4 S | down-left | 1 | no |
| 2 E | down-right | 1 | yes |
| 5 SW | left | 2 | no |
| 1 NE | right | 2 | yes |
| 6 W | up-left | 3 | no |
| 0 N | up-right | 3 | yes |
| 7 NW | up | 4 | no |

UOFiddler labels stored rows 0–4 as SW/S/SE/E/NE. Those are its own labels,
not the client's mapping.

A mirrored view is produced by mirroring the placed canvas: pixel column *i*
becomes 255 − *i*, which is mirroring about x = 127.5. Mirroring a pose uses
the same axis (x → 255 − x). Chain names are kept (see
[../../../docs/annotation-format.md](../../../docs/annotation-format.md)).

Each direction's `facing` (world x east, y north) is the direction the
character faces in that view. For example, SE is (1, −1).

## Ground projection

In ClassicUO's screen maths, one tile has side 1 and height is measured in
tile units. The ground projection is:

```text
screen x = 22 (x + y)
screen y = 22 (x − y) − 31.1127 z        (31.1127 = 22·√2)
```

This is `profiles/cameras/ground-grid.json`. It is an orthographic view at
45° elevation looking north-west, stretched vertically by √2. It matches the
ground grid exactly. Whether the *character art* was rendered with the same
projection is a separate question: see [findings.md](findings.md).

## Timeline

Frame timing is not stored in the MUL files. The existing Blender scenes key
source frame *f* at Blender frame 1 + 4*f*, and the launchers default to that
(`SPRITEMOTION_FRAME_START`, `SPRITEMOTION_FRAME_STEP`).
