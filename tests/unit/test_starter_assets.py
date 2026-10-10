import importlib.util
import json
from pathlib import Path
import struct

import jsonschema
import pytest
from spritemotion import schemas

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'examples/cc0-starter'
loader=importlib.util.spec_from_file_location('starter_catalog',ROOT/'tools/uo-content/starters.py')
starters=importlib.util.module_from_spec(loader);loader.loader.exec_module(starters)


def test_every_layer_has_an_appropriate_starter_route():
    document=json.loads((ASSETS/'catalog.json').read_text())
    jsonschema.validate(document,schemas.load_file('starter-catalog.schema.json'))
    items=document['items']
    layers=json.loads((ROOT/'games/ultima-online/equipment/layers.json').read_text())['layers']
    assert {i['layer'] for i in items}=={i['id'] for i in layers}
    assert len({i['id'] for i in items})==len(items)
    for layer in layers:
        matching=[i for i in items if i['layer']==layer['id']]
        assert all(i['kind']==('internal' if layer['kind']=='internal' else 'animated' if layer['animated'] else 'paperdoll') for i in matching)
    for item in items:
        if item['kind']=='animated':
            spec,asset=starters.settings(item['id'])
            assert asset.is_file() and spec['part']==item['part']
        else:
            with pytest.raises(ValueError):starters.settings(item['id'])


def test_bundled_sources_are_self_contained_and_mappings_validate():
    mapping=json.loads((ASSETS/'outfit-mapping.json').read_text())
    jsonschema.validate(mapping,schemas.load_file('asset-pack.schema.json'))
    for path in ASSETS.glob('*.glb'):
        raw=path.read_bytes()
        if raw.startswith(b'version https://git-lfs'):
            pytest.skip('example GLBs are git-lfs pointers; run `git lfs pull` to fetch them')
        magic,version,size=struct.unpack_from('<III',raw)
        assert (magic,version,size)==(0x46546c67,2,len(raw))
        length=struct.unpack_from('<I',raw,12)[0]
        document=json.loads(raw[20:20+length])
        assert document.get('meshes'),path.name
        assert all('uri' not in entry for entry in document.get('images',[])),path.name
        assert all('uri' not in entry for entry in document['buffers']),path.name
    for item in starters.catalog():
        if item.get('mapping'):
            assert any(p['code']==item['id'] and p['uo_layer']==item['layer'] for p in mapping['parts'])


def test_starter_selection_cannot_be_a_path_or_render_internal_slots():
    for value in ('../weapon-sword','weapon-sword.glb','/etc/passwd','unknown'):
        with pytest.raises(ValueError):starters.entry(value)
    spec,_=starters.settings('boots',{'part':'helm','fit':'auto'})
    assert spec['part']=='boots' and spec['fit']=='preserve'
