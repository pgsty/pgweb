"""等待事件栏目的取数与组装。视图只负责拼上下文，这里负责形状。

前端模板按本文件给出的键名渲染，改键名等于改契约（`docs/waitevent-column.md` §5 与 §9.3）。
版本次序一律取 `WaitEventVersion.position`：'9.6' 与 '10' 字符串比不出先后。

9.0 – 9.5 没有 `wait_event` 这套机制，它们在版本条与轨迹里是「不适用」（`na`），
不是「缺席」；9.6 既是收录起点也是机制起点，所以首版照常标「新增」。

索引页与变更页不把 `versions`、`changes`、`dossier` 三列取回来：一个事件的档案比
一行表格用到的多两个数量级，列表页只认热字段。
"""

import hashlib
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.core.cache import cache
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .models import (WAITEVENT_SOURCE_STATUS_LABEL, WAITEVENT_TYPES, GucParameter, WaitEvent,
                     WaitEventVersion)
from .waitevent_common import compare_snapshots, normal_text


CACHE_KEY = 'pgweb:wiki:waitevent-index'
VERSION_CACHE_KEY = 'pgweb:wiki:waitevent-versions'
DOC_CACHE_KEY = 'pgweb:wiki:waitevent-docpages'
CHANGES_CACHE_KEY = 'pgweb:wiki:waitevent-changes:{}'
GUC_CACHE_KEY = 'pgweb:wiki:waitevent-guc:{}'
CACHE_SECONDS = 300

ROOT = '/docs/waitevent/'
DOC_FILE = 'monitoring-stats.html'
UPSTREAM = 'https://www.postgresql.org/docs/{}/{}{}'
ATLAS = 'https://wait.pg.center/'

# 索引页与变更页不取这三列：整份档案比列表用到的多两个数量级。
DEFER = ('versions', 'changes', 'dossier')

# 九个规范类型的页面元数据。标签与一句话在 models 里定义，这里只做派生。
TYPE_META = [{'type': name, 'type_slug': name.lower(), 'en': name, 'label': label,
              'eyebrow': name.upper(), 'blurb': blurb, 'anchor': 'type-' + name.lower()}
             for name, label, blurb in WAITEVENT_TYPES]
TYPE_BY_SLUG = {meta['type_slug']: meta for meta in TYPE_META}

# 图谱里一条源码证据的性质，与它的把握程度。
RECORD_KIND_LABEL = {'trigger': '触发点', 'resource_path': '资源定义',
                     'generic_reporter': '通用上报', 'catalog_definition': '目录定义'}
SOURCE_STATUS_LABEL = WAITEVENT_SOURCE_STATUS_LABEL
# 源码证据分组时，目录定义排在每组最后：它只说明这个名字被编译进来了。
KIND_RANK = {'trigger': 0, 'resource_path': 1, 'generic_reporter': 2, 'catalog_definition': 3}

NA_NOTE = 'PostgreSQL 9.x 尚无等待事件机制；wait_event_type 与 wait_event 自 9.6 引入。'
BASELINE_NOTE = '{} 引入等待事件机制，这是本站收录的第一个版本。'
FIRST_VERSION_NOTE = '{} 引入等待事件机制，此为本事件的首个版本。'
PREVIEW_NOTICE = '{} 为预发行快照，正式发布前仍可能变化。'
DEVEL_NOTICE = '{} 为开发版快照，正式发布前仍可能变化。'


# ---------------------------------------------------------------- 版本

def version_data(version, is_default=False):
    return {
        'major': version.major, 'label': version.label or version.major,
        'status': version.status, 'status_label': version.status_label,
        'support_status': version.support_status,
        'has_wait_events': version.has_wait_events, 'method': version.method,
        'event_count': version.event_count, 'type_counts': version.type_counts or {},
        'url': version.changes_url, 'preview': version.is_preview, 'devel': version.is_devel,
        'doc_slug': version.doc_slug, 'position': version.position,
        'is_default': is_default,
    }


def versions():
    """全部版本，按 position。前六项是 9.0 – 9.5（不适用），最后一项是 20 devel。"""
    rows = cache.get(VERSION_CACHE_KEY)
    if rows is None:
        stored = list(WaitEventVersion.objects.all())
        default = stable_major(stored)
        rows = [version_data(version, version.major == default) for version in stored]
        cache.set(VERSION_CACHE_KEY, rows, CACHE_SECONDS)
    return rows


