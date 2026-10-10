"""Pose editor and Content Studio servers: loopback Host/Origin guard, JSON-only POST, no listings, confined static files."""
import functools
import http.client
import http.server
import importlib.util
import json
from pathlib import Path
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


pose = load('pose_editor_server_under_test', ROOT / 'games/ultima-online/region-masks/pose_editor_server.py')
sys.path.insert(0, str(ROOT / 'tools/uo-content'))
studio = load('studio_under_test', ROOT / 'tools/uo-content/studio.py')


def serve(handler):
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def request(server, method, path, host=None, origin=None, body=None, content_type='application/json'):
    conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
    headers = {'Host': host or f'127.0.0.1:{server.server_port}'}
    if origin: headers['Origin'] = origin
    if body is not None: headers['Content-Type'] = content_type
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse(); payload = response.read(); conn.close()
    return response.status, payload


@pytest.fixture
def editor(tmp_path, monkeypatch):
    out = tmp_path / 'out'; (out / 'editor').mkdir(parents=True); (out / 'sub').mkdir()
    (out / 'sub/file.txt').write_text('x', encoding='utf-8')
    (tmp_path / 'secret.txt').write_text('secret', encoding='utf-8')
    monkeypatch.setattr(pose, 'OUT', out)
    server = serve(functools.partial(pose.Handler, directory=str(out)))
    server.scene = {'assetId': 'a', 'clips': {}}; server.jobs = {}; server.lock = threading.Lock()
    yield server
    server.shutdown(); server.server_close()


@pytest.fixture
def content_studio():
    server = serve(studio.Handler)
    yield server
    server.shutdown(); server.server_close()


def test_editor_serves_local_requests(editor):
    port = editor.server_port
    assert request(editor, 'GET', '/api/edits')[0] == 200
    assert request(editor, 'GET', '/api/edits', host=f'localhost:{port}')[0] == 200
    assert request(editor, 'GET', '/sub/file.txt', origin=f'http://127.0.0.1:{port}')[0] == 200
    assert request(editor, 'GET', '/editor/')[0] == 200


@pytest.mark.parametrize('method,path', [('GET', '/api/edits'), ('GET', '/api/job?id=x'), ('GET', '/editor/'),
                                         ('GET', '/sub/file.txt'), ('HEAD', '/sub/file.txt')])
def test_editor_rejects_bad_host_and_origin(editor, method, path):
    assert request(editor, method, path, host='evil.example')[0] == 403
    assert request(editor, method, path, host=f'127.0.0.1:{editor.server_port + 1}')[0] == 403
    assert request(editor, method, path, origin='http://evil.example')[0] == 403


def test_editor_post_needs_a_local_origin_and_json(editor):
    port = editor.server_port
    good = f'http://127.0.0.1:{port}'
    assert request(editor, 'POST', '/api/save', body='{}')[0] == 403  # Origin is required on POST
    assert request(editor, 'POST', '/api/save', origin='http://evil.example', body='{}')[0] == 403
    assert request(editor, 'POST', '/api/save', host='evil.example', origin=good, body='{}')[0] == 403
    assert request(editor, 'POST', '/api/save', origin=good, body='{}', content_type='text/plain')[0] == 415
    assert request(editor, 'POST', '/api/save', origin=good, body='{}', content_type='application/x-www-form-urlencoded')[0] == 415
    assert request(editor, 'POST', '/api/save', origin=good, body='{}')[0] == 400  # guard passed; bad edits rejected
    assert request(editor, 'POST', '/api/other', origin=good, body='{}')[0] == 404


def test_editor_has_no_listing_and_stays_inside_its_folder(editor):
    assert request(editor, 'GET', '/sub/')[0] == 404
    assert request(editor, 'GET', '/')[0] == 404
    assert request(editor, 'GET', '/sub/file.txt')[0] == 200
    assert request(editor, 'GET', '/../secret.txt')[0] == 404
    assert request(editor, 'GET', '/%2e%2e/secret.txt')[0] == 404


def test_studio_head_applies_the_host_check(content_studio):
    assert request(content_studio, 'HEAD', '/api/config', host='evil.example')[0] == 403
    assert request(content_studio, 'HEAD', '/api/config', origin='http://evil.example')[0] == 403
    assert request(content_studio, 'GET', '/api/config', host='evil.example')[0] == 403
    assert request(content_studio, 'GET', '/api/config')[0] == 200


def test_studio_rejects_cross_origin_posts_and_listings(content_studio):
    assert request(content_studio, 'POST', '/api/cancel', origin='http://evil.example', body='{}')[0] == 403
    assert request(content_studio, 'POST', '/api/cancel', host='evil.example', body='{}')[0] == 403
    assert request(content_studio, 'POST', '/api/cancel', body='{}', content_type='text/plain')[0] == 415
    assert request(content_studio, 'GET', '/jobs/')[0] == 404
    assert request(content_studio, 'GET', '/')[0] == 200


def test_shared_guard():
    guard = load('local_guard_under_test', ROOT / 'common/local_guard.py')
    assert guard.is_local({'Host': '127.0.0.1:1'}, 1)
    assert not guard.is_local({'Host': '127.0.0.1:1'}, 1, require_origin=True)
    assert guard.is_local({'Host': 'localhost:1', 'Origin': 'http://localhost:1'}, 1, require_origin=True)
    assert not guard.is_local({'Host': '127.0.0.1:2'}, 1)
