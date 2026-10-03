"""Finished Blender renders per lab item, and progress of the one running, read from content-studio job folders."""
import json
import os
from pathlib import Path
from threading import Lock


def read_json(path):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError): return None


class RenderIndex:
    """Job id -> (item id, actions, finished time) for complete lab jobs. Job folders never change once complete."""

    def __init__(self, jobs):
        self.jobs, self.lock, self.known, self.seen = Path(jobs), Lock(), {}, set()

    def scan(self):
        try: entries = [e for e in os.scandir(self.jobs) if e.is_dir()]
        except FileNotFoundError: return
        with self.lock:
            for entry in entries:
                if entry.name in self.seen: continue
                status = read_json(Path(entry.path, 'status.json'))
                if not status or status.get('state') not in ('complete', 'failed'): continue   # retry while running
                self.seen.add(entry.name)
                spec, review = read_json(Path(entry.path, 'job.json')), read_json(Path(entry.path, 'review/manifest.json'))
                if status['state'] != 'complete' or not spec or not review or not spec.get('fit_item'): continue
                self.known[entry.name] = {'job': entry.name, 'item': spec['fit_item']['id'],
                    'actions': sorted({s['action'] for s in review['sequences']}),
                    'finished': Path(entry.path, 'status.json').stat().st_mtime}

    def renders(self, item):
        """Newest first: the render panel shows the newest job that contains the requested action."""
        self.scan()
        with self.lock: found = [dict(r) for r in self.known.values() if r['item'] == item]
        return sorted(found, key=lambda r: -r['finished'])

    def progress(self, item, started, frames):
        """Frames written by the newest job for item created after started; frames maps action -> frame count."""
        try: entries = [e for e in os.scandir(self.jobs) if e.is_dir() and e.stat().st_mtime >= started - 1]
        except FileNotFoundError: return None
        for entry in sorted(entries, key=lambda e: -e.stat().st_mtime):
            spec = read_json(Path(entry.path, 'job.json'))
            if not spec or spec.get('name') != item or 'rebuild' in spec: continue
            blocks = spec.get('blocks') or [[a, d] for a in spec.get('actions', []) for d in range(5)]
            total = sum(frames.get(a, 0) for a, _ in blocks)
            done = sum(1 for _ in Path(entry.path, 'render/clothing/frames').rglob('*.png'))
            return {'done': min(done, total), 'total': total} if total else None
        return None
