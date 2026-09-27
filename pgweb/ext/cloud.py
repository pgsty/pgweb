"""Cloud extension matrices from the two local snapshot tables.

No per-provider code, live source connection, or persisted presentation matrix.
"""
import json
from datetime import date, datetime
from urllib.parse import urlencode

from django.core.cache import cache
from django.db import connection

from .catalog import CATEGORIES, catalog, category_color, category_label, detail_url, safe_url

CACHE_KEY = 'pgweb:ext:cloud:v1'
MAJORS = (18, 17, 16, 15, 14)
ANCHOR = 'pigsty'
STATUS_LABELS = {'SUPPORTED': '支持', 'OTHER': '条件支持', 'UNSUPPORTED': '不支持',
                 'UNKNOWN': '资料不足', 'UNAVAILABLE': '未提供此 PG 版本'}
ENGINE_LABELS = {'GA': '正式可用', 'PREVIEW': '预览', 'EXISTING_ONLY': '仅现有实例',
                 'UNAVAILABLE': '未提供此 PG 版本', 'UNKNOWN': '版本状态未知'}
COVERAGE_LABELS = {'COMPLETE': '完整清单', 'PARTIAL': '部分清单', 'MISSING': '缺少资料'}
SCOPE_LABELS = {'PG_MAJOR': '按 PG 大版本', 'PG_MAJOR_PARTIAL': '部分大版本资料',
                'PG_RANGE': 'PG 版本范围', 'SERVICE_WIDE': '服务级清单',
                'CURRENT_MAJOR': '当前 PG 版本', 'DELEGATED': '厂商委托资料',
                'UNVERSIONED': '未区分版本', 'INSTANCE_ONLY': '实例级资料'}
PRIORITY = ('aws_rds', 'aws_aurora', 'google_cloud_sql', 'google_alloydb', 'azure_flexible',
            'alibaba_rds', 'alibaba_polar', 'tencentdb', 'huawei_rds')


def _rows(cursor):
    names = [column[0] for column in cursor.description]
    rows = [dict(zip(names, row)) for row in cursor.fetchall()]
    for row in rows:
        for key in ('extra', 'provenance'):
            if isinstance(row.get(key), str):
                row[key] = json.loads(row[key])
    return rows


def snapshot():
    value = cache.get(CACHE_KEY)
    if value is not None:
        return value
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM pgext.cloud ORDER BY service,pg_major')
        coverage = _rows(cursor)
        cursor.execute('SELECT * FROM pgext.cloud_fact ORDER BY service,pg_major,raw_name')
        facts = _rows(cursor)
    services = {}
    metadata = {}
    for row in coverage:
        sid = row['service']
        label = row['service_name']
        if row['provider'].casefold() not in label.casefold():
            label = row['provider'] + ' · ' + label
        metadata[(sid, row['pg_major'])] = row
        services.setdefault(sid, {'id': sid, 'name': row['service_name'], 'provider': row['provider'],
                                 'label': label,
                                 'url': '/ext/cloud/{}/'.format(sid), 'anchor': sid == ANCHOR})
    ordered = sorted(services.values(), key=lambda s: (
        -1 if s['id'] == ANCHOR else PRIORITY.index(s['id']) if s['id'] in PRIORITY else len(PRIORITY), s['name']))
    index, positive, packaged, raw = {}, set(), set(), {}
    for fact in facts:
        name = fact['extension']
        key = name if name else 'raw:' + fact['service'] + ':' + fact['raw_name']
        if not name:
            raw[key] = {'name': fact['raw_name'], 'service': fact['service']}
        index[(fact['service'], fact['pg_major'], key)] = fact
        if fact['service'] == ANCHOR:
            if (fact.get('extra') or {}).get('packaged'):
                packaged.add(key)
        elif fact['status'] in ('SUPPORTED', 'OTHER'):
            positive.add(key)
    value = {'services': ordered, 'by_service': services, 'coverage': metadata, 'facts': index,
             'positive': positive, 'packaged': packaged, 'raw': raw}
    cache.set(CACHE_KEY, value, 60)
    return value


