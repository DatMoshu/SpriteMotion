"""Garment-driven body regions for body 400, any action.

Visible silhouette = body + shirt (434) + long pants (431): the dressed reference, barefoot, gloveless.
Regions: shirt -> torso; pants -> thighs, split by knee-boot (477) alpha -> shins; bare skin below the
pants -> feet; leather sleeves (544) -> upper arms, glove (545) cuff over the sleeve -> forearms, glove
past the sleeve + bare skin out of the sleeve -> hands; plate helm (563) -> head; leather gorget (546) -> neck.
Masks (helm, gorget, sleeves, glove, knee boot) label pixels but are never drawn.
Body pixels no garment covers inherit the nearest labelled pixel.

Usage: python build_regions.py 0 9 16 21 22      (omit actions = all 35)
Then:  python package_masks.py                   (release folder: sheets, JSON, gizmos)
"""
from pathlib import Path
import sys, json, os
from collections import deque
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[2]
ROOT = Path(os.environ.get('SPRITEMOTION_REGION_WORKSPACE', str(REPO / 'workspace/ultima-online/region-audit/all-actions-region-pass'))).resolve()
from uo import UOReader, client_source

CLIENT = os.environ.get('SPRITEMOTION_UO_SOURCE')
REGIONS = ['background', 'head', 'neck', 'torso', 'upper_arms', 'hands', 'thighs', 'feet', 'shins', 'forearms', 'hips']
PALETTE = np.array([[0, 0, 0], [237, 195, 125], [219, 139, 180], [128, 189, 240],
                    [134, 213, 172], [238, 142, 119], [196, 161, 244], [197, 203, 119], [126, 157, 215], [24, 120, 104], [176, 64, 104]], np.uint8)
# (key, anim id, region) in paint order: later entries overwrite earlier ones.
GARMENTS = [('long_pants', 431, 6), ('shirt', 434, 3),
            ('leather_arms', 544, 4), ('helmet', 563, 1), ('gorget', 546, 2)]
MIN_HAND_PX = 4   # smaller hand fragments are edge noise
GLOVES = 545      # shape only: glove past the sleeve = hand, glove cuff over the sleeve = forearm
TUNIC = 909       # 0x1FA1, mask only: tunic minus shirt = the skirt over hips/upper thighs
KNEE_BOOT = 477   # 'boots' 0x170B, mask only: its top edge ~ knee
DRESSED = ['long_pants', 'shirt']   # barefoot: no boots/shoes; composited into the visible reference
NAMES = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
STORED_TO_FACING = {0: 3, 1: 4, 2: 5, 3: 6, 4: 7}   # stored direction -> facing name index


def canvas(f):
    im = Image.new('RGBA', (256, 256))
    if not f.get('empty'):
        im.alpha_composite(f['image'], (128 - f['center'][0], 192 - f['image'].height - f['center'][1]))
    return im


def nearest_fill(labels, holes):
    """BFS-propagate labels into hole pixels (4-connected, through holes only)."""
    q = deque((int(y), int(x)) for y, x in np.argwhere(labels > 0))
    h, w = labels.shape
    while q:
        y, x = q.popleft()
        for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= yy < h and 0 <= xx < w and holes[yy, xx] and labels[yy, xx] == 0:
                labels[yy, xx] = labels[y, x]; q.append((yy, xx))
    return labels


