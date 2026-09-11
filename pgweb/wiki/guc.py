"""配置参数栏目的取数与组装。视图只负责拼上下文，这里负责形状。

前端模板按本文件给出的键名渲染，改键名等于改契约（`docs/guc-column.md` §4）。
版本次序一律取 `GucVersion.position`：'9.0' 与 '10' 字符串比不出先后。

索引页与变更页都不把 `versions` 整列取回来（447 个参数乘 18 版手册译文不小），
只让 Postgres 把要用的那一两份快照抽出来，并就地去掉最大的 `doc_html`。
"""

import re

from django.core.cache import cache
from django.db.models import JSONField, Q
from django.db.models.expressions import RawSQL

from .guc_common import diff_fields, human_value, is_default_change, is_substantive
from .models import (GUC_CATEGORY_ORDER, GUC_CONTEXT_LABEL, GUC_CONTEXT_NOTE, GUC_CONTEXTS,
                     GUC_FIELD_LABEL, GUC_FIELDS, GUC_GROUP_LABEL, GUC_GROUPS,
                     GUC_SUBSTANTIVE_FIELDS, GUC_VARTYPE_LABEL, GucParameter, GucVersion)


CACHE_KEY = 'pgweb:wiki:guc-index'
VERSION_CACHE_KEY = 'pgweb:wiki:guc-versions'
DOC_CACHE_KEY = 'pgweb:wiki:guc-docpages'
CHANGES_CACHE_KEY = 'pgweb:wiki:guc-changes:{}'
CACHE_SECONDS = 300

ROOT = '/docs/guc/'

# 索引页与变更页不取这几列：整份 JSON 比页面用到的多两个数量级。
DEFER = ('versions', 'changes', 'default_history', 'docs', 'editorial', 'intro_commit')
# 行上显示的事实取默认版本的快照，默认版本没有这个参数时取它最后存在的版本。
ROW_SNAPSHOT_SQL = "coalesce(versions -> %s::text, versions -> last_version) - 'doc_html'::text"
ONE_SNAPSHOT_SQL = "(versions -> %s::text) - 'doc_html'::text"

# 逐版本快照矩阵的七列：默认值、单位与五项属性。
MATRIX_FIELDS = ('boot_val', 'unit', 'context', 'vartype', 'min_val', 'max_val', 'enumvals')

# 9.0 是收录基线，不代表这些参数首次于那一版引入。所有「引入」字样照此措辞。
BASELINE_TEMPLATE = '{0} 是本数据集的收录基线，不代表该参数首次于 {0} 引入。'
PREVIEW_NOTICE = '19 beta 3 为预发行快照，正式发布前仍可能变化。'
DEVEL_NOTICE = '20 开发版尚未定稿：pg_settings 事实沿用 19，说明取自本站 devel 手册。'
CARRIED_TEMPLATE = 'PostgreSQL {} 开发版沿用 {} 的 pg_settings 事实，说明取自 devel 手册。'

STATE_LABEL = {'absent': '不存在', 'present': '存在', 'added': '新增', 'removed': '移除',
               'changed': '变更'}
CHANGED_LABEL = {'default': '默认值变更', 'attribute': '属性变更', 'mixed': '变更'}


# ---------------------------------------------------------------- 版本

def baseline_note(order=None):
    order = order if order is not None else versions()
    return BASELINE_TEMPLATE.format(order[0]['major']) if order else ''


def version_data(version, is_default=False):
    return {
        'major': version.major, 'label': version.label or version.major,
        'status': version.status, 'status_label': version.status_label,
        'support_status': version.support_status,
        'parameter_count': version.parameter_count, 'added_count': version.added_count,
        'removed_count': version.removed_count,
        'default_changed_count': version.default_changed_count,
        'changed_count': version.changed_count, 'reworded_count': version.reworded_count,
        'position': version.position, 'doc_slug': version.doc_slug,
        'server_version': version.server_version, 'schema_source': version.schema_source,
        'url': version.changes_url, 'preview': version.is_preview, 'devel': version.is_devel,
        'is_default': is_default,
    }


def versions():
    """全部版本，按 position。第一项是最早的 9.0，最后一项是 20 devel。"""
    rows = cache.get(VERSION_CACHE_KEY)
    if rows is None:
        stored = list(GucVersion.objects.all())
        default = stable_major(stored)
        rows = [version_data(version, version.major == default) for version in stored]
        cache.set(VERSION_CACHE_KEY, rows, CACHE_SECONDS)
    return rows


def stable_major(stored):
    """默认版本是 status='stable' 的那一版（当前 18），没有就取最后一个正式版。

    只有 `versions()` 建缓存时算一次，算完就记在版本条的 `is_default` 上。
    """
    for version in stored:
        if version.status == 'stable':
            return version.major
    formal = [v for v in stored if v.status not in ('preview', 'devel')]
    return (formal or stored)[-1].major if stored else ''


