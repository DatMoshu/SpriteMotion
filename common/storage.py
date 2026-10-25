"""Bounded content-job storage; only explicitly regenerable derivatives expire."""
from contextlib import contextmanager
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

STORAGE_GUARD_VERSION = 1
DERIVED = ('render', 'review', 'original-frames.json', 'item.vd',
           'import-package.zip', 'contact-sheet.png', 'inventory.png',
           'slot-preview.png', 'build.log')


def sibling(name):
    spec = importlib.util.spec_from_file_location('_storage_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


paths = sibling('workpaths')


class StorageLimit(ValueError):
    pass


class Policy:
    def __init__(self, max_bytes=None, days=None, keep=None):
        gb = float(os.environ.get('SPRITEMOTION_MAX_WORK_GB', '5'))
        self.max_bytes = max_bytes if max_bytes is not None else int(gb * 1_000_000_000)
        self.days = days if days is not None else float(os.environ.get('SPRITEMOTION_OUTPUT_DAYS', '7'))
        self.keep = keep if keep is not None else int(os.environ.get('SPRITEMOTION_KEEP_OUTPUT_JOBS', '10'))
        if not math.isfinite(gb) or self.max_bytes <= 0 or not math.isfinite(self.days) or self.days <= 0 or self.keep < 1:
            raise ValueError('Storage limits must be positive; keep at least one completed job.')


def usage(root):
    """Logical bytes in the physical store; do not follow links or count hardlinks twice."""
    total = 0
    seen = set()
    for parent, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not linked(Path(parent, d))]
        for name in files:
            p = Path(parent, name)
            if linked(p):
                continue
            s = p.stat()
            key = (s.st_dev, s.st_ino)
            if key not in seen:
                total += s.st_size
                seen.add(key)
    return total


def linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def protected_guard(candidates):
    # Reuse fleet protection when installed; the identical portable fallback is
    # shipped for users who do not have the fleet. Never bypass protected names.
    fleet = Path(os.environ.get('ORG_ROOT', 'D:/.projects/.Org')) / 'tools/evidence/protected.py'
    if fleet.is_file():
        spec = importlib.util.spec_from_file_location('_storage_fleet_protected', fleet)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = sibling('storage_protection')
    module.guard(candidates, tool='spritemotion-generated-retention')


def derivative_paths(job, initial_scene=False):
    candidates = [job / name for name in DERIVED if (job / name).exists()]
    if initial_scene and (job / 'item.blend').exists():
        candidates.append(job / 'item.blend')
    for p in candidates:
        if p.parent != job or linked(p):
            raise ValueError('Linked generated output refused: ' + str(p))
        if p.is_dir():
            for parent, dirs, files in os.walk(p):
                if any(linked(Path(parent, n)) for n in dirs + files):
                    raise ValueError('Linked generated output contents refused: ' + str(p))
                if any(Path(n).suffix.lower() not in {'.png', '.json', '.html'} for n in files):
                    raise ValueError('Unknown file in generated derivatives; retained for inspection: ' + str(p))
    return candidates


def delete_paths(candidates):
    for p in candidates:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
    return [str(p) for p in candidates]


def remove_derived(job, initial_scene=False):
    candidates = derivative_paths(job, initial_scene)
    protected_guard(candidates)
    return delete_paths(candidates)


@contextmanager
def pin(job):
    """Keep an immutable rebuild source alive across patch/render/merge sessions."""
    marker = Path(job) / '.storage.pin'
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError('This source job is already pinned by another rebuild.')
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        marker.unlink()


