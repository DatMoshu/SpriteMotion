"""GPU monocular depth test on body sprites: does it separate front/back limbs?"""
import sys, json, numpy as np, torch
from PIL import Image, ImageDraw
from transformers import pipeline
sys.path.insert(0, '.'); import build_regions as B
PICKS = [(9, 3, 3), (0, 5, 0), (16, 5, 4), (22, 4, 1), (9, 6, 0), (0, 7, 3)]
UP = 8
models = {'DepthAnythingV2-S': 'depth-anything/Depth-Anything-V2-Small-hf', 'MiDaS-hybrid': 'Intel/dpt-hybrid-midas'}
rows = []; stats = {}
for mname, mid in models.items():
    pipe = pipeline('depth-estimation', model=mid, device=0, torch_dtype=torch.float16 if 'Anything' in mid else None)
    for a, d, i in PICKS:
        p = str(B.ROOT / f'frames/a{a:02}_d{d}_f{i:02}')
        body = Image.open(p + '_body.png'); lab = np.array(Image.open(p + '_region_ids.png'))
        bb = body.getbbox(); box = (bb[0] - 6, bb[1] - 6, bb[2] + 6, bb[3] + 6)
        crop = body.crop(box); alpha = np.array(crop.getchannel('A')) > 0
        rgb = Image.new('RGB', crop.size, (128, 128, 128)); rgb.paste(crop, mask=crop.getchannel('A'))
        big = rgb.resize((crop.width * UP, crop.height * UP), Image.Resampling.LANCZOS)
        depth = np.array(pipe(big)['predicted_depth'].squeeze().float().cpu()) if False else np.array(pipe(big)['depth'], np.float32)
        depth = np.array(Image.fromarray(depth).resize(crop.size, Image.Resampling.BILINEAR))
        v = depth[alpha]; dn = np.zeros_like(depth); dn[alpha] = (v - v.min()) / max(np.ptp(v), 1e-6)   # 1 = nearest
        L = lab[box[1]:box[3], box[0]:box[2]]
        per = {B.REGIONS[r]: round(float(dn[(L == r) & alpha].mean()), 2) for r in np.unique(L[alpha]) if r and r < 20}
        stats[f'{mname} a{a} {B.NAMES[d]} F{i}'] = per
        col = (np.stack([dn * 255, dn * 180 + 40 * (1 - dn), 255 * (1 - dn)], -1)).astype(np.uint8)
        col = np.dstack([col, alpha * 255]).astype(np.uint8)
        rows.append((mname, (a, d, i), crop, B.colorize(lab).crop(box), Image.fromarray(col)))
    del pipe; torch.cuda.empty_cache()
S = 5; cells = []
for mname, (a, d, i), crop, mask, dimg in rows:
    w, h = crop.width * S, crop.height * S
    c = Image.new('RGB', (3 * w + 20, h + 18), '#1c292d')
    for k, im in enumerate([crop, mask, dimg]):
        c.paste(im.resize((w, h), Image.Resampling.NEAREST), (k * (w + 10), 18), im.resize((w, h), Image.Resampling.NEAREST))
    ImageDraw.Draw(c).text((2, 2), f'{mname} | action {a} {B.NAMES[d]} F{i} | body | regions | depth (red/yellow = near, blue = far)', fill='white')
    cells.append(c)
half = len(cells) // 2
cols = [cells[:half], cells[half:]]
W = sum(max(x.width for x in col) + 20 for col in cols); H = max(sum(x.height + 8 for x in col) for col in cols)
out = Image.new('RGB', (W, H), '#1c292d'); x = 0
for col in cols:
    y = 0
    for c in col: out.paste(c, (x, y)); y += c.height + 8
    x += max(c.width for c in col) + 20
out.save(B.ROOT / 'depth-test.png'); json.dump(stats, open(B.ROOT / 'depth-test.json', 'w'), indent=1)
for k, v in stats.items(): print(k, v)
