"""导入配置参数百科。

两步，和系统目录栏目同形：`export_snapshot()` 把 guc 仓库 + 本站手册读成一份自包含快照，
`import_snapshot()` 把快照写进库。拆开是为了让同一份快照分别加载本地与生产——
导出要读本地手册译文，导入只认快照，生产机上不需要 guc 仓库。

本站在 guc.pg.center 之上叠两层：

1. 手册译文：每个参数、每个版本在本站手册 `runtime-config-*.html` 里的 `<dd>` 说明段，
   清洗、改写链接后存进快照（10 – 19 与 devel）；
2. PostgreSQL 20 开发版快照：guc 到 19 beta 3 为止，20 从本站 devel 手册推导。

Pigsty 相关内容一律不进本站：`pigsty` 块与 `pigsty_rationale_pending_review` 整个丢掉，
编辑文字里提到 Pigsty 的句子也清掉（docs/guc-column.md §3.3）。

比较口径与可读默认值只有 `guc_common` 一份，页面与导入共用。
"""

import collections
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlsplit

import bleach
from bs4 import BeautifulSoup, Tag
from django.db import transaction

from pgweb.docs.versions import DEVEL_MAJOR_VERSION

from .catalog_importer import Manual, text_of
from .guc_common import diff_fields, human_value, is_default_change, is_substantive
from .models import (GUC_CATEGORY_ORDER, GUC_CATEGORY_ZH, GUC_FIELDS, GUC_GROUP_ORDER,
                     GUC_GROUP_SLUG, GucParameter, GucVersion, guc_group_of)


FORMAT = 1
DEFAULT_ROOT = os.path.expanduser('~/pg.center/guc')

# 本站 devel 手册就是开发版；guc 里没有这一版，整版由手册推导。
DEVEL_MAJOR = str(DEVEL_MAJOR_VERSION)
DEVEL_TREE = 0
DEVEL_SLUG = 'devel'

NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
SPACE = re.compile(r'\s+')
# '19beta3' → 主版本 19、预发行 beta 3。
PRERELEASE_RE = re.compile(r'^(\d+(?:\.\d+)?)(alpha|beta|rc)(\d*)$')
PRERELEASE_RANK = {'alpha': 0, 'beta': 1, 'rc': 2, '': 3}
RUNTIME_FILE_RE = r'^runtime-config(?:-[a-z0-9-]+)?\.html$'
OFFICIAL_URL = 'https://www.postgresql.org/docs/{}/{}'

# 手册里写的类型名 → pg_settings.vartype；其它（pg_lsn、timestamp）归 string。
DOC_VARTYPES = {'boolean': 'bool', 'floating point': 'real', 'integer': 'integer',
                'string': 'string', 'enum': 'enum'}

# devel 手册新参数推不出子分类时的兜底：按页名归到一级分类。
PAGE_GROUPS = {
    'runtime-config-file-locations.html': 'File Locations',
    'runtime-config-connection.html': 'Connections and Authentication',
    'runtime-config-resource.html': 'Resource Usage',
    'runtime-config-wal.html': 'Write-Ahead Log',
    'runtime-config-replication.html': 'Replication',
    'runtime-config-query.html': 'Query Tuning',
    'runtime-config-logging.html': 'Reporting and Logging',
    'runtime-config-statistics.html': 'Statistics',
    'runtime-config-vacuum.html': 'Vacuuming',
    'runtime-config-autovacuum.html': 'Vacuuming',
    'runtime-config-client.html': 'Client Connection Defaults',
    'runtime-config-locks.html': 'Lock Management',
    'runtime-config-compatible.html': 'Version and Platform Compatibility',
    'runtime-config-error-handling.html': 'Error Handling',
    'runtime-config-preset.html': 'Preset Options',
    'runtime-config-custom.html': 'Customized Options',
    'runtime-config-developer.html': 'Developer Options',
}

CARRY_DOCUMENTED = '手册不含 pg_settings 事实，沿用 {}'
CARRY_UNDOCUMENTED = '手册从未收录此参数，沿用 {}'

# 一份快照里存的事实字段，照 pg_settings 的列。
SNAPSHOT_FACTS = ('setting', 'boot_val', 'unit', 'category', 'short_desc', 'extra_desc',
                  'context', 'vartype', 'min_val', 'max_val', 'enumvals')
FIELD_ORDER = [field for field, _ in GUC_FIELDS]


# ---------------------------------------------------------------- 版本键归一

def split_key(key):
    """guc 的版本键拆成 (主版本, 预发行类型, 序号)：'19beta3' → ('19', 'beta', '3')。"""
    match = PRERELEASE_RE.match(key or '')
    if match:
        return match.group(1), match.group(2), match.group(3)
    return key or '', '', ''


def major_of(key):
    return split_key(key)[0]


def label_of(key):
    """'19beta3' → '19 beta 3'；正式版就是版本号本身。"""
    major, kind, number = split_key(key)
    if not kind:
        return major
    return '{} {}{}'.format(major, kind, ' ' + number if number else '')


def version_sort_key(key):
    """'9.0' < '10' < '19beta3' < '19'：字符串比不出先后，只认这个键。"""
    major, kind, number = split_key(key)
    parts = tuple(int(part) for part in major.split('.') if part.isdigit())
    parts = parts + (0,) * (2 - len(parts))
    return parts + (PRERELEASE_RANK.get(kind, 3), int(number or 0))


def manual_tree(major):
    """本站手册的树号：devel 是 0，其余就是版本号（9.6 这种带小数的照传）。"""
    return DEVEL_TREE if major == DEVEL_MAJOR else major


