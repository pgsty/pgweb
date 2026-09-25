"""导入系统目录百科。

两步，和错误码栏目同形：`export_snapshot()` 把 cat 仓库 + 本站手册读成一份自包含快照，
`import_snapshot()` 把快照写进库。拆开是为了让同一份快照分别加载本地与生产——
导出要读本地手册译文，导入只认快照，生产机上不需要 cat 仓库。

本站在 cat 之上叠两层：
1. 中文：从本站手册（`docs` 表）里采集关系说明段、逐字段描述与总览表的一句话；
2. PostgreSQL 20 开发版快照：cat 只到 19 beta 3，20 由本站 devel 手册推导。

回退规则严格：某版某字段没有译文时，只在英文描述**完全相同**的另一份快照里借用译文
（`zh_from='inherited'`），否则留空让页面显示英文。不做近似匹配。
"""

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone

from bs4 import BeautifulSoup, Tag
from django.db import transaction

from pgweb.docs.versions import DEVEL_MAJOR_VERSION

from .snapshot import item_hash, hashed_defaults
from .models import CATALOG_KIND_ORDER, CatalogRelation, CatalogVersion


FORMAT = 1
DEFAULT_ROOT = os.path.expanduser('~/pg.center/cat')

# 本站 devel 手册就是开发版；cat 里没有这一版，整版由手册推导。
DEVEL_MAJOR = str(DEVEL_MAJOR_VERSION)
DEVEL_TREE = 0

NAME_RE = re.compile(r'^pg_[a-z0-9_]+$')

# cat 的类型别名表（scripts/build_catalog.py 的 TYPE_ALIASES），手册里写的是简写。
TYPE_ALIASES = {
    'bool': 'boolean', 'int': 'integer', 'Oid': 'oid', 'int2': 'smallint', 'int4': 'integer',
    'int8': 'bigint', 'float4': 'real', 'float8': 'double precision',
    'timestamptz': 'timestamp with time zone', 'timestamp': 'timestamp without time zone',
    'char': '"char"',
}

# 快照里不留的键：原始记录太大，或只是作者本地的文件路径。
SNAPSHOT_DROP = ('runtime_validation', 'source_path', 'definition_source_path',
                 'documentary_schema_source')

# 总览一句话的取值顺序：最新稳定版在前，再往两边找。
SUMMARY_ORDER = ('18', '19', DEVEL_MAJOR, '17', '16', '15', '14', '13', '12', '11', '10')

# 总览表所在的页。目录表的那张 14 起搬到 catalogs-overview.html，10 – 14 在
# catalogs.html；统计视图的两张一直在 monitoring-stats.html。
OVERVIEW_FILES = ('catalogs-overview.html', 'catalogs.html', 'views-overview.html',
                  'views.html', 'monitoring-stats.html')

SPACE = re.compile(r'\s+')
SECTION_CLASSES = ('chapter', 'sect1', 'sect2', 'sect3', 'sect4', 'appendix', 'part')
REFERENCE_RE = re.compile(r'(pg_[a-z0-9_]+)\s*\.\s*([a-z0-9_]+)')
SENTENCE_END = '。'
# 真实字段名全小写；手册里的 `stakindN` 之类是占位符，不是字段。
COLUMN_NAME_RE = re.compile(r'^[a-z_][a-z0-9_]*$')
ASCII_TYPE_RE = re.compile(r'^[A-Za-z0-9_"\[\](), .]+$')
# 手册里的语义锚点全大写；`id-1.10.4.13.4` 是自动生成的，换一版就变。
SEMANTIC_ANCHOR_RE = re.compile(r'^[A-Z][A-Z0-9-]*$')


# ------------------------------------------------------------------ HTML 工具

def text_of(node):
    """纯文本：去标签、保留 code 内文字、折叠空白。"""
    if node is None:
        return ''
    raw = node.get_text() if isinstance(node, Tag) else str(node)
    return SPACE.sub(' ', raw.replace('\xa0', ' ')).strip()


def canonical_type(value):
    """手册写的 int4 / bool / timestamptz 规范成 cat 用的 SQL 类型名。"""
    value = ' '.join((value or '').split()).replace(' [', '[')
    if not value:
        return ''
    if value.endswith('[]'):
        return canonical_type(value[:-2]) + '[]'
    return TYPE_ALIASES.get(value, value)


def first_sentence(value):
    """一句话说明：截到第一个句号。"""
    value = (value or '').strip()
    if not value:
        return ''
    head, sep, _ = value.partition(SENTENCE_END)
    return head + sep if sep else value


def is_table_div(node):
    return isinstance(node, Tag) and node.name == 'div' and 'table' in (node.get('class') or ())


def table_structnames(div):
    """表标题里写的 structname；定位关系的表就靠它。"""
    title = div.find('p', class_='title')
    if title is None:
        return set(), ''
    return {text_of(code) for code in title.select('code.structname')}, text_of(title)


def match_table(candidates, name):
    """先认标题里的 structname，再退到标题文本里的整词匹配。"""
    word = re.compile(r'(?<![a-z0-9_])' + re.escape(name) + r'(?![a-z0-9_])')
    fallback = None
    for div in candidates:
        names, title = table_structnames(div)
        if name in names:
            return div
        if fallback is None and word.search(title):
            fallback = div
    return fallback


def locate_table(soup, name, anchor=''):
    """定位某个关系的字段表。

    有锚点先从锚点元素往后找（锚点本身可能就是那张表）；锚点在这一版不存在时，
    退回全页扫描——同一关系在不同版本的锚点并不一致。
    """
    if soup is None:
        return None
    if anchor:
        node = soup.find(id=anchor)
        if isinstance(node, Tag):
            candidates = ([node] if is_table_div(node) else []) + node.select('div.table')
            hit = match_table(candidates, name)
            if hit is not None:
                return hit
            hit = match_table(node.find_all_next('div', class_='table'), name)
            if hit is not None:
                return hit
    return match_table(soup.select('div.table'), name)