def frame_regions(body, garments):
    dressed = canvas(body)
    for key in DRESSED:
        if garments[key] is not None:
            dressed = Image.alpha_composite(dressed, canvas(garments[key]))
    visible = np.array(dressed.getchannel('A')) > 0
    labels = np.zeros((256, 256), np.uint8)
    for key, _, region in GARMENTS:
        if garments[key] is not None:
            labels[(np.array(canvas(garments[key]).getchannel('A')) > 0) & visible] = region
    seeded = labels > 0
    labels = nearest_fill(labels, visible)
    # Bare skin that grew out of the pants is the foot (no shoe evidence exists).
    labels[visible & ~seeded & (labels == 6)] = 7
    # Naked hand = bare skin grown out of a sleeve, plus the glove's shape past the sleeve's end.
    # The glove cuff overlaps the sleeve (forearm), so only glove-minus-sleeve is hand; that part
    # also recovers fists held in front of the shirt/pants, where no bare skin is visible.
    hand = visible & ~seeded & (labels == 4)
    if garments.get('gloves_ref') is not None:
        sleeve = np.array(canvas(garments['leather_arms']).getchannel('A')) > 0 if garments['leather_arms'] is not None else False
        glove = np.array(canvas(garments['gloves_ref']).getchannel('A')) > 0
        hand |= visible & glove & ~sleeve & (labels != 1)
    # Drop specks: glove/sleeve edges leave 1-3 px slivers that are not a hand.
    comp, n = ndimage.label(hand)
    if n:
        sizes = ndimage.sum(hand, comp, range(1, n + 1))
        hand &= np.isin(comp, 1 + np.flatnonzero(sizes >= MIN_HAND_PX))
    labels[hand] = 5
    # Forearm = sleeve pixels under the glove's cuff (wrist up to about the elbow).
    # The shirt's short-sleeve edge was tried and rejected: it sits above the elbow.
    if garments.get('gloves_ref') is not None:
        labels[(labels == 4) & (np.array(canvas(garments['gloves_ref']).getchannel('A')) > 0)] = 9
    # Knee-boot alpha splits the pants leg: under the boot = shin, above = thigh. Feet stay feet.
    if garments.get('knee_boot') is not None:
        labels[(np.array(canvas(garments['knee_boot']).getchannel('A')) > 0) & (labels == 6)] = 8
    # Tunic skirt: tunic alpha minus shirt alpha, only on pants/thigh pixels (tunic sleeves ignored).
    # Leaves the lower thigh between the hem and the boot top, so the knee reads clearly.
    if garments.get('tunic') is not None:
        skirt = (np.array(canvas(garments['tunic']).getchannel('A')) > 0)
        if garments['shirt'] is not None:
            skirt &= ~(np.array(canvas(garments['shirt']).getchannel('A')) > 0)
        labels[skirt & (labels == 6)] = 10
    labels[visible & (labels == 0)] = 255      # disconnected from every garment: unknown
    return dressed, labels, seeded


def build(actions):
    (ROOT / 'frames').mkdir(parents=True, exist_ok=True)
    reader = UOReader(client_source(CLIENT))
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 18)
    small = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 13)
    old = ROOT / 'region-report.json'
    report = json.loads(old.read_text()) if old.exists() else {}
    report.update({'regions': REGIONS, 'garments': {k: a for k, a, _ in GARMENTS}})
    report.setdefault('actions', {})
    for action in actions:
        rows = []; meta = []
        stats = {'frames': 0, 'seededFraction': [], 'unknownPixels': 0, 'garmentMismatch': [], 'handVsGlove': []}
        for stored in range(5):
            body = reader.sequence(400, action, stored)
            if not body:
                continue
            seqs = {k: reader.sequence(a, action, stored) for k, a, _ in GARMENTS}
            seqs['knee_boot'] = reader.sequence(KNEE_BOOT, action, stored)
            seqs['tunic'] = reader.sequence(TUNIC, action, stored)
            gloves = reader.sequence(GLOVES, action, stored)
            seqs['gloves_ref'] = gloves
            for k, s in seqs.items():
                if len(s) != len(body):
                    stats['garmentMismatch'].append([k, stored, len(s), len(body)])
            row = []
            for i, b in enumerate(body):
                meta.append({'stored': stored, 'facing': NAMES[STORED_TO_FACING[stored]], 'index': i,
                             'center': b['center'], 'size': list(b['image'].size), 'empty': bool(b.get('empty')),
                             'sourceRecord': b['sourceRecord'], 'sourceRgbaSha256': b.get('sourceRgbaSha256')})
                g = {k: (s[i] if len(s) == len(body) else None) for k, s in seqs.items()}
                dressed, labels, seeded = frame_regions(b, g)
                prefix = f'a{action:02}_d{STORED_TO_FACING[stored]}_f{i:02}'
                dressed.save(ROOT / 'frames' / f'{prefix}_clothed.png')
                canvas(b).save(ROOT / 'frames' / f'{prefix}_body.png')
                Image.fromarray(labels).save(ROOT / 'frames' / f'{prefix}_region_ids.png')
                vis = labels > 0
                stats['frames'] += 1
                stats['seededFraction'].append(float((seeded & vis).sum() / max(1, vis.sum())))
                stats['unknownPixels'] += int((labels == 255).sum())
                if len(gloves) == len(body):
                    glove = (np.array(canvas(gloves[i]).getchannel('A')) > 0) & vis
                    hand = labels == 5
                    stats['handVsGlove'].append([int((hand & glove).sum()), int(hand.sum()), int(glove.sum())])
                row.append((dressed, labels))
            rows.append((stored, row))
        if not rows:
            print(f'action {action}: no body frames'); continue
        hv = np.array(stats['handVsGlove']).sum(axis=0)
        stats['handVsGlove'] = {'bareHandPx': int(hv[1]), 'glovePx': int(hv[2]), 'overlapPx': int(hv[0])}
        report['actions'][str(action)] = {**stats, 'seededFraction': round(float(np.mean(stats['seededFraction'])), 3)}
        (ROOT / 'frames' / f'a{action:02}_meta.json').write_text(json.dumps(meta))
        sheet(action, rows, font, small)
        print(f'action {action}: {stats["frames"]} frames, seeded {report["actions"][str(action)]["seededFraction"]:.0%}, '
              f'unknown px {stats["unknownPixels"]}, mismatches {len(stats["garmentMismatch"])}, hand/glove {stats["handVsGlove"]}', flush=True)
    reader.close()
    (ROOT / 'region-report.json').write_text(json.dumps(report, indent=2))