def doc_slug(major):
    return DEVEL_SLUG if major == DEVEL_MAJOR else major


def support_status(major, status):
    """预发行与开发版按自己的状态；其余查本站 Version.supported，查不到按已结束维护。"""
    if status in ('preview', 'devel'):
        return status
    from pgweb.core.models import Version
    row = Version.objects.filter(tree=major).first()
    return 'supported' if row is not None and row.supported else 'end-of-life'


def server_version_of(manifest, key):
    """实测服务器版本去掉括号里的发行版信息：'18.6 (Debian …)' → '18.6'。"""
    snapshot = ((manifest.get('snapshots') or {}).get(key) or {})
    return (snapshot.get('server_version') or '').split('(')[0].strip()


# ------------------------------------------------------------------ HTML 工具

BLOCK_TAGS = {'p', 'div', 'table', 'thead', 'tbody', 'tr', 'td', 'th', 'ul', 'ol', 'li',
              'dl', 'dt', 'dd', 'pre', 'blockquote', 'h4', 'h5', 'br', 'colgroup', 'col'}

DOC_TAGS = ['p', 'br', 'code', 'a', 'em', 'strong', 'b', 'i', 'ul', 'ol', 'li', 'dl', 'dt', 'dd',
            'table', 'thead', 'tbody', 'tr', 'td', 'th', 'pre', 'span', 'div', 'sub', 'sup',
            'kbd', 'samp', 'blockquote', 'h4', 'h5']
DOC_ATTRS = {'a': ['href', 'title'], 'code': ['class'], 'span': ['class'], 'div': ['class'],
             'table': ['class'], 'p': ['class'],
             'td': ['colspan', 'rowspan'], 'th': ['colspan', 'rowspan']}
JUNK_SELECTORS = ('a.indexterm', 'a.id_link')


def derived_anchor(name):
    return 'GUC-' + name.upper().replace('_', '-')


def section_anchor(node):
    """最近的一层小节锚点：同一小节里的参数共用一个 pg_settings 分类。"""
    for parent in node.parents:
        if not isinstance(parent, Tag) or parent.name != 'div':
            continue
        classes = set(parent.get('class') or ())
        if classes & {'sect2', 'sect3', 'sect1'}:
            return parent.get('id') or ''
    return ''


def vartype_of(dt):
    """`<code class="type">` 写的类型名映射成 pg_settings.vartype。"""
    node = dt.select_one('code.type')
    if node is None:
        return ''
    return DOC_VARTYPES.get(text_of(node).lower(), 'string')


def rewrite_href(href, slug, filename):
    """手册内部链接改写到本站：`x.html#Y` → `/docs/<slug>/x.html#Y`，`#Y` 补上本页页名。"""
    href = (href or '').strip()
    if not href or href.startswith(('http://', 'https://', '//', '/', 'mailto:')):
        return href
    if href.startswith('#'):
        return '/docs/{}/{}{}'.format(slug, filename, href)
    return '/docs/{}/{}'.format(slug, href)


def collapse(fragment):
    """折叠空白：正文里的连续空白压成一个空格，块级标签之间的纯空白丢掉。

    `<pre>` 里原样保留——那是示例代码，空白就是内容。
    """
    for node in list(fragment.find_all(string=True)):
        if any(isinstance(parent, Tag) and parent.name == 'pre' for parent in node.parents):
            continue
        text = SPACE.sub(' ', str(node).replace('\xa0', ' '))
        if text.strip():
            # 块级容器的头尾不留空格，同一段译文在不同版本里才比得出完全一致。
            parent = node.parent
            block = not isinstance(parent, Tag) or parent.name in BLOCK_TAGS
            if block and node.previous_sibling is None:
                text = text.lstrip()
            if block and node.next_sibling is None:
                text = text.rstrip()
            node.replace_with(text)
            continue
        # 纯空白：夹在行内元素之间的要留一个空格，块级之间的整段丢掉。
        neighbours = [node.previous_sibling, node.next_sibling]
        inline = [n for n in neighbours
                  if isinstance(n, Tag) and n.name not in BLOCK_TAGS]
        node.replace_with(' ' if len(inline) == 2 else '')


def clean_doc(node, slug, filename):
    """一段 `<dd>` 说明的内部 HTML：去噪、去 id、改写链接、折叠空白、按白名单清洗。"""
    if node is None:
        return ''
    fragment = BeautifulSoup(node.decode_contents(), 'html.parser')
    for selector in JUNK_SELECTORS:
        for junk in fragment.select(selector):
            junk.decompose()
    for anchor in list(fragment.find_all('a')):
        if not anchor.get('href') and not text_of(anchor):
            anchor.decompose()
    for tag in fragment.find_all(True):
        # 同一页面会渲染多个版本的译文，id 会撞。
        if 'id' in tag.attrs:
            del tag['id']
        if 'name' in tag.attrs and tag.name == 'a':
            del tag['name']
        if tag.name == 'a' and tag.get('href'):
            tag['href'] = rewrite_href(tag['href'], slug, filename)
    collapse(fragment)
    cleaned = bleach.clean(str(fragment), tags=DOC_TAGS, attributes=DOC_ATTRS, strip=True)
    return cleaned.strip()


def first_sentence(value):
    """一句话说明：截到第一个句号（中英文都认）。"""
    value = SPACE.sub(' ', value or '').strip()
    if not value:
        return ''
    head, sep, _ = value.partition('。')
    if sep:
        return head + sep
    match = re.search(r'\.(\s|$)', value)
    return value[:match.start() + 1] if match else value


