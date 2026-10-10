"""Fit lab: see asset-pack items on the animated UO body, adjust a slot's fit, hide body faces under clothes.

    python tools/fit-lab/run.py export --pack <pack>             # Blender: body + items listed in lab-items.json
    python tools/fit-lab/run.py serve  --pack <pack>             # http://127.0.0.1:8774

Data: workspace/ultima-online/fit-lab/<pack>/ (lab-items.json from the pack's own script, then the export).
Adjustments are saved to <sidecar>/packs/<pack>/lab-adjustments.json (SPRITEMOTION_SIDECAR, else the sibling
SpriteMotion-Sidecar folder); the pack's mapping generator merges them in. Format: docs/asset-packs.md.
"""
import argparse
import http.server
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from adjustments import AdjustmentStore, ConflictError
from assets import import_directory
from builds import Builds
from service import describe

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FIT_RULES = REPO / 'common' / 'web' / 'fit-rules.mjs'
_spec = importlib.util.spec_from_file_location('blender_helper', REPO / 'common' / 'blender.py')  # by path: runs without an installed package
_blender = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_blender)
find_blender = _blender.find_blender


def data_dir(pack): return REPO / 'workspace/ultima-online/fit-lab' / pack


def sidecar(): return Path(os.environ.get('SPRITEMOTION_SIDECAR', REPO.parent / 'SpriteMotion-Sidecar'))


def blender():
    try: return find_blender(REPO)
    except RuntimeError as error: raise SystemExit(str(error))


def export(args):
    d = data_dir(args.pack)
    if not (d / 'lab-items.json').exists():
        raise SystemExit(f'{d / "lab-items.json"} missing: run the pack\'s lab_items script first.')
    cmd = [blender(), '-b', '--factory-startup', '--python', str(HERE / 'export_blender.py'), '--', str(d / 'lab-items.json'), str(d)]
    sys.exit(subprocess.call(cmd + (['--force'] if args.force else [])))


def make_handler(pack, d, store, builds):
    """Request handler for one lab. Loopback only: Host/Origin are checked on every request (DNS rebinding)."""

    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript'}

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()

        def local(self):
            expected = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in expected: return False
            origin = self.headers.get('Origin')
            return not origin or origin in {'http://' + h for h in expected}

        def translate_path(self, path):
            path = unquote(urlsplit(path).path)
            root = d if path.startswith('/data/') else HERE / 'web'
            relative = path[6:] if path.startswith('/data/') else path.lstrip('/') or 'index.html'
            if path == '/' + FIT_RULES.name:  # one source: the package file, not a copy under web/
                root, relative = FIT_RULES.parent, FIT_RULES.name
            if path.startswith('/builds/'):
                root = REPO/'workspace/ultima-online/content-studio/jobs'
                relative = path.removeprefix('/builds/')
            target = (root / relative).resolve()
            return str(target) if target.is_relative_to(root.resolve()) else str(root / '__not_found__')

        def list_directory(self, path):
            # Never list job, data or web folders; only named files are served.
            self.send_error(404, 'Not found')
            return None

        def manifest(self):
            return json.loads((d / 'manifest.json').read_text(encoding='utf-8'))

        def do_GET(self):
            if not self.local(): return self.reply(403, b'{"error":"Local requests only."}')
            path = urlsplit(self.path).path
            if path == '/api/service': return self.reply(200, json.dumps(describe(pack)).encode())
            try:
                if path == '/api/build': return self.reply(200, json.dumps(builds.state()).encode())
                if path == '/api/renders':
                    item = parse_qs(urlsplit(self.path).query).get('item', [''])[0]
                    return self.reply(200, json.dumps({'renders': builds.renders.renders(item)}).encode())
                if path == '/api/mapping':
                    mapping = Path(self.manifest().get('mapping') or '')
                    return self.reply(200, mapping.read_bytes()) if mapping.is_file() else self.reply(404, b'{}')
                if path == '/api/state':
                    return self.reply(200, json.dumps(store.state()).encode())
                if path == '/api/adjustments':
                    return self.reply(200, json.dumps(store.state()['adjustments']).encode())
                if path.startswith('/api/backups/'):
                    return self.reply(200, json.dumps(store.backup(path.removeprefix('/api/backups/'))).encode())
            except FileNotFoundError as e:
                return self.reply(404, json.dumps({'error': str(e)}).encode())
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
                return self.reply(500, json.dumps({'error': str(e)}).encode())
            return super().do_GET()

        def do_HEAD(self):
            if not self.local(): return self.reply(403, b'{"error":"Local requests only."}')
            return super().do_HEAD()

        def do_POST(self):
            if not self.local(): return self.reply(403, b'{"error":"Local requests only."}')
            path = urlsplit(self.path).path
            if path not in ('/api/adjustments', '/api/assets', '/api/build'): return self.reply(404, b'{}')
            # JSON-only requests prevent cross-origin forms from changing local fits.
            if self.headers.get_content_type() != 'application/json':
                return self.reply(415, b'{"error":"Reload the lab before saving."}')
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 2_000_000: raise ValueError('Invalid request size.')
                data = json.loads(self.rfile.read(size))
                if path == '/api/build': return self.reply(202,json.dumps(builds.start(data)).encode())
                if path == '/api/assets':
                    if not isinstance(data, dict) or set(data) != {'directory', 'slot', 'part'} or not all(isinstance(v, str) for v in data.values()):
                        raise ValueError('Expected directory, slot and part strings')
                    manifest = self.manifest()
                    if not any(i['slot'] == data['slot'] and i['part'] == data['part'] for i in manifest['items']):
                        raise ValueError('Select a known slot first')
                    result = import_directory(data['directory'], d, data['slot'], data['part'])
                    return self.reply(200, json.dumps(result).encode())
                if not isinstance(data, dict) or set(data) != {'adjustments', 'base_revision'}:
                    raise ValueError('Expected adjustments and base_revision; reload the lab.')
                result = store.save(data['adjustments'], data['base_revision'])
                self.reply(200, json.dumps(result).encode())
            except ConflictError as e:
                self.reply(409, json.dumps({'error': str(e)}).encode())
            except (ValueError, TypeError) as e:
                self.reply(400, json.dumps({'error': str(e)}).encode())
            except OSError as e:
                self.reply(500, json.dumps({'error': str(e)}).encode())

        def reply(self, code, body):
            self.send_response(code); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

        def log_message(self, *a): pass

    return Handler


def serve(args):
    d = data_dir(args.pack)
    adjust = (d / 'lab-adjustments.json' if args.pack == 'cc0-starter'
              else sidecar() / 'packs' / args.pack / 'lab-adjustments.json')
    store = AdjustmentStore(adjust)
    builds = Builds(d, store)
    Handler = make_handler(args.pack, d, store, builds)

    url = f'http://127.0.0.1:{args.port}/'
    print('Fit lab:', url, '| data', d, '| saves to', adjust, flush=True)
    if not args.no_browser: webbrowser.open(url)
    http.server.ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()



def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('export'); e.add_argument('--pack', required=True); e.add_argument('--force', action='store_true'); e.set_defaults(fn=export)
    s = sub.add_parser('serve'); s.add_argument('--pack', required=True); s.add_argument('--port', type=int, default=8774)
    s.add_argument('--no-browser', action='store_true'); s.set_defaults(fn=serve)
    args = ap.parse_args(); args.fn(args)


if __name__ == '__main__':
    main()