def default_major():
    """默认版本。取版本条上已经标好的 `is_default`，不再查库。"""
    order = versions()
    return next((v['major'] for v in order if v['is_default']),
                order[-1]['major'] if order else '')


def version_map():
    return {version['major']: version for version in versions()}


def pick_major(wanted, present, order=None):
    """无效或缺席的 ?v= 落回默认版本；默认版本这个参数也没有时取它最后存在的版本。"""
    if wanted and wanted in present:
        return wanted
    order = order if order is not None else versions()
    default = next((v['major'] for v in order if v['is_default']), '')
    if default in present:
        return default
    return present[-1] if present else ''


# ---------------------------------------------------------------- 手册链接

# 配置参数的手册坐标只落在第 19 章那十七页上（导入时也只在这些页里找锚点），
# 所以缓存只装这些页，不把上万条手册页面都拉进内存。
DOC_FILE_PREFIX = 'runtime-config'


def doc_pages():
    """本站手册里已收录的 (版本段, 文件名) → 页面标题。缓存 5 分钟。"""
    pages = cache.get(DOC_CACHE_KEY)
    if pages is None:
        from pgweb.docs.models import DocPage
        pages = {}
        for tree, filename, title in (DocPage.objects.filter(file__startswith=DOC_FILE_PREFIX)
                                      .values_list('version', 'file', 'title')):
            slug = 'devel' if int(tree) == 0 else str(int(tree))
            pages[(slug, filename)] = title or ''
        cache.set(DOC_CACHE_KEY, pages, CACHE_SECONDS)
    return pages


def doc_url(snapshot, pages=None):
    """本站手册该版该页的地址；没收录就留空，不给死链。

    `pages` 是 `doc_pages()` 的结果。一个详情页要问几十次，调用方读一次传进来。
    """
    doc = (snapshot or {}).get('doc') or {}
    slug, filename, anchor = doc.get('slug', ''), doc.get('file', ''), doc.get('anchor', '')
    pages = doc_pages() if pages is None else pages
    if not slug or not filename or (slug, filename) not in pages:
        return ''
    return '/docs/{}/{}{}'.format(slug, filename, '#' + anchor if anchor else '')


# 手册页标题是 '19.5.1. 设置'，链接文字里那个小数点后的句点多余。
SECTION_NUMBER = re.compile(r'^(\d[\d.]*)\.\s+')


def doc_title(snapshot, pages=None):
    doc = (snapshot or {}).get('doc') or {}
    pages = doc_pages() if pages is None else pages
    title = pages.get((doc.get('slug', ''), doc.get('file', '')), '')
    return SECTION_NUMBER.sub(r'\1 ', title).strip()


def forget():
    cache.delete(CACHE_KEY)
    cache.delete(VERSION_CACHE_KEY)
    cache.delete(DOC_CACHE_KEY)
    # 变更页按版本各缓存一份；版本表刚写过，照库里现有的版本清。
    cache.delete_many([CHANGES_CACHE_KEY.format(major) for major
                       in GucVersion.objects.values_list('major', flat=True)])


# ---------------------------------------------------------------- 取值的显示形式

def render_value(field, value, unit=''):
    """一个字段值的显示形式：枚举值拼成一行，空值说清楚是哪一种空。"""
    if field == 'enumvals':
        return ', '.join(value) if value else '—'
    if field == 'context':
        return GUC_CONTEXT_LABEL.get(value, value or '—')
    if field == 'vartype':
        return GUC_VARTYPE_LABEL.get(value, value or '—')
    if field == 'boot_val':
        return human_value(value, unit)
    if value is None:
        return '—'
    if value == '':
        return '空'
    return str(value)


def raw_value(field, value):
    """变化芯片上的取值：枚举值保持列表交给模板拼，上下文与类型换成中文标签，其余原样。

    保留 None 与 '' 是有意的：模板用 `|default:` 把空值写成「（无）」。
    """
    if field == 'enumvals':
        return list(value or ())
    if field == 'context':
        return GUC_CONTEXT_LABEL.get(value, value)
    if field == 'vartype':
        return GUC_VARTYPE_LABEL.get(value, value)
    return value


def human_of(snapshot):
    """快照里的默认值可读形式，照写不改。

    导入器把「没采集到」写成空串（20 开发版的新参数只有手册，没有 pg_settings
    事实），把「真的没有默认值」写成「未设置」。这两件事不是一回事，所以有 human
    这个键时一律照用，只有整个键缺席才现算。
    """
    if 'human' in snapshot:
        return snapshot['human']
    return human_value(snapshot.get('boot_val'), snapshot.get('unit') or '')


def snapshot_value(field, snapshot):
    """矩阵与变更页里一格的显示值：默认值换算成人类可读形式。"""
    if field == 'boot_val':
        return human_of(snapshot)
    return render_value(field, snapshot.get(field), snapshot.get('unit') or '')