def section_of(node):
    for parent in node.parents:
        if isinstance(parent, Tag) and set(parent.get('class') or ()).intersection(SECTION_CLASSES):
            return parent
    return None


def relation_description(div):
    """关系说明段：该节标题之后、字段表之前的 `<p>`（跳过 indexterm 与表标题）。"""
    section = section_of(div)
    if section is None:
        return ''
    ancestors = set(id(parent) for parent in div.parents)
    paragraphs = []
    for child in section.children:
        if not isinstance(child, Tag):
            continue
        if child is div or id(child) in ancestors:
            break
        if child.name == 'p' and 'title' not in (child.get('class') or ()):
            value = clean_cell(child)
            if value:
                paragraphs.append(value)
    return '\n\n'.join(paragraphs)


def clean_cell(node):
    """一个单元格的可读文本：索引锚点不算内容。"""
    if node is None:
        return ''
    fragment = BeautifulSoup(str(node), 'html.parser')
    for junk in fragment.select('a.indexterm'):
        junk.decompose()
    return text_of(fragment)


def reference_of(node, own_name):
    """定义行里写的引用：「（引用 pg_namespace.oid）」→ 'pg_namespace.oid'。"""
    for match in REFERENCE_RE.finditer(clean_cell(node)):
        if match.group(1) != own_name:
            return '{}.{}'.format(match.group(1), match.group(2))
    return ''


def parse_columns(div, relation_name):
    """字段表的两种格式都认，返回 [{'name', 'documented_type', 'references', 'description_zh'}]。

    PG13+ 是单列 `td.catalog_table_entry`：`p.column_definition` 给字段名与类型，
    后面的 `<p>` 是描述。PG10 – 12 是四列（统计与进度视图三列，没有引用列）。
    """
    table = div.find('table', class_='table') or div.find('table')
    if table is None:
        return []
    body = table.find('tbody') or table
    rows = []
    for row in body.find_all('tr', recursive=False):
        cells = row.find_all(['td', 'th'], recursive=False)
        if not cells:
            continue
        entry = cells[0]
        definition = entry.find('p', class_='column_definition')
        if definition is not None and len(cells) == 1:
            field = definition.find('code', class_='structfield')
            if field is None:
                continue
            paragraphs = [p for p in entry.find_all('p', recursive=False) if p is not definition]
            rows.append({
                'name': text_of(field),
                'documented_type': text_of(definition.find('code', class_='type')),
                'references': reference_of(definition, relation_name),
                'description_zh': '\n\n'.join(v for v in (clean_cell(p) for p in paragraphs) if v),
            })
            continue
        field = entry.find('code', class_='structfield')
        if field is None or len(cells) < 2:
            continue
        rows.append({
            'name': text_of(field),
            'documented_type': text_of(cells[1].find('code', class_='type')) or clean_cell(cells[1]),
            'references': reference_of(cells[2], relation_name) if len(cells) >= 4 else '',
            'description_zh': clean_cell(cells[-1]),
        })
    return [row for row in rows if row['name']]


# ------------------------------------------------------------------ 本站手册

class Manual:
    """一个版本的本站手册。按需读页、缓存解析结果，用完整个对象丢掉。"""

    def __init__(self, tree):
        self.tree = tree
        self._soups = {}

    def soup(self, filename):
        if filename not in self._soups:
            from pgweb.docs.models import DocPage
            page = (DocPage.objects.filter(version=self.tree, file=filename)
                    .only('content').first()) if filename else None
            self._soups[filename] = (BeautifulSoup(page.content or '', 'html.parser')
                                     if page is not None else None)
        return self._soups[filename]

    def loaded(self):
        from pgweb.docs.models import DocPage
        return DocPage.objects.filter(version=self.tree).exists()

    def files(self, pattern):
        from pgweb.docs.models import DocPage
        regex = re.compile(pattern)
        return sorted(f for f in DocPage.objects.filter(version=self.tree)
                      .values_list('file', flat=True) if regex.match(f))

    def table(self, filename, anchor, name):
        return locate_table(self.soup(filename), name, anchor)

    def overview(self):
        """总览表：关系名 → 中文一句话。两列表格且首列是 structname 才算。"""
        out = {}
        for filename in OVERVIEW_FILES:
            soup = self.soup(filename)
            if soup is None:
                continue
            for div in soup.select('div.table'):
                table = div.find('table', class_='table') or div.find('table')
                if table is None:
                    continue
                head = table.find('thead')
                if head is None or len(head.find_all(['th', 'td'])) != 2:
                    continue
                body = table.find('tbody') or table
                for row in body.find_all('tr', recursive=False):
                    cells = row.find_all(['td', 'th'], recursive=False)
                    if len(cells) != 2:
                        continue
                    label = cells[0].find('code', class_='structname')
                    if label is None:
                        continue
                    name = text_of(label)
                    if NAME_RE.match(name) and name not in out:
                        out[name] = clean_cell(cells[1])
        return out


def doc_ref(snapshot, slug):
    """快照里的手册坐标：{'file', 'anchor', 'slug'}。9.x 也照推，渲染时再查本站有没有那一版。"""
    url = snapshot.get('source_url') or ''
    if '.html' not in url:
        url = snapshot.get('documentation_url') or ''
    if '.html' not in url:
        return {'file': '', 'anchor': '', 'slug': slug}
    path, _, anchor = url.partition('#')
    # `#docContent` 是整页锚点，不指向任何一张表。
    return {'file': path.rsplit('/', 1)[-1], 'anchor': '' if anchor == 'docContent' else anchor,
            'slug': slug}


# ------------------------------------------------------------------ 快照比较

