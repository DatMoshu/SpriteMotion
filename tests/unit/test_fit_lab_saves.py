"""Exercise actual disk recovery guarantees; no licensed pack data required."""
import importlib.util
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
import jsonschema
from spritemotion import schemas

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('fit_lab_adjustments', ROOT / 'tools/fit-lab/adjustments.py')
saves = importlib.util.module_from_spec(spec)
spec.loader.exec_module(saves)


def adjustment(n):
    return {'parts': {'CHEST': {'offset': [n / 100, 0, 0]}}, 'items': {}}


def test_three_backups_restore_and_noop(tmp_path):
    store = saves.AdjustmentStore(tmp_path / 'lab-adjustments.json')
    state = store.state()
    for n in range(5):
        state = store.save(adjustment(n), state['revision'])
    assert len(state['backups']) == 3
    assert [store.backup(b['id']) for b in state['backups']] == [adjustment(n) for n in (3, 2, 1)]
    assert store.save(adjustment(4), state['revision']) == state
    restored = store.backup(state['backups'][1]['id'])
    state = store.save(restored, state['revision'])
    assert state['adjustments'] == adjustment(2)
    assert store.backup(state['backups'][0]['id']) == adjustment(4)
    with pytest.raises(FileNotFoundError):
        store.backup('../lab-adjustments.json')
    schema = schemas.load_file('fit-adjustments.schema.json')
    jsonschema.validate(state['adjustments'], schema)


def test_failed_replace_preserves_current_and_retry_does_not_duplicate_backup(tmp_path, monkeypatch):
    store = saves.AdjustmentStore(tmp_path / 'lab-adjustments.json')
    state = store.save(adjustment(1), store.state()['revision'])
    replace = saves.os.replace
    def fail_current(source, target):
        if Path(target) == store.path:
            raise OSError('disk full')
        return replace(source, target)
    with monkeypatch.context() as patch:
        patch.setattr(saves.os, 'replace', fail_current)
        with pytest.raises(OSError):
            store.save(adjustment(2), state['revision'])
    assert store.state()['adjustments'] == adjustment(1)
    assert not list(tmp_path.glob('*.tmp'))
    final = store.save(adjustment(2), state['revision'])
    assert [store.backup(b['id']) for b in final['backups']] == [adjustment(1), {'parts': {}, 'items': {}}]


def test_concurrent_tabs_cannot_overwrite_each_other(tmp_path):
    store = saves.AdjustmentStore(tmp_path / 'lab-adjustments.json')
    revision = store.state()['revision']
    def write(n):
        try:
            store.save(adjustment(n), revision)
            return 'saved'
        except saves.ConflictError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, [1, 2])) == ['conflict', 'saved']


@pytest.mark.parametrize('bad', [None, {}, {'parts': [], 'items': {}},
    {'parts': {'X': {'scale': float('nan')}}, 'items': {}},
    {'parts': {'X': {'offset': [0, 1]}}, 'items': {}},
    {'parts': {}, 'items': {'X': {'unexpected': True}}}])
def test_invalid_data_never_changes_disk(tmp_path, bad):
    store = saves.AdjustmentStore(tmp_path / 'lab-adjustments.json')
    before = store.state()
    with pytest.raises(ValueError):
        store.save(bad, before['revision'])
    assert store.state() == before
    assert not store.path.exists()
