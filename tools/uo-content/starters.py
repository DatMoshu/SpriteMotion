"""Resolve bundled source models through a fixed, repository-owned catalog."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'examples/cc0-starter'


def catalog():
    return json.loads((ASSETS / 'catalog.json').read_text(encoding='utf-8'))['items']


def entry(identifier):
    item = next((i for i in catalog() if i['id'] == identifier), None)
    if item is None:
        raise ValueError('Unknown starter asset.')
    return item


def settings(identifier, overrides=None):
    item = entry(identifier)
    if item['kind'] != 'animated':
        raise ValueError(item['note'])
    spec = {'name':item['name'], 'mode':'preview', **(overrides or {}), 'part':item['part']}
    asset = ASSETS / item['asset']
    if item.get('mapping'):
        spec.update(fit='preserve', source_files=[str(asset)], pack_mapping=str(ASSETS/item['mapping']),
                    pack_part=identifier, fit_item={'id':identifier,'slot':item['name'].split(' — ')[0],'part':identifier})
        saved=ROOT/'workspace/ultima-online/fit-lab/cc0-starter/lab-adjustments.json'
        if saved.is_file(): spec['fit_adjustments']=json.loads(saved.read_text(encoding='utf-8'))
    else:
        spec.setdefault('fit','auto')
    return spec, asset
