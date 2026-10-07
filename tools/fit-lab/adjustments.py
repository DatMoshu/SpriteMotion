"""Atomic fit saves, bounded backups and optimistic concurrency for local lab tabs."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import threading
from datetime import datetime, timezone
from uuid import uuid4


class ConflictError(ValueError):
    pass


def validate(data):
    """Dependency-free validation matching common/schemas/fit-adjustments.schema.json."""
    def number(value):
        return type(value) in (int, float) and math.isfinite(value)

    if not isinstance(data, dict) or not {'parts', 'items'} <= set(data) or not set(data) <= {'parts', 'items', 'groups', 'corrections'}:
        raise ValueError('Adjustments need parts and items objects.')
    for section, allowed in [('parts', {'offset', 'rotate', 'scale', 'depth_scale', 'bind', 'hide_body', 'occlusion'}), ('items', {'offset', 'sides'})]:
        if not isinstance(data[section], dict):
            raise ValueError(f'{section} must be an object.')
        for name, fit in data[section].items():
            if not isinstance(name, str) or not isinstance(fit, dict) or not set(fit) <= allowed:
                raise ValueError('Invalid fit fields.')
            for key, value in fit.items():
                if key == 'sides':
                    valid = (isinstance(value, dict) and set(value) <= {'left', 'right'} and
                             all(isinstance(v, list) and len(v) == 3 and all(number(n) for n in v) for v in value.values()))
                elif key in ('offset', 'rotate'):
                    valid = isinstance(value, list) and len(value) == 3 and all(number(n) for n in value)
                elif key in ('scale', 'depth_scale'):
                    valid = number(value) and value > 0
                elif key == 'bind':
                    valid = value in ('skinned', 'rigid')
                elif key == 'occlusion':
                    valid = value in ('clothing', 'body', 'none')
                else:
                    valid = (isinstance(value, dict) and set(value) == {'enabled', 'outward', 'inward'}
                             and type(value['enabled']) is bool
                             and all(number(value[k]) and value[k] >= 0 for k in ('outward', 'inward')))
                if not valid:
                    raise ValueError(f'Invalid {key} value.')
    groups = data.get('groups', {})
    if not isinstance(groups, dict) or any(not isinstance(k, str) or not isinstance(v, list) or
            any(not isinstance(i, str) for i in v) or len(v) != len(set(v)) for k, v in groups.items()):
        raise ValueError('Groups must contain unique item IDs.')
    rules = data.get('corrections', [])
    if not isinstance(rules, list): raise ValueError('Corrections must be a list.')
    seen = set()
    for rule in rules:
        if not isinstance(rule, dict) or not {'target', 'fit'} <= set(rule) or not set(rule) <= {'target','key','action','direction','fit'}:
            raise ValueError('Invalid correction fields.')
        if rule['target'] not in ('pack','slot','group','item'): raise ValueError('Invalid correction target.')
        if rule['target'] != 'pack' and (not isinstance(rule.get('key'), str) or not rule['key']):
            raise ValueError('Correction target requires a key.')
        if rule['target'] == 'group' and rule['key'] not in groups: raise ValueError('Unknown correction group.')
        if rule['target'] == 'pack' and 'key' in rule: raise ValueError('Pack corrections do not have a key.')
        for field, maximum in [('action',34),('direction',4)]:
            if field in rule and (type(rule[field]) is not int or not 0 <= rule[field] <= maximum):
                raise ValueError('Invalid correction ' + field)
        identity = (rule['target'], rule.get('key'), rule.get('action'), rule.get('direction'))
        if identity in seen: raise ValueError('Duplicate correction selector.')
        seen.add(identity)
        fit = rule['fit']
        if not isinstance(fit, dict) or not set(fit) <= {'offset','rotate','scale','depth_scale','occlusion'}:
            raise ValueError('Invalid correction fit.')
        validate({'parts': {'correction': fit}, 'items': {}})
    return data


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class AdjustmentStore:
    def __init__(self, path):
        self.path = Path(path)
        self.backup_dir = self.path.parent / 'lab-adjustments-backups'
        self.lock = threading.RLock()

    def _read(self):
        return validate(json.loads(self.path.read_text(encoding='utf-8-sig'))) if self.path.exists() else {'parts': {}, 'items': {}}

    def _backups(self):
        return sorted(self.backup_dir.glob('*.json'), reverse=True)

    def state(self):
        with self.lock:
            data = self._read()
            return {'adjustments': data, 'revision': hashlib.sha256(canonical(data)).hexdigest(),
                    'backups': [{'id': p.name, 'saved_at': datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
                                for p in self._backups()[:3]]}

    def backup(self, name):
        with self.lock:
            path = next((p for p in self._backups()[:3] if p.name == name), None)
            if path is None:
                raise FileNotFoundError('Backup is no longer available.')
            return validate(json.loads(path.read_text(encoding='utf-8-sig')))

    def save(self, data, base_revision):
        validate(data)
        with self.lock:
            current = self.state()
            if base_revision != current['revision']:
                raise ConflictError('Disk adjustments changed. Choose which version to keep.')
            if canonical(data) == canonical(current['adjustments']):
                return current
            # Back up even the initial empty state so the first save is reversible.
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            backups = self._backups()
            if not backups or canonical(json.loads(backups[0].read_text())) != canonical(current['adjustments']):
                atomic_write(self.backup_dir / f'{stamp}-{uuid4().hex[:8]}.json', canonical(current['adjustments']))
            for old in self._backups()[3:]:
                old.unlink()
            atomic_write(self.path, (json.dumps(data, indent=1, allow_nan=False) + '\n').encode())
            return self.state()