def compare_snapshots(left, right, from_version, to_version, wording=True):
    """cat `compare_snapshots()` 的移植：两份快照之间的变化记录，没有变化返回 None。

    `wording=False` 时只比字段名、类型与顺序——20 是从手册推导的，描述与引用两侧
    不同源，比出来的差异说明不了任何事情。
    """
    a = {c['name']: c for c in left.get('columns') or ()}
    b = {c['name']: c for c in right.get('columns') or ()}
    change = {
        'from': from_version, 'to': to_version,
        'status': 'added' if not left else 'removed' if not right else 'changed',
        'added_columns': [c for c in right.get('columns') or () if c['name'] not in a],
        'removed_columns': [c for c in left.get('columns') or () if c['name'] not in b],
        'type_changes': [], 'description_changes': [], 'reference_changes': [],
        'attribute_changes': [],
        'relation_description_changed': bool(
            wording and left and right and left.get('description') != right.get('description')),
        'column_order_changed': False,
    }
    common = a.keys() & b.keys()
    for name in common:
        if a[name].get('type') != b[name].get('type'):
            change['type_changes'].append({'name': name, 'from': a[name].get('type', ''),
                                           'to': b[name].get('type', '')})
        if not wording:
            continue
        if a[name].get('description', '') != b[name].get('description', ''):
            change['description_changes'].append({'name': name, 'from': a[name].get('description', ''),
                                                  'to': b[name].get('description', '')})
        if a[name].get('references', '') != b[name].get('references', ''):
            change['reference_changes'].append({'name': name, 'from': a[name].get('references', ''),
                                                'to': b[name].get('references', '')})
        for attribute, fallback in (('hidden', False), ('not_null', False),
                                    ('type_modifier', -1), ('array_dimensions', 0)):
            if a[name].get(attribute, fallback) != b[name].get(attribute, fallback):
                change['attribute_changes'].append({
                    'name': name, 'attribute': attribute,
                    'from': a[name].get(attribute, fallback), 'to': b[name].get(attribute, fallback)})
    change['column_order_changed'] = ([n for n in a if n in common]
                                      != [n for n in b if n in common])
    for key in ('type_changes', 'description_changes', 'reference_changes', 'attribute_changes'):
        change[key].sort(key=lambda item: item['name'])
    change['structural'] = bool(change['added_columns'] or change['removed_columns']
                                or change['type_changes'] or change['attribute_changes']
                                or change['column_order_changed'] or not left or not right)
    if (change['structural'] or change['description_changes'] or change['reference_changes']
            or change['relation_description_changed']):
        return change
    return None


# ------------------------------------------------------------------ 中文采集

def trim_snapshot(snapshot, slug):
    """cat 快照裁成本站要存的形状：去掉大块原始记录与本地路径，加手册坐标。"""
    out = {k: v for k, v in snapshot.items() if k not in SNAPSHOT_DROP}
    validation = snapshot.get('runtime_validation') or {}
    out['runtime_verified'] = bool(validation.get('passed'))
    out['release'] = validation.get('release', '') or ''
    out['doc'] = doc_ref(snapshot, slug)
    out['description_zh'] = ''
    out['zh_from'] = ''
    for column in out.get('columns') or ():
        column['description_zh'] = ''
        column['zh_from'] = ''
    return out


def harvest_version(manual, relations, major, report):
    """把一个版本的手册译文写进这一版的快照里。"""
    for relation in relations:
        snapshot = relation['versions'].get(major)
        if snapshot is None:
            continue
        doc = snapshot['doc']
        div = manual.table(doc['file'], doc['anchor'], relation['name']) if doc['file'] else None
        if div is None:
            report['unlocated'].append('{} @ {}'.format(relation['name'], major))
            continue
        description = relation_description(div)
        if description:
            snapshot['description_zh'] = description
            snapshot['zh_from'] = 'doc'
        translated = {row['name']: row for row in parse_columns(div, relation['name'])}
        for column in snapshot.get('columns') or ():
            row = translated.get(column['name']) or translated.get(column.get('documented_name') or '')
            if row is None or not row['description_zh']:
                continue
            column['description_zh'] = row['description_zh']
            column['zh_from'] = 'doc'
            report['columns_doc'] += 1


def inherit_within(relation, order):
    """同一关系跨版本借用译文：只在英文描述完全相同时借。"""
    snapshots = relation['versions']
    sources = {major: snapshots[major] for major in order}

    def pick(target, english, getter):
        best, best_key = '', None
        for major in order:
            if major == target:
                continue
            snapshot = sources[major]
            value, origin, text = getter(snapshot)
            if origin != 'doc' or not value or text != english:
                continue
            key = (abs(order.index(major) - order.index(target)), -order.index(major))
            if best_key is None or key < best_key:
                best, best_key = value, key
        return best

    for major in order:
        snapshot = snapshots[major]
        english = snapshot.get('description') or ''
        if english and not snapshot.get('description_zh'):
            borrowed = pick(major, english,
                            lambda s: (s.get('description_zh', ''), s.get('zh_from', ''),
                                       s.get('description', '')))
            if borrowed:
                snapshot['description_zh'] = borrowed
                snapshot['zh_from'] = 'inherited'
        for column in snapshot.get('columns') or ():
            english = column.get('description') or ''
            if not english or column.get('description_zh'):
                continue
            name = column['name']

            def getter(s, name=name):
                for other in s.get('columns') or ():
                    if other['name'] == name:
                        return (other.get('description_zh', ''), other.get('zh_from', ''),
                                other.get('description', ''))
                return '', '', None

            borrowed = pick(major, english, getter)
            if borrowed:
                column['description_zh'] = borrowed
                column['zh_from'] = 'inherited'