def default_side(snapshot):
    """默认值变迁的一侧：原值、单位与人类可读形式。"""
    snapshot = snapshot or {}
    return {'boot_val': snapshot.get('boot_val'), 'unit': snapshot.get('unit') or '',
            'human': human_of(snapshot)}


# ---------------------------------------------------------------- 分类与分组

def category_tail(category):
    _, sep, tail = (category or '').partition(' / ')
    return tail if sep else ''


def category_anchor(group_slug, category):
    """子分类锚点：'Write-Ahead Log / Settings' → 'cat-wal-settings'。"""
    tail = category_tail(category)
    if not tail:
        return 'cat-' + group_slug
    slug = ''.join(c if c.isalnum() else '-' for c in tail.lower())
    while '--' in slug:
        slug = slug.replace('--', '-')
    return 'cat-{}-{}'.format(group_slug, slug.strip('-'))


def category_label(category_zh, group_label):
    """子分类显示名：去掉一级分类前缀；一级分类本身就是子分类时留空。"""
    _, sep, tail = (category_zh or '').partition(' / ')
    if sep:
        return tail
    return '' if category_zh == group_label else (category_zh or '')


# ---------------------------------------------------------------- 索引页

def states_of(parameter, order):
    """逐版本的生命线状态，未合段。"""
    present = set(parameter.present_in)
    changed = set(parameter.changed_in)
    removed_in = removed_after(parameter, order)
    first = parameter.first_version
    baseline = order[0]['major'] if order else ''
    states = []
    for version in order:
        major = version['major']
        if major == removed_in:
            state = 'removed'
        elif major not in present:
            state = 'absent'
        elif major == first and major != baseline:
            state = 'added'
        elif major in changed:
            state = 'changed'
        else:
            state = 'present'
        states.append((major, state))
    return states


def removed_after(parameter, order):
    """移除标在 last_version 的下一版；还在最后一版里就没有移除版本。"""
    majors = [version['major'] for version in order]
    if not parameter.last_version or parameter.last_version not in majors:
        return ''
    index = majors.index(parameter.last_version)
    return majors[index + 1] if index + 1 < len(majors) else ''


def segment_label(state, first, last, majors, defaults):
    span = '{} – {}'.format(first, last) if first != last else first
    if state == 'changed':
        marks = {major in defaults for major in majors}
        kind = 'default' if marks == {True} else 'attribute' if marks == {False} else 'mixed'
        return '{} · {}'.format(span, CHANGED_LABEL[kind])
    return '{} · {}'.format(span, STATE_LABEL.get(state, state))


def strip_of(parameter, order):
    """生命线：同状态的连续版本合成一段，各段 span 之和恒等于版本数。"""
    defaults = set(parameter.default_changed_in)
    segments = []
    for major, state in states_of(parameter, order):
        if segments and segments[-1]['state'] == state:
            segments[-1]['to'] = major
            segments[-1]['span'] += 1
            segments[-1]['majors'].append(major)
        else:
            segments.append({'state': state, 'from': major, 'to': major, 'span': 1,
                             'majors': [major]})
    for segment in segments:
        segment['label'] = segment_label(segment['state'], segment['from'], segment['to'],
                                         segment.pop('majors'), defaults)
    return segments


def row_of(parameter, order, snapshot=None):
    """索引表的一行。`snapshot` 是行上显示的那一版事实，缺省退回热字段。"""
    snapshot = snapshot or {}
    removed_in = removed_after(parameter, order)
    vartype = snapshot.get('vartype') or parameter.vartype
    context = snapshot.get('context') or parameter.context
    boot_human = human_of(snapshot) if snapshot else parameter.boot_human
    changed_in = list(parameter.changed_in)
    return {
        'name': parameter.name, 'url': parameter.url,
        'group_slug': parameter.group_slug, 'group': parameter.group,
        'category': parameter.category, 'category_zh': parameter.category_zh,
        'vartype': vartype, 'vartype_label': GUC_VARTYPE_LABEL.get(vartype, vartype),
        'context': context, 'context_label': GUC_CONTEXT_LABEL.get(context, context),
        'context_note': GUC_CONTEXT_NOTE.get(context, ''),
        'boot_human': boot_human,
        'boot_val': snapshot.get('boot_val', parameter.boot_val),
        'unit': snapshot.get('unit', parameter.unit) or '',
        'short_desc': parameter.short_desc, 'short_desc_zh': parameter.short_desc_zh,
        'first': parameter.first_version, 'last': parameter.last_version,
        'baseline': bool(parameter.baseline),
        'removed': bool(removed_in), 'removed_in': removed_in,
        'change_count': len(changed_in),
        'default_change_count': len(parameter.default_changed_in),
        'last_change': changed_in[-1] if changed_in else '',
        'strip': strip_of(parameter, order),
        'present_tokens': ' '.join(parameter.present_in),
        'text': ' '.join(v for v in (parameter.name, parameter.short_desc_zh,
                                     parameter.short_desc, parameter.category_zh) if v),
    }