def entry_rows(data):
    rows = []
    for original in catalog():
        row = dict(original)
        row.update(key=row['name'], packaged=row['name'] in data['packaged'], unresolved=False,
                   href=detail_url(row['name']), description=row.get('zh_desc') or '暂无中文简介',
                   category_label=category_label(row['category']), color=category_color(row['category']))
        rows.append(row)
    for key, original in data['raw'].items():
        name = original['name']
        origin = data['by_service'][original['service']]['label']
        rows.append({'id': None, 'key': key, 'name': name, 'pkg': '', 'category': 'RAW',
                     'category_label': '待归一', 'color': '', 'packaged': False,
                     'unresolved': True, 'href': '', 'stars': 0, 'origin_label': origin,
                     'description': '{} 原始条目，尚未确认标准扩展名，可能包含辅助模块。'.format(origin),
                     'search_text': (name + ' ' + origin).casefold()})
    order = {code: i for i, code in enumerate(CATEGORIES)}
    rows.sort(key=lambda row: (row['unresolved'], order.get(row['category'], 99), row['id'] or 0, row['name']))
    return rows


def cell(data, entry, service, pg):
    meta = data['coverage'].get((service, pg))
    fact = data['facts'].get((service, pg, entry['key']))
    version = fact['version'] if fact else None
    extra = (fact.get('extra') or {}) if fact else {}
    if not meta:
        status = 'UNKNOWN'
    elif meta['engine_status'] == 'UNAVAILABLE':
        status = 'UNAVAILABLE'
    elif meta['data_status'] == 'MISSING':
        status = 'UNKNOWN'
    elif fact:
        status = extra.get('availability', fact['status']) if service == ANCHOR else fact['status']
    elif entry['unresolved']:
        status = 'UNKNOWN'
    elif meta['data_status'] == 'COMPLETE':
        status = 'UNSUPPORTED'
    else:
        status = 'UNKNOWN'
    if status not in STATUS_LABELS:
        status = 'UNKNOWN'
    # A version in a retained but out-of-scope fact is not current availability.
    display = version if version and status in ('SUPPORTED', 'OTHER') else {
        'SUPPORTED': '支持', 'OTHER': '条件支持', 'UNSUPPORTED': '—',
        'UNKNOWN': '?', 'UNAVAILABLE': '⊘'}[status]
    return {'status': status, 'status_label': STATUS_LABELS[status], 'display': display,
            'version': version or '', 'note': (fact.get('note') or '') if fact else '',
            'raw_name': fact['raw_name'] if fact else entry['name'], 'explicit': bool(fact),
            'meta': meta, 'extra': extra,
            'evidence_url': '/ext/cloud/evidence/?' + urlencode({'service': service, 'pg': pg, 'entry': entry['key']})}


def date_text(value):
    if isinstance(value, (date, datetime)):
        return value.strftime('%Y-%m-%d')
    return str(value or '')[:10]


def evidence(data, entry, service, pg):
    value = cell(data, entry, service, pg)
    meta = value.pop('meta') or {}
    extra = value.pop('extra')
    value.update(engine_label=ENGINE_LABELS.get(meta.get('engine_status'), '版本状态未知'),
                 coverage_label=COVERAGE_LABELS.get(meta.get('data_status'), '缺少资料'),
                 scope_label=SCOPE_LABELS.get(meta.get('list_scope'), meta.get('list_scope', '')),
                 checked_at=date_text(meta.get('checked_at')), source_url=safe_url(meta.get('source_url')),
                 engine_url=safe_url(meta.get('engine_url')), coverage_note=meta.get('note') or '', extra_items=[])
    if not value['explicit']:
        if value['status'] == 'UNSUPPORTED':
            value['note'] = '该条目未出现在已核验的完整清单中。'
        elif entry['unresolved']:
            value['note'] = '原始名称尚未归一，不能根据其他厂商清单中的缺席推断不支持。'
        elif value['status'] == 'UNKNOWN':
            value['note'] = '现有资料不足以判断该扩展在此服务及 PG 版本上的支持情况。'
    if service == ANCHOR:
        if extra.get('package_relation') == 'distribution':
            value['extra_items'].append({'label': '软件包版本', 'value': ' / '.join(extra.get('package_versions', []))})
            value['extra_items'].append({'label': '版本口径', 'value': '同发行包的安装包可用性；未将主扩展版本当作此扩展版本。'})
        if 'targets' in extra:
            value['extra_items'].append({'label': '平台覆盖', 'value': '{} / {} 个平台有可用包；{} 个缺包，{} 个不适用'.format(
                extra.get('available', 0), extra['targets'], extra.get('missing', 0), extra.get('not_applicable', 0))})
        for platform in extra.get('platforms', []):
            value['extra_items'].append({'label': platform.get('os', ''), 'value': ' · '.join(str(platform.get(k) or '') for k in ('state', 'version', 'name', 'org'))})
    else:
        for key, item in extra.items():
            value['extra_items'].append({'label': key, 'value': str(item)})
    return value