def inherit_from_alias(relations):
    """只在源码里定义的变体（`pg_stat_xact_*`、`pg_statio_*` 等）手册里没有自己的表。

    它们的英文字段描述是基表的逐字拷贝，同一条判据（英文完全相同）成立，就借基表的译文。
    """
    by_name = {relation['name']: relation for relation in relations}
    borrowed = 0
    for relation in relations:
        for major, snapshot in relation['versions'].items():
            base_name = snapshot.get('alias_of') or snapshot.get('derived_from')
            base = by_name.get(base_name) if base_name else None
            if base is None:
                continue
            source = base['versions'].get(major)
            if source is None:
                continue
            translated = {c['name']: c for c in source.get('columns') or ()}
            for column in snapshot.get('columns') or ():
                if column.get('description_zh'):
                    continue
                other = translated.get(column['name'])
                if other is None or not other.get('description_zh'):
                    continue
                if (column.get('description') or '') != (other.get('description') or ''):
                    continue
                column['description_zh'] = other['description_zh']
                column['zh_from'] = 'inherited'
                borrowed += 1
    return borrowed


# ------------------------------------------------------------ 20 开发版推导

def anchor_of(div):
    """一张表的可链接锚点。

    只认表自己的语义锚点（`PG-STAT-ACTIVITY-VIEW` 这种全大写的）。DocBook 自动
    生成的 `id-1.10.4.13.4` 换一版就变，写进链接等于埋死链；小节锚点对每个关系
    独占一页的目录表来说也只是重复页面地址。
    """
    value = div.get('id') or ''
    return value if SEMANTIC_ANCHOR_RE.match(value) else ''


def devel_column(row, previous):
    """devel 手册里的一行字段，英文描述沿用 19 的同名字段。"""
    documented = row['documented_type']
    # 译文偶尔把类型名也翻了（`带时区的时间戳`）。译过的类型名不是类型，照旧用 19 的。
    if documented and not ASCII_TYPE_RE.match(documented):
        documented = ''
    canonical = canonical_type(documented) or (previous or {}).get('type', '')
    column = {
        'name': row['name'],
        'type': canonical,
        'description': (previous or {}).get('description', '') if previous else '',
        'description_zh': row['description_zh'],
        'zh_from': 'doc' if row['description_zh'] else '',
        'hidden': bool((previous or {}).get('hidden', False)),
        'not_null': bool((previous or {}).get('not_null', False)),
        'type_modifier': (previous or {}).get('type_modifier', -1),
        'array_dimensions': (previous or {}).get('array_dimensions',
                                                 1 if canonical.endswith('[]') else 0),
        # 手册推导不出真实 attnum，新字段照实留空。
        'attnum': (previous or {}).get('attnum') if previous else None,
    }
    if documented and documented != canonical:
        column['documented_type'] = documented
    # 引用：自引用（pg_class.reltoastrelid → pg_class.oid）与「any OID column」这类
    # 写法解析不出来，解析不到就沿用上一版的，不要把已知的引用弄丢。
    reference = row['references'] or (previous or {}).get('references', '')
    if reference:
        column['references'] = reference
    if previous and previous.get('type_oid') is not None:
        column['type_oid'] = previous['type_oid']
    if previous and previous.get('schema_note'):
        column['schema_note'] = previous['schema_note']
    return column


def merge_devel_columns(parsed, previous_columns, base_doc):
    """把 devel 手册解析出的字段与上一版运行时字段对账。

    返回 (要留下的手册行, 要沿用的旧字段, 丢掉的手册行字段名)。

    两类差异是手册的老账，不是版本变化：

    - 手册记着、上一版运行时没有的字段。中文手册 18/19/devel 都还留着 PG 18 已经
      删掉的 `pg_stat_wal.wal_write`，照手册推会说 20 新增了四个字段。上一版手册
      也记着它，就说明这是手册没跟上，丢掉。
    - 上一版运行时有、两版手册都没记的字段（cat 从源码头文件补出来的那些）。手册
      从来没记过它，devel 手册没记同样说明不了它被删了，按旧位置留下。
    """
    if base_doc is None:
        return parsed, [], []
    present = {column['name'] for column in previous_columns}
    documented = set(base_doc)
    kept, dropped = [], []
    for row in parsed:
        if row['name'] in present or row['name'] not in documented:
            kept.append(row)
        else:
            dropped.append(row['name'])
    names = {row['name'] for row in kept}
    carried = [column for column in previous_columns
               if column['name'] not in names and column['name'] not in documented]
    return kept, carried, dropped


def splice_carried(columns, carried, previous_columns):
    """把沿用的旧字段插回它在上一版里的相对位置。"""
    order = [column['name'] for column in previous_columns]
    for column in carried:
        index = order.index(column['name'])
        before = [name for name in order[:index]]
        at = 0
        for position, existing in enumerate(columns):
            if existing['name'] in before:
                at = position + 1
        columns.insert(at, json.loads(json.dumps(column)))
    return columns


def trusted_order(columns, previous_columns):
    """手册顺序不可信时，已知字段按上一版的顺序排，新字段留在手册给它的位置。

    既然不据手册顺序报「顺序调整」，快照里也不该按手册顺序摆——否则页面上两版的
    字段表看着换了位置，本版变化那句话却说没变。
    """
    index = {column['name']: position for position, column in enumerate(previous_columns)}
    pool = sorted((c for c in columns if c['name'] in index), key=lambda c: index[c['name']])
    out = []
    for column in columns:
        out.append(pool.pop(0) if column['name'] in index else column)
    return out


def doc_order_is_trustworthy(base_doc, previous_columns):
    """上一版手册的字段顺序和运行时顺序一致吗？

    不一致（`pg_stat_wal`、`pg_stat_database`）说明这个关系的手册顺序本来就不跟
    真实顺序走，devel 手册的顺序差异也就说明不了目录变了，不据此报顺序调整。
    """
    if base_doc is None:
        return False
    runtime = [column['name'] for column in previous_columns]
    common = set(base_doc) & set(runtime)
    return [name for name in base_doc if name in common] == [name for name in runtime if name in common]


