"""导入函数百科：上游英文原页（事实）+ 本站手册（中文）→ 自包含快照 → 幂等写库。

和系统目录、配置参数两个栏目同一套分工：**事实来自权威源，中文来自本站手册**。
哪些函数、什么签名、什么示例、归哪一组，一律逐版本取自 postgresql.org 的英文原页
（9.0 – 19 与 devel = 20，缓存在 `tmp/func-sources/<major>/`）；本站中文手册只叠中文描述。

不用本站手册判断存在性，是因为译文仓库按新版为基底回填：14 版的页面里有 PG 17 才引入的
`JSON_TABLE`、PG 18 的 `uuidv7`，而 devel 手册反而没有 PG 16 的 `any_value`。拿它算
「哪一版引入」会得出错误结论（契约 docs/func-column.md §1）。

`export_snapshot()` 读源产快照，`import_snapshot()` 把快照写进库。拆开是为了让同一份
快照分别加载本地与生产——导出要联网、要读本地手册，导入只认快照，生产机上什么源都不需要。

上游第 9 章有三种写法，导入器里并存（契约 docs/func-column.md §1）：

1. **签名段**（13 起）：`td.func_table_entry` 里一条或多条 `p.func_signature`，
   `code.function` 是函数名，后面第一批 `<p>` 是描述，带 `→` 的 `<p>` 是示例；
2. **五列表**（9.0 – 12）：表头写着「函数 | 返回类型 | 描述 | 示例 | 结果」的老式表格，
   函数名在首列的 `code.function` 里，文本形如 `ascii(string)`；
3. **散文页的 synopsis**：`functions-xml.html` 这类没有函数表的页面，
   `pre.synopsis` 是签名，其后的 `<p>` 是描述。这一形态与第 1 种共用签名解析。

9.x 上游页面是老式 DocBook：class 全大写、行内标记用 `<tt>`。解析前把整棵树的 class
统一小写、`tt` 改名 `code`，就能复用第 2 种形态的解析器。
"""

import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import bleach
from bs4 import BeautifulSoup, NavigableString, Tag
from django.db import transaction
from django.db.models import Q

from pgweb.core.models import TESTING_SHORTSTRING, Version
from pgweb.docs.versions import DEVEL_MAJOR_VERSION

from .catalog_importer import text_of
from .guc_importer import collapse
from .snapshot import item_hash, hashed_defaults
from .models import (FUNC_GROUPS, FUNC_GROUP_LABEL, FUNC_GROUP_ORDER, FuncVersion, PgFunction,
                     func_group_of, func_page_order, func_slug)

FORMAT = 1
CACHE_DIR = 'tmp/func-sources'
DEVEL_MAJOR = str(DEVEL_MAJOR_VERSION)
DEVEL_TREE = 0

# 事实全取上游：9.0 起的全部正式版加开发版。开发版在上游的地址段是 devel。
UPSTREAM_FLOOR = 9.0
UPSTREAM_URL = 'https://www.postgresql.org/docs/{}/{}'
UPSTREAM_UA = 'pgsql.cc func-column importer (+https://pgsql.cc/)'
UPSTREAM_PAUSE = 0.25

# 13 起手册把函数表从五列改成签名段，签名文本整体换了写法。
LAYOUT_NEW_FROM = 13

SPACE = re.compile(r'\s+')
ARROW = '→'
NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
SLUG_RE = re.compile(r'^[a-z][a-z0-9-]{0,79}$')
FILE_RE = re.compile(r'^functions-[a-z0-9-]+\.html$')
TRAILING_DOT = re.compile(r'(?<!\.)\.$')
# 手册偶尔不给函数名加标记，退一步认「标识符 (」开头的 synopsis 行。
BARE_CALL_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*\(')
# 「…可以写成标准 SQL 语法：」这类抬头短且以冒号收尾，不是描述。
LEAD_IN_MAX = 60
# 一格里并列摆几种写法：`char_length(string) or character_length(string)`。
ALTERNATIVE_RE = re.compile(r'\s+or\s+|或')
# 整批页面里被标成函数的名字，用来给没有标记的 synopsis 把关。
MARKED_RE = re.compile(r'class="[^"]*\bfunction\b[^"]*"[^>]*>\s*([A-Za-z_][A-Za-z0-9_]*)', re.I)

# 签名与描述都是行内片段，白名单比正文窄：只留行内标记与链接。
TAGS = ['code', 'span', 'em', 'a', 'b', 'i', 'sub', 'sup', 'br']
ATTRS = {'a': ['href', 'title'], 'code': ['class'], 'span': ['class'], 'em': ['class']}
JUNK_SELECTORS = ('script', 'style', 'iframe', 'a.indexterm', 'a.id_link')
SECTION_CLASSES = ('sect1', 'sect2', 'sect3', 'sect4', 'chapter', 'appendix')
# 手册里的语义锚点全大写；`id-1.5.8.10` 是自动生成的，换一版就变。
SEMANTIC_ANCHOR_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_-]*$')

# 老式表格的表头 → 列的角色。中英两种写法都认：上游是英文，本站手册是译文。
HEADER_ROLES = {
    role: names for role, names in (
        ('name', ('函数', '名称', 'function', 'name')),
        ('returns', ('返回类型', 'return type', 'returns')),
        ('description', ('描述', '说明', 'description')),
        ('example', ('示例', '例子', 'example')),
        ('result', ('结果', '示例结果', 'result', 'example result')),
    )
}
ROLE_OF_HEADER = {name: role for role, names in HEADER_ROLES.items() for name in names}
# 带限定语的函数列仍是函数列：9.6 起三角函数表的表头是
# 「Function (radians) | Function (degrees)」，两列都要采。
NAME_HEADER_PREFIXES = ('函数', 'function')
# 输出列表的表头是「名称 | 类型 | 描述」，讲的是函数返回哪些列，不是函数清单。
# 它的「名称」列里有一行就叫 user，当成函数会凭空造出条目。
OUTPUT_TABLE_HEADERS = ('type', '类型', '数据类型')

VERSION_FIELDS = ('label', 'status', 'support_status', 'doc_slug', 'source', 'layout',
                  'function_count', 'signature_count', 'zh_coverage', 'added_count',
                  'removed_count', 'changed_count', 'transition', 'position')
FUNCTION_FIELDS = ('name', 'name_key', 'group', 'group_label', 'groups', 'summary', 'summary_zh',
                   'signature', 'first_version', 'last_version', 'present_in', 'changed_in',
                   'signature_count', 'versions', 'changes', 'position', 'source_rev')
SNAPSHOT_FIELDS = ('group', 'group_label', 'pages', 'doc', 'lang', 'layout', 'signatures',
                   'description_zh', 'description', 'zh_from', 'prose_only')
ZH_SOURCES = ('doc', 'inherited', '')
SIGNATURE_FIELDS = ('text', 'html', 'returns', 'description_zh', 'description', 'examples',
                    'zh_from')
CHANGE_FIELDS = ('from', 'to', 'status', 'signatures', 'descriptions_changed', 'group_changed',
                 'doc_overhaul')


# ------------------------------------------------------------------ 版本

def major_of(tree):
    """手册树号 → 大版本号：0 是开发版，9.x 保留小数点（9.0 不能写成 9）。"""
    value = float(tree)
    if value == 0:
        return DEVEL_MAJOR
    if value >= 10:
        return str(int(value))
    text = '{:g}'.format(value)
    return text if '.' in text else text + '.0'


