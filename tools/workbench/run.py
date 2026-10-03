"""Run Content Studio and Fit Lab together; reuse matching local services."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parents[2]


def probe(port, endpoint, match):
    try:
        try:
            response = urlopen(f'http://127.0.0.1:{port}{endpoint}', timeout=5)
        except HTTPError as exc:
            if endpoint != '/api/service' or exc.code != 404:
                raise
            # Older lab processes predate discovery but expose their exported manifest.
            response = urlopen(f'http://127.0.0.1:{port}/data/manifest.json', timeout=5)
            with response:
                legacy = json.load(response)
            if legacy.get('rig') != 'uo-model3d-v13' or not isinstance(legacy.get('items'), list):
                raise ValueError('Not a Fit Lab manifest')
            data = {'schema': 'spritemotion.fit-lab-service', 'pack': legacy.get('pack')}
        else:
            with response:
                data = json.load(response)
    except URLError as exc:
        if isinstance(exc.reason, ConnectionRefusedError) or getattr(exc.reason, 'winerror', None) == 10061:
            return False
        raise RuntimeError(f'Cannot verify service on port {port}: {exc}') from exc
    except (ValueError, OSError) as exc:
        raise RuntimeError(f'Port {port} is not the expected SpriteMotion service.') from exc
    if not match(data):
        raise RuntimeError(f'Port {port} has another service or pack. Stop it before launching this workbench.')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack', nargs='?', default=os.environ.get('SPRITEMOTION_FIT_PACK'))
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    catalogs = ROOT / 'workspace/ultima-online/fit-lab'
    if not args.pack:
        packs = sorted(p.parent.name for p in catalogs.glob('*/manifest.json'))
        if 'cc0-starter' in packs or not packs:
            args.pack = 'cc0-starter'
        elif len(packs) == 1:
            args.pack = packs[0]
        else:
            parser.error('Choose an exported pack: workbench <pack>. Available: ' + ', '.join(packs))
    if not args.pack or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.pack):
        parser.error('Invalid pack name.')
    if not (catalogs / args.pack / 'manifest.json').is_file():
        if args.pack != 'cc0-starter':
            parser.error('This pack needs a Fit Lab export first. See tools/fit-lab/README.md.')
        print('Preparing bundled starters for Fit Lab (requires your supplied UO model and Blender).',flush=True)
        subprocess.run([sys.executable,str(ROOT/'tools/starter-assets/run.py'),'--prepare-lab'],cwd=ROOT,check=True)
    services = [
        (8772, '/api/config', lambda d: isinstance(d, dict) and 'ready' in d and 'parts' in d,
         ['tools/uo-content/studio.py']),
        (8774, '/api/service', lambda d: isinstance(d, dict) and d.get('schema') == 'spritemotion.fit-lab-service' and d.get('pack') == args.pack,
         ['tools/fit-lab/run.py', 'serve', '--pack', args.pack, '--no-browser']),
    ]
    children = []
    try:
        # Verify both ports before starting anything.
        running = [probe(port, endpoint, match) for port, endpoint, match, _ in services]
        for active, (port, endpoint, match, command) in zip(running, services):
            if not active:
                process = subprocess.Popen([sys.executable, *command], cwd=ROOT)
                children.append(process)
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError(f'Service on port {port} exited during startup.')
                    if probe(port, endpoint, match):
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError(f'Service on port {port} did not become ready.')
        print('Content Studio: http://127.0.0.1:8772/\nFit Lab: http://127.0.0.1:8774/\nCtrl+C stops services started by this launcher.', flush=True)
        if not args.no_browser:
            webbrowser.open('http://127.0.0.1:8772/')
        while children:
            if any(child.poll() is not None for child in children):
                raise RuntimeError('A workbench service stopped. See its output above.')
            time.sleep(.5)
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeError as exc:
        sys.exit(str(exc))
