"""Pack one outfit-lab item (the "New" row of the atlases) into a UOFiddler .vd file.

    python atlas_to_vd.py <outfit-lab dir> <item key> <original.vd> <out.vd> [--original] [--body anim_0400.vd]

--outline N adds N px of dark outline around the item (thickens thin items, UO style).
--body clips the new item wherever the original item was hidden behind the body (equipment frames have
that occlusion baked in; the atlas only subtracts the hand).

--original packs the untouched "UO" row instead: a round-trip self-check (result should equal original.vd).

Atlas views 3..7 map to .vd dir0..4; the atlas anchor (128,192) is the .vd frame anchor.
Blocks whose frame count does not match the original .vd (or missing atlases) keep the original frames.
Uses uo_vd_writer.py and vd.py from this folder.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uo_vd_writer  # noqa: E402
import vd  # noqa: E402

CELL = 256
ANCHOR = (128, 192)


def main(lab, key, original_vd, out_vd, use_original=False, body_vd=None, outline=0):
    lab = Path(lab)
    body = vd.read_vd(body_vd)[2] if body_vd else None
    manifest = json.loads((lab / 'manifest.json').read_text())
    keys = [i['key'] for i in manifest['items']]
    row_new = 2 + 2 * keys.index(key) + (0 if use_original else 1)   # rows: body, mask, then original/new per item
    anim_type, _, orig = vd.read_vd(original_vd)
    counts = {a['index']: {int(v): n['count'] for v, n in a['views'].items()} for a in manifest['actions']}
    blocks, replaced, kept = {}, 0, 0
    for (action, d), frames in orig.items():
        view = 3 + d
        atlas = lab / 'atlases' / f'a{action:02d}_d{view}.png'
        n = counts.get(action, {}).get(view)
        if n != len(frames) or not atlas.exists():
            blocks[(action, d)] = [orig_canvas(f) for f in frames]
            kept += 1
            continue
        im = Image.open(atlas).convert('RGBA')
        out = []
        for f in range(n):
            cell = np.array(im.crop((f * CELL, row_new * CELL, (f + 1) * CELL, (row_new + 1) * CELL)))
            cell[..., 3] = np.where(cell[..., 3] >= 128, 255, 0)
            for _ in range(outline):
                cell = add_outline(cell)
            if body is not None and len(body.get((action, d), ())) == n:
                cell[..., 3] &= visible_mask(body[(action, d)][f], frames[f])
            out.append(cell)
        blocks[(action, d)] = out
        replaced += 1
    uo_vd_writer.write_vd(out_vd, blocks, anim_type=anim_type, anchor=ANCHOR)
    print(f'{out_vd}: {replaced} blocks from atlas, {kept} kept from original')


def add_outline(cell, color=(24, 24, 24)):
    """1 px dark outline around the opaque pixels (UO style); thickens thin items by 2 px."""
    solid = Image.fromarray(cell[..., 3])
    grown = np.array(solid.filter(ImageFilter.MaxFilter(3))) > 0
    ring = grown & (cell[..., 3] == 0)
    out = cell.copy()
    out[ring] = (*color, 255)
    return out


def visible_mask(body_frame, old_frame):
    """255 where the new item may be drawn: off the body, or where the original item was in front of it."""
    body = orig_canvas(body_frame)[..., 3] > 0
    old = Image.fromarray(np.where(orig_canvas(old_frame)[..., 3] > 0, 255, 0).astype(np.uint8))
    near_old = np.array(old.filter(ImageFilter.MaxFilter(5))) > 0    # 2 px around the original item
    return np.where(~body | near_old, 255, 0).astype(np.uint8)


def orig_canvas(frame):
    """Original .vd frame -> 256x256 canvas with anchor (128,192)."""
    canvas = np.zeros((CELL, CELL, 4), np.uint8)
    x = ANCHOR[0] - frame['cx']
    y = ANCHOR[1] - frame['h'] - frame['cy']
    canvas[y:y + frame['h'], x:x + frame['w']] = frame['img']
    return canvas


if __name__ == '__main__':
    extra = sys.argv[5:]
    body_path = extra[extra.index('--body') + 1] if '--body' in extra else None
    outline = int(extra[extra.index('--outline') + 1]) if '--outline' in extra else 0
    main(*sys.argv[1:5], use_original='--original' in extra, body_vd=body_path, outline=outline)

