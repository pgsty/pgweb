"""Four small, versioned reference columns with the site's existing wiki shell."""

from collections import Counter
from copy import deepcopy
import hashlib
import json

from django.core.cache import cache
from django.db.models import JSONField
from django.db.models.expressions import RawSQL

from .models import (DataType, ExtensionHook, IndexAccessMethod, ObjectIdentifierType,
                     PredefinedRole, StorageParameter)
from .sqlcmd_common import version_rows
from .topic_specs import TOPIC_SPECS
from .topic_registry import DOMAINS, DOMAIN_KEYS
from . import models as domain_models

MODELS = {'hook': ExtensionHook, 'relopts': StorageParameter,
          'role': PredefinedRole, 'oid': ObjectIdentifierType,
          'type': DataType, 'indexam': IndexAccessMethod}
MODELS.update({key: getattr(domain_models, model) for key, model, *_ in DOMAINS})
TOPICS = {kind: dict(spec, model=MODELS[kind]) for kind, spec in TOPIC_SPECS.items()}


def cache_key(kind):
    return 'pgweb:wiki:topics:2:' + kind


def forget(kind):
    cache.delete(cache_key(kind))
    cache.delete(cache_key(kind) + ':releases')


def records(kind):
    rows = cache.get(cache_key(kind))
    if rows is None:
        model = TOPICS[kind]['model']
        if kind == 'type':
            # A family chapter is deliberately retained by every type it
            # documents. Collection navigation only needs small factual
            # projections, not hundreds of copies of complete chapters.
            projection = RawSQL("""(SELECT jsonb_object_agg(v.key,
                (v.value - 'manual_html' - 'sections' - 'operators' - 'casts' - 'operator_classes' - 'ranges' - 'comparison_data') ||
                jsonb_build_object('description', jsonb_build_array(v.value->'description'->0),
                    'attribute_hash', md5((v.value->'catalog')::text ||
                    coalesce((v.value->'casts')::text, '') || coalesce((v.value->'operators')::text, '') ||
                    coalesce((v.value->'operator_classes')::text, '') ||
                    coalesce((v.value->'aliases')::text, '') || coalesce((v.value->'ranges')::text, ''))))
                FROM jsonb_each(versions) AS v)""", [], output_field=JSONField())
            rows = list(model.objects.annotate(version_summary=projection).values(
                'slug', 'name', 'name_zh', 'category', 'summary', 'aliases', 'content_hash', 'version_summary'))
            for row in rows:
                row['versions'] = row.pop('version_summary')
        elif kind in DOMAIN_KEYS:
            # Lists and navigation do not need repeated full manual chapters.
            projection = RawSQL("""(SELECT jsonb_object_agg(v.key,
                jsonb_build_object('description', jsonb_build_array(v.value->'description'->0),
                  'signature', v.value->'signature', 'facts', v.value->'facts',
                  'release', v.value->'release', 'comparison_hash', v.value->'comparison_hash'))
                FROM jsonb_each(versions) AS v)""", [], output_field=JSONField())
            rows = list(model.objects.annotate(version_summary=projection).values(
                'slug', 'name', 'name_zh', 'category', 'summary', 'aliases', 'content_hash', 'version_summary'))
            for row in rows:
                row['versions'] = row.pop('version_summary')
        else:
            rows = list(model.objects.all().values())
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
    if wanted == 'devel':
        from pgweb.docs.versions import DEVEL_MAJOR_VERSION
        wanted = str(DEVEL_MAJOR_VERSION)
    if wanted:
        return next((v for v in versions if v['major'] == wanted), None)
    return next((v for v in versions if v['status'] == 'stable'), versions[-1])