def version_key(major):
    return tuple(int(part) for part in str(major).split('.'))


def layout_of(major):
    return 'table-new' if version_key(major)[0] >= LAYOUT_NEW_FROM else 'table-old'


def manual_majors():
    """本站手册里有第 9 章的版本；只用来叠中文，不决定收录哪些版本。"""
    trees = (DocPage_objects().filter(Q(version__gte=10) | Q(version=DEVEL_TREE),
                                      file='functions.html')
             .values_list('version', flat=True))
    return sorted({major_of(tree) for tree in trees}, key=version_key)


def DocPage_objects():
    from pgweb.docs.models import DocPage
    return DocPage.objects


def upstream_majors():
    """上游收录哪些大版本：9.0 起的全部正式版，加上开发版。"""
    majors = {major_of(row.tree) for row in Version.objects.all()
              if row.tree and float(row.tree) >= UPSTREAM_FLOOR}
    majors.add(DEVEL_MAJOR)
    return sorted(majors, key=version_key)


def upstream_slug(major):
    """上游地址段：开发版在 postgresql.org 上叫 devel，不叫 20。"""
    return 'devel' if major == DEVEL_MAJOR else major


def doc_slug_of(major, manual):
    """本站手册地址段；本站没有那一版就留空，页面只能链上游。"""
    if major not in set(manual):
        return ''
    return 'devel' if major == DEVEL_MAJOR else major


def version_rows(majors, manual=()):
    """版本行；标签与支持状态始终取本站 `core.Version`，和前几个栏目一个口径。

    事实全部来自上游，所以 `source` 恒为 upstream；中文是叠加层，覆盖率记在 zh_coverage。
    """
    majors = sorted(set(majors), key=version_key)
    stored = {major_of(row.tree): row for row in Version.objects.all()}
    formal = [major for major in majors if major != DEVEL_MAJOR and
              not (stored.get(major) and stored[major].testing)]
    default = next((major for major in reversed(formal) if stored.get(major) and
                    stored[major].current), (formal or majors or [''])[-1])
    rows = []
    for position, major in enumerate(majors):
        row = stored.get(major)
        status = ('devel' if major == DEVEL_MAJOR else 'preview' if row and row.testing
                  else 'stable' if major == default else 'historical')
        label = major
        if status == 'devel':
            label += ' devel'
        elif status == 'preview':
            label += ' {} {}'.format(TESTING_SHORTSTRING[row.testing], row.latestminor)
        support = ('supported' if row and row.supported else 'end-of-life')
        rows.append({
            'major': major, 'label': label, 'status': status,
            'support_status': status if status in ('preview', 'devel') else support,
            'doc_slug': doc_slug_of(major, manual),
            'source': 'upstream', 'layout': layout_of(major),
            'function_count': 0, 'signature_count': 0, 'zh_coverage': 0,
            'added_count': 0, 'removed_count': 0, 'changed_count': 0,
            'transition': {}, 'position': position,
        })
    return rows


def parse_context(major, doc_slug, lang):
    """解析用的上下文；版本行不带 lang，语言只在解析时区分英文原页与中文译文。"""
    return {'major': major, 'doc_slug': doc_slug, 'lang': lang, 'layout': layout_of(major),
            'source': 'upstream' if lang == 'en' else 'manual',
            # 9.x 上游是老式 DocBook，class 全大写、行内标记用 <tt>。
            'docbook': lang == 'en' and version_key(major)[0] < 10}


# ------------------------------------------------------------------ HTML 工具

def normalize_text(value):
    """签名的规范形式：折叠空白、统一 `→` 两侧空格、去掉尾部句号。"""
    text = SPACE.sub(' ', (value or '').replace('\xa0', ' ')).strip()
    text = re.sub(r'\s*{}\s*'.format(ARROW), ' {} '.format(ARROW), text)
    text = text.rstrip('。').strip()
    # `...` 结尾的语法形式不能当成句号切掉。
    return TRAILING_DOT.sub('', text).strip()


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


def link_target(href, version, filename):
    """手册内部链接改写：本站有那一版就指本站，9.x 只能指上游。"""
    href = (href or '').strip()
    if not href or href.startswith(('http://', 'https://', '//', '/', 'mailto:')):
        return href
    if href.startswith('#'):
        href = filename + href
    slug = version.get('doc_slug') or ''
    if slug:
        return '/docs/{}/{}'.format(slug, href)
    return UPSTREAM_URL.format(upstream_slug(version['major']), href)


def clean_fragment(fragment, version, filename):
    """行内片段 → 清洗后的 HTML：去噪、去 id、改写链接、折叠空白、按白名单过滤。"""
    for selector in JUNK_SELECTORS:
        for junk in fragment.select(selector):
            junk.decompose()
    for anchor in list(fragment.find_all('a')):
        if not anchor.get('href') and not text_of(anchor):
            anchor.decompose()
    for tag in fragment.find_all(True):
        # 同一页面会渲染多个版本，手册里的 id 会撞。
        tag.attrs.pop('id', None)
        if tag.name == 'a':
            tag.attrs.pop('name', None)
            if tag.get('href'):
                parsed = urlsplit(tag['href'])
                if parsed.scheme and parsed.scheme not in ('http', 'https', 'mailto'):
                    del tag['href']
                else:
                    tag['href'] = link_target(tag['href'], version, filename)
    collapse(fragment)
    return bleach.clean(str(fragment), tags=TAGS, attributes=ATTRS, strip=True).strip()


def clean_text(html):
    """签名用的规范文本。"""
    return normalize_text(text_of(BeautifulSoup(html or '', 'html.parser')))


def prose_text(html):
    """描述用的纯文本：只折叠空白，句号原样留着。"""
    return text_of(BeautifulSoup(html or '', 'html.parser'))


def fragment_of(node):
    """一个节点的内部 HTML 复制成可改写的片段。"""
    return BeautifulSoup(node.decode_contents() if isinstance(node, Tag) else str(node),
                         'html.parser')


def fragment_from(nodes):
    """一串兄弟节点拼成一个片段。"""
    return BeautifulSoup(''.join(str(node) for node in nodes), 'html.parser')


def classed(node, name):
    return node.find(attrs={'class': name}) if node is not None else None


def nearest_anchor(node):
    """最近一层带语义锚点的容器 id：`FUNCTIONS-STRING-SQL`。"""
    for parent in node.parents:
        if not isinstance(parent, Tag) or parent.name != 'div':
            continue
        classes = set(parent.get('class') or ())
        if not (classes & {'table', *SECTION_CLASSES}):
            continue
        anchor = parent.get('id') or ''
        if not anchor:
            link = parent.find('a', attrs={'name': True})
            anchor = link.get('name', '') if link is not None else ''
        if anchor and SEMANTIC_ANCHOR_RE.match(anchor):
            return anchor
    return ''


def normalize_docbook(soup):
    """9.x 的老式 DocBook：class 统一小写、`tt` 改名 `code`，其余解析就能复用。"""
    for tag in soup.find_all(True):
        classes = tag.get('class')
        if classes:
            tag['class'] = [str(name).lower() for name in classes]
        if tag.name == 'tt':
            tag.name = 'code'
    return soup


# ------------------------------------------------------------------ 签名与示例