class DocEntry:
    """手册里的一个参数条目：`<dt>` 的坐标与紧随其后的 `<dd>`。"""

    __slots__ = ('file', 'anchor', 'section', 'vartype', 'description')

    def __init__(self, file, anchor, section, vartype, description):
        self.file = file
        self.anchor = anchor
        self.section = section
        self.vartype = vartype
        self.description = description


class RuntimeIndex:
    """一个版本手册里 `runtime-config-*.html` 的参数条目索引。

    锚点与参数名两条路都建：10 – 13 的手册 `<dt>` 根本没有 id，只能按
    `<code class="varname">` 认；一个 `<dt>` 也可能同时是几个参数的说明
    （`debug_print_parse, debug_print_rewritten, debug_print_plan`）。
    """

    def __init__(self, tree, slug):
        self.tree = tree
        self.slug = slug
        self.manual = Manual(tree)
        self._by_anchor = None
        self._by_name = None

    def loaded(self):
        return self.manual.loaded()

    def build(self):
        if self._by_anchor is not None:
            return
        self._by_anchor, self._by_name = {}, {}
        for filename in self.manual.files(RUNTIME_FILE_RE):
            soup = self.manual.soup(filename)
            if soup is None:
                continue
            for dt in soup.find_all('dt'):
                names = [text_of(code) for code in dt.select('code.varname')]
                names = [name for name in names if NAME_RE.match(name)]
                if not names:
                    continue
                anchor = dt.get('id') or ''
                if not anchor.startswith('GUC-'):
                    anchor = ''
                entry = DocEntry(filename, anchor, section_anchor(dt), vartype_of(dt),
                                 dt.find_next_sibling('dd'))
                if anchor:
                    self._by_anchor.setdefault(anchor, entry)
                for name in names:
                    self._by_name.setdefault(name, entry)

    def locate(self, name, anchor=''):
        """(条目, 走的哪条路)：guc 记的锚点 → 按名字推的锚点 → 条目里写的参数名。"""
        self.build()
        if anchor and anchor in self._by_anchor:
            return self._by_anchor[anchor], 'anchor'
        guess = derived_anchor(name)
        if guess in self._by_anchor:
            return self._by_anchor[guess], 'derived'
        if name in self._by_name:
            return self._by_name[name], 'name'
        return None, ''

    def names(self):
        self.build()
        return set(self._by_name)

    def entries(self):
        self.build()
        return self._by_name


# ------------------------------------------------------------------ 去 Pigsty

# 参考资料里指向这两个站（含子域）的条目整条丢掉。
PIGSTY_SITES = ('pigsty.io', 'pigsty.cc')

# 先删短语：删掉之后整句仍然成立。
PIGSTY_PHRASES = (
    re.compile(r'或\s*(?:实测\s*)?Pigsty\s*(?:矩阵|模板)?值'),
    re.compile(r'[,，]?\s+or the measured Pigsty(?:\s+\w+)?\s+value'),
)


def sentences(text):
    """按 。；.; 拆句，终止符留在句尾；英文只在句号后面跟空白时才断，免得切开小数。"""
    out, buffer = [], ''
    for index, char in enumerate(text):
        buffer += char
        if char in '。；':
            out.append(buffer)
            buffer = ''
        elif char in '.;' and text[index + 1:index + 2] in ('', ' ', '\t', '\n'):
            out.append(buffer)
            buffer = ''
    if buffer:
        out.append(buffer)
    return out


def scrub(text):
    """编辑文字去 Pigsty：先删短语，仍然提到的整句丢掉。"""
    if not text:
        return ''
    for pattern in PIGSTY_PHRASES:
        text = pattern.sub('', text)
    if 'Pigsty' in text:
        text = ''.join(part for part in sentences(text) if 'Pigsty' not in part)
    return SPACE.sub(' ', text).strip()


def scrub_all(value):
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, list):
        return [item for item in (scrub(entry) for entry in value) if item]
    if isinstance(value, dict):
        return {key: scrub(entry) for key, entry in value.items()}
    return value


def is_pigsty_reference(item):
    """参考资料里的 Pigsty 条目：站点是 pigsty.io / pigsty.cc（含子域），或者标题里写着 Pigsty。"""
    if 'pigsty' in (item.get('title') or '').lower():
        return True
    host = (urlsplit(item.get('url') or '').hostname or '').lower()
    return any(host == site or host.endswith('.' + site) for site in PIGSTY_SITES)


def references_of(block, report=None):
    """参考资料：指向 Pigsty 的整条丢掉，丢了几条记进报告。"""
    out = []
    for item in (block.get('references') or ()):
        if not item.get('url'):
            continue
        if is_pigsty_reference(item):
            if report is not None:
                report['pigsty_references_dropped'] += 1
            continue
        out.append({'title': (item.get('title') or '').strip(),
                    'url': (item.get('url') or '').strip()})
    return out


def editorial_of(record, report):
    """`editorial.zh / en` 去掉 Pigsty，中英各留一份；`related` 稍后再按快照过滤。"""
    block = record.get('editorial') or {}
    zh, en = block.get('zh') or {}, block.get('en') or {}
    out = {
        'summary_zh': scrub(zh.get('summary', '')), 'summary': scrub(en.get('summary', '')),
        'mechanism_zh': scrub_all(zh.get('mechanism') or []),
        'mechanism': scrub_all(en.get('mechanism') or []),
        'advice_zh': scrub_all(zh.get('advice') or {}), 'advice': scrub_all(en.get('advice') or {}),
        'pitfalls_zh': scrub_all(zh.get('pitfalls') or []),
        'pitfalls': scrub_all(en.get('pitfalls') or []),
        'related': list(zh.get('related') or en.get('related') or ()),
        'references_zh': references_of(zh, report), 'references': references_of(en, report),
    }
    # 正文、建议、坑、参考资料，哪个字段还留着 Pigsty 都要报出来。
    for field, value in out.items():
        if 'pigsty' in json.dumps(value, ensure_ascii=False).lower():
            report['pigsty_left'].append('{} @ {}'.format(record['name'], field))
    return out