def devel_source_url(filename, anchor):
    return 'https://www.postgresql.org/docs/devel/{}{}'.format(filename, '#' + anchor if anchor else '')


def devel_definition_url(previous):
    """源码定义链接换到 master 分支，路径不变。"""
    url = (previous or {}).get('definition_source_url') or ''
    return re.sub(r'(/postgres/postgres/)[^/]+/', r'\1master/', url) if url else ''


def derive_devel(relations, report, base_major):
    """从本站 devel 手册推导开发版快照，以及 cat 最后一版 → 开发版的变化记录。

    本地没有 devel 手册时整段跳过，只在报告里说明。
    """
    manual = Manual(DEVEL_TREE)
    if not manual.loaded():
        report['devel'] = {'derived': False, 'reason': '本地没有 devel 手册'}
        return None

    overview = manual.overview()
    base_manual = Manual(base_major)
    by_name = {relation['name']: relation for relation in relations}
    base_names = [r['name'] for r in relations if base_major in r['versions']]

    def carry(relation, previous, doc, reason):
        """原样沿用 19 的字段：手册里没有这张表，或表里写的是占位符字段名。"""
        snapshot = json.loads(json.dumps(previous))
        snapshot['carried_from'] = base_major
        snapshot['carry_reason'] = reason
        snapshot['doc'] = dict(doc, slug='devel')
        snapshot['source_url'] = devel_source_url(doc['file'], doc['anchor'])
        snapshot['definition_source_url'] = devel_definition_url(previous)
        snapshot['schema_source'] = 'documentation'
        snapshot['runtime_verified'] = False
        snapshot['relation_oid'] = None
        snapshot['release'] = ''
        relation['versions'][DEVEL_MAJOR] = snapshot

    # 上一版手册里的字段顺序。开发版的顺序取自 devel 手册，上一版存的是运行时顺序；
    # 两者本来就不一致（pg_stat_database、pg_stat_wal），只有手册自己改了顺序才算变化。
    doc_order = {}
    # 被当成手册老账处理掉的字段，报告里列出来。
    artifacts = {}
    added, removed, carried, kept = [], [], [], []
    for name in base_names:
        relation = by_name[name]
        previous = relation['versions'][base_major]
        doc = previous['doc']
        base_div = base_manual.table(doc['file'], doc['anchor'], name) if doc['file'] else None
        if base_div is not None:
            doc_order[name] = [row['name'] for row in parse_columns(base_div, name)]
        div = manual.table(doc['file'], doc['anchor'], name) if doc['file'] else None
        if div is None:
            if previous.get('alias_of') or previous.get('derived_from'):
                carry(relation, previous, doc, '手册没有这张表')
                carried.append(name)
            else:
                removed.append(name)
            continue
        anchor = anchor_of(div)
        parsed = parse_columns(div, name)
        if parsed and not all(COLUMN_NAME_RE.match(row['name']) for row in parsed):
            # `pg_statistic` 的槽位在手册里写成 `stakindN`，那是占位符不是字段名。
            carry(relation, previous, doc, '手册用占位符字段名')
            carried.append(name)
            continue
        previous_list = list(previous.get('columns') or ())
        previous_columns = {c['name']: c for c in previous_list}
        parsed, carried_columns, dropped = merge_devel_columns(
            parsed, previous_list, doc_order.get(name))
        columns = [devel_column(row, previous_columns.get(row['name'])) for row in parsed]
        columns = splice_carried(columns, carried_columns, previous_list)
        if not doc_order_is_trustworthy(doc_order.get(name), previous_list):
            columns = trusted_order(columns, previous_list)
        if not columns:
            removed.append(name)
            continue
        stale = dropped + [column['name'] for column in carried_columns]
        if stale:
            artifacts[name] = sorted(stale)
        description_zh = relation_description(div)
        snapshot = {
            'description': previous.get('description', ''),
            'description_zh': description_zh,
            'zh_from': 'doc' if description_zh else '',
            'columns': columns,
            'source_url': devel_source_url(doc['file'], anchor or doc['anchor']),
            'schema_source': 'documentation',
            'definition_source_url': devel_definition_url(previous),
            'relation_oid': None,
            'shared': bool(previous.get('shared')),
            'relkind': previous.get('relkind', ''),
            'system_columns': previous.get('system_columns') or [],
            'runtime_verified': False,
            'release': '',
            'doc': {'file': doc['file'], 'anchor': anchor or doc['anchor'], 'slug': 'devel'},
        }
        for key in ('derived_from', 'alias_of'):
            if previous.get(key):
                snapshot[key] = previous[key]
        relation['versions'][DEVEL_MAJOR] = snapshot
        kept.append(name)

    # devel 手册里新出现的关系。已经在手的关系一个都不能再追加一遍——
    # 上一版没有、更早的版本有过的关系也在 by_name 里。
    known = set(by_name)

    def take(name, kind, filename):
        """把 devel 手册里这个关系收下：老关系挂一份新快照，新关系建一条记录。"""
        if name in known and DEVEL_MAJOR in by_name[name]['versions']:
            return
        built = new_devel_relation(manual, name, kind, filename, overview)
        if built is None:
            return
        if name in by_name:
            # 早先移除、devel 手册里又有了：挂到原来那条记录上，不另建一条。
            relation = by_name[name]
            relation['versions'][DEVEL_MAJOR] = built['versions'][DEVEL_MAJOR]
            relation['summary_zh'] = relation['summary_zh'] or built['summary_zh']
        else:
            relations.append(built)
            by_name[name] = built
        known.add(name)
        added.append(name)

    for filename in manual.files(r'^(?:catalog|view)-pg-[a-z0-9-]+\.html$'):
        soup = manual.soup(filename)
        if soup is None:
            continue
        # 页面名就是关系名（catalog-pg-class.html → pg_class），再要求页内有同名的表。
        name = 'pg_' + filename.split('-pg-', 1)[1][:-len('.html')].replace('-', '_')
        if not any(name in table_structnames(div)[0] for div in soup.select('div.table')):
            continue
        take(name, 'catalog' if filename.startswith('catalog-') else 'view', filename)
    for filename, kind in (('monitoring-stats.html', 'statistics'),
                           ('progress-reporting.html', 'progress')):
        soup = manual.soup(filename)
        if soup is None:
            continue
        for div in soup.select('div.table'):
            for name in sorted(n for n in table_structnames(div)[0] if NAME_RE.match(n)):
                take(name, kind, filename)

    # cat 最后一版 → 开发版的变化记录：只比字段名、类型与顺序。
    changed, structural = [], []
    columns_added = columns_removed = type_changes = 0
    for relation in relations:
        left = relation['versions'].get(base_major) or {}
        right = relation['versions'].get(DEVEL_MAJOR) or {}
        if not left and not right:
            continue
        change = compare_snapshots(left, right, base_major, DEVEL_MAJOR, wording=False)
        if change is None:
            continue
        before = doc_order.get(relation['name'])
        if before is not None and change['status'] == 'changed':
            after = [c['name'] for c in right.get('columns') or ()]
            common = set(before) & set(after)
            reordered = ([n for n in before if n in common] != [n for n in after if n in common])
            # 手册顺序本来就不跟运行时顺序走的关系，顺序差异说明不了目录变了。
            change['column_order_changed'] = reordered and doc_order_is_trustworthy(
                before, left.get('columns') or ())
            change['structural'] = bool(change['added_columns'] or change['removed_columns']
                                        or change['type_changes'] or change['column_order_changed'])
            if not change['structural']:
                continue
        if relation['name'] in carried:
            change['carried'] = True
        relation['changes'].append(change)
        if change['status'] == 'changed':
            changed.append(relation['name'])
            columns_added += len(change['added_columns'])
            columns_removed += len(change['removed_columns'])
            type_changes += len(change['type_changes'])
            if change['structural']:
                structural.append(relation['name'])

    report['devel'] = {
        'derived': True, 'relations': len(kept) + len(carried) + len(added),
        'from_manual': len(kept), 'carried': sorted(carried), 'added': sorted(added),
        'removed': sorted(removed), 'changed': len(changed), 'structural': len(structural),
        # 手册与运行时对不上的字段，按手册老账处理，不计入 20 的变化。
        'doc_artifacts': {name: artifacts[name] for name in sorted(artifacts)},
    }
    return {
        'from': base_major, 'to': DEVEL_MAJOR,
        'added_relations': sorted(added), 'removed_relations': sorted(removed),
        'changed_relations': sorted(changed), 'structurally_changed_relations': sorted(structural),
        'added_columns': columns_added, 'removed_columns': columns_removed,
        'type_changes': type_changes, 'description_changes': 0,
    }


