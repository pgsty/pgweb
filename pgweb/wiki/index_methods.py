"""Index-method readers: same-version comparisons and explicit unknown states."""
from copy import deepcopy

from . import topics
from .index_method_data import CAPABILITIES, METHODS, STATES

KIND = 'indexam'


def capability_map(snapshot):
    return {row['key']: row for row in (snapshot or {}).get('capabilities', [])}


def compare(left, right):
    """Compare capability conclusions and option inventory, excluding source churn.

    An unknown-to-yes transition means evidence became available; it is never
    presented as proof that a feature was introduced in that release.
    """
    if left is None or right is None:
        return {'presence': 'added' if right else 'removed' if left else '',
                'capabilities': [], 'options_added': [], 'options_removed': []}
    a, b = capability_map(left), capability_map(right)
    changes = []
    for key, label in CAPABILITIES:
        old, new = a.get(key, {}), b.get(key, {})
        before, after = old.get('state', 'unknown'), new.get('state', 'unknown')
        if before != after:
            changes.append({'key': key, 'label': label, 'before': STATES[before], 'after': STATES[after],
                            'evidence_changed': 'unknown' in {before, after}, 'sources': new.get('evidence', [])})
    old = {option['name'] for option in left.get('storage_options', [])}
    new = {option['name'] for option in right.get('storage_options', [])}
    return {'presence': '', 'capabilities': changes,
            'options_added': sorted(new - old), 'options_removed': sorted(old - new)}


def changed(delta):
    return any(delta.get(key) for key in ('presence', 'capabilities', 'options_added', 'options_removed'))


def comparison(rows, versions, target, wanted=''):
    majors = [v['major'] for v in versions]
    if wanted and wanted not in majors:
        raise ValueError('Unsupported comparison version')
    offset = majors.index(target)
    baseline = wanted or (majors[offset - 1] if offset else '')
    result = []
    if baseline:
        for row in rows:
            delta = compare(row['versions'].get(baseline), row['versions'].get(target))
            if changed(delta):
                result.append(dict(delta, name=row['name'], slug=row['slug'],
                                   url=topics.row_url(KIND, row) + '?v=' + target))
    return {'baseline': baseline, 'target': target, 'rows': result,
            'versions': [dict(v, selected=v['major'] == baseline) for v in versions]}


def index(wanted='', query='', category='', baseline=''):
    payload = topics.index(KIND, wanted, query, category)
    rows = sorted(payload['rows'], key=lambda row: list(METHODS).index(row['slug']))
    payload['rows'] = rows
    present = [row for row in rows if payload['major'] in row['versions']]
    matrix = []
    for key, label in CAPABILITIES:
        cells = []
        for row in present:
            value = deepcopy(capability_map(row['versions'][payload['major']])[key])
            value.update(name=row['name'], url=row['url'] + '#cap-' + key)
            cells.append(value)
        matrix.append({'key': key, 'label': label, 'cells': cells})
    payload['matrix'] = {'methods': present, 'rows': matrix}
    payload['comparison'] = comparison(rows, payload['versions'], payload['major'], baseline)
    return payload


def detail(slug, wanted='', baseline=''):
    payload = topics.detail(KIND, slug, wanted)
    row = payload['item']
    payload['comparison'] = comparison([row], payload['versions'], payload['major'], baseline)
    history = []
    versions = payload['versions']
    for before, after in zip(versions, versions[1:]):
        delta = compare(row['versions'].get(before['major']), row['versions'].get(after['major']))
        if changed(delta):
            history.append(dict(delta, before=before['major'], after=after['major'],
                                url=topics.row_url(KIND, row) + '?v=' + after['major']))
    payload['history'] = list(reversed(history))
    return payload