def groups_of(rows):
    """一级分类 → 子分类 → 行。分类次序按 GUC_GROUPS 与 GUC_CATEGORY_ORDER。"""
    by_slug = {}
    for row in rows:
        by_slug.setdefault(row['group_slug'], []).append(row)
    groups = []
    for group, label, slug in GUC_GROUPS:
        members = by_slug.pop(slug, [])
        if not members:
            continue
        groups.append(group_of(slug, group, label, members))
    # 分类表里没有的一级分类（导入了新数据而常量表还没跟上）排在最后，不丢参数。
    for slug, members in by_slug.items():
        group = members[0]['group']
        groups.append(group_of(slug, group, GUC_GROUP_LABEL.get(group, group), members))
    return groups


def group_of(slug, group, label, members):
    buckets = {}
    for row in members:
        buckets.setdefault(row['category'], []).append(row)
    subgroups = []
    for category in sorted(buckets, key=lambda c: (GUC_CATEGORY_ORDER.get(c, 10 ** 6), c)):
        rows = buckets[category]
        subgroups.append({
            'category': category, 'label': category_label(rows[0]['category_zh'], label),
            'category_zh': rows[0]['category_zh'],
            'anchor': category_anchor(slug, category), 'count': len(rows), 'rows': rows,
        })
    return {'slug': slug, 'group': group, 'label': label, 'anchor': 'group-' + slug,
            'count': len(members), 'subgroups': subgroups}


def filters_of(rows, order):
    """筛选下拉。计数就地算，不再查库。"""
    def options(values):
        counts = {}
        for value in values:
            if value:
                counts[value] = counts.get(value, 0) + 1
        return counts

    groups = options(row['group_slug'] for row in rows)
    contexts = options(row['context'] for row in rows)
    first = options(row['first'] for row in rows)
    present = options(major for row in rows for major in row['present_tokens'].split())
    labels = {version['major']: version['label'] for version in order}
    return [
        {'param': 'group', 'label': '分类',
         'options': [{'value': slug, 'label': label, 'count': groups[slug]}
                     for _, label, slug in GUC_GROUPS if groups.get(slug)]},
        {'param': 'context', 'label': '上下文',
         'options': [{'value': context, 'label': label, 'count': contexts[context]}
                     for context, label, _ in GUC_CONTEXTS if contexts.get(context)]},
        {'param': 'first', 'label': '引入版本',
         'options': [{'value': version['major'], 'label': labels[version['major']],
                      'count': first[version['major']]}
                     for version in reversed(order) if first.get(version['major'])]},
        {'param': 'present', 'label': '存在于版本',
         'options': [{'value': version['major'], 'label': labels[version['major']],
                      'count': present[version['major']]}
                     for version in reversed(order) if present.get(version['major'])]},
    ]


def index_rows(order):
    """索引表的全部行：JSON 大列留在库里，只把默认版本那一份快照抽出来。"""
    default = default_major()
    queryset = (GucParameter.objects.defer(*DEFER)
                .annotate(snap=RawSQL(ROW_SNAPSHOT_SQL, (default,), output_field=JSONField())))
    return [row_of(parameter, order, parameter.snap) for parameter in queryset]


def index_payload():
    order = versions()
    rows = index_rows(order)
    groups = groups_of(rows)
    totals = GucParameter.objects.values_list('present_in', 'changed_in', 'default_changed_in')
    snapshots = changes_total = default_total = 0
    for present_in, changed_in, default_changed_in in totals:
        snapshots += len(present_in)
        changes_total += len(changed_in)
        default_total += len(default_changed_in)
    return {
        'total': len(rows), 'group_count': len(groups),
        'default_major': default_major(),
        'earliest_major': order[0]['major'] if order else '',
        'latest_major': order[-1]['major'] if order else '',
        'versions': order, 'groups': groups, 'filters': filters_of(rows, order),
        'stats': {'parameters': len(rows), 'versions': len(order), 'snapshots': snapshots,
                  'default_changes': default_total, 'changes': changes_total,
                  'removed': sum(1 for row in rows if row['removed'])},
    }


def index():
    payload = cache.get(CACHE_KEY)
    if payload is None:
        payload = index_payload()
        cache.set(CACHE_KEY, payload, CACHE_SECONDS)
    return payload


def sibling_groups(group_slug, category, current=''):
    """页尾复用索引表：只留本参数所在的那个子分类。"""
    out = []
    for group in index()['groups']:
        if group['slug'] != group_slug:
            continue
        subgroups = [sub for sub in group['subgroups'] if sub['category'] == category]
        if not subgroups:
            continue
        out.append(dict(group, subgroups=subgroups, current=current,
                        count=sum(sub['count'] for sub in subgroups)))
    return out


