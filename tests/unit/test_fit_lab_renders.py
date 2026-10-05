import importlib.util
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('fit_lab_renders', ROOT / 'tools/fit-lab/renders.py')
renders = importlib.util.module_from_spec(spec); spec.loader.exec_module(renders)


def job(root, name, item, state='complete', actions=(4,), **extra):
    d = root / name; (d / 'review').mkdir(parents=True)
    (d / 'status.json').write_text(json.dumps({'state': state}))
    (d / 'job.json').write_text(json.dumps({'name': item, 'fit_item': {'id': item}, 'actions': list(actions), **extra}))
    (d / 'review/manifest.json').write_text(json.dumps({'sequences': [{'action': a, 'dir': d} for a in actions for d in range(5)]}))
    return d


def test_renders_list_complete_jobs_for_one_item_newest_first(tmp_path):
    old = job(tmp_path, 'aaa', 'cloak', actions=(4, 9)); os.utime(old / 'status.json', (1, 1))
    job(tmp_path, 'bbb', 'cloak', actions=(0,))
    job(tmp_path, 'ccc', 'other')
    job(tmp_path, 'ddd', 'cloak', state='failed')
    index = renders.RenderIndex(tmp_path)
    found = index.renders('cloak')
    assert [r['job'] for r in found] == ['bbb', 'aaa'] and found[1]['actions'] == [4, 9]
    running = job(tmp_path, 'eee', 'cloak', state='building')
    assert [r['job'] for r in index.renders('cloak')] == ['bbb', 'aaa']
    (running / 'status.json').write_text('{"state": "complete"}')
    assert index.renders('cloak')[0]['job'] == 'eee'


def test_progress_counts_frames_of_the_running_job(tmp_path):
    started = time.time()
    d = job(tmp_path, 'run', 'cloak', state='building', actions=(4, 9))
    frames = d / 'render/clothing/frames/09_x/dir0'; frames.mkdir(parents=True)
    for i in range(3): (frames / f'{i:02d}.png').write_bytes(b'')
    assert renders.RenderIndex(tmp_path).progress('cloak', started, {4: 1, 9: 7}) == {'done': 3, 'total': 40}
    patch = job(tmp_path, 'patch', 'other', state='building', actions=(9,), blocks=[[9, 3]])
    assert renders.RenderIndex(tmp_path).progress('other', started, {9: 7}) == {'done': 0, 'total': 7}
    assert renders.RenderIndex(tmp_path).progress('missing', started, {}) is None


def test_patch_only_rebuild_jobs_are_not_listed_as_renders(tmp_path):
    full = job(tmp_path, 'full', 'cloak', actions=(9,)); os.utime(full / 'status.json', (1, 1))
    job(tmp_path, 'patch', 'cloak', actions=(9,), blocks=[[9, 3]])   # newer, but holds one block only
    assert [r['job'] for r in renders.RenderIndex(tmp_path).renders('cloak')] == ['full']
