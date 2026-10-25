"""Protected-path guard for every purge or cleanup that touches D:/_agentShared (rule: evidence_central.md).

A path is protected when any component, case-insensitive, contains one of PROTECTED_MARKERS, or when a file
starts with a PEM private-key or DPAPI blob header. Tools import this module instead of copying the list:

    import sys; sys.path.insert(0, 'D:/.projects/.Org/tools/evidence')
    from protected import guard, safe_rmtree, safe_unlink, ProtectedPathError

guard(paths) scans every planned path (and everything under planned folders) and raises ProtectedPathError
before anything is deleted, so a plan with one protected entry deletes nothing. Standard library only.
CLI: `python protected.py check PATH...` (exit 2 on a hit) and `python protected.py scan ROOT [--json]`.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys

RULE_MARKERS = ('-private', 'private', 'credential', 'secret', 'token', '.key', 'dpapi', 'keystore')
# The 2026-10-18 damage audit found servermanager/ssh-key-backup-20261013 and keepassxc-nightly deleted unflagged.
EXTRA_MARKERS = ('ssh-key', 'keepass', '.kdbx', 'id_rsa', 'id_ed25519', '.pfx', '.p12', '.clixml')
PROTECTED_MARKERS = RULE_MARKERS + EXTRA_MARKERS
# CryptProtectData blobs start with a version dword and the DPAPI provider GUID df9d8cd0-1501-11d1-8c7a-00c04fc297eb.
DPAPI_HEADER = bytes.fromhex('01000000d08c9ddf0115d1118c7a00c04fc297eb')
PEM_PRIVATE = (b'-----BEGIN PRIVATE KEY', b'-----BEGIN RSA PRIVATE KEY', b'-----BEGIN EC PRIVATE KEY',
               b'-----BEGIN OPENSSH PRIVATE KEY', b'-----BEGIN ENCRYPTED PRIVATE KEY', b'-----BEGIN DSA PRIVATE KEY')
SNIFF_BYTES = 4096


class ProtectedPathError(ValueError):
    def __init__(self, hits):
        self.hits = hits
        super().__init__(f'{len(hits)} protected path(s) refused, nothing deleted: ' + '; '.join(f"{h['path']} ({h['reason']})" for h in hits[:5]))


def name_reason(path, root=None):
    """Return the marker that protects path by name, checking every component (below root when given)."""
    path = Path(path)
    if root is not None:
        try:
            path = Path(os.path.abspath(path)).relative_to(os.path.abspath(root))
        except ValueError:
            pass
    for part in path.parts:
        lower = part.lower()
        for marker in PROTECTED_MARKERS:
            if marker in lower:
                return f'name contains {marker!r} in {part!r}'
    return None


def content_reason(path):
    """Return a reason when a regular file starts like a DPAPI blob or carries a PEM private key."""
    try:
        with open(path, 'rb') as stream:
            head = stream.read(SNIFF_BYTES)
    except OSError:
        return None
    if head.startswith(DPAPI_HEADER):
        return 'DPAPI blob header'
    # DPAPI output is often stored base64-encoded; AQAAANCMnd8BFdERjHoAwE/Cl+s is the encoded header.
    if head.lstrip(b'\xef\xbb\xbf"\' \r\n').startswith(b'AQAAANCMnd8BFdERjHoAwE/Cl+s'):
        return 'base64 DPAPI blob header'
    for marker in PEM_PRIVATE:
        if marker in head:
            return 'PEM private key header'
    return None


def reason(path, root=None, content=True):
    path = Path(path)
    found = name_reason(path, root)
    if found is None and content and path.is_file() and not path.is_symlink():
        found = content_reason(path)
    return found


def scan(paths, root=None, content=True):
    """List every protected path at or below the given paths, without following links."""
    hits = []
    for top in [Path(p) for p in ([paths] if isinstance(paths, (str, os.PathLike)) else paths)]:
        found = reason(top, root, content)
        if found:
            hits.append(dict(path=str(top), reason=found))
            continue
        if top.is_dir() and not top.is_symlink():
            for parent, dirs, files in os.walk(top, followlinks=False):
                keep = []
                for name in dirs:
                    found = name_reason(Path(parent) / name, root)
                    if found:
                        hits.append(dict(path=str(Path(parent) / name), reason=found))
                    else:
                        keep.append(name)
                dirs[:] = keep
                for name in files:
                    found = reason(Path(parent) / name, root, content)
                    if found:
                        hits.append(dict(path=str(Path(parent) / name), reason=found))
    return hits


def log_skips(hits, log=None, tool=None, dry=False):
    """Print each skip to stderr and append it to a JSONL log when one is given."""
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    for hit in hits:
        print(f"protected: skip {hit['path']} ({hit['reason']})", file=sys.stderr)
    if log and hits:
        log = Path(log)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('a', encoding='utf-8') as stream:
            for hit in hits:
                stream.write(json.dumps(dict(time=stamp, tool=tool, dry=dry, **hit)) + '\n')


def guard(paths, root=None, log=None, tool=None, dry=False, content=True):
    """Raise ProtectedPathError (after logging every hit) if any planned path is or contains a protected path."""
    hits = scan(paths, root, content)
    if hits:
        log_skips(hits, log, tool, dry)
        raise ProtectedPathError(hits)
    return []


def safe_rmtree(path, root=None, log=None, tool=None):
    guard([path], root, log, tool)
    shutil.rmtree(path)


def safe_unlink(path, root=None, log=None, tool=None, missing_ok=False):
    path = Path(path)
    if missing_ok and not path.exists():
        return
    guard([path], root, log, tool)
    path.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('check', help='Exit 2 if any path is or contains a protected path')
    p.add_argument('paths', nargs='+'); p.add_argument('--root')
    p = sub.add_parser('scan', help='List protected paths under ROOT')
    p.add_argument('root'); p.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if args.cmd == 'check':
        hits = scan(args.paths, args.root)
    else:
        hits = scan([args.root], args.root)
    if getattr(args, 'json', False):
        print(json.dumps(hits, indent=2))
    else:
        for hit in hits:
            print(f"{hit['path']}\t{hit['reason']}")
    return 2 if hits else 0


if __name__ == '__main__':
    sys.exit(main())