def stable_major(stored):
    """默认版本是 status='stable' 的那一版（当前 18），没有就取最后一个有事件的正式版。

    只有 `versions()` 建缓存时算一次，算完就记在版本条的 `is_default` 上。
    """
    for version in stored:
        if version.status == 'stable':
            return version.major
    formal = [v for v in stored if v.status not in ('preview', 'devel') and v.has_wait_events]
    return (formal or stored)[-1].major if stored else ''


def default_major():
    """默认版本。取版本条上已经标好的 `is_default`，不再查库。"""
    order = versions()
    return next((v['major'] for v in order if v['is_default']),
                order[-1]['major'] if order else '')


def version_map():
    return {version['major']: version for version in versions()}


def live_versions(order=None):
    """有等待事件机制的版本（9.6 起）。"""
    order = order if order is not None else versions()
    return [version for version in order if version['has_wait_events']]


def na_majors(order=None):
    order = order if order is not None else versions()
    return [version['major'] for version in order if not version['has_wait_events']]


def pick_major(wanted, present, order=None):
    """无效或缺席的 ?v= 落回默认版本；默认版本这个事件也没有时取它最后存在的版本。"""
    if wanted and wanted in present:
        return wanted
    order = order if order is not None else versions()
    default = next((v['major'] for v in order if v['is_default']), '')
    if default in present:
        return default
    return present[-1] if present else ''


# ---------------------------------------------------------------- 手册链接

def doc_pages():
    """本站手册里已收录的 (版本段, 文件名)。缓存 5 分钟，够一屏渲染用。"""
    pairs = cache.get(DOC_CACHE_KEY)
    if pairs is None:
        from pgweb.docs.models import DocPage
        pairs = set()
        for tree, filename in DocPage.objects.values_list('version', 'file'):
            slug = 'devel' if int(tree) == 0 else str(int(tree))
            pairs.add((slug, filename))
        cache.set(DOC_CACHE_KEY, pairs, CACHE_SECONDS)
    return pairs


def doc_url(snapshot, pages=None):
    """本站手册该版监控统计页的地址；没收录就留空，不给死链。

    `pages` 是 `doc_pages()` 的结果。一个详情页要问十几次，调用方读一次传进来。
    """
    doc = (snapshot or {}).get('doc') or {}
    slug, filename, anchor = doc.get('slug', ''), doc.get('file', ''), doc.get('anchor', '')
    pages = doc_pages() if pages is None else pages
    if not slug or not filename or (slug, filename) not in pages:
        return ''
    return '/docs/{}/{}{}'.format(slug, filename, '#' + anchor if anchor else '')


def upstream_url(snapshot):
    """postgresql.org 上同一版同一锚点的地址。上游每个版本都有，不看本站收录。"""
    doc = (snapshot or {}).get('doc') or {}
    slug, filename, anchor = doc.get('slug', ''), doc.get('file', ''), doc.get('anchor', '')
    if not slug:
        return ''
    return UPSTREAM.format(slug, filename or DOC_FILE, '#' + anchor if anchor else '')


def forget():
    cache.delete(CACHE_KEY)
    cache.delete(VERSION_CACHE_KEY)
    cache.delete(DOC_CACHE_KEY)
    # 变更页按版本各缓存一份；版本表刚写过，照库里现有的版本清。
    cache.delete_many([CHANGES_CACHE_KEY.format(major) for major
                       in WaitEventVersion.objects.values_list('major', flat=True)])


# ---------------------------------------------------------------- GUC 链接

def guc_links(names):
    """一批参数名 → 本站地址。配置参数栏目有词条就用词条，否则退到手册锚点，再退到检索页。

    一次查完再缓存 5 分钟：一个详情页的相关参数最多十来个，逐个查库不值当。
    """
    names = [name for name in dict.fromkeys(names) if name]
    if not names:
        return {}
    digest = hashlib.sha1('\0'.join(sorted(names)).encode('utf-8')).hexdigest()[:16]
    links = cache.get(GUC_CACHE_KEY.format(digest))
    if links is not None:
        return links
    links = {}
    # 图谱里的参数名大小写未必与 pg_settings 一致（DateStyle / datestyle），按小写 key 对。
    lowered = {name.lower(): name for name in names}
    for key, canonical in GucParameter.objects.filter(key__in=list(lowered)).values_list('key', 'name'):
        wanted = lowered.get(key)
        if wanted:
            links[wanted] = '/docs/guc/{}/'.format(canonical)
    remaining = [name for name in names if name not in links]
    if remaining:
        links.update(manual_guc_links(remaining))
    for name in names:
        links.setdefault(name, '/search/?q={}&kind=guc'.format(quote(name)))
    cache.set(GUC_CACHE_KEY.format(digest), links, CACHE_SECONDS)
    return links


