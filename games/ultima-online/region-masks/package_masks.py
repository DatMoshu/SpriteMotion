"""Package build_regions.py output into a shareable release folder.

Per action: compare sheet, mask-only sprite sheets (colour, raw IDs, body reference) + JSON sidecar,
and a gizmo sheet (anchor, cell, bbox, region axes, joint candidates) for aligning a 3D model.

Usage: python package_masks.py            (after build_regions.py has run for all actions)
"""
from pathlib import Path
import sys, json, re, shutil, hashlib
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFont
from region_fonts import load_font

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_regions as B
SCRIPT_DIR = ROOT
ROOT = B.ROOT

OUT = ROOT / 'uo-body400-region-masks'
FRAMES = ROOT / 'frames'
PAD = 2               # transparent border around the union bbox of an action's frames
GIZMO_SCALE = 4
MIN_PART_PX = 6       # smaller connected pieces of a region are not reported as parts
MIN_EDGE_PX = 3       # joint candidates from fewer shared edge pixels are noise
# Boundaries between regions -> joint candidates. Names say what the boundary is, not a claimed bone.
JOINTS = [('neck_top', 'head', 'neck'), ('neck_base', 'neck', 'torso'), ('shoulder', 'torso', 'upper_arms'),
          ('elbow_approx', 'upper_arms', 'forearms'), ('wrist', 'forearms', 'hands'),
          ('waist', 'torso', 'hips'), ('skirt_hem', 'hips', 'thighs'), ('knee', 'thighs', 'shins'),
          ('knee_fallback', 'hips', 'shins'), ('ankle', 'shins', 'feet')]
JOINT_TAG = {'neck_top': 'Nt', 'neck_base': 'Nb', 'shoulder': 'Sh', 'elbow_approx': 'El', 'wrist': 'Wr',
             'waist': 'Wa', 'skirt_hem': 'Hm', 'knee': 'Kn', 'knee_fallback': 'Kf', 'ankle': 'An'}
SOURCES = {'head': 'plate helm anim 563 (mask only)', 'neck': 'leather gorget anim 546 (mask only)',
           'torso': 'shirt anim 434 (drawn)', 'upper_arms': 'leather sleeves anim 544 minus glove cuff (mask only)',
           'forearms': 'leather glove anim 545 cuff over the sleeve (mask only)',
           'hands': 'bare skin out of the sleeve + glove anim 545 past the sleeve (mask only)',
           'thighs': 'long pants anim 431 between the tunic hem and the knee-boot top (drawn)',
           'feet': 'bare skin below the pants', 'shins': 'knee boots anim 477 over the pants (mask only)',
           'hips': 'tunic anim 909 minus shirt 434, over the pants (mask only)'}
REGION_IDS = {n: i for i, n in enumerate(B.REGIONS)}
# Bones: limb region -> (regions at its proximal end, regions at its distal end). A bone runs between the
# boundary points at both ends of one connected limb piece. Head, hips, hands and feet get no bone line:
# their principal axis describes a blob's shape, not a bone.
BONES = {'torso': (['neck'], ['hips']), 'upper_arms': (['torso', 'neck'], ['forearms']),
         'forearms': (['upper_arms'], ['hands']), 'thighs': (['hips'], ['shins']),
         'shins': (['thighs', 'hips'], ['feet'])}
BONE_COLOR = {'torso': '#2f6fb0', 'upper_arms': '#1f8a58', 'forearms': '#0b4a40', 'thighs': '#7a4fc0', 'shins': '#34549a'}
STORED = {0: 'SE', 1: 'S', 2: 'SW', 3: 'W', 4: 'NW'}


def action_names():
    idx = ROOT.parent / 'reference/anim_400_index.json'
    return {a['action']: a['name'] for a in json.loads(idx.read_text())['animations']}


def hexcolor(rgb):
    return '#%02x%02x%02x' % tuple(int(v) for v in rgb)


def axis(ys, xs):
    """Principal axis of a pixel set: centre, direction angle and end points (pixel centres)."""
    pts = np.stack([xs, ys], 1).astype(float); c = pts.mean(0)
    if len(pts) < 3:
        return None
    w, v = np.linalg.eigh(np.cov((pts - c).T)); d = v[:, np.argmax(w)]
    if d[1] < 0 or (d[1] == 0 and d[0] < 0):
        d = -d                                        # point downward/right for a stable sign
    t = (pts - c) @ d
    return {'angleDeg': round(float(np.degrees(np.arctan2(d[1], d[0]))), 1),
            'length': round(float(t.max() - t.min()), 1),
            'p0': [round(float(v), 1) for v in c + d * t.min()], 'p1': [round(float(v), 1) for v in c + d * t.max()],
            'elongation': round(float(np.sqrt(max(w.max(), 1e-6) / max(w.min(), 1e-6))), 2)}