def group_nav(current=''):
    """「配置参数」下的十六个一级分类，侧栏导航用。"""
    return [{'title': group['label'], 'link': ROOT + '#' + group['anchor'],
             'active': group['slug'] == current} for group in index()['groups']]


# ---------------------------------------------------------------- 详情页

def previous_major(parameter, major):
    """按 present_in 顺序的上一版；首版或缺席返回 ''。"""
    present = parameter.present_in
    if major not in present:
        return ''
    index = present.index(major)
    return present[index - 1] if index else ''


def notice_of(version):
    if version and version['preview']:
        return PREVIEW_NOTICE
    if version and version['devel']:
        return DEVEL_NOTICE
    return ''


def change_at(parameter, major):
    """落在本版的变化记录（移除记在下一版，不算本版的事）。"""
    return next((c for c in parameter.changes
                 if c.get('to') == major and c.get('status') != 'removed'), None)


def change_note(parameter, major, order, change):
    """本版变化一句话，六种措辞见 docs/guc-column.md §4.2。"""
    baseline = order[0]['major'] if order else ''
    if change and change.get('carried'):
        return CARRIED_TEMPLATE.format(major, change.get('from', ''))
    if major == baseline and major in parameter.present_in:
        return baseline_note(order)
    previous = previous_major(parameter, major)
    if change is None:
        return '相对 PostgreSQL {} 无变化。'.format(previous) if previous else ''
    if change.get('status') == 'added':
        return 'PostgreSQL {} 新增此参数。'.format(major)
    fields = change.get('fields') or {}
    if not fields:
        return '相对 PostgreSQL {} 无变化。'.format(change.get('from', previous))
    if not is_substantive(fields):
        return '相对 PostgreSQL {} 仅简述或分类有更新。'.format(change.get('from', previous))
    left = parameter.versions.get(change.get('from', '')) or {}
    right = parameter.versions.get(major) or {}
    written = []
    for field, label in GUC_FIELDS:
        if field not in fields or field not in GUC_SUBSTANTIVE_FIELDS:
            continue
        written.append('{}由 {} 改为 {}'.format(
            label, render_value(field, fields[field].get('from'), left.get('unit') or ''),
            render_value(field, fields[field].get('to'), right.get('unit') or '')))
    return '相对 PostgreSQL {}：{}。'.format(change.get('from', previous), '，'.join(written))


def ribbon_of(parameter, major, order, pages=None):
    """版本条：逐版本一格，不合段。"""
    by_major = version_map()
    cells = []
    for version_major, state in states_of(parameter, order):
        version = by_major.get(version_major, {})
        snapshot = parameter.versions.get(version_major)
        cells.append({
            'major': version_major, 'label': version.get('label', version_major),
            'state': state,
            'url': '{}?v={}'.format(parameter.url, version_major)
            if state not in ('absent', 'removed') else '',
            'current': version_major == major,
            'preview': bool(version.get('preview')), 'devel': bool(version.get('devel')),
            'doc_url': doc_url(snapshot, pages) if snapshot else '',
            'status': version.get('status', ''),
        })
    return cells


def facts_of(parameter, major, snapshot, order, commit):
    facts = []

    def add(label, value, mono=False, note='', url=''):
        if value:
            facts.append({'label': label, 'value': value, 'mono': mono, 'note': note, 'url': url})

    vartype = snapshot.get('vartype') or parameter.vartype
    add('类型', GUC_VARTYPE_LABEL.get(vartype, vartype), note=vartype)
    context = snapshot.get('context') or parameter.context
    add('上下文', GUC_CONTEXT_LABEL.get(context, context), note=GUC_CONTEXT_NOTE.get(context, ''))
    unit = snapshot.get('unit') or ''
    # human 是空串就是没采集到：和上下文、取值范围一样整条不出，不假装有默认值。
    human = human_of(snapshot)
    raw = snapshot.get('boot_val')
    note = ''
    if raw is not None and (unit or str(raw) != human):
        note = '原始值 {}{}'.format(raw if raw != '' else "''", ' ' + unit if unit else '')
    add('默认值', human, mono=True, note=note)
    low, high = snapshot.get('min_val') or '', snapshot.get('max_val') or ''
    if low or high:
        add('取值范围', '{} – {}'.format(low or '—', high or '—'), mono=True)
    add('枚举值', ', '.join(snapshot.get('enumvals') or ()), mono=True)
    category_zh = snapshot.get('category_zh') or parameter.category_zh
    add('分类', category_zh,
        url=ROOT + '#' + category_anchor(parameter.group_slug, parameter.category))
    baseline = order[0]['major'] if order else ''
    first = parameter.first_version
    add('引入版本', '{}（基线）'.format(first) if first == baseline else first,
        url=(commit or {}).get('url', ''))
    removed_in = removed_after(parameter, order)
    add('状态', '于 {} 移除'.format(removed_in) if removed_in else '现存')
    return facts