def manual_guc_links(names):
    """手册里该参数的定义锚点（默认版本那一版）。检索索引没建时返回空。"""
    from pgweb.search.models import SearchEntry
    from pgweb.search.taxonomy import normalize_name
    try:
        major = Decimal(default_major())
    except (InvalidOperation, ValueError):
        # 默认版本不是数字（不该发生），当作没有手册条目。
        return {}
    keys = {normalize_name(name): name for name in names}
    rows = SearchEntry.objects.filter(source='pg', kind='guc', version=major,
                                      name_key__in=list(keys)).select_related('document__page')
    links = {}
    for row in rows:
        page = row.document.page if row.document_id else None
        name = keys.get(row.name_key)
        if not page or not name or name in links:
            continue
        anchor = '#' + quote(row.anchor, safe='-._~') if row.anchor else ''
        links[name] = '/docs/{}/{}{}'.format(page.display_version(), page.file, anchor)
    return links


# ---------------------------------------------------------------- 索引页

def removed_after(event, order):
    """移除标在 last_version 的下一版；还在最后一版里就没有移除版本。"""
    majors = [version['major'] for version in order]
    if not event.last_version or event.last_version not in majors:
        return ''
    index = majors.index(event.last_version)
    return majors[index + 1] if index + 1 < len(majors) else ''


def strip_of(event, order, changed, removed_in):
    """版本轨迹：一排方格，每格一个版本。9.0 – 9.5 是 na，不是缺席。"""
    present = set(event.present_in)
    cells = []
    for version in order:
        major = version['major']
        if not version['has_wait_events']:
            state = 'na'
        elif major == removed_in:
            state = 'removed'
        elif major not in present:
            state = 'absent'
        elif major == event.first_version:
            # 9.6 也算「新增」：等待事件机制本身就是 9.6 引入的。
            state = 'added'
        elif major in changed:
            state = 'changed'
        else:
            state = 'present'
        cells.append({
            'major': major, 'label': version['label'], 'state': state,
            'url': '{}?v={}'.format(event.url, major)
            if state not in ('absent', 'removed', 'na') else '',
            'preview': version['preview'], 'devel': version['devel'],
        })
    return cells


def row_of(event, order):
    changed = set(event.changed_in)
    removed_in = removed_after(event, order)
    aliases = list(event.aliases or ())
    variants = list(event.type_variants or ())
    return {
        'key': event.key, 'name': event.name, 'url': event.url,
        'type': event.type, 'type_slug': event.type_slug, 'type_label': event.type_label,
        'summary': event.summary, 'summary_zh': event.summary_zh,
        'first': event.first_version, 'last': event.last_version,
        'removed': bool(removed_in), 'removed_in': removed_in,
        'aliases': aliases, 'type_variants': variants,
        'has_dossier': event.has_dossier,
        'change_count': len(event.changed_in), 'last_change': event.changed_in[-1]
        if event.changed_in else '',
        'strip': strip_of(event, order, changed, removed_in),
        'present_tokens': ' '.join(event.present_in),
        'text': ' '.join([event.name, event.type, event.type_label, event.summary_zh,
                          event.summary] + aliases + variants),
    }


def groups_of(rows, latest=''):
    groups = []
    for meta in TYPE_META:
        members = [row for row in rows if row['type'] == meta['type']]
        if not members:
            continue
        groups.append(dict(meta, count=len(members), rows=members,
                           count_latest=sum(1 for row in members
                                            if latest in row['present_tokens'].split())))
    return groups


def filters_of(rows, order):
    """筛选下拉。计数就地算，不再查库。"""
    def options(values):
        counts = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return counts

    types = options(row['type'] for row in rows)
    present = options(major for row in rows for major in row['present_tokens'].split())
    first = options(row['first'] for row in rows if row['first'])
    labels = {version['major']: version['label'] for version in order}
    live = [version for version in order if version['has_wait_events']]
    return [
        {'param': 'type', 'label': '类型',
         'options': [{'value': meta['type'], 'label': meta['label'], 'count': types[meta['type']]}
                     for meta in TYPE_META if types.get(meta['type'])]},
        {'param': 'present', 'label': '存在于版本',
         'options': [{'value': version['major'], 'label': labels[version['major']],
                      'count': present[version['major']]}
                     for version in reversed(live) if present.get(version['major'])]},
        {'param': 'first', 'label': '引入版本',
         'options': [{'value': version['major'], 'label': labels[version['major']],
                      'count': first[version['major']]}
                     for version in reversed(live) if first.get(version['major'])]},
    ]


