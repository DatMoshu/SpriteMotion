"""Merge a second item into an already built one (e.g. a hood onto a cloak) so both live in ONE animation.

    python merge_items.py --source <client> --base-lab <lab of the built item> --base-key cloak \
        --graphic 0xA706 --out <new lab> --key cloak_hood [--under]

For every action/direction/frame the second item's ORIGINAL frame (from the client, Bodyconv aware) is composited over
the base item's NEW row. Frame counts must match. The result is a normal lab folder (rows: body, mask, original merged,
new merged), so atlas_to_vd.py turns it into a .vd. Nothing in the client is modified; the target animation id is
chosen only when the .vd is imported.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'region-masks'))
import build  # noqa: E402
from uo import UOReader, client_source  # noqa: E402


def blend_seam(over, under, band=3):
    """`over` drawn on `under` with a soft seam: the hard dark outline of `over` where it meets visible `under` pixels
    is eased, and the `under` pixels next to it take a little of `over`'s colour (fading out over `band` px)."""
    c = np.array(over).astype(float)
    h = np.array(under).astype(float)
    cm, hm = c[..., 3] > 0, h[..., 3] > 0
    out = h.copy()
    out[cm] = c[cm]
    hood_only = hm & ~cm
    if not hood_only.any() or not cm.any():
        return Image.fromarray(out.astype(np.uint8))

    def local_mean(rgb, mask, radius=3):
        m8 = Image.fromarray((mask * 255).astype(np.uint8))
        weight = np.maximum(np.array(m8.filter(ImageFilter.BoxBlur(radius))).astype(float) / 255., 1e-3)
        mean = np.zeros(rgb.shape[:2] + (3,))
        for ch in range(3):
            ch8 = Image.fromarray((rgb[..., ch] * mask).astype(np.uint8))
            mean[..., ch] = np.array(ch8.filter(ImageFilter.BoxBlur(radius))).astype(float) / weight
        return np.clip(mean, 0, 255)

    cloak_near = local_mean(c, cm)
    hood_near = local_mean(h, hm)

    def dilate(mask):
        return np.array(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0

    seam = cm & dilate(hood_only)                                  # cloak pixels touching the visible hood: its outline
    out[seam, :3] = .5 * cloak_near[seam] + .5 * hood_near[seam]
    reached = cm.copy()
    fade = [.55, .38, .22, .12, .06]
    for k in range(band):
        grown = dilate(reached)
        ring = grown & ~reached & hood_only
        t = fade[min(k, len(fade) - 1)]
        out[ring, :3] = (1 - t) * h[ring, :3] + t * cloak_near[ring]
        reached = grown
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def main(args):
    base = Path(args.base_lab)
    out = Path(args.out)
    (out / 'atlases').mkdir(parents=True, exist_ok=True)
    (out / 'designs').mkdir(exist_ok=True)
    manifest = json.loads((base / 'manifest.json').read_text())
    reader = UOReader(Path(args.source))
    graphic = int(args.graphic, 0)
    top = reader.item(graphic)
    aid = reader.equip.get((400, top['animId']), (top['animId'], 0))[0]
    print(f"merging {hex(graphic)} '{top['label']}' animId {top['animId']} -> animation {aid} onto '{args.base_key}'")
    problems = []
    try:
        for action in manifest['actions']:
            a = action['index']
            for facing, view in action['views'].items():
                stored = build.FACING.index(int(facing))
                atlas = Image.open(base / view['atlas']).convert('RGBA')
                seq = reader.sequence(aid, a, stored)
                n = view['count']
                if len(seq) != n:
                    problems.append((a, facing, n, len(seq)))
                    raise SystemExit(f'Frame count mismatch in action {a} facing {facing}: base {n}, {hex(graphic)} {len(seq)}')
                merged = Image.new('RGBA', atlas.size)
                merged.alpha_composite(atlas.crop((0, 0, atlas.width, 512)))              # body and mask rows unchanged
                for f in range(n):
                    layer = build.canvas(seq[f])
                    for row in (2, 3):                                                   # original row and new row
                        cell = atlas.crop((256 * f, 256 * row, 256 * (f + 1), 256 * (row + 1)))
                        combined = Image.new('RGBA', (256, 256))
                        if args.smooth and row == 3:                                     # soft seam (new row only)
                            combined = (blend_seam(cell, layer, args.smooth) if args.under
                                        else blend_seam(layer, cell, args.smooth))
                        elif args.under:
                            combined.alpha_composite(layer)
                            combined.alpha_composite(cell)                               # base item over the merged one
                        else:
                            combined.alpha_composite(cell)
                            combined.alpha_composite(layer)                              # merged item over the base (default)
                        merged.paste(combined, (256 * f, 256 * row))
                merged.save(out / view['atlas'], optimize=True)
            print(f'Merged action {a}: {action["name"]}', flush=True)
    finally:
        reader.close()
    manifest['items'][0]['key'] = args.key
    manifest['items'][0]['displayName'] = args.title or args.key
    manifest['title'] = args.title or args.key
    manifest['drawOrder'] = [args.key]
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    (out / 'data.js').write_text('window.OUTFIT=' + json.dumps(manifest) + ';')
    for name in ('viewer.js', 'style.css'):
        shutil.copyfile(HERE / name, out / name)
    html = (HERE / 'index.html').read_text(encoding='utf-8').replace('Astral Wayfarer', args.title or args.key)
    (out / 'index.html').write_text(html, encoding='utf-8')
    Image.new('RGBA', (8, 8), (128, 128, 128, 255)).save(out / 'designs' / f'{args.key}.png')
    print(json.dumps({'actions': len(manifest['actions']), 'out': str(out)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--source', default=None, help='UO client folder (default: SPRITEMOTION_UO_SOURCE)')
    p.add_argument('--base-lab', required=True)
    p.add_argument('--base-key', required=True)
    p.add_argument('--graphic', required=True, help='ItemID of the item to merge on top, e.g. 0xA706')
    p.add_argument('--out', required=True)
    p.add_argument('--key', required=True)
    p.add_argument('--title', default=None)
    p.add_argument('--smooth', type=int, default=0,
                   help='soften the seam between the two items, fading over this many px (e.g. 3)')
    p.add_argument('--under', action='store_true', help='draw the merged item UNDER the base item (default: the merged item is on top)')
    a = p.parse_args(); a.source = client_source(a.source)
    main(a)
