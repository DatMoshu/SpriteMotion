"""Paperdoll gump for a cloak merged with a hood: shorten and fray the cloak gump, lay the hood gump over it.

    python make_gump_cloak.py --client <client> --cloak-gump 50468 --hood-gump 50400 --out <dir> [--cut .25] [--fray .07]

Male gumps are given; the female ones are taken as +10000 when they exist in the client, otherwise the male gump is used.
Same shape logic as the animation (build.shorten_frayed, merge_items.blend_seam), so the paperdoll matches the .vd.
Outputs in --out: gump_<cloak id>_male.png, gump_<cloak id + 10000>_female.png, comparison.png and the source gumps.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'region-masks'))
import build  # noqa: E402
from uo import client_source  # noqa: E402
import make_gump  # noqa: E402
import merge_items  # noqa: E402


def load(client, gump_id):
    array = make_gump.read_gump(client, gump_id)
    return None if array is None else Image.fromarray(array)


def main(a):
    client, out = Path(a.client), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    bodies = {'male': load(client, 12), 'female': load(client, 13)}
    cloak_ids = {'male': a.cloak_gump, 'female': a.cloak_gump + 10000}
    hood_ids = {'male': a.hood_gump, 'female': a.hood_gump + 10000}
    results = {}
    for sex in ('male', 'female'):
        cloak = load(client, cloak_ids[sex]) or load(client, cloak_ids['male'])
        hood = load(client, hood_ids[sex]) or load(client, hood_ids['male'])
        print(f'{sex}: cloak gump {cloak_ids[sex]} '
              + ('found' if load(client, cloak_ids[sex]) else 'MISSING (male gump used)')
              + f', hood gump {hood_ids[sex]} ' + ('found' if load(client, hood_ids[sex]) else 'MISSING (male gump used)'))
        if cloak is None or hood is None:
            raise SystemExit('Original cloak/hood gump not found in the client')
        cloak.save(out / f'orig_cloak_{sex}.png')
        hood.save(out / f'orig_hood_{sex}.png')
        short = build.shorten_frayed(cloak.convert('RGBA'), bodies[sex].convert('RGBA'), a.cut, a.fray, a.tooth)
        merged = merge_items.blend_seam(hood.convert('RGBA'), short, a.smooth) if a.smooth else None
        if merged is None:
            merged = Image.new('RGBA', short.size)
            merged.alpha_composite(short)
            merged.alpha_composite(hood.convert('RGBA'))
        results[sex] = merged
        merged.save(out / f'gump_{cloak_ids[sex]}_{sex}.png')

    def comp(body, *layers):
        canvas = np.zeros(body.size[::-1] + (3,), np.uint8)
        canvas[:] = (60, 70, 90)
        for layer in (body, *layers):
            arr = np.array(layer.convert('RGBA'))
            mask = arr[..., 3] > 0
            canvas[mask] = arr[..., :3][mask]
        return canvas

    male_orig = comp(bodies['male'], load(client, cloak_ids['male']), load(client, hood_ids['male']))
    sheet = np.concatenate([male_orig, comp(bodies['male'], results['male']), comp(bodies['female'], results['female'])], 1)
    Image.fromarray(sheet).resize((sheet.shape[1] * 2, sheet.shape[0] * 2), Image.NEAREST).save(out / f'comparison_tooth{a.tooth:g}_cut{a.cut:g}.png')      # named per setting: an open viewer locks the file
    print('saved to', out)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--client', default=None, help='UO client folder (default: SPRITEMOTION_UO_SOURCE)')
    p.add_argument('--cloak-gump', type=int, required=True, help='male gump of the cloak (anim + 50000, e.g. 50468)')
    p.add_argument('--hood-gump', type=int, required=True, help='male gump of the hood (e.g. 50400 from Equipconv)')
    p.add_argument('--out', required=True)
    p.add_argument('--cut', type=float, default=.25)
    p.add_argument('--fray', type=float, default=.07)
    p.add_argument('--tooth', type=float, default=9., help='width of one ragged tooth in px (the gump is larger than the sprite)')
    p.add_argument('--smooth', type=int, default=3)
    a = p.parse_args(); a.client = client_source(a.client)
    main(a)
