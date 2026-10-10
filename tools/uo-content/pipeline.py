"""Portable orchestration for the UO v13 content pipeline (Python + Pillow + NumPy)."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_spec = importlib.util.spec_from_file_location('blender_helper', ROOT / 'common/blender.py')  # by path: runs without an installed package
_blender = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_blender)
_find_blender = _blender.find_blender
HOME = ROOT / 'workspace/ultima-online/content-studio'
BACKEND = ROOT / 'workspace/ultima-online/canonical-model'
PARTS = ['helm', 'chest', 'arms', 'gloves', 'legs', 'boots', 'robe', 'cloak', 'skirt', 'weapon', 'shield', 'bow', 'quiver']
MODELS = {'.glb', '.gltf', '.fbx', '.obj', '.stl', '.blend'}
IMAGES = {'.png', '.jpg', '.jpeg', '.webp'}

def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2), encoding='utf-8')

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def render_fingerprint():
    paths = [HERE/name for name in ('blender_build.py','fit_runtime.py','occlusion.py','pack_fit.py')]
    paths += [ROOT/'common/fit_rules.py']
    paths += [BACKEND/'pipeline'/name for name in ('render_uo_layer.py','cloth_lib.py','uo_bind_item.py','uo_vd_writer.py')]
    return hashlib.sha256(''.join(sha(path) for path in paths if path.exists()).encode()).hexdigest()

def setup(source):
    source = Path(source).resolve()
    files = ['model/UO_Body_0x190.blend', 'pipeline/uo_bind_item.py',
             'pipeline/render_uo_layer.py', 'pipeline/uo_vd_writer.py', 'vdtool/vdtool.py', 'README_EN.md']
    for name in files:
        if not (source / name).is_file():
            raise ValueError(f'Missing UO_Model3D backend file: {name}')
    # Newer renderers load cloth_lib.py and cloak_pitch.json from their own folder (else from texts embedded in the
    # .blend); older ones have neither.
    files += [name for name in ('pipeline/cloth_lib.py', 'pipeline/cloak_pitch.json') if (source / name).is_file()]
    BACKEND.mkdir(parents=True, exist_ok=True)
    for name in files:
        dest = BACKEND / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, dest)
    write_json(BACKEND / 'provenance.json', dict(source=str(source), model='UO_Model3D v13',
        files={name: sha(BACKEND / name) for name in files},
        license='Third-party model and pipeline; retain source attribution and its original terms.'))
    return BACKEND

def blender_path():
    try:
        return _find_blender(ROOT)
    except RuntimeError as error:
        raise ValueError(str(error)) from None

def normalize(spec):
    spec = dict(spec)
    spec['name'] = str(spec.get('name') or 'New UO item')[:100]
    spec['prompt'] = str(spec.get('prompt') or '')[:12000]
    spec['part'] = spec.get('part', 'helm')
    if spec['part'] not in PARTS:
        raise ValueError('Choose a supported equipment part.')
    mode = spec.get('mode', 'preview')
    if mode not in ('preview', 'full'):
        raise ValueError('Build mode must be preview or full.')
    spec['mode'] = mode
    spec.setdefault('actions', [0, 4, 9, 22, 25] if mode == 'preview' else list(range(35)))
    if not isinstance(spec['actions'], list) or not spec['actions'] or any(type(a) is not int or not 0 <= a <= 34 for a in spec['actions']) or len(set(spec['actions'])) != len(spec['actions']):
        raise ValueError('Actions must be unique IDs from 0 to 34.')
    if 'blocks' in spec:
        blocks = spec['blocks']
        if not isinstance(blocks, list) or not blocks or any(not isinstance(b, list) or len(b)!=2 or
                type(b[0]) is not int or b[0] not in spec['actions'] or type(b[1]) is not int or not 0<=b[1]<=4 for b in blocks):
            raise ValueError('Blocks must be action/stored-direction pairs within the selected actions.')
        if len(set(map(tuple,blocks))) != len(blocks): raise ValueError('Duplicate blocks.')
    if spec.get('occlusion', 'clothing') not in ('clothing','body','none'): raise ValueError('Invalid occlusion mode.')
    for field, default, low, high in [('scale', 1., .01, 100.), ('offset_x', 0., -3., 3.),
            ('offset_y', 0., -3., 3.), ('offset_z', 0., -3., 3.), ('rotate_x', 0., -360., 360.),
            ('rotate_y', 0., -360., 360.), ('rotate_z', 0., -360., 360.)]:
        v = float(spec.get(field, default))
        if not low <= v <= high:
            raise ValueError(f'{field} must be between {low} and {high}.')
        spec[field] = v
    spec['fit'] = spec.get('fit', 'auto')
    if spec['fit'] not in ('auto', 'preserve'):
        raise ValueError('Fit must be auto or preserve.')
    color = spec.get('color')
    if not color:
        words = spec['prompt'].lower()
        color = next((v for k, v in [('gold', '#d5a63c'), ('red', '#a82824'), ('blue', '#315ca6'),
            ('green', '#3c7245'), ('black', '#34373d'), ('white', '#d8dad5'), ('purple', '#7449a1')]
            if re.search(r'\b' + k + r'\b', words)), '#929ba8')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError('Color must be #RRGGBB.')
    spec['color'] = color
    return spec

def snapshot_fit(spec):
    """Freeze local adjustments at job creation, never let a running job read changing UI saves."""
    sys.path.insert(0, str(ROOT / 'tools/fit-lab'))
    from adjustments import validate
    if 'fit_adjustments' in spec:
        validate(spec['fit_adjustments'])
    elif spec.get('pack_mapping'):
        saved = Path(spec['pack_mapping']).parent / 'lab-adjustments.json'
        if saved.exists(): spec['fit_adjustments'] = validate(json.loads(saved.read_text(encoding='utf-8')))
    document = spec.get('fit_adjustments', {'parts':{},'items':{}})
    if 'fit_item' not in spec and spec.get('pack_mapping'):
        sources = {str(Path(p).resolve()).casefold() for p in spec.get('source_files', [])}
        matches = []
        for path in (ROOT / 'workspace/ultima-online/fit-lab').glob('*/lab-items.json'):
            catalog = json.loads(path.read_text(encoding='utf-8'))
            if Path(catalog.get('mapping','')).resolve() != Path(spec['pack_mapping']).resolve(): continue
            matches.extend(i for i in catalog['items'] if sources and sources == {str(Path(p).resolve()).casefold() for p in i['files']})
        if len(matches) == 1: spec['fit_item'] = {k: matches[0][k] for k in ('id','slot','part')}
    item = spec.get('fit_item')
    if item is not None and (not isinstance(item,dict) or any(not isinstance(item.get(k),str) or not item[k] for k in ('id','slot','part'))):
        raise ValueError('fit_item requires id, slot and part strings.')
    # Zero item offsets are left behind by the lab's item sliders; only real per-item/slot data needs an identity.
    item_offsets = any(any(v.get('offset', [0, 0, 0])) for v in document.get('items', {}).values())
    if item is None and (item_offsets or any(r['target']!='pack' for r in document.get('corrections',[]))):
        raise ValueError('Provide fit_item so item/group/slot corrections can be applied reliably.')


def create_job(spec, asset=None):
    spec = normalize(spec)
    snapshot_fit(spec)
    if not (BACKEND / 'provenance.json').exists():
        raise ValueError('Install the v13 backend first: pipeline.py setup --source <UO_Model3D folder>')
    job = HOME / 'jobs' / uuid.uuid4().hex[:12]
    job.mkdir(parents=True)
    if spec.get('pack_mapping'):
        frozen = job / 'pack-mapping.json'
        shutil.copy2(spec['pack_mapping'], frozen)
        spec['pack_mapping'] = str(frozen)
    if asset:
        asset = Path(asset).resolve()
        if asset.suffix.lower() not in MODELS | IMAGES:
            raise ValueError('Unsupported asset format.')
        # Copy complete local OBJ/glTF dependencies for CLI jobs; UI recommends self-contained GLB.
        dest = job / 'input' / asset.name
        dest.parent.mkdir()
        shutil.copy2(asset, dest)
        if asset.suffix.lower() in ('.obj', '.gltf'):
            for p in asset.parent.iterdir():
                if p.is_file() and p.suffix.lower() in IMAGES | {'.bin', '.mtl'}:
                    shutil.copy2(p, dest.parent / p.name)
        spec['asset'] = str(dest)
        spec['asset_sha256'] = sha(dest)
        spec['input_kind'] = 'model' if asset.suffix.lower() in MODELS else 'image'
    else:
        spec['input_kind'] = 'text'
    spec['creation_method'] = ('imported mesh' if spec['input_kind'] == 'model' else
        'procedural item template with image material' if spec['input_kind'] == 'image' else
        'procedural item template configured by text and controls')
    spec['backend'] = str(BACKEND)
    spec['backend_sha256'] = sha(BACKEND / 'model/UO_Body_0x190.blend')
    spec['render_fingerprint'] = render_fingerprint()
    spec['source_fingerprints'] = {str(Path(path).resolve()):sha(path) for path in
        [*spec.get('source_files',[]), *([spec['palette']] if spec.get('palette') else [])]}
    spec['job'] = str(job)
    write_json(job / 'job.json', spec)
    write_json(job / 'status.json', dict(state='queued', name=spec['name']))
    return job

def run_job(job):
    job = Path(job).resolve()
    spec = json.loads((job / 'job.json').read_text(encoding='utf-8'))
    write_json(job / 'status.json', dict(state='building', name=spec['name']))
    try:
        with (job / 'build.log').open('w', encoding='utf-8') as log:
            process = subprocess.run([blender_path(), '--background', '--factory-startup', '--disable-autoexec',
                '--threads', os.environ.get('SPRITEMOTION_RENDER_THREADS','0'),
                '--python-exit-code', '1', '--python', str(HERE / 'blender_build.py'), '--', str(job / 'job.json')],
                stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
        if process.returncode:
            raise RuntimeError('Blender build failed; see build.log.')
        finish(job)
        write_json(job / 'status.json', dict(state='complete', name=spec['name'], mode=spec['mode']))
    except Exception as e:
        write_json(job / 'status.json', dict(state='failed', name=spec['name'], error=str(e)))
        raise

def finish(job):
    import base64
    import zlib
    import numpy as np
    from PIL import Image, ImageDraw
    from client_import import inspect_vd
    spec = json.loads((job / 'job.json').read_text(encoding='utf-8'))
    render = job / 'render/clothing'
    meta = json.loads((render / 'meta.json').read_text(encoding='utf-8'))
    vd = job / 'item.vd'
    counts = inspect_vd(vd)
    expected = json.loads((job / 'scene-report.json').read_text(encoding='utf-8'))['actions']
    intended = {(a, d): expected[str(a)] for a,d in spec.get('blocks', [(a,d) for a in spec['actions'] for d in range(5)])}
    actual = {(b['action'], b['dir']): len(b['frames']) for b in meta['blocks'] if b['frames']}
    if actual != intended or counts != intended:
        raise ValueError('Animation identities/frame counts differ between scene, PNGs and VD.')
    # Verify VD anchors/alpha against every PNG through the independent, existing MUL decoder.
    sys.path.insert(0, str(ROOT / 'games/ultima-online/extraction'))
    from uo_anim import decode_entry
    from client_import import vd_blocks
    clipped, empty, total = [], [], 0
    native = {}
    for b in meta['blocks']:
        if not b['frames']:
            continue
        key = b['action'], b['dir']
        decoded = decode_entry(vd_blocks(vd)[key])
        native[key] = []
        for i, f in enumerate(b['frames']):
            path = render / 'frames' / b['name'] / f"dir{b['dir']}" / f['file']
            im = np.array(Image.open(path).convert('RGBA'))
            native[key].append(im)
            m = im[..., 3] >= 128
            if m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any():
                clipped.append([*key, i])
            if not m.any():
                empty.append([*key, i])
            fvd = decoded[i]
            recon = np.zeros(m.shape, bool)
            x = meta['anchor'][0] - fvd.center_x
            y = meta['anchor'][1] - fvd.center_y - fvd.height
            if m.any():
                if x < 0 or y < 0 or x + fvd.width > im.shape[1] or y + fvd.height > im.shape[0]:
                    raise ValueError('VD frame origin is outside the render canvas.')
                recon[y:y+fvd.height, x:x+fvd.width] = fvd.rgba[..., 3] > 0
            if not np.array_equal(m, recon):
                raise ValueError(f'VD round-trip alpha/anchor mismatch: {key}, frame {i}')
            total += 1
    # Original pixels are a reference only, never substituted for the new item layer.
    # The public (stripped) model carries no original frames; the review atlas then shows the item alone.
    originals = job / 'original-frames.json'
    orig = json.loads(originals.read_text(encoding='utf-8'))['frames'] if originals.is_file() else {}
    review = job / 'review'
    review.mkdir(exist_ok=True)
    items = []
    for b in meta['blocks']:
        if not b['frames']:
            continue
        a, d = b['action'], b['dir']
        atlas = Image.new('RGBA', (256 * len(b['frames']), 256 * 2))
        for i, im in enumerate(native[(a, d)]):
            raw = orig.get(f'{a},{i},{d}')
            if raw:
                body = Image.fromarray(np.frombuffer(zlib.decompress(base64.b64decode(raw)), np.uint8).reshape(120,136,4))
                atlas.paste(body, (256*i + 60, 106))
            atlas.paste(Image.fromarray(im), (256*i, 256))
        name = f'a{a:02d}-d{d}.png'
        atlas.save(review / name)
        items.append(dict(action=a, dir=d, name=b['name'], count=len(b['frames']), file=name))
    write_json(review / 'manifest.json', dict(name=spec['name'], sequences=items, fps=8, anchor=[128,192],
        stored_facings=['SE','S','SW','W','NW'], mirror_axis=127.5))
    shutil.copy2(HERE / 'review.html', review / 'index.html')
    sheet = Image.new('RGB', (5*256, 3*256), '#212832')
    draw = ImageDraw.Draw(sheet)
    for row, a in enumerate([4, 9, 22]):
        for d in range(5):
            path = review / f'a{a:02d}-d{d}.png'
            if path.exists():
                atlas = Image.open(path)
                tile = Image.alpha_composite(atlas.crop((0,0,256,256)), atlas.crop((0,256,256,512)))
                sheet.paste(tile, (d*256,row*256), tile)
                draw.text((d*256+10,row*256+10), f'Action {a} / dir {d}', fill='white')
    sheet.save(job / 'contact-sheet.png')
    # A usable inventory thumbnail, derived from the rendered item alone.
    idle = Image.fromarray(native.get((4,0), next(iter(native.values())))[0])
    box = idle.getbbox()
    if box:
        idle = idle.crop(box)
        idle.thumbnail((44,44), Image.Resampling.LANCZOS)
        # Game art has binary transparency.
        px = np.array(idle); px[...,3] = (px[...,3]>=128)*255
        Image.fromarray(px).save(job/'inventory.png')
    report = dict(frames=total, blocks=len(actual), vd_alpha_and_anchor_roundtrip=True,
        full_animation_set=set(actual)=={(a,d) for a in range(35) for d in range(5)},
        clipped_frames=clipped, empty_frames=empty, mounted='Reference horse holdout; review required.',
        deployed=False, creation_method=spec['creation_method'])
    write_json(job / 'validation.json', report)
    (job / 'IMPORT-README.txt').write_text(
        f"{spec['name']} — SpriteMotion UO content\n\n"
        f"Creation: {spec['creation_method']}\n"
        f"Build: {spec['mode']}; {total} frames; {len(actual)} action/direction blocks.\n"
        "item.vd: UOFiddler people/equipment animation import. Full builds contain 35 actions x 5 stored directions.\n"
        "render/clothing: transparent PNGs + vdtool canvas metadata. review/: aligned SpriteMotion atlas preview.\n"
        "item.blend: editable item mounted on the v13 body. Original model is preserved separately.\n"
        "For classic MUL: use client_import.py stage --vd item.vd --client <folder> --body <unused animation ID> --out <new folder>.\n"
        "This writes patched COPIES of anim.mul/anim.idx and verifies them; it does not change the source client.\n"
        "Equipment also needs a free static graphic, inventory art, tiledata Animation=chosen animation ID,\n"
        "wearable layer/flags and a server item definition. Bodyconv/Equipconv/UOP redirects must be checked for your shard.\n"
        "An animation ID is not the static item graphic ID. Female body conversion is not supplied.\n"
        "Partial previews are rejected by the importer. Review all facings, mounted poses and clipping before deployment.\n",
        encoding='utf-8')
    with zipfile.ZipFile(job / 'import-package.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for p in job.rglob('*'):
            if p.is_file() and (p.parent == review or render in p.parents or p.name in
                    {'item.vd','validation.json','IMPORT-README.txt','job.json','scene-report.json','contact-sheet.png','inventory.png'}):
                z.write(p, p.relative_to(job))
    write_json(job / 'status.json', dict(state='complete', name=spec['name'], mode=spec['mode']))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('setup'); s.add_argument('--source', required=True)
    b = sub.add_parser('build'); b.add_argument('--spec', required=True); b.add_argument('--asset')
    f = sub.add_parser('finish'); f.add_argument('job')
    r = sub.add_parser('rebuild'); r.add_argument('job'); r.add_argument('--adjustments',required=True)
    args = p.parse_args()
    if args.command == 'setup':
        print(setup(args.source))
    elif args.command == 'finish':
        finish(Path(args.job).resolve())
    elif args.command == 'rebuild':
        sys.path.insert(0,str(ROOT/'tools/fit-lab'))
        from rebuild import rebuild_job
        print(rebuild_job(args.job,json.loads(Path(args.adjustments).read_text(encoding='utf-8'))),flush=True)
    else:
        job = create_job(json.loads(Path(args.spec).read_text(encoding='utf-8')), args.asset)
        print(job, flush=True)
        run_job(job)

if __name__ == '__main__':
    main()
