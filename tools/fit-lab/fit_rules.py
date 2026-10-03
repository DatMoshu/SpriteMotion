"""Deterministic rest-pose fit resolution shared by lab builds and selective rebuilds."""
from copy import deepcopy


def stored_direction(direction):
    return direction if direction <= 4 else 8 - direction


def resolve(document, mapping, item, action=None, direction=None):
    base = {**mapping, **document.get('parts', {}).get(item['part'], {})}
    result = {'offset': list(base.get('offset', [0, 0, 0])), 'rotate': list(base.get('rotate', [0, 0, 0])),
              'scale': base.get('scale', 1), 'depth_scale': base.get('depth_scale', 1), 'bind': base.get('bind', 'skinned'),
              'hide_body': deepcopy(base.get('hide_body', {'enabled': True, 'outward': .02, 'inward': .01})),
              'occlusion': base.get('occlusion', 'body' if item.get('slot') in ('back', 'quiver') else 'clothing')}
    result['sides'] = deepcopy(document.get('items', {}).get(item['id'], {}).get('sides', {}))
    legacy = document.get('items', {}).get(item['id'], {}).get('offset', [0, 0, 0])
    result['offset'] = [a + b for a, b in zip(result['offset'], legacy)]
    ranks = {'pack': 0, 'slot': 1, 'group': 2, 'item': 3}
    rules = sorted(document.get('corrections', []), key=lambda r: (ranks[r['target']],
                   int('action' in r) + int('direction' in r), int('direction' in r), r.get('key', '')))
    for rule in rules:
        target, key = rule['target'], rule.get('key')
        if target == 'slot' and key != item.get('slot'): continue
        if target == 'item' and key != item['id']: continue
        if target == 'group' and item['id'] not in document.get('groups', {}).get(key, []): continue
        if 'action' in rule and rule['action'] != action: continue
        if 'direction' in rule and (direction is None or rule['direction'] != stored_direction(direction)): continue
        delta = rule['fit']
        for field in ('offset', 'rotate'):
            result[field] = [a + b for a, b in zip(result[field], delta.get(field, [0, 0, 0]))]
        result['scale'] *= delta.get('scale', 1)
        result['depth_scale'] *= delta.get('depth_scale', 1)
        if 'occlusion' in delta: result['occlusion'] = delta['occlusion']
    return result