def default_track_of(parameter, major, order):
    """默认值变迁条。只有一段时也画，表明自收录起未变过。"""
    positions = {version['major']: index for index, version in enumerate(order)}
    current = positions.get(major, -1)
    track = []
    for segment in parameter.default_history or ():
        start, end = segment.get('from', ''), segment.get('to', '')
        low, high = positions.get(start), positions.get(end)
        span = (high - low + 1) if low is not None and high is not None else 1
        unit = segment.get('unit') or ''
        track.append({
            'from': start, 'to': end, 'span': max(span, 1),
            'boot_val': segment.get('boot_val'), 'unit': unit,
            'human': segment.get('human') or human_value(segment.get('boot_val'), unit),
            'current': low is not None and high is not None and low <= current <= high,
        })
    return track


def timeline_of(parameter):
    """演化历史，新的在前。默认值项额外带人类可读形式。"""
    rows = []
    for change in reversed(parameter.changes or ()):
        left = parameter.versions.get(change.get('from', '')) or {}
        right = parameter.versions.get(change.get('to', '')) or {}
        fields = []
        for field, label in GUC_FIELDS:
            item = (change.get('fields') or {}).get(field)
            if item is None:
                continue
            entry = {'field': field, 'label': label,
                     'from': raw_value(field, item.get('from')),
                     'to': raw_value(field, item.get('to')),
                     'from_human': '', 'to_human': ''}
            if field == 'boot_val':
                entry['from_human'] = human_value(item.get('from'), left.get('unit') or '')
                entry['to_human'] = human_value(item.get('to'), right.get('unit') or '')
            fields.append(entry)
        to = change.get('to', '')
        rows.append({
            'to': to, 'from': change.get('from', ''), 'status': change.get('status', ''),
            'url': '{}?v={}'.format(parameter.url, to) if to in parameter.present_in else '',
            'substantive': bool(change.get('substantive')),
            'default_changed': bool(change.get('default_changed')),
            'carried': bool(change.get('carried')), 'fields': fields,
        })
    return rows


def matrix_of(parameter, major, order):
    """逐版本快照矩阵：行 = 版本，列 = 七个字段。`changed` 与上一个存在版本比。"""
    present = [version for version in order if version['major'] in parameter.versions]
    rows, previous = [], None
    for version in present:
        snapshot = parameter.versions.get(version['major']) or {}
        cells = []
        for field in MATRIX_FIELDS:
            changed = previous is not None and _normal(previous.get(field)) != _normal(snapshot.get(field))
            cells.append({'field': field, 'value': snapshot_value(field, snapshot),
                          'changed': changed})
        rows.append({
            'major': version['major'], 'label': version['label'],
            'url': '{}?v={}'.format(parameter.url, version['major']),
            'current': version['major'] == major,
            'carried': bool(snapshot.get('carried_from')), 'cells': cells,
        })
        previous = snapshot
    return {'versions': present,
            'fields': [{'field': field, 'label': GUC_FIELD_LABEL[field]}
                       for field in MATRIX_FIELDS],
            'rows': rows}


def _normal(value):
    return None if value is None or value == '' or value == [] else value


def doc_html_at(parameter, major, seen=None):
    """某一版的手册译文，逐跳解析 doc_same_as 指针。返回 (html, 实际来源版本)。"""
    seen = seen or set()
    current = major
    while current and current not in seen:
        seen.add(current)
        snapshot = parameter.versions.get(current) or {}
        if snapshot.get('doc_html'):
            return snapshot['doc_html'], current
        current = snapshot.get('doc_same_as') or ''
    return '', ''


def doc_of(parameter, major, order, pages):
    """手册说明：本版没有译文时借最近的可用版（9.x 借 10），官方链接仍指本版。"""
    snapshot = parameter.versions.get(major) or {}
    html, source = doc_html_at(parameter, major)
    borrowed = False
    if not html:
        positions = {item['major']: item['position'] for item in order}
        here = positions.get(major, 0)
        candidates = []
        for other in parameter.present_in:
            found, origin = doc_html_at(parameter, other)
            if found:
                candidates.append((abs(positions.get(other, 0) - here),
                                   -positions.get(other, 0), other, found, origin))
        if candidates:
            candidates.sort(key=lambda item: item[:2])
            _, _, _, html, source = candidates[0]
            borrowed = True
    # 链接与标题跟着正在读的这一版走。doc_same_as 只是说译文与更早某版逐字相同，
    # 本站照样有这一版的手册页；只有本站真的没有这一版手册（9.x）才落到借来的那一版。
    local, linked = doc_url(snapshot, pages), major
    if not local and source:
        local, linked = doc_url(parameter.versions.get(source), pages), source
    official = (snapshot.get('doc') or {}).get('url', '') \
        or (parameter.docs.get(major) or {}).get('url', '')
    label = ''
    if local or html:
        linked_label = (version_map().get(linked) or {}).get('label', linked)
        title = doc_title(parameter.versions.get(linked), pages)
        label = 'PostgreSQL {} 手册{}'.format(linked_label, ' · ' + title if title else '')
    return {'html': html, 'major': source, 'borrowed': borrowed, 'local_url': local,
            'official_url': official, 'label': label}


