"""Fit lab: see asset-pack items on the animated UO body, adjust a slot's fit, hide body faces under clothes.

    python tools/fit-lab/run.py export --pack <pack>             # Blender: body + items listed in lab-items.json
    python tools/fit-lab/run.py serve  --pack <pack>             # http://127.0.0.1:8774

Data: workspace/ultima-online/fit-lab/<pack>/ (lab-items.json from the pack's own script, then the export).
Adjustments are saved to <sidecar>/packs/<pack>/lab-adjustments.json (SPRITEMOTION_SIDECAR, else the sibling
SpriteMotion-Sidecar folder); the pack's mapping generator merges them in. Format: docs/asset-packs.md.
"""
import argparse
import http.server
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def data_dir(pack): return REPO / 'workspace/ultima-online/fit-lab' / pack


def sidecar(): return Path(os.environ.get('SPRITEMOTION_SIDECAR', REPO.parent / 'SpriteMotion-Sidecar'))


def blender():
    exe = os.environ.get('SPRITEMOTION_BLENDER') or shutil.which('blender')
    if not exe:
        found = sorted(Path(os.environ.get('ProgramFiles', 'C:/Program Files'), 'Blender Foundation').glob('Blender */blender.exe'))
        exe = str(found[-1]) if found else None
    if not exe: raise SystemExit('Set SPRITEMOTION_BLENDER to blender.exe.')
    return exe


def export(args):
    d = data_dir(args.pack)
    if not (d / 'lab-items.json').exists():
        raise SystemExit(f'{d / "lab-items.json"} missing: run the pack\'s lab_items script first.')
    cmd = [blender(), '-b', '--factory-startup', '--python', str(HERE / 'export_blender.py'), '--', str(d / 'lab-items.json'), str(d)]
    sys.exit(subprocess.call(cmd + (['--force'] if args.force else [])))


def serve(args):
    d = data_dir(args.pack)
    adjust = sidecar() / 'packs' / args.pack / 'lab-adjustments.json'

    class Handler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            path = path.split('?')[0]
            if path.startswith('/data/'): return str(d / path[6:])
            return str(HERE / 'web' / (path.lstrip('/') or 'index.html'))

        def do_GET(self):
            if self.path.startswith('/api/mapping'):
                manifest = json.loads((d / 'manifest.json').read_text())
                mapping = Path(manifest.get('mapping') or '')
                return self.reply(200, mapping.read_bytes()) if mapping.is_file() else self.reply(404, b'{}')
            if self.path.startswith('/api/adjustments'):
                body = adjust.read_bytes() if adjust.exists() else b'{"parts": {}, "items": {}}'
                return self.reply(200, body)
            return super().do_GET()

        def do_POST(self):
            if not self.path.startswith('/api/adjustments'): return self.reply(404, b'{}')
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            adjust.parent.mkdir(parents=True, exist_ok=True)
            adjust.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
            self.reply(200, json.dumps({'saved': str(adjust)}).encode())

        def reply(self, code, body):
            self.send_response(code); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

        def log_message(self, *a): pass

    url = f'http://127.0.0.1:{args.port}/'
    print('Fit lab:', url, '| data', d, '| saves to', adjust, flush=True)
    if not args.no_browser: webbrowser.open(url)
    http.server.ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest='cmd', required=True)
e = sub.add_parser('export'); e.add_argument('--pack', required=True); e.add_argument('--force', action='store_true'); e.set_defaults(fn=export)
s = sub.add_parser('serve'); s.add_argument('--pack', required=True); s.add_argument('--port', type=int, default=8774)
s.add_argument('--no-browser', action='store_true'); s.set_defaults(fn=serve)
args = ap.parse_args(); args.fn(args)