def intro_commit_of(record):
    """引入提交：verified 的留事实，其它状态只留状态，没有的留空。"""
    commit = record.get('introduction_commit') or {}
    if not commit:
        return {}
    if commit.get('status') != 'verified':
        return {'status': commit.get('status', '')}
    return {'hash': commit.get('hash', ''), 'authored_at': commit.get('authored_at', ''),
            'subject': commit.get('subject', ''), 'url': commit.get('url', ''),
            'discussion': list(commit.get('discussion') or ())}


# ------------------------------------------------------------------ 快照与变化

def doc_ref(record, key, major):
    """快照里的手册坐标：`{'file', 'anchor', 'slug', 'url'}`，采集时再按实际找到的页修正。"""
    entry = (record.get('official_docs') or {}).get(key) or {}
    url = entry.get('url') or ''
    anchor = entry.get('anchor') or ''
    verified = entry.get('status') == 'verified'
    file = url.split('/')[-1].split('#')[0] if (verified and '.html' in url) else ''
    return {'file': file, 'anchor': anchor, 'slug': doc_slug(major), 'url': url}


def trim_snapshot(row, record, key, major):
    """guc 的一版 pg_settings 行裁成本站要存的形状。"""
    snapshot = {field: row.get(field) for field in SNAPSHOT_FACTS}
    snapshot['human'] = human_value(row.get('boot_val'), row.get('unit'))
    snapshot['category_zh'] = GUC_CATEGORY_ZH.get(row.get('category') or '', row.get('category') or '')
    snapshot['doc'] = doc_ref(record, key, major)
    snapshot['doc_html'] = ''
    snapshot['doc_same_as'] = ''
    snapshot['carried_from'] = ''
    snapshot['carry_reason'] = ''
    return snapshot


def build_changes(snapshots, order):
    """相邻两版之间的变化记录，新的在后。

    两版都在才比字段；`added` 只记非基线的首次出现，`removed` 记在最后一版的下一版。
    """
    changes = []
    for left, right in zip(order, order[1:]):
        here, there = snapshots.get(left), snapshots.get(right)
        record = {'from': left, 'to': right, 'status': 'changed', 'fields': {},
                  'substantive': False, 'default_changed': False, 'carried': False}
        if here is not None and there is not None:
            fields = diff_fields(here, there)
            carried = bool(there.get('carried_from'))
            if not fields and not carried:
                continue
            record.update({'fields': fields, 'substantive': is_substantive(fields),
                           'default_changed': is_default_change(fields), 'carried': carried})
        elif there is not None:
            record['status'] = 'added'
        elif here is not None:
            record['status'] = 'removed'
        else:
            continue
        changes.append(record)
    return changes


def default_entry(snapshot):
    return {'boot_val': snapshot.get('boot_val'), 'unit': snapshot.get('unit'),
            'human': snapshot.get('human', '')}


def build_transitions(parameters, order):
    """每个版本相对上一版的汇总；第一版没有上一版，留空。"""
    transitions = {major: {'from': left, 'added': [], 'removed': [], 'default_changed': [],
                           'changed': [], 'reworded': []}
                   for left, major in zip(order, order[1:])}
    for item in parameters:
        for change in item['changes']:
            entry = transitions.get(change['to'])
            if entry is None:
                continue
            name = item['name']
            if change['status'] == 'added':
                entry['added'].append(name)
            elif change['status'] == 'removed':
                entry['removed'].append(name)
            elif change['default_changed']:
                entry['default_changed'].append({
                    'name': name, 'from': default_entry(item['versions'][change['from']]),
                    'to': default_entry(item['versions'][change['to']])})
            elif change['substantive']:
                entry['changed'].append({
                    'name': name,
                    'fields': [f for f in FIELD_ORDER if f in change['fields']]})
            elif change['fields']:
                entry['reworded'].append(name)
    for entry in transitions.values():
        entry['added'].sort()
        entry['removed'].sort()
        entry['reworded'].sort()
        entry['default_changed'].sort(key=lambda item: item['name'])
        entry['changed'].sort(key=lambda item: item['name'])
    return transitions


def check_diffs(transitions, diffs, source_keys):
    """与 guc `diffs.json` 逐版核对 added / removed / default_changed，对不上就不要导出。"""
    checked = []
    for major, entry in transitions.items():
        left, right = source_keys.get(entry['from']), source_keys.get(major)
        source = diffs.get('{}-{}'.format(left, right)) if left and right else None
        if source is None:
            continue
        pairs = (('added', sorted(entry['added']), sorted(source.get('added') or ())),
                 ('removed', sorted(entry['removed']), sorted(source.get('removed') or ())),
                 ('default_changed', sorted(item['name'] for item in entry['default_changed']),
                  sorted(item['name'] for item in (source.get('default_changed') or ()))))
        for field, ours, theirs in pairs:
            if ours != theirs:
                raise ValueError(
                    '{} → {} 的 {} 与 diffs.json 对不上：多 {}，少 {}'.format(
                        entry['from'], major, field,
                        sorted(set(ours) - set(theirs)), sorted(set(theirs) - set(ours))))
        checked.append('{}-{}'.format(left, right))
    return {'pairs': len(checked), 'matched': True, 'compared': sorted(checked)}


