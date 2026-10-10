"""Render changed blocks into a new validated revision; never modify the source job."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import uuid


def merge_vd(source, patch, output):
    from client_import import vd_blocks
    original, replacement = vd_blocks(source), vd_blocks(patch)
    if not set(replacement) <= set(original): raise ValueError('Patch contains blocks missing from the source build.')
    blocks = {**original, **replacement}
    header = bytearray(struct.pack('<hh', 6, 2)); body = bytearray()
    for i in range(175):
        block = blocks.get(divmod(i,5))
        if block is None: header += struct.pack('<iii',-1,-1,-1)
        else:
            header += struct.pack('<iii',2104+len(body),len(block),0); body += block
    Path(output).write_bytes(header+body)
    return {f'{a},{d}': hashlib.sha256(block).hexdigest() for (a,d),block in original.items() if (a,d) not in replacement}


def changed_blocks(spec, document, blocks):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'fit-lab'))
    from fit_rules import resolve
    item = spec.get('fit_item')
    if not item: raise ValueError('Source job needs fit_item identity; build a fresh fit-aware preview first.')
    mapping = json.loads(Path(spec['pack_mapping']).read_text(encoding='utf-8'))
    part = next((p for p in mapping['parts'] if p['code']==item['part']),{})
    old = spec.get('fit_adjustments', {'parts':{},'items':{}})
    return [list(pair) for pair in sorted(blocks) if resolve(old,part,item,*pair) != resolve(document,part,item,*pair)]


def rebuild_job(source, adjustments, selected=None):
    import pipeline
    from client_import import vd_blocks
    from adjustments import validate
    source = Path(source).resolve()
    spec = json.loads((source/'job.json').read_text(encoding='utf-8'))
    if spec.get('backend_sha256') != pipeline.sha(pipeline.BACKEND/'model/UO_Body_0x190.blend'):
        raise ValueError('The canonical model changed. Make a fresh build before rebuilding individual blocks.')
    if spec.get('render_fingerprint') != pipeline.render_fingerprint():
        raise ValueError('The renderer changed or this job predates renderer tracking. Make a fresh build first.')
    if any(not Path(path).is_file() or pipeline.sha(path)!=digest for path,digest in spec.get('source_fingerprints',{}).items()):
        raise ValueError('Source meshes or palette changed. Make a fresh build first.')
    document = validate(adjustments)
    original_blocks = vd_blocks(source/'item.vd')
    changed = changed_blocks(spec,document,original_blocks)
    selected = changed if selected is None else selected
    if not selected: return source
    if not set(map(tuple,changed)) <= set(map(tuple,selected)):
        raise ValueError('Selected blocks omit affected poses; rebuild all changed blocks to keep the revision coherent.')
    if not set(map(tuple,selected)) <= set(original_blocks): raise ValueError('Requested block is absent from the source build.')
    # A snapshot of the original mapping prevents unrelated mapping edits from entering a partial build.
    patch_spec = {**spec, 'fit_adjustments':document, 'actions':sorted({b[0] for b in selected}), 'blocks':selected}
    patch = pipeline.create_job(patch_spec, spec.get('asset'))
    pipeline.run_job(patch)
    identity = uuid.uuid4().hex[:12]
    stage = pipeline.HOME/'staging'/identity
    destination = pipeline.HOME/'jobs'/identity
    try:
        shutil.copytree(source,stage)
        render = stage/'render/clothing'
        meta = json.loads((render/'meta.json').read_text(encoding='utf-8'))
        patch_meta = json.loads((patch/'render/clothing/meta.json').read_text(encoding='utf-8'))
        replacements = {(b['action'],b['dir']):b for b in patch_meta['blocks'] if b['frames']}
        for pair, block in replacements.items():
            relative = Path('frames')/block['name']/f'dir{block["dir"]}'
            shutil.copytree(patch/'render/clothing'/relative,render/relative,dirs_exist_ok=True)
        meta['blocks'] = [replacements.get((b['action'],b['dir']),b) for b in meta['blocks']]
        pipeline.write_json(render/'meta.json',meta)
        unchanged = merge_vd(source/'item.vd',patch/'item.vd',stage/'item.vd')
        report = json.loads((stage/'scene-report.json').read_text(encoding='utf-8'))
        report.setdefault('fit_blocks',{}).update(json.loads((patch/'scene-report.json').read_text(encoding='utf-8')).get('fit_blocks',{}))
        pipeline.write_json(stage/'scene-report.json',report)
        spec.update(fit_adjustments=document, job=str(destination), rebuild={'source_job':source.name,'patch_job':patch.name,'blocks':selected,'unchanged_vd_blocks':unchanged})
        pipeline.write_json(stage/'job.json',spec)
        # The editable scene has the latest base and bindings; per-block settings remain in job.json.
        shutil.copy2(patch/'item.blend',stage/'item.blend')
        pipeline.finish(stage)
        stage.rename(destination)
        return destination
    except Exception:
        # Staging is private to this call; a failed merge must not leave a half-built revision behind.
        shutil.rmtree(stage,ignore_errors=True)
        raise
