"""Storage limits preserve inputs/authoring and stop real runaway producers."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from spritemotion import storage, workpaths


def job(home, number, state='complete', age=20):
    p = home / 'jobs' / f'{number:012x}'
    (p / 'render').mkdir(parents=True)
    (p / 'render/frame.png').write_bytes(b'render')
    (p / 'input').mkdir()
    (p / 'input/source.fbx').write_bytes(b'original input')
    (p / 'item.blend').write_bytes(b'authored scene')
    (p / 'job.json').write_text('{}')
    status = p / 'status.json'
    status.write_text(json.dumps(dict(state=state)))
    stamp = time.time() - age * 86400
    os.utime(status, (stamp, stamp))
    return p


def test_retention_preserves_inputs_scenes_active_recent_and_pinned(tmp_path):
    home = tmp_path / 'content'
    old = job(home, 1)
    active = job(home, 2, 'building')
    queued = job(home, 3, 'queued')
    recent = job(home, 4, age=1)
    pinned = job(home, 5)
    (pinned / '.keep').touch()
    store = storage.Store(home, storage.Policy(max_bytes=100000, days=7, keep=1))
    with store.session():
        pass
    assert not (old / 'render').exists()
    assert (old / 'item.blend').read_bytes() == b'authored scene'
    assert (old / 'input/source.fbx').read_bytes() == b'original input'
    assert (old / 'job.json').exists()
    assert json.loads((old / 'status.json').read_text())['state'] == 'failed'
    assert all((p / 'render/frame.png').exists() for p in [active, queued, recent, pinned])


def test_protected_plan_aborts_before_any_deletion(tmp_path):
    home = tmp_path / 'content'
    first = job(home, 1)
    second = job(home, 2)
    (first / 'render/private.png').write_bytes(b'protected fixture')
    job(home, 3, age=0)
    with pytest.raises(ValueError, match='protected'):
        storage.Store(home, storage.Policy(max_bytes=100000, keep=1)).prune()
    assert (first / 'render/frame.png').exists()
    assert (second / 'render/frame.png').exists()


def test_unknown_authored_file_is_not_expired(tmp_path):
    home = tmp_path / 'content'
    old = job(home, 1)
    (old / 'render/notes.txt').write_text('author notes')
    job(home, 2, age=0)
    with pytest.raises(ValueError, match='Unknown file'):
        storage.Store(home, storage.Policy(max_bytes=100000, keep=1)).prune()
    assert (old / 'render/notes.txt').read_text() == 'author notes'
    assert (old / 'render/frame.png').exists()


def test_capacity_and_concurrent_session_fail_without_deletion(tmp_path):
    home = tmp_path / 'content'
    store = storage.Store(home, storage.Policy(max_bytes=10000))
    with store.session():
        with pytest.raises(ValueError, match='Another content build'):
            with store.session():
                pass
        with pytest.raises(storage.StorageLimit):
            store.require(20000)
    assert not (home / '.storage.lock').exists()


def test_rebuild_pin_protects_old_source_between_sessions(tmp_path):
    home = tmp_path / 'content'
    old = job(home, 1)
    job(home, 2, age=0)
    store = storage.Store(home, storage.Policy(max_bytes=100000, keep=1))
    with storage.pin(old):
        store.prune()
        assert (old / 'render/frame.png').exists()
    assert not (old / '.storage.pin').exists()
    store.prune()
    assert not (old / 'render').exists()


@pytest.mark.parametrize('existing_scene', [False, True])
def test_runaway_child_stopped_and_only_new_derivatives_removed(tmp_path, monkeypatch, existing_scene):
    import pipeline
    home = tmp_path / 'content'
    p = job(home, 1, 'queued', age=0)
    if not existing_scene:
        (p / 'item.blend').unlink()
    monkeypatch.setattr(pipeline, 'HOME', home)
    monkeypatch.setenv('SPRITEMOTION_MAX_WORK_GB', '.00004')
    finished = tmp_path / 'child-finished'
    code = ("from pathlib import Path; import time\n"
            f"job=Path({str(p)!r}); (job/'item.blend').write_bytes(b'generated')\n"
            "with (job/'render/large.png').open('wb') as f:\n"
            " for i in range(150): f.write(b'x'*8192); f.flush(); time.sleep(.02)\n"
            f"Path({str(finished)!r}).touch()\n")
    # A real child writes the bytes; exercise pipeline's actual limit-failure wrapper.
    monkeypatch.setattr(pipeline, '_run_job', lambda path, store: store.process([sys.executable, '-c', code], path))
    if existing_scene:
        with pytest.raises(ValueError, match='Existing editable scene'):
            pipeline.run_job(p)
        assert (p / 'item.blend').read_bytes() == b'authored scene'
        assert (p / 'render/frame.png').exists()
        return
    with pytest.raises(pipeline.storage.StorageLimit):
        pipeline.run_job(p)
    assert not finished.exists()
    assert not (p / 'render').exists()
    assert (p / 'input/source.fbx').read_bytes() == b'original input'
    assert (p / 'job.json').exists()
    assert (p / 'item.blend').exists() == existing_scene
    assert json.loads((p / 'status.json').read_text())['state'] == 'failed'
    assert not (home / '.storage.lock').exists()


def test_large_input_refused_before_copy_or_job_creation(tmp_path, monkeypatch):
    import pipeline
    home = tmp_path / 'content'
    source = tmp_path / 'large.glb'
    source.write_bytes(b'x' * 100000)
    monkeypatch.setattr(pipeline, 'HOME', home)
    monkeypatch.setenv('SPRITEMOTION_MAX_WORK_GB', '.00004')
    with pytest.raises(pipeline.storage.StorageLimit):
        pipeline.create_job({}, source)
    assert source.stat().st_size == 100000
    assert not (home / 'jobs').exists()


def test_output_override_in_any_checkout_is_refused(tmp_path, monkeypatch):
    checkout = tmp_path / 'old-checkout'
    (checkout / '.git').mkdir(parents=True)
    monkeypatch.setenv('SPRITEMOTION_WORK_ROOT', str(checkout / 'output'))
    with pytest.raises(ValueError, match='outside'):
        workpaths.work_root()
    assert not (checkout / 'output').exists()


def test_historical_checkout_fails_closed_without_generated_fallback(tmp_path):
    checkout = tmp_path / 'historical'
    checkout.mkdir()
    with pytest.raises(ValueError, match='Historical checkout'):
        storage.startup(checkout, sys.executable)
    assert list(checkout.iterdir()) == []


def test_corrupt_status_is_preserved(tmp_path):
    home = tmp_path / 'content'
    old = job(home, 1)
    (old / 'status.json').write_text('[]')
    job(home, 2, age=0)
    storage.Store(home, storage.Policy(max_bytes=100000, keep=1)).prune()
    assert (old / 'render/frame.png').exists()


@pytest.mark.parametrize('setting,value', [('SPRITEMOTION_MAX_WORK_GB','0'),
    ('SPRITEMOTION_OUTPUT_DAYS','-1'), ('SPRITEMOTION_KEEP_OUTPUT_JOBS','0')])
def test_invalid_limits_refused(setting, value, monkeypatch):
    monkeypatch.setenv(setting, value)
    with pytest.raises(ValueError):
        storage.Policy()


def test_download_extraction_refuses_expansion_before_unpack(tmp_path, monkeypatch):
    import hashlib
    import zipfile
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('godot_fetch_test', root / 'tools/godot/fetch.py')
    fetch = importlib.util.module_from_spec(spec); spec.loader.exec_module(fetch)
    archive = tmp_path / 'synthetic.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('synthetic-tool', b'x' * 100000)
    data = archive.read_bytes()
    monkeypatch.setattr(fetch, 'HERE', tmp_path / 'godot')
    monkeypatch.setattr(fetch, 'BUILDS', {'linux': ('synthetic.zip', hashlib.sha512(data).hexdigest(), ['synthetic-tool'])})
    def fake_download(url, target):
        target.write_bytes(data)
        return hashlib.sha512(data).hexdigest()
    monkeypatch.setattr(fetch, 'download', fake_download)
    monkeypatch.setenv('SPRITEMOTION_MAX_WORK_GB', '.00001')
    with pytest.raises(fetch._storage.StorageLimit):
        fetch.main(['--platform', 'linux'])
    assert not (fetch.HERE / 'synthetic-tool').exists()
    assert not (fetch.HERE / '.storage.lock').exists()


def test_missing_keyed_environment_never_creates_local_fallback(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv('SPRITEMOTION_WORK_ROOT', str(tmp_path / 'external'))
    with pytest.raises(OSError):
        storage.startup(root)
    assert not (tmp_path / 'external').exists()


def test_wrong_editable_install_rejected(tmp_path, monkeypatch):
    checkout = tmp_path / 'different'
    (checkout / 'common').mkdir(parents=True)
    (checkout / 'common/storage.py').write_text('STORAGE_GUARD_VERSION = 1')
    launchers = checkout / 'launchers/_shared'
    launchers.mkdir(parents=True)
    for name in ['common.bat', 'common.sh']:
        (launchers / name).write_text('tools/storage/run.py')
    monkeypatch.setenv('SPRITEMOTION_WORK_ROOT', str(tmp_path / 'external'))
    monkeypatch.delenv('SPRITEMOTION_CONTENT_HOME', raising=False)
    with pytest.raises(ValueError, match='does not import this checkout'):
        storage.startup(checkout, sys.executable)


@pytest.mark.skipif(os.name != 'nt', reason='Windows launcher verification')
def test_real_launcher_refuses_local_override_and_historical_resume(tmp_path):
    root = Path(__file__).resolve().parents[2]
    command = ['cmd', '/c', str(root / 'launchers/dev/check-storage.bat')]
    env = dict(os.environ, SPRITEMOTION_PYTHON=sys.executable, SPRITEMOTION_WORK_ROOT=str(tmp_path / 'external'))
    env.pop('SPRITEMOTION_CONTENT_HOME', None)
    result = subprocess.run(command + ['--paths-only'], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    historical = tmp_path / 'historical'
    historical.mkdir()
    result = subprocess.run(command + ['--checkout', str(historical)], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and 'Historical checkout' in result.stderr
    env['SPRITEMOTION_CONTENT_HOME'] = str(root / 'forbidden-generated')
    result = subprocess.run(command + ['--paths-only'], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and 'outside' in result.stderr
    assert not (root / 'forbidden-generated').exists()