def mark_bare_name(fragment, name):
    """兜底认出来的函数名补上 `code.function`。

    上游偶尔不给 synopsis 里的函数名加标记（`JSON_TABLE`、老版本的 `table_to_xml`），
    补一层标记，签名卡里的函数名才和表格形态一样醒目。
    """
    for item in list(fragment.find_all(string=True)):
        text = str(item)
        stripped = text.lstrip()
        if not stripped:
            continue
        if not stripped.startswith(name):
            return False
        head = text[:len(text) - len(stripped)]
        tag = fragment.new_tag('code')
        tag['class'] = ['function']
        tag.string = name
        item.replace_with(tag)
        if head:
            tag.insert_before(NavigableString(head))
        rest = stripped[len(name):]
        if rest:
            tag.insert_after(NavigableString(rest))
        return True
    return False


def make_signature(fragment, version, filename, returns='', name=''):
    """一个片段 → 签名字典的前半截（描述与示例由调用方补）。"""
    node = classed(fragment, 'function')
    if node is None and name:
        mark_bare_name(fragment, name)
    else:
        name = text_of(node) if node is not None else name
    if not returns:
        values = fragment.find_all(attrs={'class': 'returnvalue'})
        returns = text_of(values[-1]) if values else ''
    html = clean_fragment(fragment, version, filename)
    text = clean_text(html)
    if not text:
        return None, ''
    return {'text': text, 'html': html, 'returns': normalize_text(returns),
            'description_zh': '', 'description': '', 'description_html': '',
            'description_zh_html': '', 'zh_from': '', 'examples': []}, name


def block_result(node):
    """`expr →` 后面跟一段 `<pre>` 的写法：多行结果在那一段里，不在箭头后面。"""
    for sibling in node.next_siblings:
        if isinstance(sibling, NavigableString):
            if str(sibling).strip():
                break
            continue
        if sibling.name != 'pre' or 'synopsis' in (sibling.get('class') or ()):
            break
        lines = sibling.get_text().strip('\n').splitlines()
        # 手册里这段整体缩进过，去掉公共缩进再存，页面才好照原样排。
        indent = min((len(line) - len(line.lstrip()) for line in lines if line.strip()),
                     default=0)
        return '\n'.join(line[indent:].rstrip() for line in lines).strip('\n')
    return ''


def parse_example(node):
    """带 `→` 的示例段：`expr → result`。结果多行时在紧随其后的 `<pre>` 里。"""
    text = normalize_text(text_of(node))
    if ARROW not in text:
        return None
    expr, _, result = text.partition(ARROW)
    expr, result = expr.strip(), result.strip()
    if not expr:
        return None
    return {'expr': expr, 'result': result or block_result(node)}


def attach_prose(signatures, paragraphs, version, filename, examples=None):
    """一组签名共用的描述与示例：不带 `→` 的段是描述，带 `→` 的段是示例。

    描述只取**第一段**（契约 §1）：手册里一格或一节后面常常还跟着好几段补充，
    整段并进来会让详情页的签名卡铺开七八行。其余段落一律不要，读者点「本站手册」看全文。
    老版面的示例在单独的列里，由调用方直接给 `examples`，段落一律当描述。
    """
    kept, derived = [], []
    for node in paragraphs:
        example = parse_example(node) if examples is None else None
        if example is not None and kept:
            derived.append(example)
        elif example is None and not kept:
            kept.append(node)
    chunks = [clean_fragment(fragment_of(node), version, filename) for node in kept]
    chunks = [chunk for chunk in chunks if chunk]
    html = '\n'.join(chunks)
    text = '\n'.join(part for part in (prose_text(chunk) for chunk in chunks) if part)
    field = 'description_zh' if version['lang'] == 'zh' else 'description'
    shared = list(examples if examples is not None else derived)
    for signature in signatures:
        signature['description_html'] = html
        signature[field] = text
        signature['examples'] = list(shared)
    return signatures


# ------------------------------------------------------------------ 三种抽取形态

def harvest_signature_entries(soup, version, filename):
    """形态一：13 起的 `td.func_table_entry`。"""
    found = []
    for entry in soup.select('td.func_table_entry'):
        paragraphs = entry.find_all('p', recursive=False) or entry.find_all('p')
        signature_nodes = [node for node in paragraphs
                           if 'func_signature' in (node.get('class') or ())]
        prose = [node for node in paragraphs
                 if 'func_signature' not in (node.get('class') or ())]
        if not signature_nodes:
            continue
        anchor = nearest_anchor(entry)
        made = []
        for node in signature_nodes:
            signature, name = make_signature(fragment_of(node), version, filename)
            if signature is None or not NAME_RE.match(name or ''):
                continue
            made.append((name, signature))
        attach_prose([signature for _, signature in made], prose, version, filename)
        found.extend((name, signature, anchor, False) for name, signature in made)
    return found


def table_roles(table):
    """老式表格的列角色；没有表头或没有「函数」列的表不是函数表。"""
    head = table.find('thead')
    if head is None:
        return None
    row = head.find('tr')
    if row is None:
        return None
    labels = [' '.join(text_of(cell).lower().split()).strip(' #')
              for cell in row.find_all(['th', 'td'])]
    if any(label in OUTPUT_TABLE_HEADERS for label in labels):
        return None
    roles = [header_role(label) for label in labels]
    return roles if 'name' in roles else None


def header_role(label):
    """表头文字 → 列的角色。带限定语的函数列（`Function (radians)`）仍算函数列。"""
    label = ' '.join(label.lower().split()).strip(' #')
    if label in ROLE_OF_HEADER:
        return ROLE_OF_HEADER[label]
    return 'name' if label.startswith(NAME_HEADER_PREFIXES) else ''


def harvest_old_tables(soup, version, filename):
    """形态二：9.0 – 12 的五列表（列的角色按表头认，四列的聚合表也吃得下）。"""
    found = []
    for table in soup.find_all('table'):
        if table.select('td.func_table_entry'):
            continue
        roles = table_roles(table)
        if roles is None:
            continue
        anchor = nearest_anchor(table)
        body = table.find('tbody') or table
        for row in body.find_all('tr'):
            if row.find_parent('thead') is not None:
                continue
            cells = row.find_all(['td', 'th'], recursive=False)
            if len(cells) < 2:
                continue
            slots = defaultdict(list)
            for role, cell in zip(roles, cells):
                if role:
                    slots[role].append(cell)
            if not slots['name']:
                continue
            returns = ' '.join(text_of(cell) for cell in slots['returns'])
            example = parse_old_example(slots)
            made = []
            for cell in slots['name']:
                for fragment in old_calls(cell, returns):
                    signature, name = make_signature(fragment, version, filename)
                    if signature is None or not NAME_RE.match(name or ''):
                        continue
                    made.append((name, signature))
            attach_prose([signature for _, signature in made], slots['description'], version,
                         filename, examples=[example] if example else [])
            found.extend((name, signature, anchor, False) for name, signature in made)
    return found


def split_call(text):
    """`rank(args) WITHIN GROUP (ORDER BY sorted_args)` → ('rank', 'args', ' WITHIN GROUP (…)')。

    从第一个左括号数到配对的右括号，后面的部分原样留在签名尾巴上。
    """
    head, paren, rest = text.partition('(')
    if not paren:
        return text.strip(), '', ''
    depth, cut = 1, len(rest)
    for index, char in enumerate(rest):
        depth += (char == '(') - (char == ')')
        if depth == 0:
            cut = index
            break
    return head.strip(), SPACE.sub(' ', rest[:cut]).strip(), SPACE.sub(' ', rest[cut + 1:]).strip()