def index_payload():
    order = versions()
    events = list(WaitEvent.objects.defer(*DEFER))
    rows = [row_of(event, order) for event in events]
    live = live_versions(order)
    latest = live[-1]['major'] if live else ''
    groups = groups_of(rows, latest)
    return {
        'total': len(rows), 'type_count': len(groups),
        'default_major': default_major(),
        'earliest_major': live[0]['major'] if live else '',
        'latest_major': latest, 'na_majors': na_majors(order),
        'versions': order, 'groups': groups, 'filters': filters_of(rows, order),
        'stats': {'events': len(rows), 'types': len(groups),
                  # 每个事件在库里存一份快照/版本，present_in 就是快照数。
                  'snapshots': sum(len(event.present_in) for event in events),
                  'changes': sum(len(event.changed_in) for event in events),
                  'dossiers': sum(1 for event in events if event.has_dossier)},
    }


def index():
    payload = cache.get(CACHE_KEY)
    if payload is None:
        payload = index_payload()
        cache.set(CACHE_KEY, payload, CACHE_SECONDS)
    return payload


def sibling_groups(type_label, current=''):
    """页尾复用索引表：只留本类型那一组。"""
    return [dict(group, current=current) for group in index()['groups']
            if group['type'] == type_label]


def type_nav(current=''):
    """「等待事件」下的九个类型，侧栏导航用。"""
    return [{'title': group['label'], 'link': ROOT + '#' + group['anchor'],
             'active': group['type_slug'] == current} for group in index()['groups']]


# ---------------------------------------------------------------- 查找

def lookup(type_slug, name):
    """按 (类型, 名称) 找事件，返回 `(event, 规范地址 or None)`。

    四级：精确 → 不分大小写 → 图谱 slug → 曾用名。命中非规范形式时给出规范地址供 301。
    类型不在九个规范 slug 里，或者怎么找都找不到，返回 `(None, None)`。
    """
    slug = (type_slug or '').lower()
    if slug not in TYPE_BY_SLUG:
        return None, None
    name = name or ''
    event = WaitEvent.objects.filter(type_slug=slug, name=name).first()
    if event is None:
        event = WaitEvent.objects.filter(type_slug=slug, name__iexact=name).first()
    if event is None:
        event = WaitEvent.objects.filter(type_slug=slug, slug__iexact=name).first()
    if event is None:
        event = WaitEvent.objects.filter(type_slug=slug, aliases__contains=[name]).first()
    if event is None:
        # 曾用名的大小写也认：一个类型最多百来个事件，扫一遍比再建一张表划算。
        folded = name.casefold()
        for candidate in WaitEvent.objects.filter(type_slug=slug).only(
                'key', 'type', 'type_slug', 'name', 'aliases'):
            if any(alias.casefold() == folded for alias in candidate.aliases or ()):
                event = candidate
                break
    if event is None:
        return None, None
    if type_slug != event.type_slug or name != event.name:
        return event, event.url
    return event, None


# ---------------------------------------------------------------- 详情页

def previous_major(event, major):
    """按 present_in 顺序的上一版；首版返回 ''。"""
    present = event.present_in
    if major not in present:
        return ''
    index = present.index(major)
    return present[index - 1] if index else ''


def change_at(event, major):
    """落在本版的变化记录（不含「移除」，移除记在下一版）。"""
    return next((change for change in event.changes
                 if change['to'] == major and change['status'] != 'removed'), None)


def change_note(event, major, order, change):
    """本版变化一句话。9.6 是机制起点，照实说「引入」。"""
    live = live_versions(order)
    baseline = live[0]['major'] if live else ''
    if major == event.first_version and major == baseline:
        return FIRST_VERSION_NOTE.format(baseline)
    previous = previous_major(event, major)
    if change is None:
        return '相对 PostgreSQL {} 无变化。'.format(previous) if previous else ''
    if change['status'] == 'added':
        return 'PostgreSQL {} 新增此等待事件。'.format(major)
    clauses = []
    if change.get('renamed'):
        clauses.append('由 {} 更名为 {}'.format(change['renamed']['from'], change['renamed']['to']))
    if change.get('moved'):
        clauses.append('类型由 {} 改为 {}'.format(change['moved']['from'], change['moved']['to']))
    if change.get('reworded'):
        clauses.append('描述措辞更新')
    if not clauses:
        return '相对 PostgreSQL {} 无变化。'.format(change['from'] or previous)
    return 'PostgreSQL {}：{}。'.format(major, '，'.join(clauses))


