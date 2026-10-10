"""Paperdoll gump for a hand-held item: fit a horizontal item image onto the ORIGINAL gump's axis, clip to the body.

    python make_gump.py --client <client dir> --anim 617 --image staff.png --thickness 26 --out <dir>

Gump ids: male = anim + 50000, female = male + 10000 (the usual UO convention). The original male gump must exist in the
client (Gumpidx.mul / Gumpart.mul); the female one often does not (then use Insert in UOFiddler, not Replace).
The image runs horizontally, butt/hilt on the LEFT, tip on the RIGHT (a taller-than-wide image is rotated).
Outputs in --out: orig_<id>.png, gump_<male>_male.png, gump_<female>_female.png, comparison.png.
"""
import argparse
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'region-masks'))
import build  # noqa: E402
from uo import client_source  # noqa: E402

BODY_MALE, BODY_FEMALE = 12, 13     # paperdoll body gumps


def read_gump(client, gump_id):
    idx = (client / 'Gumpidx.mul').read_bytes()
    mul = (client / 'Gumpart.mul').read_bytes()
    lo, ln, ex = struct.unpack_from('<iii', idx, 12 * gump_id)
    if lo < 0 or ln <= 0:
        return None
    w, h = (ex >> 16) & 0xFFFF, ex & 0xFFFF
    data = mul[lo:lo + ln]
    offsets = struct.unpack_from('<%dI' % h, data, 0)
    image = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        p, x = offsets[y] * 4, 0
        while x < w:
            color, run = struct.unpack_from('<HH', data, p)
            p += 4
            if color:
                image[y, x:x + run] = ((color >> 10) & 31) * 255 // 31, ((color >> 5) & 31) * 255 // 31, (color & 31) * 255 // 31, 255
            x += run
    return image


def butt_marker(shape, alpha, where):
    """Label image with one 'hand' pixel at the butt end; fit_energy_blade puts the item's left end there."""
    ys, xs = np.nonzero(alpha)
    labels = np.zeros(shape, np.uint8)
    if where == 'bottom':
        labels[ys.max(), int(xs[ys == ys.max()].mean())] = 5
    elif where == 'top':
        labels[ys.min(), int(xs[ys == ys.min()].mean())] = 5
    elif where == 'left':
        labels[int(ys[xs == xs.min()].mean()), xs.min()] = 5
    else:
        labels[int(ys[xs == xs.max()].mean()), xs.max()] = 5
    return labels


def shifted(image, dx, dy):
    out = np.zeros_like(image)
    h, w = image.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    ty, tx = ys + dy, xs + dx
    ok = (ty >= 0) & (ty < h) & (tx >= 0) & (tx < w)
    out[ty[ok], tx[ok]] = image[ys[ok], xs[ok]]
    return out


def composite(body, item):
    canvas = np.zeros(body.shape[:2] + (3,), np.uint8)
    canvas[:] = (60, 70, 90)
    for layer in (body, item):
        mask = layer[..., 3] > 0
        canvas[mask] = layer[..., :3][mask]
    return canvas


def main(a):
    client = Path(a.client)
    male_id = a.gump_id or 50000 + a.anim
    female_id = male_id + 10000
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    old = read_gump(client, male_id)
    if old is None:
        raise SystemExit(f'Original gump {male_id} not found in the client')
    Image.fromarray(old).save(out / f'orig_{male_id}.png')
    print(f'gump {male_id}: {old.shape[1]}x{old.shape[0]}; female {female_id}: '
          + ('exists in the client' if read_gump(client, female_id) is not None else 'MISSING (use Insert in UOFiddler)'))
    bodies = {'male': read_gump(client, BODY_MALE), 'female': read_gump(client, BODY_FEMALE)}

    design = Image.open(a.image).convert('RGBA')
    design = design.crop(design.getchannel('A').point(lambda v: 255 if v >= 64 else 0).getbbox())
    if design.height > design.width:
        design = design.rotate(-90, expand=True)
    old_image = Image.fromarray(old)
    labels = butt_marker(old.shape[:2], old[..., 3] > 0, a.butt)
    fitted = np.array(build.fit_energy_blade(old_image, design, labels, a.ratio, a.thickness))
    fitted[..., 3] = np.where(fitted[..., 3] >= 128, 255, 0)
    if a.outline:
        solid = Image.fromarray(fitted[..., 3])
        ring = (np.array(solid.filter(ImageFilter.MaxFilter(3))) > 0) & (fitted[..., 3] == 0)
        fitted[ring] = (24, 24, 24, 255)
    dx, dy = (int(v) for v in a.shift.split(','))
    fitted = shifted(fitted, dx, dy)

    near = np.array(Image.fromarray(np.where(old[..., 3] > 0, 255, 0).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
    if a.front_below is not None:
        near[a.front_below:, :] = False        # below this row the hand is in front of the item (e.g. below a cross-guard)
    results = {}
    for name, body in bodies.items():
        clipped = fitted.copy()
        clipped[..., 3] = np.where((fitted[..., 3] > 0) & ((body[..., 3] == 0) | near), 255, 0)
        results[name] = clipped
        target = male_id if name == 'male' else female_id
        Image.fromarray(clipped).save(out / f'gump_{target}_{name}.png')
    sheet = np.concatenate([composite(bodies['male'], old), composite(bodies['male'], results['male']),
                            composite(bodies['female'], results['female'])], 1)
    Image.fromarray(sheet).resize((sheet.shape[1] * 2, sheet.shape[0] * 2), Image.NEAREST).save(out / 'comparison.png')
    print('saved to', out)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--client', default=None, help='UO client folder (default: SPRITEMOTION_UO_SOURCE)')
    p.add_argument('--anim', type=int, required=True, help='animation id of the item (gump = anim + 50000)')
    p.add_argument('--gump-id', type=int, default=None, help='override the male gump id')
    p.add_argument('--image', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--thickness', type=float, default=None, help='item thickness in gump px (staff ~26)')
    p.add_argument('--ratio', type=float, default=.15, help='thickness as a fraction of length when --thickness is not given')
    p.add_argument('--butt', choices=['bottom', 'top', 'left', 'right'], default='bottom', help='which end of the original gump is the butt/hilt')
    p.add_argument('--shift', default='0,0', help='dx,dy shift in px after fitting (e.g. 3,-9 for the energy blade)')
    p.add_argument('--front-below', type=int, default=None, help='row from which the hand covers the item (energy blade: 106)')
    p.add_argument('--outline', action='store_true', help='add a 1 px dark outline')
    a = p.parse_args(); a.client = client_source(a.client)
    main(a)