def call_text(node, cell):
    """一个 `code.function` 对应的完整调用式文本。

    上游英文页往往只把函数名放进 `code.function`，参数留在同一格后面的兄弟节点上
    （`<code class="function">to_char</code> ( <code class="type">timestamp</code>, … )`）。
    名字里没有括号时就顺着同一格往后读，读到括号配平为止——否则签名会退化成
    `to_char → text`，参数全丢。
    """
    name = text_of(node)
    if '(' in name or cell is None:
        return name
    skip = {id(item) for item in node.descendants}
    chunks, depth, started = [], 0, False
    for item in node.next_elements:
        if id(item) in skip or not isinstance(item, NavigableString):
            continue
        if cell is not item and cell not in item.parents:
            break
        piece = str(item)
        if not started and piece.strip() and not piece.lstrip().startswith('('):
            break
        for char in piece:
            if char == '(':
                depth += 1
                started = True
            elif char == ')':
                depth -= 1
            chunks.append(char)
            if started and depth == 0:
                return name + ''.join(chunks)
        if len(chunks) > 400:
            break
    return name


def top_level(nodes):
    """同一类标记互相嵌套时只取最外层，免得一条调用被拆成几截。

    只在同一批候选之间去重：`<code class="literal"><code class="function">…</code></code>`
    是老版面的常规写法，里面那个 `code.function` 必须留着。
    """
    marks = {id(node) for node in nodes}
    return [node for node in nodes
            if not any(id(parent) in marks for parent in node.parents)]


def bare_calls(cell):
    """首格取不到 `code.function` 时，退一步按「标识符 (」认调用。

    上游 ≤12 的枚举与 JSON 函数表整页都没有 `code.function`，调用只包在 `code.literal` 里
    （`<code class="literal">enum_first(anyenum)</code>`），一格里还常并列摆几条
    （`to_json(anyelement)` 与 `to_jsonb(anyelement)` 各占一个 `<p>`）。不兜底的话
    enum_* 与 json_* 整批会被误判成 13 才引入。操作符行（`string || string`）
    不匹配这个形状，不会误收。
    """
    nodes = top_level(cell.find_all(attrs={'class': 'literal'}))
    texts = [text_of(node) for node in nodes] or ALTERNATIVE_RE.split(text_of(cell))
    out = []
    for text in texts:
        text = SPACE.sub(' ', text or '').strip()
        if BARE_CALL_RE.match(text) and text not in out:
            out.append(text)
    return out


def build_old_signature(raw, returns):
    """一条调用式文本 → 和新版面同形的签名片段。

    `ascii(string)` 加上「返回类型」列的 `int` → `ascii ( string ) → int`。
    括号里取原文，不保留行内标记：老版面的参数名与类型没有稳定的标注。
    """
    name, args, tail = split_call(raw)
    fragment = BeautifulSoup('', 'html.parser')
    tag = fragment.new_tag('code')
    tag['class'] = ['function']
    tag.string = name
    fragment.append(tag)
    if '(' in raw:
        fragment.append(NavigableString(' ( {} )'.format(args) if args else ' ( )'))
    if tail:
        fragment.append(NavigableString(' ' + tail))
    returns = normalize_text(returns)
    if returns:
        fragment.append(NavigableString(' {} '.format(ARROW)))
        value = fragment.new_tag('code')
        value['class'] = ['returnvalue']
        value.string = returns
        fragment.append(value)
    return fragment


def old_calls(cell, returns):
    """一格里的全部调用式：有标记就按标记逐个取，取不出名字再按文本兜底。

    判据是「标记有没有取出合法的函数名」，不是「有没有标记」：上游偶尔把标记写坏，
    `pg_replication_origin_advance` 的名字留在外层 `code.literal` 的文本里，内层
    `code.function` 从左括号才开始，按「有标记就用」会拿到一个括号、整格作废。
    """
    nodes = top_level(cell.find_all(attrs={'class': 'function'}))
    raws = [call_text(node, cell) for node in nodes]
    if not any(NAME_RE.match(split_call(raw)[0] or '') for raw in raws):
        raws = bare_calls(cell)
    return [build_old_signature(raw, returns) for raw in raws]


def parse_old_example(slots):
    expr = ' '.join(text_of(cell) for cell in slots['example']).strip()
    result = ' '.join(text_of(cell) for cell in slots['result']).strip()
    if not expr:
        return None
    return {'expr': normalize_text(expr), 'result': normalize_text(result)}


def synopsis_segments(pre):
    """一个 `pre.synopsis` 拆成若干签名段，返回 [(节点列表, 兜底名称)]。

    空行断开；以 `code.function` 开头的行一定另起一段；手册偶尔不给函数名加标记
    （`JSON_TABLE`、9.x – 12 的 `table_to_xml`），所以括号配平时，以「标识符 (」
    开头的行也另起一段，名字从文本里取，是否收录留给调用方按「本版标过的函数名」过滤。
    """
    lines, current = [], []
    for node in pre.contents:
        if isinstance(node, NavigableString) and '\n' in str(node):
            parts = str(node).split('\n')
            current.append(NavigableString(parts[0]))
            for part in parts[1:]:
                lines.append(current)
                current = [NavigableString(part)]
        else:
            current.append(node)
    lines.append(current)

    segments, segment, depth = [], None, 0
    for line in lines:
        text = ''.join(node.get_text() if isinstance(node, Tag) else str(node) for node in line)
        if not text.strip():
            segment, depth = None, 0
            continue
        leading = next((node for node in line
                        if not (isinstance(node, NavigableString) and not str(node).strip())), None)
        marked = isinstance(leading, Tag) and 'function' in (leading.get('class') or ())
        bare = BARE_CALL_RE.match(text.strip())
        if marked or (bare and depth <= 0):
            segment = list(line)
            segments.append([segment, '' if marked else bare.group(1)])
            depth = text.count('(') - text.count(')')
            continue
        if segment is None:
            continue
        segment.extend([NavigableString(' ')] + list(line))
        depth += text.count('(') - text.count(')')
    return [(nodes, name) for nodes, name in segments]


def is_lead_in(node):
    """引导句：短、冒号结尾——`或使用现在废除的 SQL:1999 语法：`。它是下一条写法的抬头，不是描述。"""
    text = text_of(node).rstrip()
    return bool(text) and len(text) < LEAD_IN_MAX and text.endswith((':', '：'))


def backward_prose(pre):
    """往前找最近一段实打实的正文。

    手册常把同一个函数的几种写法连着摆：`<p>…可以写成标准 SQL 语法：</p><pre>…</pre>
    <p>或使用已废弃的 SQL:1999 语法：</p><pre>…</pre>`。这几种写法说的是同一件事，
    所以往前翻过引导句与别的 synopsis，取那段真正的说明。
    """
    for step, sibling in enumerate(pre.previous_siblings):
        if step > 12:
            break
        if isinstance(sibling, NavigableString):
            continue
        if sibling.name == 'pre':
            continue
        if sibling.name != 'p':
            break
        # 抬头与示例段都不是描述。
        if not is_lead_in(sibling) and text_of(sibling) and parse_example(sibling) is None:
            return [sibling]
    return []