def ribbon_of(event, major, order, changed, removed_in, pages=None):
    cells = strip_of(event, order, changed, removed_in)
    by_major = {version['major']: version for version in order}
    for cell in cells:
        snapshot = event.versions.get(cell['major'])
        cell['current'] = cell['major'] == major
        cell['doc_url'] = doc_url(snapshot, pages) if snapshot else ''
        cell['status'] = by_major[cell['major']]['status']
    return cells


def runs_of(event, order, major=''):
    """各版本描述分段：相邻且（类型、名称、归一后英文）都相同的版本并成一段，旧在前。"""
    majors = [version['major'] for version in order]
    segments = []
    previous_index = None
    for major in event.present_in:
        snapshot = event.versions.get(major) or {}
        signature = (snapshot.get('type', ''), snapshot.get('name', ''),
                     normal_text(snapshot.get('description', '')))
        index = majors.index(major) if major in majors else None
        adjacent = (segments and previous_index is not None and index is not None
                    and index == previous_index + 1 and segments[-1]['signature'] == signature)
        if adjacent:
            segments[-1]['majors'].append(major)
            segments[-1]['snapshots'].append(snapshot)
        else:
            segments.append({'signature': signature, 'majors': [major], 'snapshots': [snapshot]})
        previous_index = index
    runs = []
    for segment in segments:
        newest = segment['snapshots'][-1]
        description_zh = next((snapshot.get('description_zh', '')
                               for snapshot in reversed(segment['snapshots'])
                               if snapshot.get('description_zh')), '')
        zh_from = next((snapshot.get('zh_from', '') for snapshot in reversed(segment['snapshots'])
                        if snapshot.get('description_zh')), '')
        runs.append({
            'majors': segment['majors'], 'first': segment['majors'][0],
            'last': segment['majors'][-1], 'type': newest.get('type', ''),
            'name': newest.get('name', ''), 'description': newest.get('description', ''),
            'description_zh': description_zh, 'zh_from': zh_from,
            'renamed': newest.get('name', '') != event.name,
            'moved': newest.get('type', '') != event.type,
            'current': major in segment['majors'],
        })
    return runs


def source_rows(dossier):
    """源码证据，新版本在前；每组里目录定义排最后。"""
    groups, order = {}, []
    for record in dossier.get('source_locations') or ():
        major = str(record.get('major', '') or record.get('version', '') or '')
        if major not in groups:
            groups[major] = {'major': major, 'tag': record.get('tag', ''), 'rows': []}
            order.append(major)
        path, line = record.get('path', ''), record.get('line', '')
        groups[major]['rows'].append({
            'path': path, 'line': line,
            'path_line': '{}:{}'.format(path, line) if path and line else path,
            'symbol': record.get('symbol', ''), 'kind': record.get('kind', ''),
            'kind_label': RECORD_KIND_LABEL.get(record.get('kind', ''), record.get('kind', '')),
            'status': record.get('status', ''),
            'status_label': SOURCE_STATUS_LABEL.get(record.get('status', ''),
                                                    record.get('status', '')),
            'excerpt': record.get('excerpt', ''), 'url': record.get('url', ''),
            'commit': record.get('commit', ''), 'commit_short': (record.get('commit') or '')[:9],
        })
    for major in order:
        groups[major]['rows'].sort(key=lambda row: KIND_RANK.get(row['kind'], 9))
    ranked = sorted(order, key=lambda major: version_position(major), reverse=True)
    return [groups[major] for major in ranked]


def version_position(major):
    return next((version['position'] for version in versions() if version['major'] == major), -1)


def named(items):
    """图谱里的参数/指标清单：字符串与 {name: …} 两种写法都收。"""
    rows = []
    for item in items or ():
        if isinstance(item, dict):
            name = item.get('name', '') or item.get('guc', '') or item.get('metric', '')
            if name:
                rows.append(dict(item, name=name))
        elif item:
            rows.append({'name': str(item)})
    return rows


CODE_SPAN = re.compile(r'`([^`\n]+)`')


