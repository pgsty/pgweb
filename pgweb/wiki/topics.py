"""Four small, versioned reference columns with the site's existing wiki shell."""

from collections import Counter
from copy import deepcopy
import hashlib
import json

from django.core.cache import cache

from .models import ExtensionHook, ObjectIdentifierType, PredefinedRole, StorageParameter
from .sqlcmd_common import version_rows
from .topic_specs import TOPIC_SPECS

MODELS = {'hook': ExtensionHook, 'relopts': StorageParameter,
          'role': PredefinedRole, 'oid': ObjectIdentifierType}
TOPICS = {kind: dict(spec, model=MODELS[kind]) for kind, spec in TOPIC_SPECS.items()}


def cache_key(kind):
    return 'pgweb:wiki:topics:1:' + kind


def forget(kind):
    cache.delete(cache_key(kind))


def records(kind):
    rows = cache.get(cache_key(kind))
    if rows is None:
        rows = list(TOPICS[kind]['model'].objects.all().values())
        cache.set(cache_key(kind), rows, 300)
    return deepcopy(rows)


def row_url(kind, row):
    return '/wiki/{}/{}/'.format(kind, row['slug'])


def releases(rows, root):
    sampled = {}
    for row in rows:
        for major, snapshot in row['versions'].items():
            sampled.setdefault(major, snapshot['release'])
    result = version_rows(sampled)
    for version in result:
        major = version['major']
        source = sampled[major]
        # Current support is distinct from the source build (e.g. beta 4).
        version.update(label=source.get('label') or major, source=source,
                       url=root + '?v=' + major,
                       tone={'devel': 'dev', 'preview': 'beta', 'supported': 'live',
                             'end-of-life': 'eol'}[version['support_status']])
    return result


def choose_version(versions, wanted):
    if not versions:
        return None
    if wanted:
        return next((v for v in versions if v['major'] == wanted), None)
    return next((v for v in versions if v['status'] == 'stable'), versions[-1])


def signature_of(snapshot):
    """A factual change marker, excluding translated prose and source builds."""
    return json.dumps({k: snapshot.get(k) for k in ('signature', 'facts')},
                      sort_keys=True, ensure_ascii=False)


def cells(kind, row, versions):
    result, previous = [], None
    for i, version in enumerate(versions):
        major = version['major']
        snapshot = row['versions'].get(major)
        state, label = 'absent', '该版未收录'
        if snapshot:
            if i and not previous:
                state, label = 'added', '本次采样首次出现'
            elif previous and signature_of(previous) != signature_of(snapshot):
                state, label = 'changed', '接口或属性变化'
            else:
                state, label = 'present', '已收录'
        elif previous:
            state, label = 'removed', '该版不再收录'
        result.append(dict(major=major, state=state, label=label,
                           title='PostgreSQL {} · {}'.format(version['label'], label),
                           url=row_url(kind, row) + '?v=' + major))
        previous = snapshot
    return result


def index(kind, wanted='', query='', category=''):
    spec = TOPICS[kind]
    rows = records(kind)
    root = '/wiki/{}/'.format(kind)
    versions = releases(rows, root)
    version = choose_version(versions, wanted)
    if wanted and version is None:
        raise ValueError('Unsupported version')
    major = version['major'] if version else ''
    counts = Counter(r['category'] for r in rows)
    present = sum(major in r['versions'] for r in rows)
    selected = []
    for row in rows:
        search = ' '.join([row['name'], row['name_zh'], row['summary'], row['category'], *row['aliases']]).casefold()
        if query.casefold() not in search or (category and row['category'] != category):
            continue
        row.update(url=row_url(kind, row) + '?v=' + major,
                   cells=cells(kind, row, versions), present=major in row['versions'])
        selected.append(row)
    for v in versions:
        v['is_current'] = v['major'] == major
    return dict(topic=spec, kind=kind, root=root, rows=selected, total=len(rows),
                found=len(selected), present=present, versions=versions, version=version,
                major=major, categories=[dict(name=k, count=v) for k, v in counts.items()],
                query=query, category=category)


def detail(kind, slug, wanted=''):
    rows = records(kind)
    row = next((r for r in rows if r['slug'] == slug), None)
    if row is None:
        raise TOPICS[kind]['model'].DoesNotExist()
    root = '/wiki/{}/'.format(kind)
    versions = releases(rows, row_url(kind, row))
    version = choose_version(versions, wanted)
    if version is None:
        raise ValueError('Unsupported version')
    major = version['major']
    snapshot = row['versions'].get(major)
    for v in versions:
        v.update(is_current=v['major'] == major, present=v['major'] in row['versions'])
    available = [v for v in versions if v['present']]
    neighbours = [dict(name=r['name'], name_zh=r['name_zh'], url=row_url(kind, r) + '?v=' + major)
                  for r in rows if r['category'] == row['category'] and r['slug'] != slug
                  and major in r['versions']][:12]
    return dict(topic=TOPICS[kind], kind=kind, root=root, item=row,
                versions=versions, version=version, major=major, snapshot=snapshot,
                available=available, first=available[0], last=available[-1],
                neighbours=neighbours, cells=cells(kind, row, versions))


def entity_key(kind, row):
    if kind == 'oid':
        return 'type:' + row['name'].casefold()
    return kind + ':' + row['slug']


def digest(record):
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()
