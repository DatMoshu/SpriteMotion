"""Clothing poke-through benchmark: dress a candidate body-400 replacement in every original UO garment.

For each wearable anim ID in the classic anim.mul (clothing/armour layers; weapons, shields, hair and beards
excluded), every action, stored direction and frame is composited over the ORIGINAL body and over the CANDIDATE
body. The garment layer is authentic, so any candidate skin that shows where the original body did not is a leak:

  leak   = candidate & ~original & ~garment
  poke   = leak whose nearest original-body pixel was hidden by the garment (skin pushes past the cloth edge)
  edge   = leak whose nearest original-body pixel was exposed skin (bare hand/foot/head silhouette mismatch)
  gap    = original & ~candidate & ~garment (exposed skin the candidate fails to fill)

Region masks (build_regions.frame_regions) name every body pixel. Per garment and stored direction, a region is
'covered' when >= COVER of its original pixels sit under the garment: that is the outfit's exposure contract,
i.e. what should and should not poke out. The mask trim applies the contract to the candidate: body pixels of a
covered region outside the garment are erased. Wrong-trim counts what the same rule would wrongly erase from the
original body, so the contract is validated on the authentic frames.

Usage:
  python clothing_fit.py --vd <path to body.vd> --label levy-v10 --out workspace/levy-review/clothing-fit
  python clothing_fit.py --frames workspace/ultima-online/cc4-fullpass/renders-male --label cc4-male --out ...
Frames dirs hold action-NNN/d{facing}_fNN.png 256x256 canvases anchored at (128,192).
"""
from pathlib import Path
import argparse, hashlib, json, os, struct, sys, time
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFont
from region_fonts import load_font

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(SCRIPT_DIR))
import build_regions as B
from uo import UOReader, client_source

CLOTHING_LAYERS = {3, 4, 5, 6, 7, 10, 12, 13, 17, 19, 20, 22, 23}   # not 1/2 hand-held, 11 hair, 16 beard
COVER = 0.95          # region is 'covered' by a garment in a direction at this original coverage
NAMES = B.NAMES
S2F = B.STORED_TO_FACING


class FastReader(UOReader):
    """Same records and placement as UOReader.sequence, with vectorised run copies."""

    def sequence(self, body, action, direction):
        record = 35000 + (body - 400) * 175 + action * 5 + direction
        if record * 12 + 12 > len(self.idx):
            return []
        offset, length, _ = struct.unpack_from('<iii', self.idx, record * 12)
        if offset < 0 or length <= 0:
            return []
        self.mul.seek(offset); data = self.mul.read(length)
        pal = np.array(struct.unpack_from('<256H', data), np.uint32)
        lut = np.zeros((256, 4), np.uint8)
        for k, sh in enumerate((10, 5, 0)):
            c = (pal >> sh) & 31; lut[:, k] = (c << 3) | (c >> 2)
        lut[:, 3] = 255
        buf = np.frombuffer(data, np.uint8)
        count = struct.unpack_from('<I', data, 512)[0]
        out = []
        for i in range(count):
            p = 512 + struct.unpack_from('<I', data, 516 + i * 4)[0]
            cx, cy, w, h = struct.unpack_from('<hhhh', data, p); p += 8
            if w <= 0 or h <= 0:
                out.append({'image': Image.new('RGBA', (1, 1)), 'center': [cx, cy], 'index': i, 'empty': True}); continue
            px = np.zeros((h, w, 4), np.uint8)
            while True:
                hdr = struct.unpack_from('<I', data, p)[0]; p += 4
                if hdr == 0x7fff7fff:
                    break
                run = hdr & 4095; x = (hdr >> 22) & 1023; y = (hdr >> 12) & 1023
                x = (x - 1024 if x & 512 else x) + cx; y = (y - 1024 if y & 512 else y) + cy + h
                px[y, x:x + run] = lut[buf[p:p + run]]; p += run
            out.append({'image': Image.fromarray(px), 'center': [cx, cy], 'index': i})
        return out


def canvas_np(f):
    return np.array(B.canvas(f)) if f is not None else np.zeros((256, 256, 4), np.uint8)


def load_candidate(args):
    frames = {}
    if args.vd:
        sys.path.insert(0, str(REPO / 'tools/vd'))
        import vdtool
        _, blocks = vdtool.read_vd(args.vd)
        for b in blocks:
            for i, f in enumerate(b['frames']):
                c = np.zeros((256, 256, 4), np.uint8)
                im = vdtool.frame_rgba(f, b['palette'])
                x0, y0 = 128 - f['cx'], 192 - f['cy'] - f['h']
                c[y0:y0 + im.shape[0], x0:x0 + im.shape[1]] = im
                frames[b['action'], b['dir'], i] = c
    else:
        root = Path(args.frames)
        for p in root.glob('action-*/d*_f*.png'):
            a = int(p.parent.name.split('-')[1]); facing = int(p.stem[1]); i = int(p.stem.split('_f')[1])
            stored = {v: k for k, v in S2F.items()}.get(facing)
            if stored is not None:
                frames[a, stored, i] = np.array(Image.open(p).convert('RGBA'))
    return frames