def inline_code(text):
    """图谱正文里的 `标识符` 是 Markdown 写法：先转义，再把成对反引号换成行内等宽。

    只认同一段文字里成对的反引号；没有反引号的文字只是转义后原样返回。
    """
    if not text:
        return ''
    parts = CODE_SPAN.split(text)
    return mark_safe(''.join(
        '<code class="we-mono">{}</code>'.format(escape(part)) if index % 2 else escape(part)
        for index, part in enumerate(parts)))


def bilingual(block):
    block = block or {}
    return {'zh': inline_code(block.get('zh', '')), 'en': inline_code(block.get('en', ''))}


def dossier_of(event):
    """图谱档案原样带出，再补几个模板直接能用的派生字段（不改原键）。"""
    raw = event.dossier or {}
    if not raw:
        return {}
    data = dict(raw)
    data['kind_label'] = RECORD_KIND_LABEL.get(raw.get('record_kind', ''), raw.get('record_kind', ''))
    data['status_label'] = SOURCE_STATUS_LABEL.get(raw.get('source_status', ''),
                                                   raw.get('source_status', ''))
    data['sources_by_major'] = source_rows(raw)
    emission = raw.get('emission') or {}
    data['emission_reason'] = emission.get('reason', '')
    data['emission_note'] = ''
    if emission.get('status') and emission['status'] != 'active':
        data['emission_note'] = '已编目但未见上报。'
    data['emission_evidence'] = emission.get('evidence', '')
    availability = raw.get('availability') or {}
    data['availability_note'] = availability.get('zh', '') or availability.get('en', '')
    data['observed_releases'] = availability.get('observed_releases') or []
    data['not_observed'] = availability.get('not_observed') or []
    for key in ('mechanism', 'normal', 'trouble', 'incident_pattern'):
        data[key] = bilingual(raw.get(key))
    data['availability_note'] = inline_code(data['availability_note'])
    data['actions_zh'] = [inline_code(step) for step in (raw.get('actions') or {}).get('zh') or ()]
    data['actions_en'] = [inline_code(step) for step in (raw.get('actions') or {}).get('en') or ()]
    data['sql'] = [{
        'id': item.get('id', ''), 'title': item.get('title', ''),
        'title_zh': item.get('title_zh', '') or item.get('title', ''),
        'min_version': item.get('min_version', ''), 'sql': item.get('sql', ''),
        'dom_id': 'we-sql-{}'.format(item.get('id', '') or index),
    } for index, item in enumerate(raw.get('diagnostic_sql') or ())]
    gucs = named(raw.get('gucs'))
    links = guc_links([row['name'] for row in gucs])
    data['gucs'] = [dict(row, url=links.get(row['name'], '')) for row in gucs]
    data['metrics'] = named(raw.get('metrics'))
    slug = event.slug or event.name.lower()
    data['wait_url'] = '{}{}/{}/'.format(ATLAS, event.type_slug, slug)
    return data


def facts_of(event, major, snapshot, order, dossier, local_doc):
    live = live_versions(order)
    baseline = live[0]['major'] if live else ''
    first = event.first_version
    rows = [('类型', event.type_label, ROOT + '#type-' + event.type_slug),
            ('引入版本', '{}（机制起点）'.format(first) if first == baseline else first, '')]
    version = version_map().get(major)
    if version:
        rows.append(('版本状态', version['status_label'], version['url']))
    rows.append(('覆盖版本', '{} 个 · {} – {}'.format(len(event.present_in), first,
                                                      event.last_version) if first else '', ''))
    if dossier:
        rows.append(('触发路径', dossier.get('status_label', ''), ''))
        verified = (dossier.get('emission') or {}).get('verified_release', '')
        if verified:
            rows.append(('实测发行版', str(verified), ''))
    names = []
    if event.aliases:
        names.append('曾用名 ' + '、'.join(event.aliases))
    if event.type_variants:
        names.append('曾属 ' + '、'.join(event.type_variants))
    rows.append(('名称变动', ' · '.join(names) or '无', ''))
    if local_doc:
        rows.append(('手册章节', '监控统计', local_doc))
    return [{'label': label, 'value': value, 'url': url} for label, value, url in rows if value]


def timeline_of(event):
    """演化历史，新的在前。"""
    rows = []
    for change in reversed(event.changes):
        target = event.versions.get(change['to']) or {}
        rows.append({
            'to': change['to'], 'from': change['from'], 'status': change['status'],
            'url': '{}?v={}'.format(event.url, change['to'])
            if change['to'] in event.present_in else '',
            'renamed': change.get('renamed'), 'moved': change.get('moved'),
            'reworded': change.get('reworded'),
            'description_zh_to': target.get('description_zh', ''),
        })
    return rows


