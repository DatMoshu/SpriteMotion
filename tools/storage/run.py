"""Validate a checkout before resuming it, or expire obsolete generated derivatives."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('storage', ROOT / 'common/storage.py')
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('startup')
    s.add_argument('--checkout', type=Path, default=ROOT)
    s.add_argument('--python')
    s.add_argument('--paths-only', action='store_true')
    sub.add_parser('prune')
    sub.add_parser('check')
    sub.add_parser('godot-path')
    args = p.parse_args()
    try:
        if args.command == 'godot-path':
            print(storage.paths.work_root() / 'godot')
            return 0
        if args.command == 'startup':
            result = storage.startup(args.checkout, args.python, args.paths_only)
        else:
            store = storage.Store(storage.paths.content_home())
            if args.command == 'prune':
                with store.session() as session:
                    result = dict(bytes=session.require(), limit_bytes=session.policy.max_bytes)
            else:
                result = dict(bytes=store.require(), limit_bytes=store.policy.max_bytes)
        print(json.dumps(result))
        return 0
    except (ValueError, OSError) as error:
        print('[SpriteMotion storage] ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