def harvest_synopsis(soup, version, filename):
    """形态三：散文页里的 `pre.synopsis`。

    描述只取 synopsis 之后的**第一段**：这些小节后面往往还有整节正文，全并进来
    会让详情页的说明铺开七八段。紧跟其后的引导句不算描述，这时往前取正文。
    """
    found = []
    for pre in soup.select('pre.synopsis'):
        segments = synopsis_segments(pre)
        if not segments:
            continue
        anchor = nearest_anchor(pre)
        described, examples = [], []
        for sibling in pre.next_siblings:
            if isinstance(sibling, NavigableString):
                continue
            if sibling.name != 'p':
                break
            example = parse_example(sibling)
            if example is not None:
                examples.append(example)
            elif not described and not is_lead_in(sibling):
                described.append(sibling)
        if not described:
            described = backward_prose(pre)
        made = []
        for nodes, fallback in segments:
            signature, name = make_signature(fragment_from(nodes), version, filename,
                                             name=fallback)
            if signature is None or not NAME_RE.match(name or ''):
                continue
            made.append((name, signature, bool(fallback)))
        attach_prose([signature for _, signature, _ in made], described, version, filename,
                     examples=examples)
        found.extend((name, signature, anchor, tentative) for name, signature, tentative in made)
    return found


def harvest_prose_mentions(soup, version, filename):
    """形态四：正文段落里带标记的函数名，只记存在性。

    上游 ≤12 的 `functions-trigger.html`、`functions-event-triggers.html`、
    `functions-statistics.html` 只写一句「`pg_mcv_list_items` returns a list of …」，
    既没有表格行也没有 `pre.synopsis`。判据收得很紧：必须是 `<p>` 的直接子节点、
    带 `code.function` 标记，且该名字在别的版本有过真正的签名条目（调用方把关）。
    收进来的快照签名为空、`prose_only` 为真——如实说「上游这一版只在正文里提到」，
    不借别版的签名冒充。
    """
    found, seen = [], set()
    for node in soup.find_all(attrs={'class': 'function'}):
        parent = node.parent
        if parent is None or parent.name != 'p':
            continue
        name = text_of(node).partition('(')[0].strip()
        if not NAME_RE.match(name) or name.lower() in seen:
            continue
        seen.add(name.lower())
        html = clean_fragment(fragment_of(parent), version, filename)
        found.append({'name': name, 'anchor': nearest_anchor(node), 'file': filename,
                      'description': prose_text(html), 'description_html': html})
    return found


def parse_page(content, filename, version):
    """一页手册 → ([(函数名, 签名字典, 锚点, 兜底)], 本页标过的名字, 正文里提到的函数)。"""
    soup = BeautifulSoup(content or '', 'html.parser')
    if version.get('docbook'):
        normalize_docbook(soup)
    marked = set()
    for node in soup.find_all(attrs={'class': 'function'}):
        name = text_of(node).partition('(')[0].strip()
        if NAME_RE.match(name):
            marked.add(name.lower())
    found = harvest_signature_entries(soup, version, filename)
    found += harvest_old_tables(soup, version, filename)
    found += harvest_synopsis(soup, version, filename)
    return found, marked, harvest_prose_mentions(soup, version, filename)


# ------------------------------------------------------------------ 组装一个版本

def marked_names(contents):
    """一批页面里被标成 `code.function` 的名字（小写）。

    上游给同一个函数的标记并不一致：12 的 `functions-xml.html` 里 `table_to_xml` 标了，
    同一段 synopsis 里的 `schema_to_xml`、`cursor_to_xmlschema` 就没标。只按本版判断的话，
    这些函数会被误判成 13 才引入，所以把关用的名单取**全部版本**的并集。
    """
    found = set()
    for content in contents:
        for name in MARKED_RE.findall(content or ''):
            found.add(name.lower())
    return found


def harvest_version(pages, version, report, known=None):
    """一个版本的全部函数页 → ({name_key: 版本快照}, 正文里提到的函数)。"""
    order = sorted(pages, key=lambda name: (func_page_order(name), name))
    harvested, marked, mentions = [], set(), []
    for filename in order:
        found, names, mentioned = parse_page(pages[filename], filename, version)
        marked |= names
        mentions.extend(mentioned)
        if not any(not tentative for *_, tentative in found):
            report['pages_without_functions'].append([version['major'], filename])
        harvested.append((filename, found))
    marked |= known or set()

    collected = {}
    for filename, found in harvested:
        group = func_group_of(filename)
        for name, signature, anchor, tentative in found:
            key = name.lower()
            # 手册没标记的 synopsis：只有别处把这个名字标成函数才收，
            # 否则 `EXISTS (subquery)` 这样的语法形式会混进来。
            if tentative and key not in marked:
                continue
            item = collected.get(key)
            if item is None:
                item = collected[key] = {
                    'name': name, 'group': group,
                    'group_label': FUNC_GROUP_LABEL.get(group, group),
                    'pages': [], 'doc': {'file': filename, 'anchor': anchor,
                                         'slug': version['doc_slug']},
                    'lang': version['lang'], 'layout': version['layout'],
                    'signatures': [], 'description_zh': '', 'description': '',
                    'description_html': '', 'description_zh_html': '', 'zh_from': '',
                    'prose_only': False, '_seen': set(),
                }
            if filename not in item['pages']:
                item['pages'].append(filename)
            if signature['text'] in item['_seen']:
                continue
            item['_seen'].add(signature['text'])
            item['signatures'].append(signature)
    for item in collected.values():
        item.pop('_seen', None)
        head = item['signatures'][0]
        item['description_zh'] = head['description_zh']
        item['description'] = head['description']
        item['description_html'] = head['description_html']
    return collected, mentions


def prose_snapshot(mention, version):
    """正文里提到的函数 → 一份没有签名的版本快照。"""
    group = func_group_of(mention['file'])
    return {
        'name': mention['name'], 'group': group,
        'group_label': FUNC_GROUP_LABEL.get(group, group),
        'pages': [mention['file']],
        'doc': {'file': mention['file'], 'anchor': mention['anchor'],
                'slug': version['doc_slug']},
        # 事实一律来自上游英文原页，版本行上没有 lang 这一列。
        'lang': 'en', 'layout': version['layout'],
        'signatures': [], 'prose_only': True, 'zh_from': '',
        'description_zh': '', 'description': mention['description'],
        'description_html': mention['description_html'], 'description_zh_html': '',
    }


def apply_mentions(per_version, mentions, versions, report):
    """正文提到的函数：别的版本有过真正的签名条目才收，只记存在性。

    上游 ≤12 只在正文里写一句的那几个函数（`pg_mcv_list_items` 一类），不收就会被
    误判成 13 才引入；借别版的签名又等于替上游编内容，所以签名留空、记 `prose_only`。
    """
    confirmed = {key for snapshots in per_version.values() for key in snapshots}
    added = []
    for version in versions:
        major = version['major']
        for mention in mentions.get(major, ()):
            key = mention['name'].lower()
            if key not in confirmed or key in per_version[major]:
                continue
            per_version[major][key] = prose_snapshot(mention, version)
            added.append('{}@{}'.format(mention['name'], major))
    report['prose_only'] = {'count': len(added), 'entries': sorted(added)}
    return added


# ------------------------------------------------------------------ 版本间比较

def normal_description(value):
    return ' '.join((value or '').split()).rstrip('.。 ').strip()