def notice_of(version):
    if version and version['preview']:
        return PREVIEW_NOTICE.format(version['label'])
    if version and version['devel']:
        return DEVEL_NOTICE.format(version['label'])
    return ''


def detail(type_slug, name, wanted=''):
    """一个等待事件的详情页上下文。

    命中非规范地址时只返回 `{'canonical': 规范地址, 'event': …}`，视图据此 301；
    找不到事件抛 `WaitEvent.DoesNotExist`。
    """
    event, canonical = lookup(type_slug, name)
    if event is None:
        raise WaitEvent.DoesNotExist('{}/{}'.format(type_slug, name))
    if canonical:
        return {'canonical': canonical, 'event': event}
    return dict(detail_payload(event, wanted), canonical='')


def detail_payload(event, wanted=''):
    order = versions()
    major = pick_major(wanted, event.present_in, order)
    if not major:
        raise WaitEvent.DoesNotExist(event.key)
    snapshot = event.versions[major]
    # 手册页清单一次读到底：下面的版本条与链接要问它十几次。
    pages = doc_pages()
    version = version_map().get(major)
    change = change_at(event, major)
    dossier = dossier_of(event)
    local_doc = doc_url(snapshot, pages)
    doc_versions = []
    for item in order:
        if item['major'] not in event.present_in:
            continue
        url = doc_url(event.versions.get(item['major']), pages)
        if url:
            doc_versions.append({'major': item['major'], 'label': item['label'], 'url': url})
    definition = next((row['url'] for group in dossier.get('sources_by_major') or ()
                       for row in group['rows']
                       if row['kind'] == 'catalog_definition' and row['url']), '')
    source = next((row['url'] for group in dossier.get('sources_by_major') or ()
                   for row in group['rows'] if row['kind'] == 'trigger' and row['url']),
                  definition)
    siblings = sibling_groups(event.type, event.key)
    return {
        'event': event, 'name': event.name, 'type': event.type, 'type_slug': event.type_slug,
        'type_label': event.type_label, 'eyebrow': event.eyebrow, 'blurb': event.blurb,
        'version': version, 'previous_major': previous_major(event, major), 'snapshot': snapshot,
        'description': snapshot.get('description', ''),
        'description_zh': snapshot.get('description_zh', ''),
        'zh_from': snapshot.get('zh_from', ''),
        'change': change, 'change_note': change_note(event, major, order, change),
        'ribbon': ribbon_of(event, major, order, set(event.changed_in),
                            removed_after(event, order), pages),
        'runs': runs_of(event, order, major),
        'links': {
            'doc': local_doc,
            'doc_label': 'PostgreSQL {} 手册'.format(
                (version or {}).get('label') or major) if local_doc else '',
            'official': upstream_url(snapshot),
            'definition': definition, 'source': source,
            'atlas': dossier.get('wait_url', ATLAS),
        },
        'facts': facts_of(event, major, snapshot, order, dossier, local_doc),
        'dossier': dossier, 'has_dossier': bool(dossier),
        'timeline': timeline_of(event),
        'siblings': siblings, 'sibling_groups': siblings,
        'doc_versions': doc_versions,
        'notice': notice_of(version),
        'versions': order,
    }


# ---------------------------------------------------------------- 变更页

def compare(left, right):
    """两份快照现算一条变化记录，供非相邻比较用。"""
    return compare_snapshots(left or {}, right or {}, '', '')


def card_of(event, major, base, change):
    present = set(event.present_in)
    if major in present:
        url = '{}?v={}'.format(event.url, major)
    elif base in present:
        url = '{}?v={}'.format(event.url, base)
    else:
        url = event.url
    renamed, moved, reworded = (change.get('renamed') or {}, change.get('moved') or {},
                                change.get('reworded') or {})
    return {
        'key': event.key, 'name': event.name, 'url': url,
        'type': event.type, 'type_slug': event.type_slug, 'type_label': event.type_label,
        'summary_zh': event.summary_zh, 'summary': event.summary,
        'status': change['status'], 'has_dossier': event.has_dossier,
        'from_name': renamed.get('from', ''), 'to_name': renamed.get('to', ''),
        'from_type': moved.get('from', ''), 'to_type': moved.get('to', ''),
        'from_text': reworded.get('from', ''), 'to_text': reworded.get('to', ''),
    }