class Store:
    def __init__(self, home, policy=None):
        self.home = paths.external_path(Path(home))
        self.policy = policy or Policy()

    def require(self, extra=0):
        size = usage(self.home)
        if size + extra > self.policy.max_bytes:
            raise StorageLimit(f'Generated storage limit reached ({size + extra} > {self.policy.max_bytes} bytes). '
                               'Run tools/storage/run.py prune, remove obsolete derivatives, or select another external '
                               'SPRITEMOTION_CONTENT_HOME. Inputs and editable scenes are never expired. '
                               'SPRITEMOTION_MAX_WORK_GB sets the limit.')
        return size

    def prune(self, protect=()):
        protected = {Path(p).resolve() for p in protect}
        jobs = []
        if linked(self.home / 'jobs'):
            raise ValueError('Linked jobs directory refused; retention never follows links.')
        for p in (self.home / 'jobs').glob('*/status.json'):
            if not re.fullmatch('[a-f0-9]{12}', p.parent.name) or linked(p.parent) or linked(p) or p.parent.resolve() in protected or (p.parent / '.keep').exists() or (p.parent / '.storage.pin').exists():
                continue
            try:
                status = json.loads(p.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue  # Unknown or corrupt state is not proof of obsolescence.
            if isinstance(status, dict) and status.get('state') in ('complete', 'failed'):
                jobs.append((p.stat().st_mtime, p, status))
        plans = []
        for index, (stamp, p, status) in enumerate(sorted(jobs, reverse=True)):
            if index < self.policy.keep or time.time() - stamp < self.policy.days * 86400:
                continue
            plans.append((p, status, derivative_paths(p.parent)))
        protected_guard([q for p, status, candidates in plans for q in candidates])
        removed = []
        for p, status, candidates in plans:
            deleted = delete_paths(candidates)
            if deleted:
                status.update(state='failed', error='Generated derivatives expired; retained inputs/settings/scene can rebuild.')
                p.write_text(json.dumps(status, indent=2), encoding='utf-8')
                removed.extend(deleted)
        return removed

    @contextmanager
    def session(self, protect=()):
        self.home.mkdir(parents=True, exist_ok=True)
        lock = self.home / '.storage.lock'
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ValueError('Another content build/cleanup holds .storage.lock. Wait; after a crash verify no build is active before removing the lock.')
        try:
            os.write(fd, str(os.getpid()).encode())
            self.prune(protect)
            self.require()
            yield self
        finally:
            os.close(fd)
            lock.unlink()

    def process(self, command, job, **kwargs):
        """Stop the child on overflow; polling may allow one write interval of overshoot."""
        self.require()
        child = subprocess.Popen(command, **kwargs)
        try:
            while child.poll() is None:
                time.sleep(.25)
                self.require()
            self.require()
            return child.returncode
        except BaseException:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            raise


def startup(checkout, python=None, paths_only=False):
    checkout = Path(checkout).resolve()
    module = checkout / 'common/storage.py'
    if not module.is_file() or 'STORAGE_GUARD_VERSION = 1' not in module.read_text(encoding='utf-8'):
        raise ValueError('Historical checkout lacks storage guards. Update/rebase it before resuming; no repository-local fallback is allowed.')
    for name in ('common.bat', 'common.sh'):
        text = (checkout / 'launchers/_shared' / name).read_text(encoding='utf-8').replace('\\', '/')
        if 'tools/storage/run.py' not in text:
            raise ValueError('Historical checkout launcher lacks storage startup validation: ' + name)
    work, content = paths.work_root(), paths.content_home()
    paths.external_path(paths.backend_home(), checkout)
    paths.external_path(work, checkout)
    paths.external_path(content, checkout)
    if not paths_only:
        if not python:
            python = os.environ.get('SPRITEMOTION_PYTHON') or paths.checkout_venv(checkout) / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        exe = Path(python).resolve()
        paths.external_path(exe, checkout)
        result = subprocess.run([str(exe), '-c', 'import spritemotion; print(spritemotion.__file__)'],
                                cwd=checkout.parent, capture_output=True, text=True)
        if result.returncode or Path(result.stdout.strip()).resolve().parent != checkout / 'common':
            raise ValueError('Python does not import this checkout. Run its worktree-venv launcher or set SPRITEMOTION_PYTHON to its external environment.')
    return dict(work_root=str(work), content_home=str(content), max_bytes=Policy().max_bytes)