def to_local(v, anchor):
    return [round(float(v[0] - anchor[0]), 1), round(float(v[1] - anchor[1]), 1)]


def describe(labels, anchor):
    """Region stats and joint candidates, in anchor-relative pixels (x right, y down, ground anchor = 0,0)."""
    regions = {}
    for name, rid in REGION_IDS.items():
        if rid == 0:
            continue
        m = labels == rid
        if not m.any():
            continue
        ys, xs = np.nonzero(m)
        comp, n = ndimage.label(m, structure=np.ones((3, 3)))
        parts = []
        for k in range(1, n + 1):
            py, px = np.nonzero(comp == k)
            if len(py) < MIN_PART_PX:
                continue
            ax = axis(py, px)
            if ax:
                ax['p0'] = to_local(ax['p0'], anchor); ax['p1'] = to_local(ax['p1'], anchor)
            parts.append({'px': int(len(py)), 'centroid': to_local((px.mean(), py.mean()), anchor),
                          'bbox': [int(px.min() - anchor[0]), int(py.min() - anchor[1]), int(px.ptp() + 1), int(py.ptp() + 1)],
                          'axis': ax})
        parts.sort(key=lambda p: -p['px'])
        regions[name] = {'id': rid, 'px': int(m.sum()), 'centroid': to_local((xs.mean(), ys.mean()), anchor),
                         'bbox': [int(xs.min() - anchor[0]), int(ys.min() - anchor[1]), int(xs.ptp() + 1), int(ys.ptp() + 1)],
                         'parts': parts}
    joints = {}
    for jname, a, b in JOINTS:
        ma, mb = labels == REGION_IDS[a], labels == REGION_IDS[b]
        if not (ma.any() and mb.any()):
            continue
        near_b = ndimage.binary_dilation(mb); near_a = ndimage.binary_dilation(ma)
        edge = (ma & near_b) | (mb & near_a)
        comp, n = ndimage.label(ndimage.binary_dilation(edge), structure=np.ones((3, 3)))
        pts = []
        for k in range(1, n + 1):
            py, px = np.nonzero((comp == k) & edge)
            if len(py) >= MIN_EDGE_PX:
                pts.append({'xy': to_local((px.mean(), py.mean()), anchor), 'edgePx': int(len(py))})
        if pts:
            joints[jname] = sorted(pts, key=lambda p: -p['edgePx'])
    return regions, joints, bones(labels, anchor)


def edge_points(part, neighbour):
    """Centres of the stretches where a limb piece touches a neighbouring region."""
    edge = part & ndimage.binary_dilation(neighbour)
    comp, n = ndimage.label(ndimage.binary_dilation(edge), structure=np.ones((3, 3)))
    out = []
    for k in range(1, n + 1):
        py, px = np.nonzero((comp == k) & edge)
        if len(py) >= MIN_EDGE_PX:
            out.append((np.array([px.mean(), py.mean()]), len(py)))
    return out


def bones(labels, anchor):
    result = []
    for region, (prox_names, dist_names) in BONES.items():
        comp, n = ndimage.label(labels == REGION_IDS[region], structure=np.ones((3, 3)))
        prox_mask = np.isin(labels, [REGION_IDS[r] for r in prox_names])
        dist_mask = np.isin(labels, [REGION_IDS[r] for r in dist_names])
        for k in range(1, n + 1):
            part = comp == k
            if part.sum() < MIN_PART_PX:
                continue
            prox, dist = edge_points(part, prox_mask), edge_points(part, dist_mask)
            ys, xs = np.nonzero(part); pts = np.stack([xs, ys], 1).astype(float)
            pairs = []
            if prox and dist:
                # Merged limbs (both legs in one piece) have 2 ends each side: pair each distal end
                # with its nearest proximal end.
                for dp, dn in dist:
                    pp, pn = min(prox, key=lambda q: np.linalg.norm(q[0] - dp))
                    pairs.append((pp, dp, 'joints', min(pn, dn)))
            elif prox or dist:
                # One end known: the other end is the piece's farthest pixel from it.
                for q, qn in (prox or dist):
                    far = pts[np.argmax(np.linalg.norm(pts - q, axis=1))]
                    pairs.append((q, far, 'joint+extent', qn) if prox else (far, q, 'extent+joint', qn))
            for a, b, method, support in pairs:
                if np.linalg.norm(b - a) < 2:
                    continue
                result.append({'region': region, 'from': to_local(a, anchor), 'to': to_local(b, anchor),
                               'length': round(float(np.linalg.norm(b - a)), 1),
                               'angleDeg': round(float(np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0]))), 1),
                               'method': method, 'edgePx': int(support)})
    return result


