"""Import self-contained fitted GLBs without exposing arbitrary filesystem paths to HTTP."""
import hashlib
import json
import re
import struct
from pathlib import Path


def dominant_bone(raw, doc):
    """Sum actual vertex weights, respecting interleaved GLB accessor strides."""
    json_size = struct.unpack_from('<I', raw, 12)[0]
    binary = raw[28 + json_size:]
    totals = {}
    def values(index):
        accessor = doc['accessors'][index]
        if 'sparse' in accessor:
            raise ValueError('Sparse skin attributes must be baked before importing')
        view = doc['bufferViews'][accessor['bufferView']]
        kind = accessor['componentType']
        fmt = {5121: '4B', 5123: '4H', 5126: '4f'}[kind]
        size = struct.calcsize('<' + fmt)
        offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        for i in range(accessor['count']):
            row = struct.unpack_from('<' + fmt, binary, offset + i * view.get('byteStride', size))
            divisor = {5121: 255, 5123: 65535}.get(kind, 1) if accessor.get('normalized') else 1
            yield [value / divisor for value in row]
    for node in doc['nodes']:
        if 'mesh' not in node:
            continue
        joints = doc['skins'][node['skin']]['joints']
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            attr = primitive['attributes']
            for indices, weights in zip(values(attr['JOINTS_0']), values(attr['WEIGHTS_0']), strict=True):
                for index, weight in zip(indices, weights):
                    name = doc['nodes'][joints[int(index)]]['name']
                    totals[name] = totals.get(name, 0) + weight
    if not totals or max(totals.values()) <= 0:
        raise ValueError('No positive skin weights')
    return max(totals, key=totals.get)


def glb_document(raw):
    if len(raw) < 20 or raw[:4] != b'glTF':
        raise ValueError('Not a GLB')
    version, size, length, kind = struct.unpack_from('<4I', raw, 4)
    if version != 2 or size != len(raw) or kind != 0x4e4f534a or length > len(raw) - 20:
        raise ValueError('Invalid GLB header')
    doc = json.loads(raw[20:20 + length])
    if not isinstance(doc, dict):
        raise ValueError('Invalid GLB document')
    if any('uri' in value and not value['uri'].startswith('data:')
           for key in ('images', 'buffers') for value in doc.get(key, [])):
        raise ValueError('External textures/buffers are unsupported; export a self-contained GLB')
    return doc


def import_directory(directory, data, slot, part):
    root = Path(directory).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Choose a directory')
    body = glb_document((data / 'body.glb').read_bytes())
    bone_names = {body['nodes'][i]['name'] for skin in body['skins'] for i in skin['joints']}
    files = sorted(root.rglob('*.glb'))
    if len(files) > 100:
        raise ValueError('Choose a smaller directory (at most 100 GLBs)')
    imported, skipped = [], []
    cache = data / 'imports'
    cache.mkdir(exist_ok=True)
    for path in files:
        try:
            if not path.resolve().is_relative_to(root):
                raise ValueError('Linked files outside the chosen directory are unsupported')
            if path.stat().st_size > 50_000_000:
                raise ValueError('Larger than 50 MB')
            raw = path.read_bytes()
            doc = glb_document(raw)
            skins = doc.get('skins', [])
            if not skins:
                raise ValueError('No skeleton; fit and skin this model first')
            names = [doc['nodes'][i].get('name', '') for skin in skins for i in skin['joints']]
            if not set(names) <= bone_names:
                raise ValueError('Skeleton differs from the UO body; use pack fitting first')
            mesh_nodes = [node for node in doc.get('nodes', []) if 'mesh' in node]
            if not mesh_nodes or any('skin' not in node for node in mesh_nodes):
                raise ValueError('Every mesh must be skinned to the canonical rig')
            if any(not {'JOINTS_0', 'WEIGHTS_0'} <= set(p['attributes'])
                   for mesh in doc['meshes'] for p in mesh['primitives']):
                raise ValueError('Missing skin weights')
            digest = hashlib.sha256(raw).hexdigest()[:16]
            bone = dominant_bone(raw, doc)
            safe = re.sub(r'[^a-zA-Z0-9_-]', '_', path.stem)[:64]
            identity = f'local-{safe}-{digest}'
            (cache / f'{identity}.glb').write_bytes(raw)
            imported.append({'id': identity, 'slot': slot, 'part': part, 'family': path.stem,
                             'file': f'imports/{identity}.glb', 'dominant_bone': bone})
        except (ValueError, KeyError, IndexError, OSError, struct.error) as error:
            skipped.append({'file': path.name, 'reason': str(error)})
    return {'items': imported, 'skipped': skipped}