def compare_snapshots(left, right, from_major='', to_major=''):
    """相邻两版的变化记录；没有任何变化返回 None。

    12 → 13 是手册重排（`layout` 从五列表换成签名段），签名文本整体改写，逐条比会把
    几百个函数全标成「变化」：这一跳只记增删，签名与描述一律不比。中英之间（9.6 → 10）
    同理不比描述，但签名是代码，照比。
    """
    if not left and not right:
        return None
    record = {'from': from_major, 'to': to_major, 'status': 'changed',
              'signatures': {'added': [], 'removed': []}, 'descriptions_changed': False,
              'group_changed': None, 'doc_overhaul': False}
    if not left:
        return dict(record, status='added')
    if not right:
        return dict(record, status='removed')
    if left.get('group') != right.get('group'):
        record['group_changed'] = {'from': left.get('group', ''), 'to': right.get('group', '')}
    record['doc_overhaul'] = left.get('layout') != right.get('layout')
    # 一侧只在正文里被提到、没有签名时，两边没有可比的东西：硬比会把「12 没签名、
    # 13 有签名」算成新增 N 条签名，changed_in 与索引页的版本方格都会脏。
    comparable = bool(left.get('signatures')) and bool(right.get('signatures'))
    if not record['doc_overhaul'] and comparable:
        before = [item['text'] for item in left.get('signatures') or ()]
        after = [item['text'] for item in right.get('signatures') or ()]
        record['signatures'] = {'added': [text for text in after if text not in set(before)],
                                'removed': [text for text in before if text not in set(after)]}
        if left.get('lang') == right.get('lang'):
            field = 'description_zh' if left.get('lang') == 'zh' else 'description'
            record['descriptions_changed'] = (normal_description(left.get(field)) !=
                                              normal_description(right.get(field)))
    if not (record['signatures']['added'] or record['signatures']['removed'] or
            record['descriptions_changed'] or record['group_changed'] or record['doc_overhaul']):
        return None
    return record


def build_changes(snapshots, order):
    out = []
    for left, right in zip(order, order[1:]):
        change = compare_snapshots(snapshots.get(left), snapshots.get(right), left, right)
        if change:
            out.append(change)
    return out


def build_transition(version, previous, functions):
    """一个版本相对上一版的汇总（契约 §2.1）。"""
    transition = {'from': previous, 'added': [], 'removed': [], 'changed': [], 'moved': [],
                  'doc_overhaul': False}
    for item in functions:
        for change in item['changes']:
            if change['to'] != version or change['from'] != previous:
                continue
            if change['status'] == 'added':
                transition['added'].append(item['slug'])
            elif change['status'] == 'removed':
                transition['removed'].append(item['slug'])
            counts = change['signatures']
            if counts['added'] or counts['removed']:
                transition['changed'].append({'slug': item['slug'], 'added': len(counts['added']),
                                              'removed': len(counts['removed'])})
            if change['group_changed']:
                transition['moved'].append({'slug': item['slug'], **change['group_changed']})
            transition['doc_overhaul'] = transition['doc_overhaul'] or change['doc_overhaul']
    return transition


# ------------------------------------------------------------------ 上游抓取

def cache_path(cache_dir, major, filename):
    return Path(cache_dir) / major / filename