def package_action(action, name, font, small):
    meta = json.loads((FRAMES / f'a{action:02}_meta.json').read_text())
    items = []
    for m in meta:
        p = FRAMES / f"a{action:02}_d{B.STORED_TO_FACING[m['stored']]}_f{m['index']:02}"
        items.append((m, np.array(Image.open(f'{p}_region_ids.png')), Image.open(f'{p}_body.png')))
    boxes = [Image.fromarray(((l > 0) * 255).astype(np.uint8)).getbbox() for _, l, _ in items]
    boxes = [b for b in boxes if b]
    x0 = min(b[0] for b in boxes) - PAD; y0 = min(b[1] for b in boxes) - PAD
    x1 = max(b[2] for b in boxes) + PAD; y1 = max(b[3] for b in boxes) + PAD
    cw, ch = x1 - x0, y1 - y0
    cols = max(m['index'] for m, _, _ in items) + 1
    rows = sorted({m['stored'] for m, _, _ in items})
    W, H = cols * cw, len(rows) * ch
    color = Image.new('RGBA', (W, H)); ids = Image.new('L', (W, H)); body = Image.new('RGBA', (W, H))
    anchor_cell = [128 - x0, 192 - y0]
    folder = OUT / 'sheets' / f'a{action:02}_{name}'; folder.mkdir(parents=True, exist_ok=True)
    frames = []
    gz = []   # (cell origin, labels, body, frame record)
    for m, labels, bimg in items:
        r = rows.index(m['stored']); ox, oy = m['index'] * cw, r * ch
        crop = (x0, y0, x1, y1)
        color.paste(B.colorize(labels).crop(crop), (ox, oy))
        ids.paste(Image.fromarray(labels).crop(crop), (ox, oy))
        body.paste(bimg.crop(crop), (ox, oy))
        regions, joints, bone_list = describe(labels, (128, 192))
        vis = labels > 0
        bb = None
        if vis.any():
            ys, xs = np.nonzero(vis); bb = [int(xs.min() - 128), int(ys.min() - 192), int(xs.ptp() + 1), int(ys.ptp() + 1)]
        rec = {'facing': m['facing'], 'storedDirection': m['stored'], 'frame': m['index'],
               'rect': [ox, oy, cw, ch], 'anchor': [ox + anchor_cell[0], oy + anchor_cell[1]],
               'bbox': bb, 'pixels': int(vis.sum()), 'unknownPixels': int((labels == 255).sum()),
               'regions': regions, 'joints': joints, 'bones': bone_list,
               'source': {'body': 400, 'action': action, 'record': m['sourceRecord'], 'center': m['center'],
                          'size': m['size'], 'rgbaSha256': m['sourceRgbaSha256'], 'empty': m['empty']}}
        frames.append(rec); gz.append(((ox, oy), labels.copy(), bimg, rec))
    color.save(folder / 'mask_color.png', optimize=True)
    ids.save(folder / 'mask_ids.png', optimize=True)
    body.save(folder / 'body.png', optimize=True)
    sidecar = {'schema': 'uo-body400-region-masks/frames@1', 'body': 400, 'action': action, 'name': name,
               'sheetSize': [W, H], 'cellSize': [cw, ch], 'anchorInCell': anchor_cell,
               'layout': 'rows = stored directions (' + ', '.join(STORED[s] for s in rows) + '), columns = frame index',
               'images': {'mask_color': 'mask_color.png', 'mask_ids': 'mask_ids.png', 'body': 'body.png'},
               'coordinates': 'rect/anchor are sheet pixels. Everything under regions/joints/bbox is anchor-relative '
                              'pixels: x right, y down, (0,0) = ground anchor. sheet_xy = anchor + local_xy.',
               'frames': frames}
    (folder / 'frames.json').write_text(json.dumps(sidecar, separators=(',', ':')))
    gizmo(action, name, gz, rows, cols, (cw, ch), anchor_cell, font, small)
    return {'action': action, 'name': name, 'frames': len(frames), 'directions': [STORED[s] for s in rows],
            'framesPerDirection': cols, 'cellSize': [cw, ch], 'anchorInCell': anchor_cell,
            'sheet': f'sheets/a{action:02}_{name}/frames.json', 'gizmo': f'gizmos/a{action:02}_{name}.png',
            'compare': f'compare/a{action:02}_{name}.png'}


