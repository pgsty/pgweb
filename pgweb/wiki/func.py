"""函数百科的取数与组装。视图只负责拼上下文，这里负责形状。

前端模板按本文件给出的键名渲染，改键名等于改契约（`docs/func-column.md` §4）。
版本次序一律取 `FuncVersion.position`：'9.0' 与 '10' 字符串比不出先后。

六百多个函数乘 18 版签名、示例与签名 HTML 不小，两个列表页都不整列取回来：
索引页 `defer` 掉 `versions` 与 `changes`，行上要的事实全在热字段里；变更页只让
Postgres 把要比的那两份快照抽出来，并就地把最大的签名 HTML 与示例去掉，只留
比较用的签名文本。详情页才真的取一整行。
"""

import re

from django.core.cache import cache
from django.db.models import JSONField, Q
from django.db.models.expressions import RawSQL

from .ruler import mark_ticks
from .models import (FUNC_GROUP_EYEBROW, FUNC_GROUP_LABEL, FUNC_GROUP_ORDER,
                     FuncVersion, PgFunction)


CACHE_KEY = 'pgweb:wiki:func-index'
VERSION_CACHE_KEY = 'pgweb:wiki:func-versions'
DOC_CACHE_KEY = 'pgweb:wiki:func-docpages'
CHANGES_CACHE_KEY = 'pgweb:wiki:func-changes:{}'
CACHE_SECONDS = 300

ROOT = '/docs/func/'
EYEBROW = 'FUNCTION'

# 列表页不取这两列：整份 JSON 比页面用到的多两个数量级。
DEFER = ('versions', 'changes')
# 变更页要的那一份快照：去掉每条签名的 html 与示例，只留比较用的 text。
# 缺席的版本整个表达式为 NULL，调用方按「这一版没有」处理。
LEAN_SNAPSHOT_SQL = """
((versions -> %s::text) - 'signatures' || jsonb_build_object('texts', coalesce(
    (SELECT jsonb_agg(s ->> 'text')
     FROM jsonb_array_elements(coalesce(versions -> %s::text -> 'signatures', '[]'::jsonb)) s
     WHERE s ->> 'text' IS NOT NULL), '[]'::jsonb)))
"""

# 手册第 9 章那二十几页；缓存只装这些页，不把上万条手册页面都拉进内存。
DOC_FILE_PREFIX = 'functions-'
# 手册页标题是 '9.4. 字符串函数和操作符'，链接文字里那个小数点后的句点多余。
SECTION_NUMBER = re.compile(r'^(\d[\d.]*)\.\s+')

# 最早收录的版本是基线，不代表这些函数首次于那一版引入。所有「引入」字样照此措辞。
BASELINE_TEMPLATE = '{0} 是本数据集的收录基线，不代表该函数首次于 {0} 引入。'
PREVIEW_TEMPLATE = '{} 为预发行快照，正式发布前仍可能变化。'
DEVEL_TEMPLATE = 'PostgreSQL {} 开发版尚未定稿：函数清单取自本站 devel 手册，正式发布前仍可能变化。'
OVERHAUL_TEMPLATE = 'PostgreSQL {} 重排了函数表的写法，签名文本整体改变，此处不逐条比较。'
# 事实一律来自上游英文页，本站手册只提供中文描述：所以「来源」说的是描述的来源。
NO_ZH_NOTE = '本站手册未收录该版的这条译文，说明按英文原文显示。'

STATE_LABEL = {'absent': '不存在', 'present': '存在', 'added': '新增', 'removed': '移除',
               'changed': '签名变更'}
ZH_FROM_LABEL = {'doc': '本站译文', 'inherited': '本站译文（沿用）', '': '英文原文'}

# 相关函数取同分组里位置相邻的这么多个（前后各 N 个）。
RELATED_SPAN = 4

GROUP_LABEL, GROUP_EYEBROW, GROUP_ORDER = (FUNC_GROUP_LABEL, FUNC_GROUP_EYEBROW,
                                           FUNC_GROUP_ORDER)


