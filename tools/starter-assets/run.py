"""Build a bundled CC0 equipment example without downloading an asset pack."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'examples/cc0-starter'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sys.path.insert(0, str(ROOT / 'tools/uo-content'))
    import starters
    parser.add_argument('item', nargs='?', choices=[i['id'] for i in starters.catalog()])
    parser.add_argument('--list', action='store_true', help='List every UO layer and its starter route.')
    parser.add_argument('--prepare-lab', action='store_true', help='Export the bundled animated outfits to Fit Lab.')
    parser.add_argument('--smoke', action='store_true', help='Render only idle, stored direction 0.')
    args = parser.parse_args()
    import pipeline
    if args.list:
        for item in starters.catalog(): print(f"{item['layer']:2} {item['id']:18} {item['kind']}")
        return 0
    if args.prepare_lab:
        from prepare_lab import prepare
        return prepare()
    if not args.item: parser.error('Choose an item, --list or --prepare-lab.')
    item=starters.entry(args.item)
    if item['kind'] != 'animated':
        print(item['note'])
        if 'asset' in item: print('Source GLB:', ASSETS/item['asset'])
        return 0
    if not (pipeline.BACKEND / 'provenance.json').exists():
        parser.error('Install your supplied UO model first: python tools/uo-content/pipeline.py setup --source <model-folder>')
    pipeline.blender_path()
    spec, asset = starters.settings(args.item)
    if args.smoke:
        spec.update(actions=[4], blocks=[[4, 0]])
    job = pipeline.create_job(spec, asset)
    print('Building:', job, flush=True)
    pipeline.run_job(job)
    status = json.loads((job / 'status.json').read_text())
    print(json.dumps(status, indent=2))
    return 0 if status['state'] == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