def assign_positions(parameters):
    """一级分类序 × 10000 + 子分类序 × 100 + 子分类内按名排序。"""
    buckets = {}
    for item in parameters:
        buckets.setdefault((item['group'], item['category']), []).append(item)
    for (group, category), items in buckets.items():
        items.sort(key=lambda item: item['key'])
        base = (GUC_GROUP_ORDER.get(group, len(GUC_GROUP_ORDER)) * 10000 +
                GUC_CATEGORY_ORDER.get(category, len(GUC_CATEGORY_ORDER)) * 100)
        for index, item in enumerate(items):
            item['position'] = base + index
    parameters.sort(key=lambda item: (item['position'], item['key']))


def refresh_facts(item, order):
    """热字段取最新存在版本的快照；现存参数最新的那一版就是 20。"""
    present = [major for major in order if major in item['versions']]
    item['present_in'] = present
    item['first_version'] = present[0] if present else ''
    item['last_version'] = present[-1] if present else ''
    last = item['versions'][present[-1]] if present else {}
    item['category'] = last.get('category') or ''
    item['category_zh'] = GUC_CATEGORY_ZH.get(item['category'], item['category'])
    item['group'] = guc_group_of(item['category'])
    item['group_slug'] = GUC_GROUP_SLUG.get(item['group'], '')
    item['vartype'] = last.get('vartype') or ''
    item['context'] = last.get('context') or ''
    item['unit'] = last.get('unit') or ''
    item['boot_val'] = last.get('boot_val')
    item['boot_human'] = last.get('human') or ''
    item['short_desc'] = last.get('short_desc') or ''
    item['enumvals'] = list(last.get('enumvals') or ())
    item['min_val'] = last.get('min_val') or ''
    item['max_val'] = last.get('max_val') or ''
    item['changed_in'] = [change['to'] for change in item['changes']
                          if change['status'] == 'changed' and change['substantive']]
    item['default_changed_in'] = [change['to'] for change in item['changes']
                                  if change['status'] == 'changed' and change['default_changed']]


def build_parameters(records, report):
    """guc 的 447 条记录裁成本站的参数记录（还不含 20 与手册译文）。"""
    parameters = []
    for record in records:
        name = record['name']
        if not NAME_RE.match(name):
            raise ValueError('参数名格式不对：{!r}'.format(name))
        versions = {}
        for key, row in (record.get('versions') or {}).items():
            major = major_of(key)
            versions[major] = trim_snapshot(row, record, key, major)
        docs = {}
        for key, entry in (record.get('official_docs') or {}).items():
            docs[major_of(key)] = {field: entry[field] for field in ('status', 'anchor', 'url')
                                   if field in entry}
        history = []
        for span in record.get('default_history') or ():
            history.append({'from': major_of(span.get('from', '')), 'to': major_of(span.get('to', '')),
                            'boot_val': span.get('boot_val'), 'unit': span.get('unit'),
                            'human': human_value(span.get('boot_val'), span.get('unit'))})
        lifecycle = record.get('lifecycle') or {}
        item = {
            'name': name, 'key': name.lower(),
            'versions': versions, 'docs': docs, 'default_history': history,
            'editorial': editorial_of(record, report), 'intro_commit': intro_commit_of(record),
            'baseline': bool(lifecycle.get('first_seen_is_scope_boundary')),
            'short_desc_zh': ((record.get('editorial') or {}).get('zh') or {}).get(
                'official_short_desc_translation', '') or '',
            'changes': [],
        }
        parameters.append(item)
    return parameters


# ------------------------------------------------------------ 20 开发版推导

def devel_url(filename, anchor):
    return OFFICIAL_URL.format(DEVEL_SLUG, filename + ('#' + anchor if anchor else ''))


def section_categories(index, by_name, base_major):
    """(页, 小节锚点) → 该小节里上一版参数最常见的 pg_settings 分类。"""
    counts = {}
    for name, entry in index.entries().items():
        item = by_name.get(name)
        snapshot = item['versions'].get(base_major) if item else None
        if snapshot is None or not snapshot.get('category'):
            continue
        counts.setdefault((entry.file, entry.section), collections.Counter())[snapshot['category']] += 1
    return {place: counter.most_common(1)[0][0] for place, counter in counts.items()}


def carried_snapshot(previous, doc, base_major, reason):
    """20 的快照：19 的事实照搬，手册坐标换成 devel。"""
    snapshot = json.loads(json.dumps(previous, default=str))
    snapshot['doc'] = doc
    snapshot['doc_html'] = ''
    snapshot['doc_same_as'] = ''
    snapshot['carried_from'] = base_major
    snapshot['carry_reason'] = reason
    return snapshot


def new_devel_parameter(name, entry, category):
    """devel 手册里新出现的参数：手册只给类型与说明，pg_settings 的事实一概留空。"""
    lead = first_sentence(text_of(entry.description))
    doc = {'file': entry.file, 'anchor': entry.anchor, 'slug': DEVEL_SLUG,
           'url': devel_url(entry.file, entry.anchor)}
    snapshot = {'setting': '', 'boot_val': None, 'unit': '', 'human': '',
                'category': category, 'category_zh': GUC_CATEGORY_ZH.get(category, category),
                'short_desc': '', 'extra_desc': '', 'context': '',
                'vartype': entry.vartype or '', 'min_val': '', 'max_val': '', 'enumvals': [],
                'doc': doc, 'doc_html': '', 'doc_same_as': '',
                'carried_from': '', 'carry_reason': ''}
    return {
        'name': name, 'key': name.lower(),
        'versions': {DEVEL_MAJOR: snapshot}, 'default_history': [], 'changes': [],
        'docs': {DEVEL_MAJOR: {'status': 'derived', 'anchor': entry.anchor,
                               'url': doc['url']}} if entry.anchor else {},
        'editorial': {}, 'intro_commit': {}, 'baseline': False, 'short_desc_zh': lead,
    }