def new_devel_relation(manual, name, kind, filename, overview):
    """devel 手册里新出现的关系，作为 20 的新增关系入库。"""
    div = manual.table(filename, '', name)
    if div is None:
        return None
    columns = parse_columns(div, name)
    if not columns:
        return None
    anchor = anchor_of(div)
    description_zh = relation_description(div)
    snapshot = {
        'description': '',
        'description_zh': description_zh,
        'zh_from': 'doc' if description_zh else '',
        'columns': [devel_column(row, None) for row in columns],
        'source_url': devel_source_url(filename, anchor),
        'schema_source': 'documentation',
        'definition_source_url': '',
        'relation_oid': None, 'shared': False,
        'relkind': 'v' if kind != 'catalog' else 'r',
        'system_columns': [], 'runtime_verified': False, 'release': '',
        'doc': {'file': filename, 'anchor': anchor, 'slug': 'devel'},
    }
    return {
        'name': name, 'kind': kind, 'summary': '',
        'summary_zh': overview.get(name) or first_sentence(description_zh),
        'first_version': DEVEL_MAJOR, 'last_version': DEVEL_MAJOR,
        'versions': {DEVEL_MAJOR: snapshot}, 'changes': [],
    }


# ------------------------------------------------------------------ 导出

def read_json(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def repo_head(root):
    try:
        out = subprocess.run(['git', '-C', root, 'rev-parse', '--short', 'HEAD'],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def version_row(item, position, transition):
    major = item['id']
    return {
        'major': major, 'label': item.get('label', major),
        'status': item.get('status', ''), 'support_status': item.get('support_status', ''),
        'source_tag': item.get('source_tag', '') or '',
        'documentation_version': item.get('documentation_version', '') or '',
        'release': item.get('release', '') or '',
        'doc_slug': major,
        'relation_count': item.get('relation_count') or 0,
        'column_count': item.get('column_count') or 0,
        'kinds': dict(item.get('kinds') or {}),
        'runtime_verified': bool(item.get('runtime_verified')),
        'schema_source': 'runtime+documentation',
        'transition': transition or {},
        'position': position,
    }


def export_snapshot(root=DEFAULT_ROOT):
    """把 cat 仓库 + 本站手册读成一份自包含快照。"""
    root = os.path.expanduser(root)
    path = os.path.join(root, 'data', 'catalog.json')
    if not os.path.exists(path):
        raise ValueError('找不到系统目录数据：{}'.format(path))
    data = read_json(path)
    source_rev = '{}@{}'.format(data.get('generated_at', ''), repo_head(root) or 'unknown')
    report = {'columns_doc': 0, 'unlocated': [], 'devel': {}}

    transitions = {item['to']: item for item in data.get('transitions') or ()}
    versions = [version_row(item, position, transitions.get(item['id']))
                for position, item in enumerate(data['versions'])]
    order = [version['major'] for version in versions]

    relations = []
    for item in data['relations']:
        present = [major for major in order if major in item['versions']]
        relations.append({
            'name': item['name'], 'kind': item['kind'], 'summary': item.get('summary', '') or '',
            'summary_zh': '',
            'first_version': item.get('first_version', '') or (present[0] if present else ''),
            'last_version': item.get('last_version', '') or (present[-1] if present else ''),
            'versions': {major: trim_snapshot(item['versions'][major], major) for major in present},
            'changes': [dict(change) for change in item.get('changes') or ()],
        })

    # 中文采集：本站只有 10 及以后的手册。
    overviews = {}
    for version in versions:
        if version['major'].startswith('9.'):
            continue
        manual = Manual(int(version['major']))
        if not manual.loaded():
            continue
        harvest_version(manual, relations, version['major'], report)
        overviews[version['major']] = manual.overview()
        del manual

    devel_transition = derive_devel(relations, report, order[-1])
    if devel_transition is not None:
        devel = Manual(DEVEL_TREE)
        overviews[DEVEL_MAJOR] = devel.overview()
        del devel
        versions.append({
            'major': DEVEL_MAJOR, 'label': DEVEL_MAJOR + ' devel', 'status': 'devel',
            'support_status': 'devel',
            'source_tag': 'master', 'documentation_version': 'devel', 'release': '',
            'doc_slug': 'devel',
            'relation_count': sum(1 for r in relations if DEVEL_MAJOR in r['versions']),
            'column_count': sum(len(r['versions'][DEVEL_MAJOR].get('columns') or ())
                                for r in relations if DEVEL_MAJOR in r['versions']),
            'kinds': {kind: sum(1 for r in relations
                                if r['kind'] == kind and DEVEL_MAJOR in r['versions'])
                      for kind in CATALOG_KIND_ORDER},
            'runtime_verified': False, 'schema_source': 'documentation',
            'transition': devel_transition, 'position': len(versions),
        })
        order.append(DEVEL_MAJOR)

    # 译文回退与总览一句话。
    for relation in relations:
        present = [major for major in order if major in relation['versions']]
        relation['present_in'] = present
        inherit_within(relation, present)
    report['columns_alias'] = inherit_from_alias(relations)

    for relation in relations:
        for major in SUMMARY_ORDER:
            value = (overviews.get(major) or {}).get(relation['name'])
            if value:
                relation['summary_zh'] = value
                break
        if not relation['summary_zh'] and relation['kind'] == 'progress':
            for major in SUMMARY_ORDER:
                snapshot = relation['versions'].get(major)
                if snapshot and snapshot.get('description_zh'):
                    relation['summary_zh'] = first_sentence(snapshot['description_zh'])
                    break

    # 排序、派生列与内容指纹。
    by_kind = {}
    for relation in sorted(relations, key=lambda r: r['name']):
        by_kind.setdefault(relation['kind'], []).append(relation['name'])
    place = {name: CATALOG_KIND_ORDER.get(kind, 9) * 1000 + index
             for kind, names in by_kind.items() for index, name in enumerate(names)}

    for relation in relations:
        present = relation['present_in']
        last = relation['versions'][present[-1]] if present else {}
        relation['changed_in'] = [change['to'] for change in relation['changes']
                                  if change['status'] == 'changed' and change.get('structural')]
        relation['first_version'] = present[0] if present else ''
        relation['last_version'] = present[-1] if present else ''
        relation['column_count'] = len(last.get('columns') or ())
        relation['relation_oid'] = last.get('relation_oid')
        relation['relkind'] = last.get('relkind', '') or ''
        relation['shared'] = bool(last.get('shared'))
        relation['position'] = place[relation['name']]
        relation['source_rev'] = source_rev
    relations.sort(key=lambda r: r['position'])

    stats = dict(data.get('stats') or {})
    stats['version_count'] = len(versions)
    stats['relation_count'] = len(relations)
    stats['relation_snapshots'] = sum(len(r['versions']) for r in relations)
    stats['column_snapshots'] = sum(len(s.get('columns') or ())
                                    for r in relations for s in r['versions'].values())
    stats['structural_changes'] = sum(1 for r in relations for c in r['changes']
                                      if c.get('structural'))
    stats['adjacent_change_records'] = sum(len(r['changes']) for r in relations)

    return {
        'format': FORMAT,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'root': root,
        'source_rev': source_rev,
        'snapshot_date': data.get('snapshot_date', ''),
        'default_major': data.get('default_version', '18'),
        'stats': stats,
        'scope': data.get('scope') or {},
        'harvest': report,
        'versions': versions,
        'relations': relations,
    }


# ------------------------------------------------------------------ 导入

VERSION_FIELDS = ('label', 'status', 'support_status', 'source_tag', 'documentation_version',
                  'release', 'doc_slug', 'relation_count', 'column_count', 'kinds',
                  'runtime_verified', 'schema_source', 'transition', 'position')
RELATION_FIELDS = ('kind', 'summary', 'summary_zh', 'first_version', 'last_version', 'present_in',
                   'changed_in', 'column_count', 'relation_oid', 'relkind', 'shared', 'versions',
                   'changes', 'position', 'source_rev')


def require(item, fields, label):
    """缺字段要在校验阶段说清楚是哪一个，不能等到写库时抛 KeyError。"""
    absent = [field for field in fields if field not in item]
    if absent:
        raise ValueError('{} 缺少字段：{}'.format(label, '、'.join(absent)))


def validate(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError('快照不是一个对象')
    if snapshot.get('format') != FORMAT:
        raise ValueError('快照格式为 {}，期望 {}'.format(snapshot.get('format'), FORMAT))
    for key in ('versions', 'relations'):
        if not isinstance(snapshot.get(key), list) or not snapshot[key]:
            raise ValueError('快照缺少 {}'.format(key))
    majors = set()
    for version in snapshot['versions']:
        if not version.get('major'):
            raise ValueError('版本缺少 major')
        require(version, VERSION_FIELDS, '版本 {}'.format(version['major']))
        majors.add(version['major'])
    if len(majors) != len(snapshot['versions']):
        raise ValueError('版本 major 有重复')
    seen = set()
    for relation in snapshot['relations']:
        name = relation.get('name', '')
        if not NAME_RE.match(name):
            raise ValueError('关系名格式不对：{!r}'.format(name))
        require(relation, RELATION_FIELDS, '关系 ' + name)
        if name in seen:
            raise ValueError('关系重复：{}'.format(name))
        seen.add(name)
        if relation.get('kind') not in CATALOG_KIND_ORDER:
            raise ValueError('{} 的类别不认识：{!r}'.format(name, relation.get('kind')))
        if not relation.get('versions'):
            raise ValueError('{} 没有任何版本快照'.format(name))
        unknown = set(relation['versions']) - majors
        if unknown:
            raise ValueError('{} 引用了未知版本：{}'.format(name, sorted(unknown)))
    for item in snapshot['relations']:
        item_hash(CatalogRelation, item, RELATION_FIELDS)
    return True


def changed_names(snapshot):
    """这次导入会改动哪些关系。按稳定内容指纹比对，无变化的整条跳过。"""
    stored = {row.pk: row for row in CatalogRelation.objects.only('name', 'content_hash')}
    added, updated, unchanged = [], [], []
    for item in snapshot['relations']:
        calculated = item_hash(CatalogRelation, item, RELATION_FIELDS)
        row = stored.get(item['name'])
        if row is None:
            added.append(item['name'])
        elif row.content_hash != calculated:
            updated.append(item['name'])
        else:
            unchanged.append(item['name'])
    incoming = {item['name'] for item in snapshot['relations']}
    missing = {
        'relations': sorted(set(stored) - incoming),
        'versions': [row.major for row in CatalogVersion.objects.all()
                     if row.major not in {v['major'] for v in snapshot['versions']}],
    }
    return added, updated, unchanged, missing


def retention_note(missing):
    """没加 --prune 时说清楚库里留了什么，免得以为已经删掉了。"""
    parts = []
    if missing['relations']:
        parts.append('{} 个关系'.format(len(missing['relations'])))
    if missing['versions']:
        parts.append('版本 ' + '、'.join(missing['versions']))
    if not parts:
        return ''
    return '快照里没有但库里还在：{}。未加 --prune，这些记录保留。'.format('，'.join(parts))


def coverage(snapshot):
    """译文覆盖：多少条字段记录有本版译文、多少条借用、多少条没有。"""
    counts = {'doc': 0, 'inherited': 0, 'none': 0}
    relation_zh = {'doc': 0, 'inherited': 0, 'none': 0}
    for relation in snapshot['relations']:
        for version in relation['versions'].values():
            relation_zh[version.get('zh_from') or 'none'] += 1
            for column in version.get('columns') or ():
                counts[column.get('zh_from') or 'none'] += 1
    return {'columns': counts, 'relations': relation_zh,
            'summary_zh': sum(1 for r in snapshot['relations'] if r['summary_zh'])}


def preview(snapshot):
    """不写库，只报告这次导入会改动什么。"""
    validate(snapshot)
    added, updated, unchanged, missing = changed_names(snapshot)
    return {
        'versions': len(snapshot['versions']),
        'relations': len(snapshot['relations']),
        'added': added, 'changed': len(updated), 'unchanged': len(unchanged), 'missing': missing,
        'note': retention_note(missing),
        'snapshots': sum(len(r['versions']) for r in snapshot['relations']),
        'columns': sum(len(s.get('columns') or ())
                       for r in snapshot['relations'] for s in r['versions'].values()),
        'coverage': coverage(snapshot),
        'harvest': {k: v for k, v in (snapshot.get('harvest') or {}).items() if k != 'unlocated'},
    }


@transaction.atomic
def import_snapshot(snapshot, prune=False):
    """按关系名原位更新。无变化的关系整条跳过，不重写 JSON 列。"""
    validate(snapshot)
    report = {'versions': 0, 'added': 0, 'updated': 0, 'unchanged': 0}

    for item in snapshot['versions']:
        CatalogVersion.objects.update_or_create(
            major=item['major'], defaults={field: item[field] for field in VERSION_FIELDS})
        report['versions'] += 1

    added, updated, unchanged, missing = changed_names(snapshot)
    write = set(added) | set(updated)
    for item in snapshot['relations']:
        if item['name'] not in write:
            continue
        CatalogRelation.objects.update_or_create(
            name=item['name'], defaults=hashed_defaults(CatalogRelation, item, RELATION_FIELDS))
    report.update({'added': len(added), 'updated': len(updated), 'unchanged': len(unchanged)})

    report['pruned'] = bool(prune)
    report['missing'] = missing
    if prune:
        stale = CatalogRelation.objects.filter(name__in=missing['relations'])
        report['removed'] = {'relations': stale.count(), 'versions': list(missing['versions'])}
        stale.delete()
        CatalogVersion.objects.filter(major__in=missing['versions']).delete()
    else:
        report['removed'] = {'relations': 0, 'versions': []}
        report['note'] = retention_note(missing)

    report['coverage'] = coverage(snapshot)
    report['harvest'] = {k: v for k, v in (snapshot.get('harvest') or {}).items()
                         if k != 'unlocated'}
    report['unlocated'] = len((snapshot.get('harvest') or {}).get('unlocated') or ())
    from . import catalog
    transaction.on_commit(catalog.forget)
    return report


def digest(snapshot):
    """一份快照的内容指纹，方便核对两端加载的是同一份。"""
    payload = json.dumps({'versions': snapshot['versions'], 'relations': snapshot['relations']},
                         ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