def signature_of(snapshot):
    """A factual change marker, excluding translated prose and source builds."""
    if snapshot.get('comparison_hash'):
        return snapshot['comparison_hash']
    if 'comparison_data' in snapshot:
        return digest(snapshot['comparison_data'])
    attributes = snapshot.get('attribute_hash')
    if attributes is None and 'catalog' in snapshot:
        attributes = digest({k: snapshot.get(k) for k in
                             ('catalog', 'casts', 'operators', 'operator_classes', 'aliases', 'ranges')})
    return json.dumps(dict(signature=snapshot.get('signature'), facts=snapshot.get('facts'), attribute_hash=attributes),
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
        search = ' '.join([row['name'], row['name_zh'], row['summary'], row['category'], *row['aliases']])
        case_sensitive = kind == 'psql' and query.startswith('\\')
        matches = query in search if case_sensitive else query.casefold() in search.casefold()
        if not matches or (category and row['category'] != category):
            continue
        snapshot = row['versions'].get(major)
        if kind in ('type', 'indexam') + DOMAIN_KEYS:
            row['summary'] = snapshot['description'][0] if snapshot else '所选版本未收录此条目。'
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
    if kind in DOMAIN_KEYS:
        return domain_detail(kind, slug, wanted)
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
    if kind == 'type' or kind in DOMAIN_KEYS:
        row = dict(row, versions=TOPICS[kind]['model'].objects.values_list('versions', flat=True).get(pk=slug))
    snapshot = row['versions'].get(major)
    if kind in ('type', 'indexam') + DOMAIN_KEYS:
        row['summary'] = snapshot['description'][0] if snapshot else '所选版本未收录此条目。'
    for v in versions:
        v.update(is_current=v['major'] == major, present=v['major'] in row['versions'])
    available = [v for v in versions if v['present']]
    neighbours = [dict(name=r['name'], name_zh=r['name_zh'], url=row_url(kind, r) + '?v=' + major)
                  for r in rows if r['category'] == row['category'] and r['slug'] != slug and
                  major in r['versions']][:12]
    return dict(topic=TOPICS[kind], kind=kind, root=root, item=row,
                versions=versions, version=version, major=major, snapshot=snapshot,
                available=available, first=available[0], last=available[-1],
                neighbours=neighbours, cells=cells(kind, row, versions))


def domain_detail(kind, slug, wanted=''):
    """Load one rich entity; navigation needs only the small release inventory."""
    model = TOPICS[kind]['model']
    row = model.objects.values('slug', 'name', 'name_zh', 'category', 'summary', 'aliases',
                               'content_hash', 'versions').get(pk=slug)
    root = '/wiki/{}/'.format(kind)
    key = cache_key(kind) + ':releases'
    versions = cache.get(key)
    if versions is None:
        versions = releases(records(kind), root)
        cache.set(key, versions, 300)
    versions = deepcopy(versions)
    version = choose_version(versions, wanted)
    if version is None:
        raise ValueError('Unsupported version')
    major = version['major']
    snapshot = row['versions'].get(major)
    row['summary'] = snapshot['description'][0] if snapshot else '所选版本未收录此条目。'
    for v in versions:
        v.update(is_current=v['major'] == major, present=v['major'] in row['versions'],
                 url=row_url(kind, row) + '?v=' + v['major'])
    available = [v for v in versions if v['present']]
    neighbours = [dict(name=r['name'], name_zh=r['name_zh'], url=row_url(kind, r) + '?v=' + major)
                  for r in model.objects.filter(category=row['category'], versions__has_key=major)
                  .exclude(pk=slug).values('slug', 'name', 'name_zh')[:12]]
    return dict(topic=TOPICS[kind], kind=kind, root=root, item=row, versions=versions,
                version=version, major=major, snapshot=snapshot, available=available,
                first=available[0], last=available[-1], neighbours=neighbours,
                cells=cells(kind, row, versions))


def entity_key(kind, row):
    if kind in ('psql', 'tool', 'conn'):
        from pgweb.search.taxonomy import normalize_name
        return ('option' if kind == 'conn' else kind) + ':' + normalize_name(row['name'])
    if kind in ('oid', 'type'):
        return 'type:' + row['name'].casefold()
    if kind == 'indexam':
        return 'am:' + row['slug']
    return kind + ':' + row['slug']


def digest(record):
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()