def zh_from_of(snapshot, signature=None):
    """这一版这条说明的中文来源：'doc' 本版译文 / 'inherited' 借用别版 / '' 没有译文。

    契约把 `zh_from` 记在快照上，导入器在每条签名上也带了一份。逐条那份才准：整份快照
    标 'doc' 不代表每条签名都配上了中文（全库有 96 条没配上），所以签名带了这个键就认
    它，**空串也认**——那正是「这条没有译文」的意思；只有整个键缺席才回落到快照。
    """
    if signature is not None and 'zh_from' in signature:
        return signature['zh_from'] or ''
    return (snapshot or {}).get('zh_from', '') or ''


def zh_label(snapshot, signature=None):
    """说明来源的中文标签，逐条签名判定。

    没记 `zh_from` 的老数据看描述本身：有中文就当本版译文，免得整页都说成英文原文。
    """
    zh_from = zh_from_of(snapshot, signature)
    if zh_from:
        return ZH_FROM_LABEL.get(zh_from, ZH_FROM_LABEL[''])
    if signature is not None:
        marked = 'zh_from' in signature
        has_text = bool(signature.get('description_zh'))
        return ZH_FROM_LABEL['doc'] if (not marked and has_text) else ZH_FROM_LABEL['']
    return ZH_FROM_LABEL['doc'] if has_zh(snapshot) else ZH_FROM_LABEL['']


def has_zh(snapshot):
    """本版是否有中文说明。快照没记 zh_from 的老数据看描述本身。"""
    snapshot = snapshot or {}
    if snapshot.get('zh_from'):
        return True
    return bool(snapshot.get('description_zh')
                or any(item.get('description_zh') for item in snapshot.get('signatures') or ()))


# ---------------------------------------------------------------- 版本

def baseline_note(order=None):
    order = order if order is not None else versions()
    return BASELINE_TEMPLATE.format(order[0]['major']) if order else ''


def version_data(version, is_default=False):
    return {
        'major': version.major, 'label': version.label or version.major,
        'status': version.status, 'status_label': version.status_label,
        'support_status': version.support_status,
        'function_count': version.function_count, 'signature_count': version.signature_count,
        'added_count': version.added_count, 'removed_count': version.removed_count,
        'changed_count': version.changed_count,
        'position': version.position, 'doc_slug': version.doc_slug,
        # 事实恒为上游英文页，`source` 只剩记录意义；中文多少由 zh_coverage 说。
        'source': version.source, 'layout': version.layout,
        'zh_coverage': version.zh_coverage,
        'url': version.changes_url, 'preview': version.is_preview, 'devel': version.is_devel,
        'is_default': is_default,
    }


def versions():
    """全部版本，按 position。第一项是最早的 9.0，最后一项是 20 devel。"""
    rows = cache.get(VERSION_CACHE_KEY)
    if rows is None:
        stored = list(FuncVersion.objects.all())
        default = stable_major(stored)
        rows = mark_ticks([version_data(version, version.major == default) for version in stored])
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
    """无效或缺席的 ?v= 落回默认版本；默认版本这个函数也没有时取它最后存在的版本。"""
    if wanted and wanted in present:
        return wanted
    order = order if order is not None else versions()
    default = next((v['major'] for v in order if v['is_default']), '')
    if default in present:
        return default
    return present[-1] if present else ''


def notice_of(version):
    if version and version['preview']:
        return PREVIEW_TEMPLATE.format(version['label'])
    if version and version['devel']:
        return DEVEL_TEMPLATE.format(version['major'])
    return ''