def editorial_of(parameter):
    """编辑分析只取中文那一份；related 解析成本站链接。"""
    editorial = parameter.editorial or {}
    related = []
    names = [name for name in (editorial.get('related') or ()) if name]
    if names:
        known = {row[1]: row for row in GucParameter.objects.filter(
            key__in=[name.lower() for name in names]).values_list('name', 'key', 'short_desc_zh')}
        for name in names:
            row = known.get(name.lower())
            related.append({'name': row[0] if row else name,
                            'url': '/docs/guc/{}/'.format(row[0]) if row else '',
                            'short_desc_zh': row[2] if row else '', 'exists': bool(row)})
    advice = editorial.get('advice_zh') or {}
    return {
        'summary_zh': editorial.get('summary_zh', ''), 'summary': editorial.get('summary', ''),
        'mechanism': list(editorial.get('mechanism_zh') or ()),
        'advice': {'oltp': advice.get('oltp', ''), 'olap': advice.get('olap', ''),
                   'small': advice.get('small', '')},
        'pitfalls': list(editorial.get('pitfalls_zh') or ()),
        'related': related,
        'references': [{'title': item.get('title', ''), 'url': item.get('url', '')}
                       for item in (editorial.get('references_zh') or ())
                       if item.get('url') or item.get('title')],
    }


def intro_commit_of(parameter):
    commit = parameter.intro_commit or {}
    if not commit.get('hash'):
        return None
    return {'hash': commit['hash'], 'short': commit['hash'][:10],
            'date': (commit.get('authored_at') or '')[:10],
            'subject': commit.get('subject', ''), 'url': commit.get('url', ''),
            'discussion': list(commit.get('discussion') or ())}


def origin_url(name):
    """上游站的参数页：Hugo 把 slug 小写，下划线在那边写成连字符（DateStyle → datestyle）。"""
    return 'https://guc.pg.center/zh/parameters/{}/'.format(name.lower().replace('_', '-'))


def detail(name, wanted=''):
    """一个配置参数的详情页上下文。找不到抛 GucParameter.DoesNotExist。

    查找不分大小写（`key` 是小写形式）；调用方拿 `name` 与请求里的拼写比，
    对不上就 301 到规范地址。
    """
    parameter = GucParameter.objects.get(key=name.lower())
    order = versions()
    major = pick_major(wanted, parameter.present_in, order)
    if not major:
        raise GucParameter.DoesNotExist(name)
    snapshot = parameter.versions.get(major) or {}
    pages = doc_pages()
    version = version_map().get(major)
    change = change_at(parameter, major)
    commit = intro_commit_of(parameter)
    context = snapshot.get('context') or parameter.context
    vartype = snapshot.get('vartype') or parameter.vartype
    document = doc_of(parameter, major, order, pages)
    doc_versions = []
    for item in order:
        if item['major'] not in parameter.present_in:
            continue
        url = doc_url(parameter.versions.get(item['major']), pages)
        if url:
            doc_versions.append({'major': item['major'], 'label': item['label'], 'url': url})
    return {
        'parameter': parameter, 'name': parameter.name,
        'group': parameter.group, 'group_slug': parameter.group_slug,
        'group_label': parameter.group_label,
        'category': parameter.category,
        'category_zh': snapshot.get('category_zh') or parameter.category_zh,
        'eyebrow': parameter.eyebrow, 'origin_url': origin_url(parameter.name),
        'version': version, 'previous_major': previous_major(parameter, major),
        'snapshot': snapshot,
        'facts': facts_of(parameter, major, snapshot, order, commit),
        'context_label': GUC_CONTEXT_LABEL.get(context, context),
        'context_note': GUC_CONTEXT_NOTE.get(context, ''),
        'vartype_label': GUC_VARTYPE_LABEL.get(vartype, vartype),
        'default_track': default_track_of(parameter, major, order),
        'ribbon': ribbon_of(parameter, major, order, pages),
        'change': change, 'change_note': change_note(parameter, major, order, change),
        'notice': notice_of(version),
        'doc': document,
        'editorial': editorial_of(parameter),
        'timeline': timeline_of(parameter),
        'matrix': matrix_of(parameter, major, order),
        'intro_commit': commit,
        'links': {
            'doc': doc_url(snapshot, pages),
            'doc_label': 'PostgreSQL {} 手册'.format((version or {}).get('label', major)),
            'official': document['official_url'],
            'commit': (commit or {}).get('url', ''),
        },
        'doc_versions': doc_versions,
        'siblings': sibling_groups(parameter.group_slug, parameter.category, parameter.name),
        'versions': order,
    }


