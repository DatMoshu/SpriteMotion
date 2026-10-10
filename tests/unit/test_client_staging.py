"""Client staging fails before creating output when files are missing, and removes partial output on failure.

Fixtures are synthetic byte buffers, never client data.
"""
import json
from pathlib import Path
import sys

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/uo-content'))
sys.path.insert(0, str(ROOT / 'tools/fit-lab'))
import client_import
import equipment
import pipeline
import rebuild

TILEDATA_ITEMS = 0x1420 // 32 + 1   # enough item groups for the chest template graphic


def client(tmp_path, skip=()):
    folder = tmp_path / 'client'; folder.mkdir(parents=True)
    files = {'anim.mul': b'', 'anim.idx': b'', 'art.mul': b'', 'artidx.mul': b'',
             'tiledata.mul': bytes(512 * (4 + 32 * 26) + TILEDATA_ITEMS * (4 + 32 * 37))}
    for name, data in files.items():
        if name not in skip: (folder / name).write_bytes(data)
    return folder


def job(tmp_path):
    folder = tmp_path / 'job'; folder.mkdir()
    (folder / 'job.json').write_text(json.dumps({'name': 'Test chest', 'part': 'chest'}), encoding='utf-8')
    (folder / 'validation.json').write_text(json.dumps({'clipped_frames': 0}), encoding='utf-8')
    image = Image.new('RGBA', (4, 4)); image.putpixel((1, 1), (200, 10, 10, 255))
    image.save(folder / 'inventory.png')
    return folder


@pytest.mark.parametrize('missing', ['art.mul', 'artidx.mul', 'tiledata.mul', 'anim.mul'])
def test_equipment_missing_client_file_fails_before_output(tmp_path, missing):
    folder = job(tmp_path)
    with pytest.raises(ValueError, match=missing):
        equipment.stage_equipment(folder, client(tmp_path, skip=(missing,)), 400, 0x1416)
    assert not (folder / 'staged-client').exists()


def test_anim_stage_missing_client_file_fails_before_output(tmp_path):
    out = tmp_path / 'out'
    with pytest.raises(ValueError, match='anim.idx'):
        client_import.stage(tmp_path / 'item.vd', client(tmp_path, skip=('anim.idx',)), 400, out)
    assert not out.exists()


def test_equipment_failure_after_staging_removes_partial_output(tmp_path, monkeypatch):
    folder = job(tmp_path)

    def fake_stage(vd, source, body, out):
        Path(out).mkdir(); (Path(out) / 'anim.mul').write_bytes(b'partial')
        return {'source_hashes': {}, 'staged_hashes': {}}

    def broken_source(*args):
        raise OSError('disk full')

    monkeypatch.setattr(equipment, 'stage', fake_stage)
    monkeypatch.setattr(equipment, 'server_source', broken_source)
    with pytest.raises(OSError, match='disk full'):
        equipment.stage_equipment(folder, client(tmp_path), 400, 0x1416)
    assert not (folder / 'staged-client').exists()
    # The retry is not blocked by a leftover folder.
    monkeypatch.setattr(equipment, 'server_source', lambda *a: '// item')
    assert equipment.stage_equipment(folder, client(tmp_path / 'again'), 400, 0x1416)['graphic'] == 0x1416


def test_failed_rebuild_merge_removes_staging(tmp_path, monkeypatch):
    home, source, patch = tmp_path / 'home', tmp_path / 'home/jobs/source', tmp_path / 'home/jobs/patch'
    source.mkdir(parents=True); patch.mkdir()
    (source / 'job.json').write_text(json.dumps({'backend_sha256': 'model', 'render_fingerprint': 'renderer'}), encoding='utf-8')
    (source / 'item.vd').write_bytes(b'')
    monkeypatch.setattr(pipeline, 'HOME', home)
    monkeypatch.setattr(pipeline, 'sha', lambda path: 'model')
    monkeypatch.setattr(pipeline, 'render_fingerprint', lambda: 'renderer')
    monkeypatch.setattr(pipeline, 'create_job', lambda spec, asset=None: patch)
    monkeypatch.setattr(pipeline, 'run_job', lambda job: None)
    monkeypatch.setattr(client_import, 'vd_blocks', lambda path: {(9, 0): b'', (9, 3): b''})
    monkeypatch.setattr(rebuild, 'changed_blocks', lambda spec, document, blocks: [[9, 3]])
    with pytest.raises(OSError):   # the source has no render/clothing/meta.json to merge into
        rebuild.rebuild_job(source, {'parts': {}, 'items': {}})
    assert list((home / 'staging').iterdir()) == []
    assert sorted(p.name for p in (home / 'jobs').iterdir()) == ['patch', 'source']