def garment_list(reader):
    by_anim = {}
    for g in range(0x10000):
        p = 512 * (4 + 32 * 30) + (g // 32) * (4 + 32 * 41) + 4 + (g % 32) * 41
        if p + 41 > len(reader.tiledata):
            break
        if not struct.unpack_from('<Q', reader.tiledata, p)[0] & 0x400000:
            continue
        it = reader.item(g)
        if it['animId'] >= 400 and it['layer'] in CLOTHING_LAYERS:
            by_anim.setdefault(it['animId'], {'layer': it['layer'], 'label': it['label'].strip(), 'graphics': []})['graphics'].append(g)
    return {a: v for a, v in sorted(by_anim.items()) if reader.sequence(a, 4, 0)}


def body_context(reader, actions):
    """Original body alpha, region labels and nearest-original-pixel lookup per stored frame."""
    ctx = {}
    keys = [k for k, _, _ in B.GARMENTS]
    for a in actions:
        for d in range(5):
            body = reader.sequence(400, a, d)
            seqs = {k: reader.sequence(anim, a, d) for k, anim, _ in B.GARMENTS}
            seqs['knee_boot'] = reader.sequence(B.KNEE_BOOT, a, d)
            seqs['tunic'] = reader.sequence(B.TUNIC, a, d)
            seqs['gloves_ref'] = reader.sequence(B.GLOVES, a, d)
            for i, b in enumerate(body):
                g = {k: (s[i] if len(s) == len(body) else None) for k, s in seqs.items()}
                for k in keys:
                    g.setdefault(k, None)
                _, labels, _ = B.frame_regions(b, g)
                rgba = canvas_np(b); O = rgba[..., 3] > 0
                dist, (iy, ix) = ndimage.distance_transform_edt(~O, return_indices=True)
                lab = np.where(O, labels, 0).astype(np.uint8)
                lab[O & (lab == 0)] = 255
                ctx[a, d, i] = {'rgba': rgba, 'O': O, 'lab': lab, 'dist': dist.astype(np.float32),
                                'iy': iy.astype(np.uint8), 'ix': ix.astype(np.uint8)}
    return ctx


def region_name(r):
    return B.REGIONS[r] if r < len(B.REGIONS) else 'unknown'


def run(args):
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    reader = FastReader(client_source(args.source))
    actions = args.actions or list(range(35))
    t0 = time.time()
    ctx = body_context(reader, actions)
    cand = load_candidate(args)
    garments = garment_list(reader)
    if args.garments:
        garments = {a: v for a, v in garments.items() if a in args.garments}
    print(f'{len(ctx)} body frames, {len(cand)} candidate frames, {len(garments)} garments ({time.time()-t0:.0f}s)', flush=True)
    nreg = len(B.REGIONS)
    missing_candidate = sorted({k for k in ctx if k not in cand})
    results = {}; worst = {}
    shape_hash = {}
    for anim, info in garments.items():
        h = hashlib.sha256()
        # region coverage per direction: [dir, region] original px / covered px
        reg_tot = np.zeros((5, 256)); reg_cov = np.zeros((5, 256))
        rows = []; skipped = []; cache = {}
        for a in actions:
            for d in range(5):
                seq = reader.sequence(anim, a, d)
                nb = sum(1 for k in ctx if k[0] == a and k[1] == d)
                if len(seq) != nb:
                    skipped.append([a, d, len(seq), nb]); continue
                for i, f in enumerate(seq):
                    g = canvas_np(f); G = g[..., 3] > 0; h.update(np.packbits(G).tobytes())
                    c = ctx[a, d, i]; O = c['O']; lab = c['lab']
                    reg_tot[d] += np.bincount(lab[O], minlength=256)
                    reg_cov[d] += np.bincount(lab[O & G], minlength=256)
                    cache[a, d, i] = g
        shape_hash[anim] = h.hexdigest()[:16]
        contract = (reg_cov / np.maximum(reg_tot, 1) >= COVER) & (reg_tot > 0)   # [dir, region]
        agg = {'frames': 0, 'poke': 0, 'edge': 0, 'gap': 0, 'poke_frames': 0, 'fail_frames': 0,
               'trim_residual_frames': 0, 'trim_residual': 0, 'wrong_trim': 0, 'poke_regions': np.zeros(256, int),
               'by_action': {}}
        best = (-1, None)
        for (a, d, i), g in cache.items():
            if (a, d, i) not in cand:
                continue
            c = ctx[a, d, i]; O = c['O']; G = g[..., 3] > 0; L = cand[a, d, i][..., 3] > 127
            leak = L & ~O & ~G
            ys, xs = np.nonzero(leak)
            ny, nx = c['iy'][ys, xs], c['ix'][ys, xs]
            hidden = G[ny, nx]; depth = c['dist'][ys, xs]; reg = c['lab'][ny, nx]
            poke = int(hidden.sum()); edge = int((~hidden).sum())
            gap = int((O & ~L & ~G).sum())
            deep = bool((depth[hidden] >= 2).any())
            residual = int((hidden & ~contract[d][reg]).sum())
            wrong = int((O & ~G & contract[d][c['lab']]).sum())
            agg['frames'] += 1; agg['poke'] += poke; agg['edge'] += edge; agg['gap'] += gap
            agg['poke_frames'] += poke > 0; agg['fail_frames'] += deep
            agg['trim_residual'] += residual; agg['trim_residual_frames'] += residual > 0; agg['wrong_trim'] += wrong
            np.add.at(agg['poke_regions'], reg[hidden], 1)
            ba = agg['by_action'].setdefault(a, [0, 0, 0])
            ba[0] += 1; ba[1] += poke > 0; ba[2] += deep
            if poke > best[0]:
                best = (poke, (a, d, i))
        if agg['frames'] == 0:
            print(f'{anim} {info["label"]}: no comparable frames'); continue
        cov_names = {NAMES[S2F[d]]: [region_name(r) for r in range(1, 256) if contract[d, r] and r != 255] for d in range(5)}
        exposed = {region_name(r): round(float(1 - reg_cov[:, r].sum() / reg_tot[:, r].sum()), 3)
                   for r in list(range(1, nreg)) if reg_tot[:, r].sum()}
        n = agg['frames']
        results[anim] = {
            'label': info['label'], 'layer': info['layer'], 'graphics': info['graphics'], 'shape': shape_hash[anim],
            'frames': n, 'skippedSequences': skipped,
            'pokeFrameRate': agg['poke_frames'] / n, 'cleanRate': 1 - agg['poke_frames'] / n,
            'deepFailRate': agg['fail_frames'] / n, 'cleanAfterTrimRate': 1 - agg['trim_residual_frames'] / n,
            'pokePxPerFrame': agg['poke'] / n, 'edgePxPerFrame': agg['edge'] / n, 'gapPxPerFrame': agg['gap'] / n,
            'wrongTrimPxPerFrame': agg['wrong_trim'] / n,
            'pokeRegions': {region_name(r): int(v) for r, v in enumerate(agg['poke_regions']) if v},
            'exposedFraction': exposed, 'coveredRegionsByFacing': cov_names,
            'byAction': {a: {'frames': v[0], 'pokeRate': v[1] / v[0], 'deepRate': v[2] / v[0]} for a, v in sorted(agg['by_action'].items())},
            'worstFrame': best[1], 'worstPokePx': best[0]}
        worst[anim] = (best[1], cache.get(best[1]))
        r = results[anim]
        print(f'{anim:4} {info["label"][:18]:18} clean {r["cleanRate"]:6.1%} deep-fail {r["deepFailRate"]:6.1%} '
              f'after-trim {r["cleanAfterTrimRate"]:6.1%} poke/f {r["pokePxPerFrame"]:5.1f} ({time.time()-t0:.0f}s)', flush=True)
    groups = {}
    for anim, s in shape_hash.items():
        groups.setdefault(s, []).append(anim)
    distinct = {min(v): v for v in groups.values()}
    tot = lambda k: sum(results[a][k] * results[a]['frames'] for a in distinct if a in results) / max(1, sum(results[a]['frames'] for a in distinct if a in results))
    summary = {'label': args.label, 'candidate': str(args.vd or args.frames), 'cover': COVER,
               'garmentsTested': len(results), 'distinctShapes': len(distinct), 'duplicateShapes': {k: v for k, v in distinct.items() if len(v) > 1},
               'garmentFrames': sum(results[a]['frames'] for a in distinct if a in results),
               'cleanRate': tot('cleanRate'), 'deepFailRate': tot('deepFailRate'), 'cleanAfterTrimRate': tot('cleanAfterTrimRate'),
               'pokePxPerFrame': tot('pokePxPerFrame'), 'edgePxPerFrame': tot('edgePxPerFrame'), 'gapPxPerFrame': tot('gapPxPerFrame'),
               'missingCandidateFrames': len(missing_candidate)}
    (out / f'{args.label}.json').write_text(json.dumps({'summary': summary, 'garments': results}, indent=1))
    print(json.dumps(summary, indent=1))
    sheets(out, args.label, results, worst, ctx, cand, distinct, actions)


def overlay(body_rgba, g, O, L=None, c=None):
    im = body_rgba.copy(); a = g[..., 3] > 0; im[a] = g[a]
    if L is not None:
        G = a; leak = L & ~O & ~G
        ys, xs = np.nonzero(leak); hidden = G[c['iy'][ys, xs], c['ix'][ys, xs]]
        im[ys[hidden], xs[hidden]] = [255, 0, 0, 255]; im[ys[~hidden], xs[~hidden]] = [255, 220, 0, 255]
        im[O & ~L & ~G] = [0, 200, 255, 255]
    return Image.fromarray(im)


def sheets(out, label, results, worst, ctx, cand, distinct, actions):
    font = load_font(12)
    big = load_font(16)
    order = sorted((a for a in distinct if a in results), key=lambda a: -results[a]['deepFailRate'])
    cell = 120; cols = 6; W = cols * (2 * cell + 20) + 20
    H = 70 + ((len(order) + cols - 1) // cols) * (cell + 44)
    im = Image.new('RGB', (W, H), '#1c292d'); dr = ImageDraw.Draw(im)
    dr.text((14, 10), f'{label}: worst frame per distinct garment shape, sorted by 2+ px poke rate. Left = original body + garment, '
            'right = candidate + garment.', font=big, fill='white')
    dr.text((14, 36), 'Red = candidate skin past a cloth edge (poke). Yellow = bare-skin silhouette leak. Cyan = exposed skin the candidate misses.',
            font=font, fill='#bacbd1')
    for n, anim in enumerate(order):
        key, g = worst[anim]
        if key is None:
            continue
        c = ctx[key]; L = cand[key][..., 3] > 127
        pair = [overlay(c['rgba'], g, c['O']), overlay(cand[key], g, c['O'], L, c)]
        box = Image.fromarray(np.maximum(c['rgba'][..., 3], g[..., 3]) | cand[key][..., 3]).getbbox()
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2; s = max(box[2] - box[0], box[3] - box[1]) + 6
        crop = (round(cx - s / 2), round(cy - s / 2), round(cx + s / 2), round(cy + s / 2))
        x = 14 + (n % cols) * (2 * cell + 20); y = 64 + (n // cols) * (cell + 44)
        r = results[anim]
        dr.text((x, y), f'{anim} {r["label"][:20]}  clean {r["cleanRate"]:.0%}', font=font, fill='white')
        dr.text((x, y + 14), f'a{key[0]} {NAMES[S2F[key[1]]]} f{key[2]}  {r["worstPokePx"]} px', font=font, fill='#bacbd1')
        for k, p in enumerate(pair):
            t = p.crop(crop).resize((cell, cell), Image.Resampling.NEAREST)
            im.paste(t, (x + k * (cell + 4), y + 30), t)
    im.save(out / f'{label}-worst-frames.png')
    # heatmap: distinct garments x actions, poke-frame rate
    cw, ch, lw = 18, 14, 190
    hm = Image.new('RGB', (lw + len(actions) * cw + 20, 40 + len(order) * ch + 10), '#1c292d'); d = ImageDraw.Draw(hm)
    for j, a in enumerate(actions):
        d.text((lw + j * cw + 2, 22), str(a), font=font, fill='white')
    d.text((8, 4), f'{label}: share of frames with a poke 2+ px deep (black 0% .. red 50%+)', font=font, fill='white')
    for k, anim in enumerate(order):
        r = results[anim]; y = 40 + k * ch
        d.text((8, y), f'{anim} {r["label"][:22]}', font=font, fill='white')
        for j, a in enumerate(actions):
            v = r['byAction'].get(a)
            t = min(1, 2 * v['deepRate']) if v else 0
            col = (60, 60, 60) if v is None else (int(40 + 215 * t), int(40 * (1 - t)), 40)
            d.rectangle((lw + j * cw, y, lw + j * cw + cw - 2, y + ch - 2), fill=col)
    hm.save(out / f'{label}-heatmap.png')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--vd'); src.add_argument('--frames')
    ap.add_argument('--label', required=True)
    ap.add_argument('--out', default=str(REPO / 'workspace/levy-review/clothing-fit'))
    ap.add_argument('--source', default=os.environ.get('SPRITEMOTION_UO_SOURCE', B.CLIENT))
    ap.add_argument('--actions', type=int, nargs='*')
    ap.add_argument('--garments', type=int, nargs='*')
    run(ap.parse_args())