def derive_devel(parameters, indexes, base_major, report):
    """从本站 devel 手册推导开发版快照。本地没有 devel 手册时整段跳过。"""
    index = indexes.setdefault(DEVEL_MAJOR, RuntimeIndex(DEVEL_TREE, DEVEL_SLUG))
    if not index.loaded():
        report['devel'] = {'derived': False, 'reason': '本地没有 devel 手册'}
        return False
    base_index = indexes.setdefault(base_major, RuntimeIndex(manual_tree(base_major), base_major))
    documented = base_index.names() if base_index.loaded() else set()

    by_name = {item['name']: item for item in parameters}
    carried, undocumented, removed, added = [], [], [], []
    for item in parameters:
        previous = item['versions'].get(base_major)
        if previous is None:
            continue
        entry, _ = index.locate(item['name'], (previous.get('doc') or {}).get('anchor', ''))
        if entry is None:
            if item['name'] in documented:
                # 上一版手册收录、devel 手册没有了：真的被删了。
                removed.append(item['name'])
                continue
            doc = {'file': '', 'anchor': (previous.get('doc') or {}).get('anchor', ''),
                   'slug': DEVEL_SLUG, 'url': ''}
            reason = CARRY_UNDOCUMENTED.format(base_major)
            undocumented.append(item['name'])
        else:
            doc = {'file': entry.file, 'anchor': entry.anchor, 'slug': DEVEL_SLUG,
                   'url': devel_url(entry.file, entry.anchor)}
            reason = CARRY_DOCUMENTED.format(base_major)
            carried.append(item['name'])
            if entry.anchor:
                item['docs'][DEVEL_MAJOR] = {'status': 'derived', 'anchor': entry.anchor,
                                             'url': doc['url']}
        item['versions'][DEVEL_MAJOR] = carried_snapshot(previous, doc, base_major, reason)

    categories = section_categories(index, by_name, base_major)
    for name in sorted(index.names()):
        item = by_name.get(name)
        if item is not None and DEVEL_MAJOR in item['versions']:
            continue
        # 手册记着、pg_settings 从来没有的参数（只在调试构建里存在的那些）：
        # 上一版手册也记着它，就说明这是手册的老账，不是 20 新增。
        if name in documented:
            continue
        entry = index.entries()[name]
        category = categories.get((entry.file, entry.section)) or PAGE_GROUPS.get(entry.file, '')
        built = new_devel_parameter(name, entry, category)
        if item is None:
            parameters.append(built)
            by_name[name] = built
        else:
            # 早先移除、devel 手册里又有了：挂回原来那条记录。
            item['versions'][DEVEL_MAJOR] = built['versions'][DEVEL_MAJOR]
            item['docs'].update(built['docs'])
        added.append(name)

    # 默认值变迁的最后一段延伸到 20。
    for item in parameters:
        if DEVEL_MAJOR not in item['versions'] or not item['default_history']:
            continue
        if item['default_history'][-1]['to'] == base_major:
            item['default_history'][-1]['to'] = DEVEL_MAJOR

    report['devel'] = {
        'derived': True, 'base': base_major, 'manual_parameters': len(index.names()),
        'carried': len(carried), 'undocumented': sorted(undocumented),
        'added': sorted(added), 'removed': sorted(removed),
    }
    return True


# ------------------------------------------------------------------ 中文采集

def harvest_version(index, parameters, major, report):
    """把一个版本的手册译文写进这一版的快照里。"""
    stats = {'located': 0, 'doc': 0, 'unlocated': 0, 'anchor': 0, 'derived': 0, 'name': 0}
    for item in parameters:
        snapshot = item['versions'].get(major)
        if snapshot is None:
            continue
        doc = snapshot['doc']
        entry, route = index.locate(item['name'], doc.get('anchor') or '')
        if entry is None:
            report['unlocated'].append('{} @ {}'.format(item['name'], major))
            stats['unlocated'] += 1
            continue
        stats['located'] += 1
        stats[route] += 1
        if entry.file:
            doc['file'] = entry.file
        if entry.anchor:
            doc['anchor'] = entry.anchor
        if not doc.get('url') and doc.get('file'):
            doc['url'] = OFFICIAL_URL.format(
                doc['slug'], doc['file'] + ('#' + doc['anchor'] if doc.get('anchor') else ''))
        html = clean_doc(entry.description, index.slug, entry.file)
        if html:
            snapshot['doc_html'] = html
            stats['doc'] += 1
    report['doc'][major] = stats
    return stats


def dedupe_docs(item, order):
    """同一段译文在多版完全一致时只存一份，其余版本记一个指针。"""
    seen = {}
    for major in order:
        snapshot = item['versions'].get(major)
        if snapshot is None:
            continue
        html = snapshot.get('doc_html') or ''
        if not html:
            continue
        first = seen.get(html)
        if first is None:
            seen[html] = major
        else:
            snapshot['doc_html'] = ''
            snapshot['doc_same_as'] = first


# ------------------------------------------------------------------ 导出