def colorize(labels):
    rgba = np.zeros((256, 256, 4), np.uint8)
    rgba[:, :, :3] = np.where((labels == 255)[..., None], [255, 0, 0], PALETTE[np.minimum(labels, 10)])
    rgba[:, :, 3] = (labels > 0) * 255
    return Image.fromarray(rgba)


def sheet(action, rows, font, small, max_cols=24, cell=150):
    ncols = min(max_cols, max(len(r) for _, r in rows))
    W = 20 + ncols * (2 * cell + 16); H = 100 + len(rows) * (cell + 30) + 40
    im = Image.new('RGB', (W, H), '#1c292d'); d = ImageDraw.Draw(im)
    d.text((18, 12), f'Action {action} | body 400 | garment regions (shirt / long pants, barefoot + naked hands, glove-cuff forearms, tunic-skirt hips, knee-boot shins, sleeves, helm, gorget)',
           font=font, fill='white')
    d.text((18, 40), 'Each cell: dressed reference | region estimate. Five stored views; N, NE, E = mirrored W, SW, S. '
           'Regions are estimates, not reviewed anatomy. Red = unknown.', font=small, fill='#bacbd1')
    x = 18
    for rid, name in enumerate(REGIONS[1:], 1):
        d.rectangle((x, 62, x + 14, 76), fill=tuple(PALETTE[rid].tolist())); d.text((x + 19, 62), name, font=small, fill='white'); x += 100
    for r, (stored, frames) in enumerate(rows):
        idx = np.unique(np.linspace(0, len(frames) - 1, min(ncols, len(frames))).round().astype(int))
        boxes = [f[0].getbbox() for f in frames if f[0].getbbox()]
        x0 = min(b[0] for b in boxes) - 4; y0 = min(b[1] for b in boxes) - 4
        x1 = max(b[2] for b in boxes) + 4; y1 = max(b[3] for b in boxes) + 4
        side = max(x1 - x0, y1 - y0); cx = (x0 + x1) / 2; cy = (y0 + y1) / 2
        box = (round(cx - side / 2), round(cy - side / 2), round(cx + side / 2), round(cy + side / 2))
        for c, i in enumerate(idx):
            ox = 20 + c * (2 * cell + 16); oy = 100 + r * (cell + 30) + 18
            dressed, labels = frames[i]
            for k, src in enumerate([dressed, colorize(labels)]):
                crop = src.crop(box).resize((cell, cell), Image.Resampling.NEAREST)
                im.paste(crop, (ox + k * cell, oy), crop)
            d.text((ox, oy - 17), f'{NAMES[STORED_TO_FACING[stored]]} / F{i}', font=small, fill='white')
    (ROOT / 'compare').mkdir(exist_ok=True)
    im.save(ROOT / 'compare' / f'regions-action{action:02}.png')


if __name__ == '__main__':
    build([int(a) for a in sys.argv[1:]] or list(range(35)))
