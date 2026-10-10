"""Fit Lab HTTP server: loopback Host/Origin guard, no directory listings, JSON errors for a missing export."""
import http.client
import http.server
import importlib.util
import json
from pathlib import Path
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/fit-lab'))
spec = importlib.util.spec_from_file_location('fit_lab_run', ROOT / 'tools/fit-lab/run.py')
run = importlib.util.module_from_spec(spec); spec.loader.exec_module(run)


class NoBuilds:
    def state(self): return {'state': 'idle'}


@pytest.fixture
def lab(tmp_path):
    data = tmp_path / 'data'; (data / 'sub').mkdir(parents=True)
    (data / 'sub/file.json').write_text('{}', encoding='utf-8')
    store = run.AdjustmentStore(tmp_path / 'lab-adjustments.json')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), run.make_handler('test-pack', data, store, NoBuilds()))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield server
    server.shutdown(); server.server_close()


def request(server, method, path, host=None, origin=None, body=None):
    conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
    headers = {'Host': host or f'127.0.0.1:{server.server_port}'}
    if origin: headers['Origin'] = origin
    if body is not None: headers['Content-Type'] = 'application/json'
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse(); payload = response.read(); conn.close()
    return response.status, payload


def test_local_host_passes(lab):
    status, body = request(lab, 'GET', '/api/service')
    assert status == 200 and json.loads(body)['pack'] == 'test-pack'
    assert request(lab, 'GET', '/api/service', host=f'localhost:{lab.server_port}')[0] == 200
    assert request(lab, 'GET', '/api/service', origin=f'http://127.0.0.1:{lab.server_port}')[0] == 200


@pytest.mark.parametrize('method,path,body', [('GET', '/api/service', None), ('GET', '/', None),
                                              ('GET', '/data/sub/file.json', None),
                                              ('POST', '/api/adjustments', '{}')])
def test_foreign_host_or_origin_is_refused(lab, method, path, body):
    # DNS rebinding: the browser sends the attacker's host name to our loopback port.
    assert request(lab, method, path, host=f'evil.example:{lab.server_port}', body=body)[0] == 403
    assert request(lab, method, path, host=f'127.0.0.1:{lab.server_port + 1}', body=body)[0] == 403
    assert request(lab, method, path, origin='http://evil.example', body=body)[0] == 403


def test_directories_are_not_listed(lab):
    assert request(lab, 'GET', '/data/sub/')[0] == 404
    assert request(lab, 'GET', '/builds/')[0] == 404
    assert request(lab, 'GET', '/data/sub/file.json')[0] == 200


def test_missing_manifest_returns_json_error(lab):
    status, body = request(lab, 'GET', '/api/mapping')
    assert status == 404 and 'error' in json.loads(body)
