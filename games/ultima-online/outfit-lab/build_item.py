"""Build A/B atlases for ONE clothing item (any tiledata item with a human animation) from a single design image.

    python build_item.py --source <client dir> --graphic 0x2684 --design shroud.png --out <dir> [--key shroud] [--actions 0 4 9]

Same texture transfer as build.py (fit_texture: native alpha and folds, new material). Output layout is what
atlas_to_vd.py expects: rows body / region mask / original / new, 256 px per frame, anchor (128,192).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'region-masks'))
import build  # noqa: E402
from uo import UOReader, client_source  # noqa: E402

DEFAULT_MASKS = REPO / 'workspace/ultima-online/region-audit/all-actions-region-pass/frames'


def main(args):
    out = Path(args.out)
    (out / 'atlases').mkdir(parents=True, exist_ok=True)
    reader = UOReader(Path(args.source))
    graphic = int(args.graphic, 0)
    item = dict(key=args.key, **reader.item(graphic))
    design = None                                 # optional with --cut: then only the shape changes, colours stay original
    if args.design:
        sheet = Image.open(args.design).convert('RGBA')
        box = sheet.getbbox()
        if box is None:
            raise SystemExit('Design image is empty')
        design = sheet.crop(box)
        design.save(out / f'{args.key}-design.png')
    elif not (args.cut or args.fray_only):
        raise SystemExit('--design is required unless --cut / --fray-only is given')
    back = None                                   # picture for the back side of the item (--planar only)
    if args.planar and args.back != 'none':
        if args.back == 'auto':                   # a plain strip of the design: left of the centre, clear of rim and emblem
            bw, bh = design.size
            back = design.crop((int(.10 * bw), int(.20 * bh), int(.19 * bw), int(.80 * bh)))
        else:
            back = Image.open(args.back).convert('RGBA')
            back = back.crop(back.getchannel('A').point(lambda v: 255 if v >= 64 else 0).getbbox())
        back.save(out / f'{args.key}-back.png')
    aid = reader.equip.get((400, item['animId']), (item['animId'], 0))[0]
    print(f"item {hex(graphic)} '{item['label']}' animId {item['animId']} -> animation {aid}, layer {item['layer']}")
    actions = json.loads((HERE.parent / 'profiles/human-actions.json').read_text())['actions']
    manifest = {'title': args.key, 'body': 400, 'canvas': 256, 'origin': [128, 192],
                'items': [item], 'actions': [], 'rows': {'body': 0, 'mask': 1}, 'missing': []}
    masks = Path(args.masks)
    try:
        for action in actions:
            a = action['index']
            if args.actions and a not in args.actions:
                continue
            entry = {**action, 'views': {}}
            for stored, facing in enumerate(build.FACING):
                body = reader.sequence(400, a, stored)
                seq = reader.sequence(aid, a, stored)
                if not body or len(seq) != len(body):
                    manifest['missing'].append({'action': a, 'facing': facing, 'body': len(body or []), 'item': len(seq or [])})
                    continue
                n = len(body)
                atlas = Image.new('RGBA', (256 * n, 256 * 4))
                pstate = {}                       # keeps the picture's top end stable across frames (--planar)
                for f, b in enumerate(body):
                    labels = np.array(Image.open(masks / f'a{a:02}_d{facing}_f{f:02}_region_ids.png'))
                    original = build.canvas(seq[f])
                    if args.cut or args.fray_only:
                        shaped = build.shorten_frayed(original, build.canvas(b), args.cut, args.fray)
                        new = build.fit_texture(shaped, design) if design is not None else shaped
                    elif not args.planar:
                        new = build.fit_texture(original, design)
                    elif back is None:
                        new = build.fit_planar(original, design, pstate)
                    elif args.back_mode == 'frame' and build.warm_fraction(original) >= args.back_warm:
                        new = build.fit_texture(original, back)      # whole frame shows the back: plain material, no emblem
                    elif args.back_mode == 'pixel':
                        # steel pixels of the original get the picture, brown pixels (inside, edge) get the plain material
                        front = np.array(build.fit_planar(original, design, pstate))
                        plain = np.array(build.fit_texture(original, back))
                        brown = build.warm_mask(original, args.warm_pixel)
                        new = Image.fromarray(np.where(brown[..., None], plain, front))
                    else:
                        new = build.fit_planar(original, design, pstate)
                    if args.hide_labels:
                        new = build.occlude(new, labels, args.hide_labels)   # cut new cloth where body regions show
                    atlas.paste(build.canvas(b), (256 * f, 0))
                    atlas.paste(original, (256 * f, 512))
                    atlas.paste(new, (256 * f, 768))
                name = f'a{a:02}_d{facing}.png'
                atlas.save(out / 'atlases' / name, optimize=True)
                entry['views'][str(facing)] = {'count': n, 'atlas': 'atlases/' + name}
            manifest['actions'].append(entry)
            print(f'Built {a}: {action["name"]}', flush=True)
    finally:
        reader.close()
    manifest['title'] = args.title or args.key
    manifest['drawOrder'] = [args.key]
    manifest['limitations'] = ['Body 400 only; one item, native alpha and folds, new material (2D texture transfer).',
                               'No independent back view is drawn: the design is sampled row by row.']
    manifest['report'] = {'source': str(args.source), 'occludedPixels': 0,
                          'missing': [{'action': m['action'], 'facing': m['facing'], 'item': args.key}
                                      for m in manifest['missing']]}
    (out / 'designs').mkdir(exist_ok=True)
    if design is not None:
        design.save(out / 'designs' / f'{args.key}.png')
    else:                                          # shape-only change: the viewer's design gallery needs some image
        Image.new('RGBA', (8, 8), (128, 128, 128, 255)).save(out / 'designs' / f'{args.key}.png')
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    (out / 'data.js').write_text('window.OUTFIT=' + json.dumps(manifest) + ';')
    html = (HERE / 'index.html').read_text(encoding='utf-8').replace('Astral Wayfarer', manifest['title'])
    (out / 'index.html').write_text(html, encoding='utf-8')
    for name in ('viewer.js', 'style.css'):
        (out / name).write_bytes((HERE / name).read_bytes())
    print(json.dumps({'actions': len(manifest['actions']), 'missing': len(manifest['missing']), 'out': str(out)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source', default=None, help='UO client folder (default: SPRITEMOTION_UO_SOURCE)')
    p.add_argument('--graphic', required=True, help='item id, e.g. 0x2684')
    p.add_argument('--design', default=None)
    p.add_argument('--cut', type=float, default=0., help='shorten a hanging item (cloak) by this fraction of its length, e.g. 0.25')
    p.add_argument('--fray', type=float, default=.07, help='how ragged the new end is (fraction of the length)')
    p.add_argument('--fray-only', action='store_true', help='fray the existing end without shortening')
    p.add_argument('--out', required=True)
    p.add_argument('--key', default='item')
    p.add_argument('--title', default=None, help='page title of the generated viewer')
    p.add_argument('--back', default='auto', help="with --planar: picture for frames where the back shows: 'auto' (plain strip of the design), 'none' or a PNG path")
    p.add_argument('--back-mode', choices=['pixel', 'frame'], default='pixel',
                   help="pixel: brown pixels of the original get the plain back material (default); frame: the whole frame")
    p.add_argument('--warm-pixel', type=int, default=25, help='r - b above this counts as a brown pixel (--back-mode pixel)')
    p.add_argument('--back-warm', type=float, default=.13, help='--back-mode frame: share of brown pixels from which a frame is the back side')
    p.add_argument('--planar', action='store_true',
                   help='lay the whole picture onto the item (shield, banner) instead of row-wise texture transfer')
    p.add_argument('--masks', default=str(DEFAULT_MASKS))
    p.add_argument('--actions', nargs='+', type=int)
    p.add_argument('--hide-labels', nargs='*', type=int, default=[],
                   help='region ids to cut out of the new cloth (build.py uses 1 5 for robes: face/hands showing)')
    a = p.parse_args(); a.source = client_source(a.source)
    main(a)
