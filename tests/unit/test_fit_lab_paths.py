"""Lab catalogs resolve against the checkout that reads them, not the one that wrote them."""
import importlib.util
import json
import logging
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('fit_lab_labpaths', ROOT / 'tools/fit-lab/labpaths.py')
labpaths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labpaths)

MAPPING = 'examples/cc0-starter/outfit-mapping.json'


def catalog(**kw):
    return {'pack': 'cc0-starter', 'items': [{'id': 'a', 'slot': 's', 'part': 'p', 'files': [MAPPING]}], 'mapping': MAPPING, **kw}


def test_relative_catalog_resolves_to_this_checkout(tmp_path, monkeypatch):
    fake = tmp_path / 'other-checkout'
    (fake / 'examples/cc0-starter').mkdir(parents=True)
    (fake / MAPPING).write_text('{}')
    monkeypatch.setattr(labpaths, 'REPO', fake)
    out = labpaths.resolve(catalog(root='repo'))
    assert Path(out['mapping']) == fake / MAPPING and Path(out['items'][0]['files'][0]) == fake / MAPPING


def test_copied_lab_folder_uses_the_copying_checkouts_mapping(tmp_path, monkeypatch):
    lab = tmp_path / 'lab-items.json'
    lab.write_text(json.dumps(catalog(root='repo')))
    copy = tmp_path / 'copy'; copy.mkdir()
    shutil.copy(lab, copy / 'lab-items.json')
    checkout = tmp_path / 'checkout-b'
    (checkout / 'examples/cc0-starter').mkdir(parents=True)
    (checkout / MAPPING).write_text('{}')
    monkeypatch.setattr(labpaths, 'REPO', checkout)
    assert Path(labpaths.load(copy / 'lab-items.json')['mapping']) == checkout / MAPPING


def test_sidecar_root(tmp_path, monkeypatch):
    monkeypatch.setenv('SPRITEMOTION_SIDECAR', str(tmp_path))
    out = labpaths.resolve(catalog(root='sidecar', mapping='packs/x/asset-pack.json'))
    assert Path(out['mapping']) == tmp_path / 'packs/x/asset-pack.json'


def test_legacy_absolute_path_inside_checkout_loads_unchanged():
    legacy = str(ROOT / MAPPING)
    out = labpaths.resolve(catalog(mapping=legacy))
    assert Path(out['mapping']) == ROOT / MAPPING


def test_legacy_absolute_path_of_another_checkout_is_remapped_with_one_warning(caplog):
    other = 'Z:/gone/checkout/' + MAPPING
    doc = catalog(mapping=other)
    doc['items'][0]['files'] = [other, other]
    with caplog.at_level(logging.WARNING, logger='fit-lab'):
        out = labpaths.resolve(doc)
    assert Path(out['mapping']) == ROOT / MAPPING and [Path(f) for f in out['items'][0]['files']] == [ROOT / MAPPING] * 2
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_legacy_path_with_no_local_twin_is_left_alone():
    assert Path(labpaths.resolve(catalog(mapping='Z:/gone/nothing.json'))['mapping']) == Path('Z:/gone/nothing.json')


@pytest.mark.parametrize('bad', ['../escape.json', 'C:/abs.json', '/abs.json'])
def test_rooted_catalog_refuses_escapes(bad):
    with pytest.raises(ValueError):
        labpaths.resolve(catalog(root='repo', mapping=bad))


def test_unknown_root_is_refused():
    with pytest.raises(ValueError):
        labpaths.resolve(catalog(root='home'))


def test_relative_round_trip():
    assert labpaths.relative(ROOT / MAPPING, 'repo') == MAPPING
