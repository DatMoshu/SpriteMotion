"""Build a whole outfit from a Fit Lab catalogue and composite it in client layer order.

    python tools/whole-outfit/run.py build     --catalog lab-items.json --adjustments lab-adjustments.json --work DIR ITEM_ID...
    python tools/whole-outfit/run.py body      --work DIR
    python tools/whole-outfit/run.py composite --catalog lab-items.json --work DIR --out DIR [--direction 2] [--story ID]

`build` makes one preview-coverage job per item (the job the lab's Render makes) and records the job names in
DIR/jobs.json. `body` renders the bare body into DIR/body. `composite` stacks every job's frames over the body, checks
each frame (256x256 RGBA, clipped, empty) and writes contact sheets, an overview, two GIFs and a per-slot table into
--out, named spritemotion_<story>_<subject>_<kind>_<YYYYMMDD-HHMM>.<ext>. All of it is built from game-derived frames:
keep the output local (workspace/ is ignored).
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/uo-content'))
ACTIONS = {0: '00_walk_unarmed', 4: '04_stand', 9: '09_attack_1h_slash', 17: '17_spell_area', 22: '22_die_backward', 25: '25_mounted_stand'}
# Back to front: what the client draws first sits underneath.
ORDER = ['back', 'boots', 'knees', 'legs', 'hips', 'chest', 'upper-arms', 'forearms', 'elbows', 'shoulders', 'gloves',
         'hip-back', 'hip-front', 'hip-sides', 'face', 'hair', 'helm']


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def build(args):
    import pipeline
    catalog = read_json(args.catalog)
    adjustments = read_json(args.adjustments)
    mapping = read_json(catalog['mapping'])
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    record = work/'jobs.json'
    jobs = read_json(record) if record.exists() else {}
    for item_id in args.items:
        item = next(i for i in catalog['items'] if i['id'] == item_id)
        part = next(p for p in mapping['parts'] if p['code'] == item['part'])
        spec = {'name': item_id, 'part': part['studio_part'], 'mode': 'preview', 'actions': list(ACTIONS), 'fit': 'preserve',
                'source_files': item['files'], 'palette': item.get('palette'), 'pack_mapping': catalog['mapping'],
                'pack_part': item['part'], 'fit_item': {k: item[k] for k in ('id', 'slot', 'part')}, 'fit_adjustments': adjustments}
        start = time.time()
        job = pipeline.create_job(spec, item['files'][0]); pipeline.run_job(job)
        jobs[item_id] = {'job': job.name, 'sec': round(time.time()-start, 1)}
        record.write_text(json.dumps(jobs, indent=1)); print(item_id, jobs[item_id], flush=True)


def body(args):
    import pipeline
    backend = ROOT/'workspace/ultima-online/canonical-model'
    blend = next((backend/'model').glob('*.blend'))
    out = Path(args.work)/'body'; out.mkdir(parents=True, exist_ok=True)
    command = [pipeline.blender_path(), '--background', '--factory-startup', '--python-exit-code', '1', str(blend), '--python',
               str(Path(__file__).with_name('body_render.py')), '--', str(backend), str(out), ','.join(ACTIONS.values())]
    sys.exit(subprocess.run(command).returncode)


def composite(args):
    from PIL import Image
    work, out = Path(args.work), Path(args.out); out.mkdir(parents=True, exist_ok=True)
    jobs = read_json(work/'jobs.json')
    catalog_doc = read_json(args.catalog)
    catalog = {i['id']: i for i in catalog_doc['items']}
    layer_of = {p['code']: p.get('uo_layer') for p in read_json(catalog_doc['mapping'])['parts']}
    stamp = time.strftime('%Y%m%d-%H%M')
    items = sorted(jobs, key=lambda i: ORDER.index(catalog[i]['slot']))
    jobs_dir = ROOT/'workspace/ultima-online/content-studio/jobs'

    def frames(base, action, direction):
        return sorted((base/ACTIONS[action]/f'dir{direction}').glob('*.png'))
    stats = {i: {'bad': [], 'empty': 0, 'edge': []} for i in items}
    comp = {}
    for action in ACTIONS:
        for direction in range(5):
            base_frames = frames(work/'body/body/frames', action, direction)
            layers = [(i, frames(jobs_dir/jobs[i]['job']/'render/clothing/frames', action, direction)) for i in items]
            for k, base in enumerate(base_frames):
                image = Image.open(base).convert('RGBA')
                for item_id, files in layers:
                    if len(files) != len(base_frames):
                        raise SystemExit(f'{item_id}: {len(files)} frames, body has {len(base_frames)} (action {action} dir {direction})')
                    layer = Image.open(files[k]); s = stats[item_id]
                    if layer.size != (256, 256) or layer.mode != 'RGBA': s['bad'].append((action, direction, k, layer.size, layer.mode))
                    layer = layer.convert('RGBA'); box = layer.getchannel('A').getbbox()
                    if box is None: s['empty'] += 1; continue
                    if 0 in box[:2] or 256 in box[2:]: s['edge'].append((action, direction, k)); continue   # clipped: left out
                    image.alpha_composite(layer)
                comp[(action, direction, k)] = image
    counts = {a: max(k for (aa, d, k) in comp if aa == a)+1 for a in ACTIONS}
    box = None
    for image in comp.values():
        b = image.getchannel('A').getbbox()
        if b: box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    box = (max(0, box[0]-6), max(0, box[1]-6), min(256, box[2]+6), min(256, box[3]+6)); cw, ch = box[2]-box[0], box[3]-box[1]
    bg = (58, 62, 70, 255)

    def cell(image, scale=2):
        c = Image.new('RGBA', (cw, ch), bg); c.alpha_composite(image.crop(box)); return c.resize((cw*scale, ch*scale), Image.NEAREST)

    def name(subject, kind, ext): return out/f'spritemotion_{args.story}_{subject}_{kind}_{stamp}.{ext}'
    for action in ACTIONS:
        sheet = Image.new('RGBA', (counts[action]*cw*2, 5*ch*2), bg)
        for d in range(5):
            for k in range(counts[action]): sheet.paste(cell(comp[(action, d, k)]), (k*cw*2, d*ch*2))
        sheet.convert('RGB').save(name(f'action{action:02d}-{ACTIONS[action][3:]}', 'contact-sheet', 'png'))
    overview = Image.new('RGBA', (5*cw*2, len(ACTIONS)*ch*2), bg)
    for r, action in enumerate(ACTIONS):
        for d in range(5): overview.paste(cell(comp[(action, d, 0)]), (d*cw*2, r*ch*2))
    overview.convert('RGB').save(name('all-actions-frame0', 'overview', 'png'))
    for action in (0, 17):
        gif = [cell(comp[(action, args.direction, k)]).convert('P', palette=Image.ADAPTIVE) for k in range(counts[action])]
        gif[0].save(name(f'action{action:02d}-{ACTIONS[action][3:]}-dir{args.direction}', 'animation', 'gif'),
                    save_all=True, append_images=gif[1:], duration=100, loop=0, disposal=2)
    rows = ['| slot | item | uo layer | validated | notes |', '|---|---|---|---|---|']
    for i in items:
        validation = read_json(jobs_dir/jobs[i]['job']/'validation.json'); s = stats[i]
        ok = validation.get('vd_alpha_and_anchor_roundtrip') and not s['bad'] and not validation['clipped_frames']
        rows.append(f"| {catalog[i]['slot']} | {i} | {layer_of.get(catalog[i]['part'])} | {'yes' if ok else 'NO'} | "
                    f"clipped {len(validation['clipped_frames'])}, empty {len(validation['empty_frames'])}, "
                    f"fully-empty {s['empty']}, edge-touching left out {len(s['edge'])} |")
    name('per-slot', 'table', 'md').write_text('\n'.join(rows)+'\n', encoding='utf-8')
    print('\n'.join(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build'); b.add_argument('--catalog', required=True); b.add_argument('--adjustments', required=True)
    b.add_argument('--work', required=True); b.add_argument('items', nargs='+')
    y = sub.add_parser('body'); y.add_argument('--work', required=True)
    c = sub.add_parser('composite'); c.add_argument('--catalog', required=True); c.add_argument('--work', required=True)
    c.add_argument('--out', required=True); c.add_argument('--direction', type=int, default=2)
    c.add_argument('--story', default='whole-outfit', help='story id used in the evidence file names')
    args = parser.parse_args()
    {'build': build, 'body': body, 'composite': composite}[args.command](args)


if __name__ == '__main__':
    main()