def read_json(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def repo_rev(root):
    """'<HEAD 日期>@<HEAD 短哈希>'，取不到就 unknown。"""
    def run(*args):
        try:
            out = subprocess.run(('git', '-C', root) + args, capture_output=True, text=True,
                                 timeout=10)
            return out.stdout.strip() if out.returncode == 0 else ''
        except (OSError, subprocess.SubprocessError):
            return ''
    return '{}@{}'.format(run('log', '-1', '--format=%cs') or 'unknown',
                          run('rev-parse', '--short', 'HEAD') or 'unknown')


def version_row(key, major, position, default_major, manifest, transition, count):
    status = ('preview' if split_key(key)[1]
              else 'stable' if major == default_major else 'historical')
    transition = transition or {}
    return {
        'major': major, 'label': label_of(key), 'status': status,
        'support_status': support_status(major, status),
        'source_key': key, 'server_version': server_version_of(manifest, key),
        'doc_slug': doc_slug(major), 'parameter_count': count,
        'added_count': len(transition.get('added') or ()),
        'removed_count': len(transition.get('removed') or ()),
        'default_changed_count': len(transition.get('default_changed') or ()),
        'changed_count': len(transition.get('changed') or ()),
        'reworded_count': len(transition.get('reworded') or ()),
        'schema_source': 'runtime', 'transition': transition, 'position': position,
    }


def export_snapshot(root=DEFAULT_ROOT):
    """把 guc 仓库 + 本站手册读成一份自包含快照。"""
    root = os.path.expanduser(root)
    path = os.path.join(root, 'data', 'guc.json')
    if not os.path.exists(path):
        raise ValueError('找不到配置参数数据：{}'.format(path))
    records = read_json(path)
    diffs = read_json(os.path.join(root, 'data', 'diffs.json'))
    catalog = read_json(os.path.join(root, 'data', 'catalog.json'))
    manifest_path = os.path.join(root, 'raw', 'manifest.json')
    manifest = read_json(manifest_path) if os.path.exists(manifest_path) else {}
    report = {'doc': {}, 'unlocated': [], 'pigsty_left': [],
              'pigsty_references_dropped': 0, 'devel': {}, 'diffs': {}}

    keys = sorted({key for record in records for key in (record.get('versions') or {})},
                  key=version_sort_key)
    if not keys:
        raise ValueError('数据里没有任何版本快照')
    source_keys = {major_of(key): key for key in keys}
    order = [major_of(key) for key in keys]
    default_major = next((major_of(key) for key in reversed(keys) if not split_key(key)[1]),
                         order[-1])

    parameters = build_parameters(records, report)

    # 20 开发版：本地有 devel 手册才推。
    indexes = {}
    if derive_devel(parameters, indexes, order[-1], report):
        order.append(DEVEL_MAJOR)

    for item in parameters:
        item['changes'] = build_changes(item['versions'], order)
    transitions = build_transitions(parameters, order)
    report['diffs'] = check_diffs(transitions, diffs, source_keys)

    # 手册译文：本站只有 10 及以后的手册，9.x 留空。
    for major in order:
        index = indexes.get(major) or RuntimeIndex(manual_tree(major), doc_slug(major))
        if not index.loaded():
            continue
        harvest_version(index, parameters, major, report)
        indexes.pop(major, None)
        del index
    for item in parameters:
        dedupe_docs(item, order)

    known = {item['name'] for item in parameters}
    for item in parameters:
        if item['editorial']:
            item['editorial']['related'] = [name for name in item['editorial']['related']
                                            if name in known]
        refresh_facts(item, order)
    assign_positions(parameters)

    source_rev = repo_rev(root)
    for item in parameters:
        item['source_rev'] = source_rev

    counts = {major: sum(1 for item in parameters if major in item['versions']) for major in order}
    versions = [version_row(source_keys.get(major, ''), major, position, default_major, manifest,
                            transitions.get(major), counts[major])
                for position, major in enumerate(order)]
    for version in versions:
        if version['major'] == DEVEL_MAJOR:
            version.update({'label': DEVEL_MAJOR + ' devel', 'status': 'devel',
                            'support_status': 'devel', 'source_key': '', 'server_version': '',
                            'schema_source': 'documentation'})

    stats = {
        'parameter_count': len(parameters), 'version_count': len(versions),
        'snapshots': sum(len(item['versions']) for item in parameters),
        'change_records': sum(len(item['changes']) for item in parameters),
        'substantive_changes': sum(1 for item in parameters for c in item['changes']
                                   if c['substantive']),
        'default_changes': sum(1 for item in parameters for c in item['changes']
                               if c['default_changed']),
        'removed': sum(1 for item in parameters if item['last_version'] != order[-1]),
        'documented_snapshots': sum(1 for item in parameters for s in item['versions'].values()
                                    if s.get('doc_html') or s.get('doc_same_as')),
        'source_counts': dict(catalog.get('version_counts') or {}),
    }

    return {
        'format': FORMAT,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'root': root,
        'source_rev': source_rev,
        'default_major': default_major,
        'scope': dict(catalog.get('scope') or {}),
        'stats': stats,
        'harvest': report,
        'versions': versions,
        'parameters': parameters,
    }


# ------------------------------------------------------------------ 导入

VERSION_FIELDS = ('label', 'status', 'support_status', 'source_key', 'server_version', 'doc_slug',
                  'parameter_count', 'added_count', 'removed_count', 'default_changed_count',
                  'changed_count', 'reworded_count', 'schema_source', 'transition', 'position')
PARAMETER_FIELDS = ('key', 'group', 'group_slug', 'category', 'category_zh', 'vartype', 'context',
                    'unit', 'boot_val', 'boot_human', 'short_desc', 'short_desc_zh', 'enumvals',
                    'min_val', 'max_val', 'first_version', 'last_version', 'present_in',
                    'changed_in', 'default_changed_in', 'baseline', 'versions', 'changes',
                    'default_history', 'docs', 'editorial', 'intro_commit', 'position',
                    'source_rev')


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
    for key in ('versions', 'parameters'):
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
    for item in snapshot['parameters']:
        name = item.get('name', '')
        if not NAME_RE.match(name):
            raise ValueError('参数名格式不对：{!r}'.format(name))
        require(item, PARAMETER_FIELDS, '参数 ' + name)
        if item['key'] in seen:
            raise ValueError('参数重复：{}'.format(name))
        seen.add(item['key'])
        if not item.get('versions'):
            raise ValueError('{} 没有任何版本快照'.format(name))
        unknown = set(item['versions']) - majors
        if unknown:
            raise ValueError('{} 引用了未知版本：{}'.format(name, sorted(unknown)))
    return True


def changed_names(snapshot):
    """这次导入会改动哪些参数。JSON 列整份比对，无变化的整条跳过。"""
    stored = {row.pk: row for row in GucParameter.objects.all()}
    added, updated, unchanged = [], [], []
    for item in snapshot['parameters']:
        row = stored.get(item['name'])
        if row is None:
            added.append(item['name'])
        elif any(getattr(row, field) != item[field] for field in PARAMETER_FIELDS):
            updated.append(item['name'])
        else:
            unchanged.append(item['name'])
    incoming = {item['name'] for item in snapshot['parameters']}
    missing = {
        'parameters': sorted(set(stored) - incoming),
        'versions': [row.major for row in GucVersion.objects.all()
                     if row.major not in {v['major'] for v in snapshot['versions']}],
    }
    return added, updated, unchanged, missing


def retention_note(missing):
    """没加 --prune 时说清楚库里留了什么，免得以为已经删掉了。"""
    parts = []
    if missing['parameters']:
        parts.append('{} 个参数'.format(len(missing['parameters'])))
    if missing['versions']:
        parts.append('版本 ' + '、'.join(missing['versions']))
    if not parts:
        return ''
    return '快照里没有但库里还在：{}。未加 --prune，这些记录保留。'.format('，'.join(parts))


def coverage(snapshot):
    """译文覆盖：多少版快照有自己的译文、多少版指向更早的一版、多少版没有。"""
    counts = {'doc': 0, 'same_as': 0, 'none': 0}
    per_version = {}
    for item in snapshot['parameters']:
        for major, version in item['versions'].items():
            state = 'doc' if version.get('doc_html') else (
                'same_as' if version.get('doc_same_as') else 'none')
            counts[state] += 1
            per_version.setdefault(major, {'doc': 0, 'same_as': 0, 'none': 0})[state] += 1
    return {'snapshots': counts, 'versions': per_version,
            'short_desc_zh': sum(1 for item in snapshot['parameters'] if item['short_desc_zh']),
            'editorial': sum(1 for item in snapshot['parameters'] if item['editorial']),
            'intro_commit': sum(1 for item in snapshot['parameters']
                                if item['intro_commit'].get('hash'))}


def harvest_note(snapshot):
    report = dict(snapshot.get('harvest') or {})
    report['unlocated'] = len(report.get('unlocated') or ())
    report['pigsty_left'] = len(report.get('pigsty_left') or ())
    return report


def preview(snapshot):
    """不写库，只报告这次导入会改动什么。"""
    validate(snapshot)
    added, updated, unchanged, missing = changed_names(snapshot)
    return {
        'versions': len(snapshot['versions']),
        'parameters': len(snapshot['parameters']),
        'added': added, 'changed': len(updated), 'unchanged': len(unchanged), 'missing': missing,
        'note': retention_note(missing),
        'snapshots': sum(len(item['versions']) for item in snapshot['parameters']),
        'coverage': coverage(snapshot),
        'harvest': harvest_note(snapshot),
    }


@transaction.atomic
def import_snapshot(snapshot, prune=False):
    """按参数名原位更新。无变化的参数整条跳过，不重写 JSON 列。"""
    validate(snapshot)
    report = {'versions': 0, 'added': 0, 'updated': 0, 'unchanged': 0}

    for item in snapshot['versions']:
        GucVersion.objects.update_or_create(
            major=item['major'], defaults={field: item[field] for field in VERSION_FIELDS})
        report['versions'] += 1

    added, updated, unchanged, missing = changed_names(snapshot)
    write = set(added) | set(updated)
    for item in snapshot['parameters']:
        if item['name'] not in write:
            continue
        GucParameter.objects.update_or_create(
            name=item['name'], defaults={field: item[field] for field in PARAMETER_FIELDS})
    report.update({'added': len(added), 'updated': len(updated), 'unchanged': len(unchanged)})

    report['pruned'] = bool(prune)
    report['missing'] = missing
    if prune:
        stale = GucParameter.objects.filter(name__in=missing['parameters'])
        report['removed'] = {'parameters': stale.count(), 'versions': list(missing['versions'])}
        stale.delete()
        GucVersion.objects.filter(major__in=missing['versions']).delete()
    else:
        report['removed'] = {'parameters': 0, 'versions': []}
        report['note'] = retention_note(missing)

    report['coverage'] = coverage(snapshot)
    report['harvest'] = harvest_note(snapshot)
    return report


def digest(snapshot):
    """一份快照的内容指纹，方便核对两端加载的是同一份。"""
    payload = json.dumps({'versions': snapshot['versions'], 'parameters': snapshot['parameters']},
                         ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