def positive(value):
    return value['status'] in ('SUPPORTED', 'OTHER')


def matrix_url(service=None, *, selected=None, page=None, format=None):
    path = '/ext/cloud/{}/'.format(service) if service else '/ext/cloud/'
    values = dict(selected or {})
    if service:
        for key in ('pg', 'service', 'selection'):
            values.pop(key, None)
    if page and page != 1:
        values['page'] = page
    if format:
        values['format'] = format
    values = {key: value for key, value in values.items() if value != '' and value is not None}
    query = urlencode(values, doseq=True)
    return path + ('?' + query if query else '')


def selection(request, data, service=None):
    try:
        pg = int(request.GET.get('pg', 18))
    except (TypeError, ValueError):
        pg = 18
    if pg not in MAJORS:
        pg = 18
    allowed_scopes = ('supported', 'packaged', 'all', 'raw') if service else ('compare', 'packaged', 'cloud', 'raw')
    scope = request.GET.get('scope', allowed_scopes[0])
    if scope not in allowed_scopes:
        scope = allowed_scopes[0]
    category = request.GET.get('category', '').upper()[:100]
    if category not in (*CATEGORIES, 'RAW'):
        category = ''
    status = request.GET.get('status', '')
    if status not in ('supported', 'different', 'unknown'):
        status = ''
    chosen = set(request.GET.getlist('service'))
    ids = [s['id'] for s in data['services'] if not s['anchor']]
    if 'selection' not in request.GET and not chosen:
        chosen = set(ids)
    return {'pg': pg, 'q': request.GET.get('q', '').strip()[:255], 'scope': scope,
            'category': category, 'status': status,
            'service': [sid for sid in ids if sid in chosen], 'selection': '1'}


def columns(data, selected, service=None):
    pairs = [(service, pg) for pg in MAJORS] if service else [
        (sid, selected['pg']) for sid in ([ANCHOR] if ANCHOR in data['by_service'] else []) + selected['service']]
    result = []
    for sid, pg in pairs:
        meta = data['coverage'].get((sid, pg), {})
        svc = data['by_service'][sid]
        result.append({'key': '{}:{}'.format(sid, pg), 'service': sid, 'pg': pg,
                       'label': 'PG {}'.format(pg) if service else 'Pigsty' if sid == ANCHOR else svc['name'],
                       'subtitle': svc['provider'] if not service else '', 'url': svc['url'] if not service else '',
                       'anchor': sid == ANCHOR and not service,
                       'engine_label': ENGINE_LABELS.get(meta.get('engine_status'), '版本状态未知'),
                       'coverage_label': COVERAGE_LABELS.get(meta.get('data_status'), '缺少资料')})
    return result


def filtered_entries(data, selected, cols, service=None):
    rows = entry_rows(data)
    words = selected['q'].casefold().split()
    result = []
    for row in rows:
        key = row['key']
        scope = selected['scope']
        if scope == 'compare':
            include = row['packaged'] or key in data['positive']
        elif scope == 'packaged':
            include = row['packaged']
        elif scope == 'cloud':
            include = key in data['positive'] and not row['packaged']
        elif scope == 'all':
            include = not row['unresolved']
        elif scope == 'raw':
            include = row['unresolved'] and (not service or any((service, pg, key) in data['facts'] for pg in MAJORS))
        else:
            include = any(positive(cell(data, row, service, pg)) for pg in MAJORS)
        if not include or (selected['category'] and row['category'] != selected['category']):
            continue
        if not all(word in row['search_text'] for word in words):
            continue
        state = selected['status']
        if state:
            values = [cell(data, row, c['service'], c['pg']) for c in cols]
            if state == 'supported' and not any(positive(c) for c in values):
                continue
            if state == 'unknown' and not any(c['status'] == 'UNKNOWN' for c in values):
                continue
            if state == 'different' and len({(c['status'], c['display']) for c in values}) < 2:
                continue
        result.append(row)
    return result