def fetch_page(url, path, report, offline=False):
    """抓一页并缓存；同名文件在就不再联网，`offline` 时缺了就报错。"""
    if path.exists():
        return path.read_text(encoding='utf-8', errors='replace')
    if offline:
        raise OSError('缓存里没有 {}，去掉 --offline 再跑'.format(path))
    request = urllib.request.Request(url, headers={'User-Agent': UPSTREAM_UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode('utf-8', 'replace')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')
    report['downloads'] = report.get('downloads', 0) + 1
    time.sleep(UPSTREAM_PAUSE)
    return body


def fetch_upstream(major, cache_dir, report, offline=False):
    """一个版本的全部函数页；失败抛 OSError，由调用方降级。"""
    slug = upstream_slug(major)
    index = fetch_page(UPSTREAM_URL.format(slug, 'functions.html'),
                       cache_path(cache_dir, major, 'functions.html'), report, offline)
    soup = BeautifulSoup(index, 'html.parser')
    files = []
    for link in soup.select('a[href]'):
        name = urlsplit(link['href']).path.rsplit('/', 1)[-1]
        if FILE_RE.fullmatch(name) and name not in files:
            files.append(name)
    if not files:
        raise OSError('{} 的 functions.html 里没有找到子页面'.format(major))
    return {name: fetch_page(UPSTREAM_URL.format(slug, name),
                             cache_path(cache_dir, major, name), report, offline)
            for name in files}


def upstream_pages(majors, cache_dir, offline, report):
    """尽力抓全；哪一版失败就跳过哪一版，报告里记下来。"""
    out = {}
    for major in majors:
        try:
            out[major] = fetch_upstream(major, cache_dir, report, offline)
        except (OSError, ValueError, urllib.error.URLError) as error:
            report['failures'].append({'major': major, 'error': str(error)})
    report['majors'] = sorted(out, key=version_key)
    return out


# ------------------------------------------------------------------ 中文叠加层

def harvest_manual(major, doc_slug):
    """本站手册的一版 → {name_key: 中文描述与逐签名译文}；只取中文，不取事实。"""
    pages = manual_pages(major)
    if not pages:
        return {}
    context = parse_context(major, doc_slug, 'zh')
    collected, mentions = harvest_version(pages, context, {'pages_without_functions': []})
    out = {}
    for key, item in collected.items():
        out[key] = {
            'description': item['description_zh'],
            'description_html': item['description_html'],
            'signatures': {signature['text']: (signature['description_zh'],
                                               signature['description_html'])
                           for signature in item['signatures']},
            'order': [signature['description_zh'] for signature in item['signatures']],
            'order_html': [signature['description_html'] for signature in item['signatures']],
        }
    # 只在正文里提到的函数也要出中文，否则那几版的条目只有英文。
    for mention in mentions:
        key = mention['name'].lower()
        if key in out or not mention['description']:
            continue
        out[key] = {'description': mention['description'],
                    'description_html': mention['description_html'],
                    'signatures': {}, 'order': [], 'order_html': []}
    return out


def attach_signature_zh(snapshot, entry, source, report):
    """逐条签名配中文：先按签名文本对，对不上且条数一致时按位置兜底。

    每条签名自己带一份 `zh_from`：整份快照有译文不代表每条签名都配得上，
    页面靠它决定哪一条显示中文、哪一条退回英文。
    """
    signatures = snapshot['signatures']
    matched = 0
    for signature in signatures:
        text, html = entry['signatures'].get(signature['text'], ('', ''))
        if text:
            matched += 1
        signature['description_zh'] = text
        signature['description_zh_html'] = html
        signature['zh_from'] = source if text else ''
    report['by_text'] += matched
    if matched or len(signatures) != len(entry['order']):
        report['unmatched'] += len(signatures) - matched
        return
    for index, signature in enumerate(signatures):
        signature['description_zh'] = entry['order'][index]
        signature['description_zh_html'] = entry['order_html'][index]
        signature['zh_from'] = source if entry['order'][index] else ''
    report['by_position'] += sum(bool(item) for item in entry['order'])


def apply_chinese(functions, order, manual, report):
    """把本站手册的中文叠到上游事实上。

    同版有译文就用（`zh_from='doc'`）；没有就按版本距离就近借另一版，且只在**英文描述
    完全相同**时才借（`'inherited'`）；再没有就留空，页面显示英文（`''`）。
    """
    counts = {'doc': 0, 'inherited': 0, 'none': 0}
    rank = {major: index for index, major in enumerate(order)}
    for item in functions:
        key = item['name_key']
        present = item['present_in']
        having = [major for major in present if (manual.get(major) or {}).get(key, {}).get('description')]
        for major in present:
            snapshot = item['versions'][major]
            source = major if major in having else ''
            if not source:
                english = normal_description(snapshot['description'])
                nearby = sorted(having, key=lambda other: (abs(rank[other] - rank[major]),
                                                           rank[other]))
                source = next((other for other in nearby if english and normal_description(
                    item['versions'][other]['description']) == english), '')
                snapshot['zh_from'] = 'inherited' if source else ''
            else:
                snapshot['zh_from'] = 'doc'
            if not source:
                counts['none'] += 1
                continue
            counts[snapshot['zh_from']] += 1
            entry = manual[source][key]
            snapshot['description_zh'] = entry['description']
            snapshot['description_zh_html'] = entry['description_html']
            attach_signature_zh(snapshot, entry, snapshot['zh_from'], report)
    return counts


# ------------------------------------------------------------------ 导出

def repo_head():
    result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                            cwd=Path(__file__).resolve().parents[2],
                            capture_output=True, text=True, timeout=10)
    return result.stdout.strip() or 'unknown'


def manual_pages(major):
    tree = DEVEL_TREE if major == DEVEL_MAJOR else float(major)
    rows = DocPage_objects().filter(version=tree, file__startswith='functions-') \
        .values_list('file', 'content')
    return {name: content for name, content in rows if FILE_RE.fullmatch(name)}


def export_snapshot(offline=False, cache_dir=CACHE_DIR):
    """上游英文原页读成事实，本站手册叠中文，产出一份自包含快照。"""
    generated = datetime.now(timezone.utc).isoformat()
    source_rev = repo_head()
    report = {'versions': {}, 'pages_without_functions': [], 'multi_group': [],
              'upstream': {'majors': [], 'failures': []}, 'zh': {}, 'doc_overhaul_at': []}
    fetched = upstream_pages(upstream_majors(), cache_dir, offline, report['upstream'])
    if not fetched:
        raise ValueError('一个上游版本都没抓到：{}'.format(report['upstream']['failures']))

    manual = manual_majors()
    known = marked_names(content for pages in fetched.values() for content in pages.values())
    versions = version_rows(fetched, manual)
    order = [version['major'] for version in versions]
    per_version, mentions = {}, {}
    for version in versions:
        major = version['major']
        context = parse_context(major, version['doc_slug'], 'en')
        per_version[major], mentions[major] = harvest_version(
            fetched[major], context, report, known)
    apply_mentions(per_version, mentions, versions, report)
    for version in versions:
        major = version['major']
        version['function_count'] = len(per_version[major])
        version['signature_count'] = sum(len(item['signatures'])
                                         for item in per_version[major].values())
        report['versions'][major] = {
            'functions': version['function_count'], 'signatures': version['signature_count'],
            'pages': len(fetched[major]), 'layout': version['layout'], 'zh': 0,
        }

    keys = sorted({key for snapshots in per_version.values() for key in snapshots})
    functions = []
    for key in keys:
        snapshots = {major: per_version[major][key] for major in order if key in per_version[major]}
        present = [major for major in order if major in snapshots]
        last = snapshots[present[-1]]
        groups = []
        for major in present:
            for filename in snapshots[major]['pages']:
                group = func_group_of(filename)
                if group not in groups:
                    groups.append(group)
        groups.sort(key=lambda slug: FUNC_GROUP_ORDER.get(slug, len(FUNC_GROUPS)))
        changes = build_changes(snapshots, order)
        functions.append({
            'slug': func_slug(last['name']), 'name': last['name'], 'name_key': key,
            'group': last['group'], 'group_label': last['group_label'], 'groups': groups,
            'summary': '', 'summary_zh': '',
            'signature': last['signatures'][0]['text'] if last['signatures'] else '',
            'first_version': present[0], 'last_version': present[-1], 'present_in': present,
            'changed_in': [change['to'] for change in changes
                           if change['signatures']['added'] or change['signatures']['removed']],
            'signature_count': len(last['signatures']),
            'versions': {major: snapshots[major] for major in present},
            'changes': changes, 'position': 0, 'source_rev': source_rev,
        })
        if len(groups) > 1:
            report['multi_group'].append([functions[-1]['slug'], groups])

    # 中文叠加层：本站手册按 name_key 对齐，只补描述。
    translations = {major: harvest_manual(major, doc_slug_of(major, manual))
                    for major in order if doc_slug_of(major, manual)}
    match = {'by_text': 0, 'by_position': 0, 'unmatched': 0}
    report['zh'] = apply_chinese(functions, order, translations, match)
    report['zh']['signatures'] = match
    for item in functions:
        present = item['present_in']
        item['summary'] = first_sentence(next(
            (item['versions'][major]['description'] for major in reversed(present)
             if item['versions'][major]['description']), ''))
        item['summary_zh'] = first_sentence(next(
            (item['versions'][major]['description_zh'] for major in reversed(present)
             if item['versions'][major]['description_zh']), ''))
        item['versions'] = {major: strip_snapshot(item['versions'][major]) for major in present}

    for version in versions:
        major = version['major']
        version['zh_coverage'] = sum(major in item['versions'] and
                                     bool(item['versions'][major]['description_zh'])
                                     for item in functions)
        report['versions'][major]['zh'] = version['zh_coverage']

    assign_positions(functions)
    for position, version in enumerate(versions):
        previous = order[position - 1] if position else ''
        if not previous:
            continue
        version['transition'] = build_transition(version['major'], previous, functions)
        version['added_count'] = len(version['transition']['added'])
        version['removed_count'] = len(version['transition']['removed'])
        version['changed_count'] = len(version['transition']['changed'])
        if version['transition']['doc_overhaul']:
            report['doc_overhaul_at'].append(version['major'])

    snapshot = {
        'format': FORMAT, 'generated_at': generated, 'source_rev': source_rev,
        'default_major': next((v['major'] for v in versions if v['status'] == 'stable'), order[-1]),
        'stats': {
            'functions': len(functions), 'versions': len(versions),
            'snapshots': sum(len(item['versions']) for item in functions),
            'signatures': sum(len(snap['signatures']) for item in functions
                              for snap in item['versions'].values()),
            'changes': sum(len(item['changes']) for item in functions),
            'removed': sum(item['last_version'] != order[-1] for item in functions),
            'zh_coverage': sum(version['zh_coverage'] for version in versions),
        },
        'harvest': report, 'versions': versions, 'functions': functions,
    }
    validate(snapshot)
    return snapshot


def strip_snapshot(item):
    """写进快照的版本快照：只留契约里的键加两段描述 HTML，中间产物不留。"""
    keep = SNAPSHOT_FIELDS + ('description_html', 'description_zh_html')
    return {field: item[field] for field in keep}


def assign_positions(functions):
    buckets = defaultdict(list)
    for item in functions:
        buckets[item['group']].append(item)
    for group, members in buckets.items():
        members.sort(key=lambda item: item['name_key'])
        base = FUNC_GROUP_ORDER.get(group, len(FUNC_GROUPS)) * 1000
        for rank, item in enumerate(members):
            item['position'] = base + rank
    functions.sort(key=lambda item: (item['position'], item['slug']))


# ------------------------------------------------------------------ 校验

def require(item, fields, label):
    if not isinstance(item, dict):
        raise ValueError('{} 不是对象'.format(label))
    absent = [field for field in fields if field not in item]
    if absent:
        raise ValueError('{} 缺少字段：{}'.format(label, '、'.join(absent)))


def validate(snapshot):
    require(snapshot, ('format', 'generated_at', 'source_rev', 'default_major', 'stats',
                       'harvest', 'versions', 'functions'), '快照')
    if snapshot['format'] != FORMAT:
        raise ValueError('快照格式应为 {}'.format(FORMAT))
    for key in ('versions', 'functions'):
        if not isinstance(snapshot[key], list) or not snapshot[key]:
            raise ValueError('快照缺少 {}'.format(key))
    for version in snapshot['versions']:
        require(version, ('major',) + VERSION_FIELDS, '版本')
    order = [version['major'] for version in snapshot['versions']]
    if len(set(order)) != len(order) or order != sorted(order, key=version_key):
        raise ValueError('版本重复或顺序不对')
    if snapshot['default_major'] not in order:
        raise ValueError('default_major 引用了未知版本')
    seen_slug, seen_key = set(), set()
    for item in snapshot['functions']:
        require(item, ('slug',) + FUNCTION_FIELDS, '函数')
        slug, key = item['slug'], item['name_key']
        if not SLUG_RE.fullmatch(slug) or slug in seen_slug:
            raise ValueError('函数 slug 无效或重复：{}'.format(slug))
        if not NAME_RE.fullmatch(item['name']) or key != item['name'].lower() or key in seen_key:
            raise ValueError('函数名无效或重复：{}'.format(item['name']))
        seen_slug.add(slug)
        seen_key.add(key)
        if not item['versions']:
            raise ValueError('{} 没有任何版本快照'.format(slug))
        present = [major for major in order if major in item['versions']]
        if (set(item['versions']) - set(order) or present != item['present_in'] or
                item['first_version'] != present[0] or item['last_version'] != present[-1]):
            raise ValueError('{} 版本覆盖不一致'.format(slug))
        for group in [item['group'], *item['groups']]:
            if group not in FUNC_GROUP_ORDER:
                raise ValueError('{} 的分组不认识：{!r}'.format(slug, group))
        if not any(snap['signatures'] for snap in item['versions'].values()):
            # 允许个别版本只在正文里被提到（签名为空），但不能一条签名都没有。
            raise ValueError('{} 在所有版本里都没有签名'.format(slug))
        for major, snap in item['versions'].items():
            label = '{} @ {}'.format(slug, major)
            require(snap, SNAPSHOT_FIELDS, label)
            # 没有签名的版本必须如实标成「只在正文里提到」，反过来也不许自相矛盾。
            if not snap['signatures'] and not snap['prose_only']:
                raise ValueError('{} 没有签名却没标 prose_only'.format(label))
            if snap['prose_only'] and snap['signatures']:
                raise ValueError('{} 标了 prose_only 却带着签名'.format(label))
            for signature in snap['signatures']:
                require(signature, SIGNATURE_FIELDS, label + ' 签名')
                if signature['zh_from'] not in ZH_SOURCES:
                    raise ValueError('{} 签名 zh_from 无效'.format(label))
                for example in signature['examples']:
                    require(example, ('expr', 'result'), label + ' 示例')
            if not FILE_RE.fullmatch(snap['doc']['file']):
                raise ValueError('{} 手册文件名无效'.format(label))
            if snap['zh_from'] not in ZH_SOURCES:
                raise ValueError('{} zh_from 无效：{!r}'.format(label, snap['zh_from']))
            if snap['zh_from'] and not snap['description_zh']:
                raise ValueError('{} 标了 zh_from 却没有中文描述'.format(label))
        for change in item['changes']:
            require(change, CHANGE_FIELDS, slug + ' 变化')
            if change['status'] not in ('added', 'removed', 'changed'):
                raise ValueError('{} 变化状态无效：{}'.format(slug, change['status']))
        expected = [change['to'] for change in item['changes']
                    if change['signatures']['added'] or change['signatures']['removed']]
        if item['changed_in'] != expected:
            raise ValueError('{} changed_in 不一致'.format(slug))
    for version in snapshot['versions']:
        actual = sum(version['major'] in item['versions'] for item in snapshot['functions'])
        if version['function_count'] != actual:
            raise ValueError('{} 函数数不一致'.format(version['major']))
    for item in snapshot['functions']:
        item_hash(PgFunction, item, FUNCTION_FIELDS)
    return True


# ------------------------------------------------------------------ 写库

def changed_slugs(snapshot):
    stored = {row.slug: row for row in PgFunction.objects.only('slug', 'content_hash')}
    added, updated, unchanged = [], [], []
    for item in snapshot['functions']:
        calculated = item_hash(PgFunction, item, FUNCTION_FIELDS)
        row = stored.get(item['slug'])
        bucket = (added if row is None else
                  updated if row.content_hash != calculated
                  else unchanged)
        bucket.append(item['slug'])
    incoming = {item['slug'] for item in snapshot['functions']}
    majors = {version['major'] for version in snapshot['versions']}
    missing = {'functions': sorted(set(stored) - incoming),
               'versions': [row.major for row in FuncVersion.objects.all()
                            if row.major not in majors]}
    return added, updated, unchanged, missing


def retention_note(missing):
    parts = []
    if missing['functions']:
        parts.append('函数 {} 个'.format(len(missing['functions'])))
    if missing['versions']:
        parts.append('版本 ' + '、'.join(missing['versions']))
    if not parts:
        return ''
    return '快照里没有但库里还在：{}。未加 --prune，这些记录保留。'.format('，'.join(parts))


def preview(snapshot):
    """不写库，只报告这次导入会改动什么。"""
    validate(snapshot)
    added, updated, unchanged, missing = changed_slugs(snapshot)
    return {'versions': len(snapshot['versions']), 'functions': len(snapshot['functions']),
            'added': len(added), 'updated': len(updated), 'unchanged': len(unchanged),
            'missing': missing, 'removed': {'functions': 0, 'versions': []},
            'note': retention_note(missing), 'stats': snapshot['stats'],
            'zh': snapshot['harvest'].get('zh', {}), 'harvest': snapshot['harvest']}


def forget():
    """页面缓存 5 分钟，导入后主动清掉；页面模块还没落地时不拦着导入。"""
    try:
        from . import func
    except ImportError:
        return
    getattr(func, 'forget', lambda: None)()


@transaction.atomic
def import_snapshot(snapshot, prune=False):
    """按 slug 原位更新。整条比对无变化的函数跳过，不重写 JSON 列。"""
    report = preview(snapshot)
    added, updated, _, missing = changed_slugs(snapshot)
    for version in snapshot['versions']:
        FuncVersion.objects.update_or_create(
            major=version['major'], defaults={field: version[field] for field in VERSION_FIELDS})
    write = set(added) | set(updated)
    for item in snapshot['functions']:
        if item['slug'] in write:
            PgFunction.objects.update_or_create(
                slug=item['slug'], defaults=hashed_defaults(PgFunction, item, FUNCTION_FIELDS))
    report['pruned'] = bool(prune)
    if prune:
        stale = PgFunction.objects.filter(slug__in=missing['functions'])
        report['removed'] = {'functions': stale.count(), 'versions': list(missing['versions'])}
        stale.delete()
        FuncVersion.objects.filter(major__in=missing['versions']).delete()
        report['note'] = ''
    transaction.on_commit(forget)
    return report


def digest(snapshot):
    """一份快照的内容指纹，方便核对两端加载的是同一份。"""
    payload = json.dumps({'versions': snapshot['versions'], 'functions': snapshot['functions']},
                         ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
