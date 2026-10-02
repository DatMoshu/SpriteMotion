"""Reference pixels and local import validation use generated fixtures, never game assets."""
import base64
import importlib.util
import json
import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'tools/fit-lab/{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


assets = module('assets')
reference = module('reference')


def glb(names=('head', 'spine')):
    data = struct.pack('<4H4f', 0, 1, 0, 0, .2, .8, 0, 0)
    doc = {'nodes': [{'name': n} for n in names] + [{'mesh': 0, 'skin': 0}],
           'skins': [{'joints': list(range(len(names)))}],
           'meshes': [{'primitives': [{'attributes': {'JOINTS_0': 0, 'WEIGHTS_0': 1}}]}],
           'bufferViews': [{'byteOffset': 0}, {'byteOffset': 8}],
           'accessors': [{'bufferView': 0, 'componentType': 5123, 'count': 1},
                         {'bufferView': 1, 'componentType': 5126, 'count': 1}]}
    encoded = json.dumps(doc).encode()
    encoded += b' ' * (-len(encoded) % 4)
    return b'glTF' + struct.pack('<4I', 2, 28 + len(encoded) + len(data), len(encoded), 0x4e4f534a) + encoded + struct.pack('<2I', len(data), 0x004e4942) + data


def test_fitted_directory_copies_and_uses_weighted_bone(tmp_path):
    source, data = tmp_path / 'source', tmp_path / 'data'
    source.mkdir(); data.mkdir()
    raw = glb()
    (source / 'gear.glb').write_bytes(raw); (data / 'body.glb').write_bytes(raw)
    result = assets.import_directory(str(source), data, 'chest', 'CHEST')
    assert not result['skipped']
    item = result['items'][0]
    assert item['dominant_bone'] == 'spine'
    assert (data / item['file']).read_bytes() == raw == (source / 'gear.glb').read_bytes()


def test_wrong_skeleton_and_malformed_are_reported(tmp_path):
    source, data = tmp_path / 'source', tmp_path / 'data'
    source.mkdir(); data.mkdir()
    (data / 'body.glb').write_bytes(glb())
    (source / 'wrong.glb').write_bytes(glb(('unknown', 'spine')))
    (source / 'broken.glb').write_bytes(b'bad')
    result = assets.import_directory(str(source), data, 'chest', 'CHEST')
    assert result['items'] == []
    assert len(result['skipped']) == 2


def test_external_resources_rejected():
    raw = glb()
    doc = assets.glb_document(raw)
    doc['images'] = [{'uri': 'file:///private.png'}]
    encoded = json.dumps(doc).encode()
    modified = b'glTF' + struct.pack('<4I', 2, 20 + len(encoded), len(encoded), 0x4e4f534a) + encoded
    with pytest.raises(ValueError, match='External'):
        assets.glb_document(modified)


def test_reference_retains_exact_rgba_and_orientation(tmp_path):
    raw = bytearray(136 * 120 * 4)
    raw[:4] = b'\xff\0\0\xff'; raw[-4:] = b'\0\xff\0\x80'
    reference.write_reference({'tile': [136, 120], 'frames': {'0,0,0': base64.b64encode(zlib.compress(raw)).decode()}}, tmp_path)
    atlas = Image.open(tmp_path / 'reference.png')
    assert atlas.crop((0, 0, 136, 120)).tobytes() == raw
    assert json.loads((tmp_path / 'reference.json').read_text())['tiles'] == {'0,0,0': [0, 0]}