def gizmo(action, name, gz, rows, cols, cell, anchor_cell, font, small):
    s = GIZMO_SCALE; cw, ch = cell[0] * s, cell[1] * s; gap = 26; top = 150
    W = max(1100, 20 + cols * (cw + 12)); H = top + len(rows) * (ch + gap) + 20
    im = Image.new('RGB', (W, H), '#1c292d'); d = ImageDraw.Draw(im)
    d.text((16, 10), f'Action {action} {name} | body 400 | alignment gizmos', font=font, fill='white')
    lines = [f'Cell {cell[0]}x{cell[1]} px, drawn at {s}x. Anchor (ground point, magenta cross) at cell ({anchor_cell[0]},{anchor_cell[1]}); '
             'magenta line = ground row through the anchor.',
             'White box = tight sprite bbox (label: local x,y,w,h). Thick lines = bones between the joint points at both ends of a limb piece '
             '(grey = one end estimated from the far edge of the piece). Dots = region centroids.',
             'Rings = joint candidates where two regions meet: Nt neck top, Nb neck base, Sh shoulder, El elbow (approx.), '
             'Wr wrist, Wa waist, Hm skirt hem, Kn knee, Kf knee fallback, An ankle.',
             'All numbers are in frames.json (anchor-relative px). Left/right is not identified. Estimates, not reviewed anatomy.']
    for k, t in enumerate(lines):
        d.text((16, 38 + k * 17), t, font=small, fill='#bacbd1')
    x = 16
    for rid, rn in enumerate(B.REGIONS[1:], 1):
        d.rectangle((x, 112, x + 13, 125), fill=tuple(B.PALETTE[rid].tolist())); d.text((x + 17, 111), rn, font=small, fill='white'); x += 100
    x0 = 128 - anchor_cell[0]; y0 = 192 - anchor_cell[1]
    for (ox, oy), labels, bimg, rec in gz:
        r = rows.index(rec['storedDirection']); gx = 20 + rec['frame'] * (cw + 12); gy = top + r * (ch + gap) + 16
        crop = (x0, y0, x0 + cell[0], y0 + cell[1])
        base = bimg.crop(crop).convert('RGBA'); mask = B.colorize(labels).crop(crop)
        blend = Image.blend(base, mask, 0.6); blend.putalpha(base.getchannel('A'))
        bg = Image.new('RGBA', blend.size, (40, 56, 61, 255)); bg.alpha_composite(blend)
        im.paste(bg.resize((cw, ch), Image.Resampling.NEAREST), (gx, gy))
        d.rectangle((gx, gy, gx + cw - 1, gy + ch - 1), outline='#5d7680')
        d.text((gx, gy - 15), f"{rec['facing']} F{rec['frame']}", font=small, fill='white')
        P = lambda p: (gx + (anchor_cell[0] + p[0] + .5) * s, gy + (anchor_cell[1] + p[1] + .5) * s)
        ax_, ay_ = gx + anchor_cell[0] * s, gy + anchor_cell[1] * s
        d.line((gx, ay_, gx + cw - 1, ay_), fill='#b0409a'); d.line((ax_ - 7, ay_, ax_ + 7, ay_), fill='#ff4fd8', width=2)
        d.line((ax_, ay_ - 7, ax_, ay_ + 7), fill='#ff4fd8', width=2)
        if rec['bbox']:
            bx, by, bw, bh = rec['bbox']
            d.rectangle((gx + (anchor_cell[0] + bx) * s, gy + (anchor_cell[1] + by) * s,
                         gx + (anchor_cell[0] + bx + bw) * s - 1, gy + (anchor_cell[1] + by + bh) * s - 1), outline='white')
            d.text((gx + 2, gy + ch - 14), f'{bx},{by},{bw},{bh}', font=small, fill='#e8e8e8')
        for rn, reg in rec['regions'].items():
            col = tuple(int(v * .45) for v in B.PALETTE[reg['id']]) if reg['id'] < len(B.PALETTE) else (255, 0, 0)
            for part in reg['parts']:
                cx, cy = P(part['centroid']); d.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=col)
        for bone in rec['bones']:
            d.line((P(bone['from']), P(bone['to'])), fill='black', width=5)
            d.line((P(bone['from']), P(bone['to'])), fill=BONE_COLOR[bone['region']] if bone['method'] == 'joints' else '#e0e0e0', width=3)
        for jn, pts in rec['joints'].items():
            for p in pts:
                cx, cy = P(p['xy'])
                d.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), outline='white', width=2)
                d.text((cx + 5, cy - 6), JOINT_TAG[jn], font=small, fill='white', stroke_width=2, stroke_fill='black')
    im.save(OUT / 'gizmos' / f'a{action:02}_{name}.png', optimize=True)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    for sub in ['sheets', 'gizmos', 'compare']:
        (OUT / sub).mkdir(parents=True)
    names = action_names()
    font = load_font(18)
    small = load_font(12)
    report = json.loads((ROOT / 'region-report.json').read_text())
    actions = []
    for a in range(35):
        if not (FRAMES / f'a{a:02}_meta.json').exists():
            print('skip', a); continue
        name = re.sub(r'[^A-Za-z0-9_]+', '_', names.get(a, f'action{a}'))
        shutil.copy(ROOT / 'compare' / f'regions-action{a:02}.png', OUT / 'compare' / f'a{a:02}_{name}.png')
        info = package_action(a, name, font, small)
        info['quality'] = {k: report['actions'][str(a)][k] for k in ['seededFraction', 'unknownPixels', 'garmentMismatch']}
        actions.append(info); print('packaged', a, name, info['frames'], flush=True)
    manifest = {
        'schema': 'uo-body400-region-masks/manifest@1', 'body': 400, 'bodyName': 'human male (classic anim.mul)',
        'status': 'Estimated from garment silhouettes; not manually reviewed anatomy.',
        'regions': [{'id': i, 'name': n, 'color': hexcolor(B.PALETTE[i]), 'source': SOURCES.get(n)}
                    for i, n in enumerate(B.REGIONS) if i] + [{'id': 255, 'name': 'unknown', 'color': '#ff0000'}],
        'visibleReference': 'naked body 400 + shirt 434 + long pants 431 (barefoot, no gloves, no helm)',
        'directions': {'stored': [{'stored': k, 'facing': v} for k, v in STORED.items()],
                       'mirrored': [{'facing': 'N', 'mirrorOf': 'W'}, {'facing': 'NE', 'mirrorOf': 'SW'}, {'facing': 'E', 'mirrorOf': 'S'}],
                       'mirrorRule': 'Flip horizontally about the anchor x (x_local -> -x_local). Mirroring swaps apparent left/right.'},
        'coordinates': {'local': 'anchor-relative pixels, x right, y down; anchor = ground contact point of the sprite',
                        'sheet': 'sheet_xy = frame.anchor + local_xy', 'pixelCentres': 'region/joint points are pixel centres (+0.5 applied when drawing)',
                        'sourcePlacement': 'UO draws a frame with its top-left at (anchor.x - center.x, anchor.y - height - center.y); '
                                           'source.center/size are the original anim.mul values.'},
        'camera': {'groundTile': 'one world tile step projects to (22, 22) and (22, -22) px (client ground grid)',
                   'characterProjection': 'approximately orthographic, ~45 deg elevation, 45 deg heading steps between facings. '
                                          'Measured in the UOCharacter2 stage; one study found character depth closer to 1/sqrt(5). Not recovered production metadata.',
                   'alignmentTip': 'Place the model root on the anchor, match torso centroid and axis, then limb axes; '
                                   'use joint candidates as soft targets (weight by edgePx).'},
        'joints': {j: f'boundary between {a} and {b}' for j, a, b in JOINTS},
        'jointCaveats': ['elbow_approx: top of the glove cuff; in fully straight arms it sits nearer the wrist than the real elbow.',
                         'knee: thigh/shin boundary; when the tunic hem reaches the boot top use knee_fallback (hips/shins).',
                         'skirt_hem and waist are garment edges, not hip joints.',
                         'Paired limbs are not split left/right; each joint may list 0-2+ points (largest edgePx first).',
                         'Occluded limbs have no pixels and therefore no points.'],
        'actions': actions,
        'generator': {'scripts': ['build_regions.py', 'package_masks.py'], 'client': 'UO Classic anim.mul/anim.idx (read only)'}}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    shutil.copy(SCRIPT_DIR / 'RELEASE_README.md', OUT / 'README.md')
    # Canonical scripts live in games/ultima-online/region-masks.
    sums = {str(p.relative_to(OUT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(OUT.rglob('*')) if p.is_file()}
    (OUT / 'checksums.json').write_text(json.dumps(sums, indent=1))
    print('actions', len(actions), 'frames', sum(a['frames'] for a in actions))


if __name__ == '__main__':
    main()