# ---------------------------------------------------------------- 变更页

def compare(left, right, from_major='', to_major=''):
    """两份快照现算一条变化记录，供非相邻比较用；完全一致返回 None。"""
    left, right = left or {}, right or {}
    if not left and not right:
        return None
    if not left:
        return {'from': from_major, 'to': to_major, 'status': 'added', 'fields': {},
                'substantive': True, 'default_changed': False, 'carried': False}
    if not right:
        return {'from': from_major, 'to': to_major, 'status': 'removed', 'fields': {},
                'substantive': True, 'default_changed': False, 'carried': False}
    fields = diff_fields(left, right)
    if not fields:
        return None
    return {'from': from_major, 'to': to_major, 'status': 'changed', 'fields': fields,
            'substantive': is_substantive(fields), 'default_changed': is_default_change(fields),
            'carried': False}


def card_of(parameter, snapshot):
    snapshot = snapshot or {}
    vartype = snapshot.get('vartype') or parameter.vartype
    context = snapshot.get('context') or parameter.context
    return {
        'name': parameter.name, 'url': parameter.url,
        'group_slug': parameter.group_slug,
        'category': parameter.category,
        'category_zh': snapshot.get('category_zh') or parameter.category_zh,
        'short_desc_zh': parameter.short_desc_zh, 'short_desc': parameter.short_desc,
        'vartype': vartype, 'vartype_label': GUC_VARTYPE_LABEL.get(vartype, vartype),
        'context': context, 'context_label': GUC_CONTEXT_LABEL.get(context, context),
        'boot_human': human_of(snapshot) if snapshot else parameter.boot_human,
        'unit': snapshot.get('unit', parameter.unit) or '',
    }


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
        raise GucVersion.DoesNotExist(major)
    majors = [version['major'] for version in order]
    index_of = majors.index(major)
    natural = majors[index_of - 1] if index_of else ''
    if from_major not in majors or from_major == major:
        from_major = ''
    base = from_major or natural
    arbitrary = bool(from_major) and from_major != natural

    version = by_major[major]
    previous = by_major.get(base)
    # 两份快照由 Postgres 抽出来，最大的 doc_html 就地去掉：整列取回来是几十兆。
    queryset = (GucParameter.objects.defer(*DEFER)
                .annotate(left=RawSQL(ONE_SNAPSHOT_SQL, (base,), output_field=JSONField()),
                          right=RawSQL(ONE_SNAPSHOT_SQL, (major,), output_field=JSONField()))
                .filter(Q(present_in__contains=[base]) | Q(present_in__contains=[major])))

    added, removed, default_changed, changed, reworded, baseline_rows = [], [], [], [], [], []
    for parameter in queryset:
        left, right = parameter.left, parameter.right
        if right:
            baseline_rows.append((parameter, right))
        if not base:
            continue
        change = compare(left, right, base, major)
        if change is None:
            continue
        if change['status'] == 'added':
            added.append(card_of(parameter, right))
        elif change['status'] == 'removed':
            removed.append(card_of(parameter, left))
        elif change['default_changed']:
            default_changed.append({
                'name': parameter.name, 'url': parameter.url,
                'category_zh': parameter.category_zh,
                'from': default_side(left), 'to': default_side(right)})
        elif change['substantive']:
            changed.append({
                'name': parameter.name, 'url': parameter.url,
                'category_zh': parameter.category_zh,
                'fields': [{'field': field, 'label': GUC_FIELD_LABEL[field],
                            'from': raw_value(field, change['fields'][field]['from']),
                            'to': raw_value(field, change['fields'][field]['to'])}
                           for field, _ in GUC_FIELDS if field in change['fields']]})
        else:
            reworded.append(card_of(parameter, right))

    baseline = not base
    baseline_groups = []
    if baseline:
        baseline_groups = groups_of([row_of(parameter, order, snapshot)
                                     for parameter, snapshot in baseline_rows])
    return {
        'version': version, 'previous': previous, 'from_major': from_major,
        'arbitrary': arbitrary,
        'versions': [dict(item, is_current=item['major'] == major) for item in order],
        'notice': notice_of(version),
        'baseline_note': baseline_note(order) if baseline else '',
        'summary': {'added': len(added), 'removed': len(removed),
                    'default_changed': len(default_changed), 'changed': len(changed),
                    'reworded': len(reworded)},
        'added': added, 'removed': removed, 'default_changed': default_changed,
        'changed': changed, 'reworded': reworded,
        'baseline': baseline, 'baseline_groups': baseline_groups,
    }