def cards_by_type(cards):
    """卡片按九个规范类型分组，空组不出现。"""
    groups = []
    for meta in TYPE_META:
        members = [card for card in cards if card['type'] == meta['type']]
        if members:
            groups.append({'type': meta['type'], 'type_slug': meta['type_slug'],
                           'type_label': meta['label'], 'cards': members})
    return groups


def changes(major, from_major=''):
    """一个版本相对上一版（或 ?from= 指定的基准）的变更页上下文。

    相邻比较是默认入口，和索引页一样缓存 5 分钟；`?from=` 的非相邻比较现算不缓存。
    """
    if not from_major:
        payload = cache.get(CHANGES_CACHE_KEY.format(major))
        if payload is None:
            payload = changes_payload(major)
            cache.set(CHANGES_CACHE_KEY.format(major), payload, CACHE_SECONDS)
        return payload
    return changes_payload(major, from_major)


def changes_payload(major, from_major=''):
    order = versions()
    by_major = {version['major']: version for version in order}
    if major not in by_major:
        raise WaitEventVersion.DoesNotExist(major)
    version = by_major[major]
    live = live_versions(order)
    first_major = live[0]['major'] if live else ''
    empty = {'version': version, 'previous': None, 'from_major': '', 'arbitrary': False,
             'versions': [dict(item, is_current=item['major'] == major) for item in order],
             'summary': {'added': 0, 'removed': 0, 'renamed': 0, 'moved': 0, 'reworded': 0,
                         'total': 0, 'types': 0},
             'added': [], 'removed': [], 'renamed': [], 'moved': [], 'reworded': [],
             'baseline': False, 'baseline_groups': [], 'na': False, 'na_note': '',
             'first_url': '/docs/waitevent/changes/{}/'.format(first_major) if first_major else '',
             'notice': notice_of(version), 'baseline_note': ''}
    if not version['has_wait_events']:
        # 9.0 – 9.5：页面只放一段说明，并链到 9.6。
        return dict(empty, na=True, na_note=NA_NOTE)

    majors = [item['major'] for item in live]
    index = majors.index(major)
    natural = majors[index - 1] if index else ''
    if from_major not in majors or from_major == major:
        from_major = ''
    base = from_major or natural
    arbitrary = bool(from_major) and from_major != natural
    # 相邻比较只读变化记录；基线页与 ?from= 的任意两版比较才需要逐版本快照。
    heavy = arbitrary or not base
    events = list(WaitEvent.objects.defer('dossier') if heavy
                  else WaitEvent.objects.defer('dossier', 'versions'))

    if not base:
        # 9.6 是机制起点，没有上一版可比：列出该版全部事件。
        rows = []
        for event in events:
            if major not in event.present_in:
                continue
            snapshot = event.versions.get(major) or {}
            rows.append(dict(row_of(event, order), name_at=snapshot.get('name', event.name),
                             type_at=snapshot.get('type', event.type)))
        return dict(empty, baseline=True, baseline_groups=groups_of(rows, majors[-1]),
                    baseline_note=BASELINE_NOTE.format(major),
                    summary=dict(empty['summary'], added=len(rows), total=len(rows),
                                 types=len({row['type'] for row in rows})))

    added, removed, renamed, moved, reworded = [], [], [], [], []
    touched, types = set(), set()
    for event in events:
        if arbitrary:
            left = event.versions.get(base) or {}
            right = event.versions.get(major) or {}
            if not left and not right:
                continue
            change = compare_snapshots(left, right, base, major)
        else:
            change = next((item for item in event.changes
                           if item['to'] == major and item['from'] == base), None)
        if change is None:
            continue
        card = card_of(event, major, base, change)
        touched.add(event.key)
        types.add(event.type)
        if change['status'] == 'added':
            added.append(card)
        elif change['status'] == 'removed':
            removed.append(card)
        else:
            if change.get('renamed'):
                renamed.append(card)
            if change.get('moved'):
                moved.append(card)
            if change.get('reworded'):
                reworded.append(card)
    return dict(
        empty, previous=by_major.get(base), from_major=from_major, arbitrary=arbitrary,
        summary={'added': len(added), 'removed': len(removed), 'renamed': len(renamed),
                 'moved': len(moved), 'reworded': len(reworded), 'total': len(touched),
                 'types': len(types)},
        added=cards_by_type(added), removed=cards_by_type(removed),
        renamed=cards_by_type(renamed), moved=cards_by_type(moved),
        reworded=cards_by_type(reworded))