# ---------------------------------------------------------------- 手册链接

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

    `pages` 是 `doc_pages()` 的结果。一个详情页要问十几次，调用方读一次传进来。
    """
    doc = (snapshot or {}).get('doc') or {}
    slug, filename, anchor = doc.get('slug', ''), doc.get('file', ''), doc.get('anchor', '')
    pages = doc_pages() if pages is None else pages
    if not slug or not filename or (slug, filename) not in pages:
        return ''
    return '/docs/{}/{}{}'.format(slug, filename, '#' + anchor if anchor else '')


def doc_title(snapshot, pages=None):
    doc = (snapshot or {}).get('doc') or {}
    pages = doc_pages() if pages is None else pages
    title = pages.get((doc.get('slug', ''), doc.get('file', '')), '')
    return SECTION_NUMBER.sub(r'\1 ', title).strip()


def official_url(snapshot, version):
    """上游原页。9.x 的版本段就是版本号本身，20 走 devel。"""
    doc = (snapshot or {}).get('doc') or {}
    filename, anchor = doc.get('file', ''), doc.get('anchor', '')
    slug = (version or {}).get('doc_slug', '') or doc.get('slug', '') or (version or {}).get('major', '')
    if not slug or not filename:
        return ''
    return 'https://www.postgresql.org/docs/{}/{}{}'.format(
        slug, filename, '#' + anchor if anchor else '')


def forget():
    cache.delete(CACHE_KEY)
    cache.delete(VERSION_CACHE_KEY)
    cache.delete(DOC_CACHE_KEY)
    # 变更页按版本各缓存一份；版本表刚写过，照库里现有的版本清。
    cache.delete_many([CHANGES_CACHE_KEY.format(major) for major
                       in FuncVersion.objects.values_list('major', flat=True)])


# ---------------------------------------------------------------- 签名

def texts_of(snapshot):
    """一份快照的签名文本。整份快照给 `signatures`，瘦身过的只有 `texts`。"""
    snapshot = snapshot or {}
    if 'texts' in snapshot:
        return [text for text in snapshot['texts'] or () if text]
    return [signature.get('text', '') for signature in snapshot.get('signatures') or ()
            if signature.get('text')]


def descriptions_differ(left, right):
    """首条签名的描述变没变。只在可比的两者之间比。

    一边有译文、另一边没有，差的是本站译文的覆盖面，不是 PostgreSQL 的说明变了；
    这种情况一律算没变。两边都有中文就比中文，都没有就比英文原文。
    """
    left, right = left or {}, right or {}
    left_zh, right_zh = left.get('description_zh') or '', right.get('description_zh') or ''
    if left_zh and right_zh:
        return left_zh != right_zh
    if left_zh or right_zh:
        return False
    return (left.get('description') or '') != (right.get('description') or '')


# ---------------------------------------------------------------- 索引页

def removed_after(function, order):
    """移除标在 last_version 的下一版；还在最后一版里就没有移除版本。"""
    majors = [version['major'] for version in order]
    if not function.last_version or function.last_version not in majors:
        return ''
    index = majors.index(function.last_version)
    return majors[index + 1] if index + 1 < len(majors) else ''


def states_of(function, order):
    """逐版本的版本变动状态。一版一格，不合段。"""
    present = set(function.present_in)
    changed = set(function.changed_in)
    removed_in = removed_after(function, order)
    first = function.first_version
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


def strip_of(function, order):
    """版本变动：一排方格，每格一个版本，与表头刻度一一对应。"""
    return [{'major': major, 'state': state,
             'label': '{} · {}'.format(major, STATE_LABEL.get(state, state))}
            for major, state in states_of(function, order)]


def row_of(function, order):
    """索引表的一行。事实全取热字段，不碰 JSON 大列。"""
    removed_in = removed_after(function, order)
    changed_in = list(function.changed_in)
    return {
        'slug': function.slug, 'name': function.name, 'url': function.url,
        'group': function.group, 'group_label': function.group_label,
        'summary_zh': function.summary_zh, 'summary': function.summary,
        'signature': function.signature, 'signature_count': function.signature_count,
        'first': function.first_version, 'last': function.last_version,
        'baseline': bool(order) and function.first_version == order[0]['major'],
        'removed': bool(removed_in), 'removed_in': removed_in,
        'change_count': len(changed_in), 'last_change': changed_in[-1] if changed_in else '',
        'present_tokens': ' '.join(function.present_in),
        'strip': strip_of(function, order),
        'text': ' '.join(v for v in (function.name, function.summary_zh, function.summary,
                                     function.signature, function.group_label) if v),
    }


def groups_of(rows):
    """分组 → 行。分组次序按行的 `position` 次序，常量表只用来补英文眉题。"""
    buckets, order = {}, []
    for row in rows:
        if row['group'] not in buckets:
            buckets[row['group']] = []
            order.append(row['group'])
        buckets[row['group']].append(row)
    # 常量表里没有的分组（导入了新数据而常量表还没跟上）排在最后，不丢函数。
    seen = {slug: index for index, slug in enumerate(order)}
    order.sort(key=lambda slug: (GROUP_ORDER.get(slug, 10 ** 6), seen[slug]))
    return [{'slug': slug, 'label': buckets[slug][0]['group_label'] or GROUP_LABEL.get(slug, slug),
             'eyebrow': GROUP_EYEBROW.get(slug, slug.replace('-', ' ').upper()),
             'anchor': 'group-' + slug, 'count': len(buckets[slug]), 'rows': buckets[slug]}
            for slug in order]


def filters_of(rows, groups, order):
    """筛选下拉。计数就地算，不再查库。"""
    def options(values):
        counts = {}
        for value in values:
            if value:
                counts[value] = counts.get(value, 0) + 1
        return counts

    first = options(row['first'] for row in rows)
    present = options(major for row in rows for major in row['present_tokens'].split())
    labels = {version['major']: version['label'] for version in order}
    return [
        {'param': 'group', 'label': '分组',
         'options': [{'value': group['slug'], 'label': group['label'], 'count': group['count']}
                     for group in groups]},
        {'param': 'first', 'label': '引入版本',
         'options': [{'value': version['major'], 'label': labels[version['major']],
                      'count': first[version['major']]}
                     for version in reversed(order) if first.get(version['major'])]},
        {'param': 'present', 'label': '存在于版本',
         'options': [{'value': version['major'], 'label': labels[version['major']],
                      'count': present[version['major']]}
                     for version in reversed(order) if present.get(version['major'])]},
    ]


def index_payload():
    order = versions()
    rows = [row_of(function, order) for function in PgFunction.objects.defer(*DEFER)]
    groups = groups_of(rows)
    return {
        'total': len(rows), 'group_count': len(groups),
        'default_major': default_major(),
        'earliest_major': order[0]['major'] if order else '',
        'latest_major': order[-1]['major'] if order else '',
        'versions': order, 'groups': groups,
        'filters': filters_of(rows, groups, order),
        'stats': {
            'functions': len(rows), 'versions': len(order),
            'snapshots': sum(len(row['present_tokens'].split()) for row in rows),
            'signatures': sum(row['signature_count'] for row in rows),
            'changes': sum(row['change_count'] for row in rows),
            'removed': sum(1 for row in rows if row['removed']),
        },
    }


def index():
    payload = cache.get(CACHE_KEY)
    if payload is None:
        payload = index_payload()
        cache.set(CACHE_KEY, payload, CACHE_SECONDS)
    return payload


def sibling_groups(group_slug, current=''):
    """页尾复用索引表：只留本函数所在的那一组。"""
    return [dict(group, current=current) for group in index()['groups']
            if group['slug'] == group_slug]


def related_of(group_slug, slug, span=RELATED_SPAN):
    """同分组里位置相邻的函数，前后各 `span` 个。行来自缓存好的索引表，不再查库。"""
    rows = next((group['rows'] for group in index()['groups'] if group['slug'] == group_slug), [])
    position = next((index_of for index_of, row in enumerate(rows) if row['slug'] == slug), None)
    if position is None:
        return []
    neighbours = rows[max(0, position - span):position] + rows[position + 1:position + 1 + span]
    return [{'slug': row['slug'], 'name': row['name'], 'url': row['url'],
             'summary_zh': row['summary_zh'] or row['summary']} for row in neighbours]


def group_nav(current=''):
    """「函数百科」下的各个分组，侧栏导航用。"""
    return [{'title': group['label'], 'link': ROOT + '#' + group['anchor'],
             'active': group['slug'] == current} for group in index()['groups']]


# ---------------------------------------------------------------- 详情页

def previous_major(function, major):
    """按 present_in 顺序的上一版；首版或缺席返回 ''。"""
    present = function.present_in
    if major not in present:
        return ''
    index_of = present.index(major)
    return present[index_of - 1] if index_of else ''


def change_at(function, major):
    """落在本版的变化记录（移除记在下一版，不算本版的事）。"""
    return next((change for change in function.changes or ()
                 if change.get('to') == major and change.get('status') != 'removed'), None)


def overhaul_between(function, major):
    """本版与它的上一个存在版本之间，手册是不是换了函数表的写法（12 → 13 那一跳）。

    重排那一跳签名文本整体改变，不逐条比较；判断只看两份快照自己记下的 `layout`，
    不依赖版本表，函数在中间某版缺席时也判得准。
    """
    previous = previous_major(function, major)
    if not previous:
        return False
    left = (function.versions or {}).get(previous) or {}
    right = (function.versions or {}).get(major) or {}
    return bool(left.get('layout')) and bool(right.get('layout')) \
        and left['layout'] != right['layout']


def change_note(function, major, order, change, version=None, snapshot=None):
    """本版变化一句话，六种措辞见 `docs/func-column.md` §4.2。"""
    baseline = order[0]['major'] if order else ''
    note = ''
    if major == baseline and major in function.present_in:
        note = baseline_note(order)
    elif change is not None and change.get('status') == 'added':
        count = len(((function.versions or {}).get(major) or {}).get('signatures') or ())
        note = 'PostgreSQL {} 新增此函数，共 {} 条签名。'.format(major, count)
    elif (change or {}).get('doc_overhaul') or overhaul_between(function, major):
        note = OVERHAUL_TEMPLATE.format(major)
    elif change is None:
        previous = previous_major(function, major)
        note = '相对 PostgreSQL {} 无变化。'.format(previous) if previous else ''
    else:
        previous = change.get('from', '') or previous_major(function, major)
        signatures = change.get('signatures') or {}
        written = []
        if signatures.get('added'):
            written.append('新增 {} 条签名'.format(len(signatures['added'])))
        if signatures.get('removed'):
            written.append('移除 {} 条'.format(len(signatures['removed'])))
        moved = change.get('group_changed') or None
        if moved:
            written.append('分组由{}改为{}'.format(
                GROUP_LABEL.get(moved.get('from', ''), moved.get('from', '')),
                GROUP_LABEL.get(moved.get('to', ''), moved.get('to', ''))))
        if change.get('descriptions_changed') and not written:
            written.append('说明有更新')
        note = ('相对 PostgreSQL {}：{}。'.format(previous, '，'.join(written)) if written
                else '相对 PostgreSQL {} 无变化。'.format(previous))
    # 事实来自上游英文页，本站手册未必有这一版的译文；没有就说清楚说明是英文原文。
    if snapshot is not None and not has_zh(snapshot):
        note = (note + NO_ZH_NOTE) if note else NO_ZH_NOTE
    return note


def ribbon_of(function, major, order, pages=None):
    """版本条：逐版本一格，不合段。"""
    by_major = version_map()
    cells = []
    for version_major, state in states_of(function, order):
        version = by_major.get(version_major, {})
        snapshot = (function.versions or {}).get(version_major)
        cells.append({
            'major': version_major, 'label': version.get('label', version_major),
            'state': state,
            'url': '{}?v={}'.format(function.url, version_major)
            if state not in ('absent', 'removed') else '',
            'current': version_major == major,
            'preview': bool(version.get('preview')), 'devel': bool(version.get('devel')),
            'doc_url': doc_url(snapshot, pages) if snapshot else '',
            'status': version.get('status', ''),
        })
    return cells


def facts_of(function, major, snapshot, order, version):
    facts = []

    def add(label, value, mono=False, url=''):
        if value:
            facts.append({'label': label, 'value': value, 'mono': mono, 'url': url})

    group = snapshot.get('group') or function.group
    add('分组', snapshot.get('group_label') or function.group_label, url=ROOT + '#group-' + group)
    add('签名数', '{} 条'.format(len(snapshot.get('signatures') or ())))
    baseline = order[0]['major'] if order else ''
    first = function.first_version
    add('引入版本', '{}（基线）'.format(first) if first == baseline else first)
    removed_in = removed_after(function, order)
    add('状态', '于 {} 移除'.format(removed_in) if removed_in else '现存')
    add('签名变更', '{} 次'.format(len(function.changed_in)) if function.changed_in else '未变过')
    # 事实（存在性、签名、示例）一律来自上游英文页，这一条说的是说明文字的来源。
    add('本版来源', zh_label(snapshot))
    return facts


def signatures_of(snapshot, change):
    """本版的签名。`added` 标出本版相对上一版新增的那几条。"""
    added = set(((change or {}).get('signatures') or {}).get('added') or ())
    rows = []
    for signature in snapshot.get('signatures') or ():
        text = signature.get('text', '')
        zh_from = zh_from_of(snapshot, signature)
        rows.append({
            'text': text, 'html': signature.get('html', ''),
            'returns': signature.get('returns', ''),
            'description_zh': signature.get('description_zh', ''),
            'description': signature.get('description', ''),
            # 描述各有一份清洗过的 HTML：纯文本会丢掉参数名的斜体、code 与链接，
            # 模板要保真就用它。两份分语言，`description_html` 是英文原文那份，
            # `description_zh_html` 是中文译文那份，没有译文时为空。
            'description_html': signature.get('description_html', ''),
            'description_zh_html': signature.get('description_zh_html', ''),
            'examples': [{'expr': example.get('expr', ''), 'result': example.get('result', '')}
                         for example in signature.get('examples') or ()],
            'added': text in added,
            # 中文来源：'doc' 本版译文 / 'inherited' 借用别版（模板加「沿用」标记）/
            # '' 没有译文（模板显示英文并标 lang="en"）。
            'zh_from': zh_from, 'inherited': zh_from == 'inherited',
            'zh_label': zh_label(snapshot, signature),
        })
    return rows


def removed_signatures_of(function, major, change):
    """本版相对上一版移除的签名，整条取上一版的快照。"""
    gone = set(((change or {}).get('signatures') or {}).get('removed') or ())
    if not gone:
        return []
    base = (function.versions or {}).get((change or {}).get('from', '')) or {}
    return [row for row in signatures_of(base, None) if row['text'] in gone]


def timeline_of(function):
    """演化历史，新的在前。"""
    rows = []
    for change in reversed(function.changes or ()):
        signatures = change.get('signatures') or {}
        to = change.get('to', '')
        rows.append({
            'to': to, 'from': change.get('from', ''), 'status': change.get('status', ''),
            'url': '{}?v={}'.format(function.url, to) if to in function.present_in else '',
            'added': list(signatures.get('added') or ()),
            'removed': list(signatures.get('removed') or ()),
            'doc_overhaul': bool(change.get('doc_overhaul')),
            'group_changed': change.get('group_changed') or None,
            'descriptions_changed': bool(change.get('descriptions_changed')),
        })
    return rows


def matrix_of(function, major, order):
    """签名 × 版本。行按签名首次出现的版本次序排，格子只说存在与否。"""
    present = [version for version in order if version['major'] in (function.versions or {})]
    texts, seen = [], set()
    per_version = {}
    for version in present:
        items = texts_of(function.versions.get(version['major']))
        per_version[version['major']] = set(items)
        for text in items:
            if text not in seen:
                seen.add(text)
                texts.append(text)
    rows = []
    for text in texts:
        cells = []
        for version in present:
            exists = text in per_version[version['major']]
            cells.append({'major': version['major'], 'state': 'exists' if exists else 'absent',
                          'url': '{}?v={}'.format(function.url, version['major']) if exists else '',
                          'current': version['major'] == major})
        rows.append({'text': text, 'cells': cells})
    return {'versions': present, 'rows': rows}


def doc_of(function, major, order, pages, version):
    """手册坐标：本版本站没有手册时（9.x）借最近的可用版，官方链接仍指本版。"""
    snapshot = (function.versions or {}).get(major) or {}
    doc = snapshot.get('doc') or {}
    local, linked, borrowed = doc_url(snapshot, pages), major, False
    if not local:
        positions = {item['major']: item['position'] for item in order}
        here = positions.get(major, 0)
        candidates = []
        for other in function.present_in:
            url = doc_url((function.versions or {}).get(other), pages)
            if url:
                candidates.append((abs(positions.get(other, 0) - here),
                                   -positions.get(other, 0), other, url))
        if candidates:
            candidates.sort(key=lambda item: item[:2])
            _, _, linked, local = candidates[0]
            borrowed = True
    label = ''
    if local:
        linked_version = version_map().get(linked) or {}
        title = doc_title((function.versions or {}).get(linked), pages)
        label = 'PostgreSQL {} 手册{}'.format(
            linked_version.get('label', linked), ' · ' + title if title else '')
    return {'file': doc.get('file', ''), 'anchor': doc.get('anchor', ''),
            'local_url': local, 'official_url': official_url(snapshot, version),
            'label': label, 'borrowed': borrowed, 'major': linked if local else ''}


def lookup(token):
    """slug 优先，再按小写函数名；两者都不中抛 PgFunction.DoesNotExist。

    调用方拿返回的 `slug` 与地址里的写法比，对不上就 301 到规范地址。
    """
    token = (token or '').strip()
    function = PgFunction.objects.filter(slug=token).first()
    if function is None:
        function = PgFunction.objects.filter(name_key=token.lower()).first()
    if function is None:
        raise PgFunction.DoesNotExist(token)
    return function


def detail(slug, wanted=''):
    """一个函数的详情页上下文。找不到抛 PgFunction.DoesNotExist。"""
    function = lookup(slug)
    order = versions()
    major = pick_major(wanted, function.present_in, order)
    if not major:
        raise PgFunction.DoesNotExist(slug)
    snapshot = (function.versions or {}).get(major) or {}
    pages = doc_pages()
    version = version_map().get(major)
    change = change_at(function, major)
    group = snapshot.get('group') or function.group
    doc_versions = []
    for item in order:
        if item['major'] not in function.present_in:
            continue
        url = doc_url((function.versions or {}).get(item['major']), pages)
        if url:
            doc_versions.append({'major': item['major'], 'label': item['label'], 'url': url})
    return {
        'function': function, 'name': function.name, 'slug': function.slug,
        'group': group, 'group_slug': group,
        'group_label': snapshot.get('group_label') or function.group_label,
        'eyebrow': EYEBROW,
        'version': version, 'previous_major': previous_major(function, major),
        'snapshot': snapshot,
        'summary_zh': function.summary_zh, 'summary': function.summary,
        'description_zh': snapshot.get('description_zh', ''),
        'description': snapshot.get('description', ''),
        'facts': facts_of(function, major, snapshot, order, version),
        'signatures': signatures_of(snapshot, change),
        'removed_signatures': removed_signatures_of(function, major, change),
        'ribbon': ribbon_of(function, major, order, pages),
        'change': change,
        'change_note': change_note(function, major, order, change, version, snapshot),
        'notice': notice_of(version),
        'doc': doc_of(function, major, order, pages, version),
        'pages': list(snapshot.get('pages') or ()),
        'timeline': timeline_of(function),
        'matrix': matrix_of(function, major, order),
        'related': related_of(group, function.slug),
        'siblings': sibling_groups(group, function.slug),
        'doc_versions': doc_versions,
        'versions': order,
    }


# ---------------------------------------------------------------- 变更页

def compare(left, right, from_major='', to_major=''):
    """两份快照现算一条变化记录，供非相邻比较用；完全一致返回 None。

    手册重排那一跳（≤12 的五列表 → 13 起的签名段）签名文本整体换了写法，只记增删，
    从快照自己记的 `layout` 看出来；描述只在两边都有中文或两边都没有时才比。
    """
    left, right = left or {}, right or {}
    if not left and not right:
        return None
    blank = {'added': [], 'removed': []}
    if not left:
        return {'from': from_major, 'to': to_major, 'status': 'added', 'signatures': dict(blank),
                'descriptions_changed': False, 'group_changed': None, 'doc_overhaul': False}
    if not right:
        return {'from': from_major, 'to': to_major, 'status': 'removed', 'signatures': dict(blank),
                'descriptions_changed': False, 'group_changed': None, 'doc_overhaul': False}
    overhaul = bool(left.get('layout')) and bool(right.get('layout')) \
        and left['layout'] != right['layout']
    if overhaul:
        signatures = dict(blank)
    else:
        before, after = texts_of(left), texts_of(right)
        signatures = {'added': [text for text in after if text not in set(before)],
                      'removed': [text for text in before if text not in set(after)]}
    descriptions_changed = bool(not overhaul and descriptions_differ(left, right))
    group_changed = None
    if left.get('group') and right.get('group') and left['group'] != right['group']:
        group_changed = {'from': left['group'], 'to': right['group']}
    if not any((signatures['added'], signatures['removed'], descriptions_changed, group_changed)):
        return None
    return {'from': from_major, 'to': to_major, 'status': 'changed', 'signatures': signatures,
            'descriptions_changed': descriptions_changed, 'group_changed': group_changed,
            'doc_overhaul': overhaul}


def card_of(function, snapshot=None):
    snapshot = snapshot or {}
    texts = texts_of(snapshot)
    return {
        'slug': function.slug, 'name': function.name, 'url': function.url,
        'group': snapshot.get('group') or function.group,
        'group_label': snapshot.get('group_label') or function.group_label,
        'summary_zh': function.summary_zh, 'summary': function.summary,
        'signature': texts[0] if texts else function.signature,
        'signature_count': len(texts) if texts else function.signature_count,
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
        raise FuncVersion.DoesNotExist(major)
    majors = [version['major'] for version in order]
    index_of = majors.index(major)
    natural = majors[index_of - 1] if index_of else ''
    if from_major not in majors or from_major == major:
        from_major = ''
    base = from_major or natural
    arbitrary = bool(from_major) and from_major != natural

    version = by_major[major]
    previous = by_major.get(base)
    # 两份快照由 Postgres 抽出来，签名的 html 与示例就地去掉：整列取回来是几十兆。
    queryset = (PgFunction.objects.defer(*DEFER)
                .annotate(left=RawSQL(LEAN_SNAPSHOT_SQL, (base, base), output_field=JSONField()),
                          right=RawSQL(LEAN_SNAPSHOT_SQL, (major, major), output_field=JSONField()))
                .filter(Q(present_in__contains=[base]) | Q(present_in__contains=[major])))

    # 手册重排那一跳只记增删：两端版面不同，签名文本整体换了写法，逐条比没有意义。
    overhaul = bool(previous and previous.get('layout') and version.get('layout')
                    and previous['layout'] != version['layout'])

    added, removed, changed, moved, baseline_rows = [], [], [], [], []
    for function in queryset:
        left, right = function.left, function.right
        if right:
            baseline_rows.append(function)
        if not base:
            continue
        change = compare(left, right, base, major)
        if change is None:
            continue
        if change['status'] == 'added':
            added.append(card_of(function, right))
            continue
        if change['status'] == 'removed':
            removed.append(card_of(function, left))
            continue
        if change['group_changed']:
            card = card_of(function, right)
            moved.append(dict(card, from_group=change['group_changed']['from'],
                              to_group=change['group_changed']['to'],
                              from_group_label=GROUP_LABEL.get(change['group_changed']['from'],
                                                               change['group_changed']['from']),
                              to_group_label=GROUP_LABEL.get(change['group_changed']['to'],
                                                             change['group_changed']['to'])))
        signatures = change['signatures']
        if signatures['added'] or signatures['removed']:
            card = card_of(function, right)
            changed.append(dict(card, added=len(signatures['added']),
                                removed=len(signatures['removed']),
                                sample=signatures['added'][0] if signatures['added'] else ''))

    baseline = not base
    baseline_groups = []
    if baseline:
        baseline_groups = groups_of([row_of(function, order) for function in baseline_rows])
    return {
        'version': version, 'previous': previous, 'from_major': from_major,
        'arbitrary': arbitrary,
        'versions': [dict(item, is_current=item['major'] == major) for item in order],
        'notice': notice_of(version),
        'baseline_note': baseline_note(order) if baseline else '',
        'doc_overhaul': overhaul,
        'overhaul_note': OVERHAUL_TEMPLATE.format(major) if overhaul else '',
        'summary': {'added': len(added), 'removed': len(removed), 'changed': len(changed),
                    'moved': len(moved)},
        'added': added, 'removed': removed, 'changed': changed, 'moved': moved,
        'baseline': baseline, 'baseline_groups': baseline_groups,
    }
