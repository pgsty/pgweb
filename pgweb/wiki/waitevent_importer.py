"""导入等待事件百科。

两步，和系统目录栏目同形：`export_snapshot()` 把图谱 + 本站手册 + 上游文档读成一份自包含
快照，`import_snapshot()` 把快照写进库。拆开是为了让同一份快照分别加载本地与生产——
导出要读本地手册译文与源仓库，导入只认快照，生产机上什么都不需要。

三层来源叠在一起（契约见 docs/waitevent-column.md §1）：

1. 图谱 `~/pg.center/wait`：13 – 18 的逐版本英文描述、中文官方描述与整份档案；
2. 本站手册 `docs` 表的 `monitoring-stats.html`：10 – 19 与 devel 的中文描述；
3. 上游：9.6 – 12 的英文总表（本站没有 9.6 手册，9.6 的事件身份也只有这一来源），
   以及 `wait_event_names.txt` 在 `REL_19_BETA3` 与 `master` 的内容（19、20 的英文描述）。

9.0 – 9.5 没有 `wait_event` 列，这六个版本在快照里存在、事件数为 0、`has_wait_events=False`。
身份归一与快照比较的规则只在 `waitevent_common.py` 一处，导入与页面共用。
"""

import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone

from bs4 import BeautifulSoup, Tag
from django.db import transaction

from pgweb.docs.versions import DEVEL_MAJOR_VERSION

from .snapshot import item_hash, hashed_defaults
from .models import WAITEVENT_TYPE_ORDER, WaitEvent, WaitEventVersion
from .waitevent_common import canonical_type, compare_snapshots, identity, normal_text, position_of


FORMAT = 1
DEFAULT_ROOT = '~/pg.center/wait'
CACHE_DIR = 'tmp/waitevent-sources'
USER_AGENT = 'pgsql.cc waitevent importer (+https://pgsql.cc)'

DOC_FILE = 'monitoring-stats.html'
DEVEL_MAJOR = str(DEVEL_MAJOR_VERSION)
DEVEL_TREE = 0

# 18 个大版本。9.0 – 9.5 没有等待事件机制；状态与 position 跟 wiki_catalog_version 同一套值。
# (major, label, status, support_status, doc_slug, has_wait_events)
VERSION_SPEC = (
    ('9.0', '9.0', 'historical', 'end-of-life', '9.0', False),
    ('9.1', '9.1', 'historical', 'end-of-life', '9.1', False),
    ('9.2', '9.2', 'historical', 'end-of-life', '9.2', False),
    ('9.3', '9.3', 'historical', 'end-of-life', '9.3', False),
    ('9.4', '9.4', 'historical', 'end-of-life', '9.4', False),
    ('9.5', '9.5', 'historical', 'end-of-life', '9.5', False),
    ('9.6', '9.6', 'historical', 'end-of-life', '9.6', True),
    ('10', '10', 'historical', 'end-of-life', '10', True),
    ('11', '11', 'historical', 'end-of-life', '11', True),
    ('12', '12', 'historical', 'end-of-life', '12', True),
    ('13', '13', 'historical', 'end-of-life', '13', True),
    ('14', '14', 'historical', 'supported', '14', True),
    ('15', '15', 'historical', 'supported', '15', True),
    ('16', '16', 'historical', 'supported', '16', True),
    ('17', '17', 'historical', 'supported', '17', True),
    ('18', '18', 'stable', 'supported', '18', True),
    ('19', '19 beta 3', 'preview', 'preview', '19', True),
    (DEVEL_MAJOR, DEVEL_MAJOR + ' devel', 'devel', 'devel', 'devel', True),
)
VERSION_ORDER = [major for major, _, _, _, _, _ in VERSION_SPEC]
LIVE_ORDER = [major for major, _, _, _, _, live in VERSION_SPEC if live]
# 大版本 → 本站手册地址段。9.6 本站没有手册，`slug` 仍写 9.6，由页面判断有没有那一版。
DOC_SLUG = {major: slug for major, _, _, _, slug, _ in VERSION_SPEC}

# 12 → 13 那批机械对不上的更名（契约 §2 预留的 CURATED_RENAMES），'旧 Type/Name' → '13 的 Type/Name'。
# 依据：PostgreSQL 13 发行说明「监控」一节的“统一等待事件命名”条目，以及 13 源码里
# src/include/storage/lwlocknames.txt（具名锁：CLogControl → XactSLRU 等）、
# src/backend/storage/lmgr/lwlock.c 的 BuiltinTrancheNames（tranche：clog → XactBuffer 等）、
# src/backend/executor/nodeHash.c（并行哈希的 IPC 事件去掉 -ing）。每一对语义相同、
# 只是名字变了，故记为更名而非移除 + 新增。RecoveryWalAll 与 buffer_io 之外的移除照旧。
# 12 的 Activity/RecoveryWalStream 在 13 改成 Timeout/RecoveryRetrieveRetryInterval，而
# RecoveryWalAll 改名占用了 RecoveryWalStream；同一个名字在两版指两件事，全局映射表达不了，
# 这一对如实留作移除 + 新增。
CURATED_RENAMES = {
    # 具名轻量级锁（lwlocknames.txt）
    'LWLock/CLogControlLock': 'LWLock/XactSLRU',
    'LWLock/CLogTruncationLock': 'LWLock/XactTruncation',
    'LWLock/CommitTsControlLock': 'LWLock/CommitTsSLRU',
    'LWLock/SubtransControlLock': 'LWLock/SubtransSLRU',
    'LWLock/MultiXactOffsetControlLock': 'LWLock/MultiXactOffsetSLRU',
    'LWLock/MultiXactMemberControlLock': 'LWLock/MultiXactMemberSLRU',
    'LWLock/AsyncCtlLock': 'LWLock/NotifySLRU',
    'LWLock/AsyncQueueLock': 'LWLock/NotifyQueue',
    'LWLock/OldSerXidLock': 'LWLock/SerialSLRU',
    'LWLock/SerializablePredicateLockListLock': 'LWLock/SerializablePredicateList',
    # 轻量级锁 tranche（lwlock.c BuiltinTrancheNames）
    'LWLock/clog': 'LWLock/XactBuffer',
    'LWLock/commit_timestamp': 'LWLock/CommitTsBuffer',
    'LWLock/subtrans': 'LWLock/SubtransBuffer',
    'LWLock/multixact_offset': 'LWLock/MultiXactOffsetBuffer',
    'LWLock/multixact_member': 'LWLock/MultiXactMemberBuffer',
    'LWLock/async': 'LWLock/NotifyBuffer',
    'LWLock/oldserxid': 'LWLock/SerialBuffer',
    'LWLock/replication_origin': 'LWLock/ReplicationOriginState',
    'LWLock/proc': 'LWLock/LockFastPath',
    'LWLock/tbm': 'LWLock/SharedTidBitmap',
    'LWLock/serializable_xact': 'LWLock/PerXactPredicateList',
    # buffer_io 在 13 改名 BufferIO，14 起换成条件变量并归入 IPC；图谱的映射接着把 13 的
    # LWLock/BufferIO 指向 IPC/BufferIO，identity() 会沿着两跳走到底。
    'LWLock/buffer_io': 'LWLock/BufferIO',
    # 并行哈希连接的进程间事件（nodeHash.c）
    'IPC/ClogGroupUpdate': 'IPC/XactGroupUpdate',
    'IPC/Hash/Batch/Allocating': 'IPC/HashBatchAllocate',
    'IPC/Hash/Batch/Electing': 'IPC/HashBatchElect',
    'IPC/Hash/Batch/Loading': 'IPC/HashBatchLoad',
    'IPC/Hash/Build/Allocating': 'IPC/HashBuildAllocate',
    'IPC/Hash/Build/Electing': 'IPC/HashBuildElect',
    'IPC/Hash/Build/HashingInner': 'IPC/HashBuildHashInner',
    'IPC/Hash/Build/HashingOuter': 'IPC/HashBuildHashOuter',
    'IPC/Hash/GrowBatches/Allocating': 'IPC/HashGrowBatchesAllocate',
    'IPC/Hash/GrowBatches/Deciding': 'IPC/HashGrowBatchesDecide',
    'IPC/Hash/GrowBatches/Electing': 'IPC/HashGrowBatchesElect',
    'IPC/Hash/GrowBatches/Finishing': 'IPC/HashGrowBatchesFinish',
    'IPC/Hash/GrowBatches/Repartitioning': 'IPC/HashGrowBatchesRepartition',
    'IPC/Hash/GrowBuckets/Allocating': 'IPC/HashGrowBucketsAllocate',
    'IPC/Hash/GrowBuckets/Electing': 'IPC/HashGrowBucketsElect',
    'IPC/Hash/GrowBuckets/Reinserting': 'IPC/HashGrowBucketsReinsert',
    # 重量级锁：投机插入令牌
    'Lock/speculative token': 'Lock/spectoken',
}

ATLAS_MAJORS = ('13', '14', '15', '16', '17', '18')
# 上游英文总表：9.6 只有这一来源，10 – 12 用它补英文（中文取本站手册）。
UPSTREAM_HTML_MAJORS = ('9.6', '10', '11', '12')
# 19 与开发版的英文来自源码里的事件清单文件。
NAMES_TXT_TAGS = {'19': 'REL_19_BETA3', DEVEL_MAJOR: 'master'}
NAMES_TXT_URL = ('https://raw.githubusercontent.com/postgres/postgres/{}'
                 '/src/backend/utils/activity/wait_event_names.txt')
UPSTREAM_HTML_URL = 'https://www.postgresql.org/docs/{}/monitoring-stats.html'

# 本站手册里每类一张表的锚点后缀 → 该版写的原始类型标签。13 起用它，12 及更早只有一张总表。
DOC_TYPE_TABLES = (
    ('ACTIVITY', 'Activity'), ('BUFFER', 'Buffer'), ('BUFFERPIN', 'BufferPin'),
    ('CLIENT', 'Client'), ('EXTENSION', 'Extension'), ('IO', 'IO'), ('IPC', 'IPC'),
    ('LOCK', 'Lock'), ('LWLOCK', 'LWLock'), ('TIMEOUT', 'Timeout'),
)
TOTAL_ANCHOR = 'WAIT-EVENT-TABLE'
# 这几版的手册只有一张三列总表；13 起每类一张，`WAIT-EVENT-TABLE` 改成了类型说明表。
TOTAL_TABLE_MAJORS = ('9.6', '10', '11', '12')

# wait_event_names.txt 的节名 → 类型标签。LWLock、Lock、Extension 三节里的名字已是最终形式。
NAMES_TXT_SECTION = re.compile(r'^Section:\s*ClassName\s*-\s*"?WaitEvent(\w+)"?')
NAMES_TXT_VERBATIM = ('LWLock', 'Lock', 'Extension')

SPACE = re.compile(r'\s+')
KEY_RE = re.compile(r'^[a-z]+/[a-z0-9]+(?:~\d+)?$')

# DocBook 标记：guc- 开头的交叉引用还原成参数名，其余标签只留内容。
XREF_RE = re.compile(r'<xref\s+linkend="([^"]+)"\s*/>')
QUOTE_RE = re.compile(r'<quote>(.*?)</quote>', re.S)
TAG_RE = re.compile(r'</?[a-zA-Z][^>]*>')
# 交叉引用被删掉后留下的「; see .」这类残句。
SEE_RE = re.compile(r'[;,]?\s*\bsee\s+(?=[.,;]|$)')


# ------------------------------------------------------------------ 小工具

def text_of(node):
    """纯文本：去标签、折叠空白。"""
    if node is None:
        return ''
    raw = node.get_text() if isinstance(node, Tag) else str(node)
    return SPACE.sub(' ', raw.replace('\xa0', ' ')).strip()


def slug_of(name):
    """名字生成短横线小写：BufferContent → buffer-content。图谱有 slug 时不走这里。"""
    value = re.sub(r'(.)([A-Z][a-z]+)', r'\1-\2', name or '')
    value = re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', value)
    value = re.sub(r'[^A-Za-z0-9]+', '-', value)
    return value.strip('-').lower()


def camel_name(enum):
    """枚举名按 17 起的规则生成事件名：ARCHIVER_MAIN → ArchiverMain、IO_WORKER_MAIN → IoWorkerMain。"""
    return ''.join(part[:1].upper() + part[1:].lower() for part in (enum or '').split('_'))


def docbook_text(value):
    """wait_event_names.txt 里的描述带 DocBook 标记，还原成可读英文。"""
    def xref(match):
        target = match.group(1)
        # <xref linkend="guc-archive-command"/> 指的是参数 archive_command。
        return target[4:].replace('-', '_') if target.startswith('guc-') else ''

    value = XREF_RE.sub(xref, value or '')
    value = QUOTE_RE.sub(lambda match: '“' + match.group(1) + '”', value)
    value = TAG_RE.sub('', value)
    value = SEE_RE.sub('', value)
    value = value.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    return SPACE.sub(' ', value).strip()


def doc_anchor(type_label, major):
    """本站手册里这一行所在表的锚点。12 及更早是一张总表，13 起每类一张。"""
    if major in TOTAL_TABLE_MAJORS:
        return TOTAL_ANCHOR
    return 'WAIT-EVENT-{}-TABLE'.format((type_label or '').upper())


def read_json(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def file_stamp(path):
    """文件的修改时间，当作这份来源的抓取时间：重复导出得到同一份快照。"""
    if not os.path.exists(path):
        return ''
    return datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat()


def repo_head(root):
    try:
        out = subprocess.run(['git', '-C', root, 'rev-parse', '--short', 'HEAD'],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


# ------------------------------------------------------------------ HTML 表格

def table_at(soup, anchor):
    """按锚点定位一张表。9.6 的老版式锚点是表前的 `<a>`，不是表本身。"""
    node = soup.find(id=anchor) if soup is not None else None
    if node is None:
        return None
    if isinstance(node, Tag) and node.name == 'table':
        return node
    inner = node.find('table') if isinstance(node, Tag) else None
    return inner if inner is not None else node.find_next('table')


def body_rows(table):
    body = table.find('tbody') or table
    rows = body.find_all('tr', recursive=False)
    return rows or body.find_all('tr')


def header_texts(table):
    head = table.find('thead')
    if head is not None:
        return [text_of(cell) for cell in head.find_all(['th', 'td'])]
    first = table.find('tr')
    return [text_of(cell) for cell in first.find_all(['th', 'td'])] if first is not None else []


def find_total_table(soup):
    """三列总表：锚点找不到时按表头文字兜底。"""
    table = table_at(soup, TOTAL_ANCHOR)
    if table is not None and len(header_texts(table)) >= 3:
        return table
    for candidate in soup.find_all('table'):
        texts = header_texts(candidate)
        if len(texts) == 3 and ('Wait Event Type' in texts[0] or '等待事件类型' in texts[0]):
            return candidate
    return None


def total_table_rows(table):
    """三列总表（类型列带 rowspan）→ [(类型标签, 名称, 描述)]。"""
    rows, current = [], ''
    for line in body_rows(table):
        cells = line.find_all(['td', 'th'], recursive=False)
        if len(cells) >= 3:
            current = text_of(cells[0])
            name, description = text_of(cells[1]), text_of(cells[2])
        elif len(cells) == 2:
            name, description = text_of(cells[0]), text_of(cells[1])
        else:
            continue
        if name:
            rows.append((current, name, description))
    return rows


def typed_table_rows(table):
    """每类一张的两列表 → [(名称, 描述)]。"""
    rows = []
    for line in body_rows(table):
        cells = line.find_all(['td', 'th'], recursive=False)
        if len(cells) < 2:
            continue
        name, description = text_of(cells[0]), text_of(cells[1])
        if name:
            rows.append((name, description))
    return rows


def parse_event_tables(soup):
    """一页 monitoring-stats.html 里的等待事件表 → [(类型标签, 名称, 描述)]。

    13 起每类一张表；12 及更早是一张三列总表。13 起也有一张叫 `WAIT-EVENT-TABLE` 的表，
    但那是「等待事件类型」两列表，不是事件清单，所以先认分表。
    """
    rows = []
    for suffix, label in DOC_TYPE_TABLES:
        table = table_at(soup, 'WAIT-EVENT-{}-TABLE'.format(suffix))
        if table is None:
            continue
        rows.extend((label, name, description) for name, description in typed_table_rows(table))
    if rows:
        return rows
    table = find_total_table(soup)
    return total_table_rows(table) if table is not None else []


# ------------------------------------------------------------------ 本站手册

class Manual:
    """一个版本的本站手册。只读 monitoring-stats.html 一页，用完整个对象丢掉。"""

    def __init__(self, tree):
        self.tree = tree
        self._rows = None

    def rows(self):
        if self._rows is None:
            from pgweb.docs.models import DocPage
            page = DocPage.objects.filter(version=self.tree, file=DOC_FILE).only('content').first()
            soup = BeautifulSoup(page.content or '', 'html.parser') if page is not None else None
            self._rows = parse_event_tables(soup) if soup is not None else []
        return self._rows


def manual_rows(major):
    """某个大版本的本站手册行。20 读 devel 那棵树，9.x 本站没有手册。"""
    if major == DEVEL_MAJOR:
        return Manual(DEVEL_TREE).rows()
    if major.startswith('9.'):
        return []
    return Manual(int(major)).rows()


# ------------------------------------------------------------------ 上游抓取

def fetch_text(url, path, fetch, report):
    """缓存优先：同名文件在就不联网。抓不到只记一笔，不让整次导出失败。"""
    if os.path.exists(path):
        with open(path, encoding='utf-8') as handle:
            return handle.read()
    if not fetch:
        report['skipped'].append(os.path.basename(path))
        return ''
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode('utf-8', 'replace')
    except (urllib.error.URLError, OSError, ValueError) as error:
        report['failed'].append({'url': url, 'error': str(error)})
        return ''
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    report['fetched'].append(url)
    return text


def upstream_html_rows(text):
    soup = BeautifulSoup(text or '', 'html.parser')
    table = find_total_table(soup)
    return total_table_rows(table) if table is not None else []


def parse_names_txt(text):
    """源码里的事件清单 → [(类型标签, 名称, 英文描述)]。

    格式：节标题 `Section: ClassName - WaitEventXxx`，正文行 `ENUM_NAME<TAB>"description"`。
    `ABI_compatibility:` 是节内的续写区，里面的行照常算事件。
    """
    rows, label = [], ''
    for line in (text or '').splitlines():
        match = NAMES_TXT_SECTION.match(line)
        if match:
            label = match.group(1)
            continue
        line = line.rstrip()
        stripped = line.lstrip()
        if not stripped or stripped.startswith('#') or stripped.startswith('ABI_compatibility'):
            continue
        if '\t' not in line or not label:
            continue
        enum, _, raw = line.partition('\t')
        enum = enum.strip()
        if not enum:
            continue
        name = enum if label in NAMES_TXT_VERBATIM else camel_name(enum)
        rows.append((label, name, docbook_text(raw.strip().strip('"'))))
    return rows


# ------------------------------------------------------------------ 图谱

def read_atlas(root):
    """读图谱：逐版本身份与描述的矩阵、每个事件的档案、拼写更名与类型迁移表。"""
    matrix_path = os.path.join(root, 'facts', 'wait_event_matrix.json')
    events_path = os.path.join(root, 'data', 'wait_events.jsonl')
    if not os.path.exists(matrix_path):
        raise ValueError('找不到等待事件矩阵：{}'.format(matrix_path))
    if not os.path.exists(events_path):
        raise ValueError('找不到等待事件档案：{}'.format(events_path))

    # 人工核定的更名在前，图谱的映射在后：同一个键以图谱为准。
    canonical_map = dict(CURATED_RENAMES)
    map_path = os.path.join(root, 'facts', 'wait_event_canonical_map.json')
    if os.path.exists(map_path):
        canonical_map.update(read_json(map_path))
    manifest = {}
    manifest_path = os.path.join(root, 'facts', 'inventory_manifest.json')
    if os.path.exists(manifest_path):
        manifest = read_json(manifest_path)

    records = {}
    with open(events_path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            records[identity(record['type'], record['name'], canonical_map)] = record

    stamp = file_stamp(events_path)
    return {
        'matrix': read_json(matrix_path),
        'records': records,
        'canonical_map': canonical_map,
        'manifest': manifest,
        'stamp': stamp,
        'source_rev': '{}@{}'.format(stamp[:10], repo_head(root) or 'unknown'),
    }


# 档案原样带出的键，键名不改；其余（本地路径、抓取痕迹）不进库。
DOSSIER_KEYS = ('mechanism', 'normal', 'trouble', 'actions', 'incident_pattern', 'diagnostic_sql',
                'gucs', 'metrics', 'source_locations', 'source_status', 'emission', 'availability',
                'record_kind', 'official_descriptions')


def dossier_of(record):
    if not record:
        return {}
    return {key: record[key] for key in DOSSIER_KEYS if record.get(key) not in (None, '', [], {})}


# ------------------------------------------------------------------ 逐版本清单

def make_row(type_label, name, description, description_zh, source, major):
    return {
        'type': type_label, 'name': name,
        'description': description or '', 'description_zh': description_zh or '',
        'zh_from': 'doc' if description_zh else '', 'source': source,
        'doc': {'file': DOC_FILE, 'anchor': doc_anchor(type_label, major),
                'slug': DOC_SLUG.get(major, major)},
    }


def keyed(rows, canonical_map, major, collisions):
    """一版的原始行按身份归一成 {key: row}。

    同一版本内归一后撞 key 的不合并：按 (类型, 名称) 排序后，第一条用本名，其余加 `~2`、`~3`
    后缀。排序而不是按文档顺序，是为了让同一个事件在每个版本都落到同一个 key 上。
    """
    buckets = {}
    for row in rows:
        buckets.setdefault(identity(row['type'], row['name'], canonical_map), []).append(row)
    out = {}
    for key, bucket in sorted(buckets.items()):
        if len(bucket) == 1:
            out[key] = bucket[0]
            continue
        bucket.sort(key=lambda row: (row['type'], row['name']))
        for index, row in enumerate(bucket):
            out[key if index == 0 else '{}~{}'.format(key, index + 1)] = row
        collisions.append({'major': major, 'key': key,
                           'events': ['{}/{}'.format(row['type'], row['name']) for row in bucket]})
    return out


def doc_translations(major, canonical_map):
    """本站手册这一版的行，按身份归一，只用来取译文。"""
    return keyed([make_row(label, name, '', description, 'manual', major)
                  for label, name, description in manual_rows(major)], canonical_map, major, [])


def attach_zh(inventory, major, canonical_map, report):
    """把本站手册的译文按身份挂到清单上；手册里有、清单里没有的行记进报告。

    本站 14 – 18 的手册译文其实是 15 那张表的旧稿，19 的也是拼盘：归一后对得上就用，
    对不上的不硬塞，只记进 `doc_only`。
    """
    doc_rows = doc_translations(major, canonical_map)
    if not doc_rows:
        return
    report['doc_used'].append(major)
    for key, row in inventory.items():
        source = doc_rows.get(key)
        if source is not None and source['description_zh']:
            row['description_zh'] = source['description_zh']
            row['zh_from'] = 'doc'
    extra = sorted(set(doc_rows) - set(inventory))
    if extra:
        report['doc_only'][major] = extra


def atlas_inventory(atlas, major, collisions):
    """13 – 18：清单与英文描述都来自图谱矩阵，保留该版写的原始类型标签与名称。"""
    rows = []
    for entry in atlas['matrix']:
        if int(major) not in (entry.get('versions') or ()):
            continue
        rows.append(make_row(entry['type'], entry['name'],
                             (entry.get('descriptions') or {}).get(major, ''), '', 'atlas', major))
    return keyed(rows, atlas['canonical_map'], major, collisions)


def upstream_inventory(major, english, atlas, report, collisions):
    """英文清单（上游）+ 中文译文（本站手册）合成一版。

    上游抓不到时退回本站手册：清单与译文都出自手册，只是没有英文原文。两边都没有就整版缺席。
    """
    canonical_map = atlas['canonical_map']
    chinese = manual_rows(major)
    if english:
        rows = [make_row(label, name, description, '', 'upstream', major)
                for label, name, description in english]
        method = 'manual+upstream' if chinese else 'upstream'
    elif chinese:
        rows = [make_row(label, name, '', description, 'manual', major)
                for label, name, description in chinese]
        method = 'manual'
    else:
        report['absent'].append(major)
        return {}, ''
    inventory = keyed(rows, canonical_map, major, collisions)
    if english and chinese:
        attach_zh(inventory, major, canonical_map, report)
    return inventory, method


def build_inventories(atlas, fetch, cache_dir, report):
    """每个有等待事件的大版本一份 {key: 版本快照}。"""
    collisions = report['collisions']
    inventories, methods = {}, {}

    for major in ATLAS_MAJORS:
        inventories[major] = atlas_inventory(atlas, major, collisions)
        attach_zh(inventories[major], major, atlas['canonical_map'], report)
        methods[major] = 'atlas'
        report['stamps'][major] = atlas['stamp']

    for major in UPSTREAM_HTML_MAJORS:
        path = os.path.join(cache_dir, 'monitoring-stats-{}.html'.format(major))
        english = upstream_html_rows(fetch_text(UPSTREAM_HTML_URL.format(major), path, fetch,
                                                report['upstream']))
        inventories[major], methods[major] = upstream_inventory(
            major, english, atlas, report, collisions)
        report['stamps'][major] = file_stamp(path)

    for major, tag in NAMES_TXT_TAGS.items():
        path = os.path.join(cache_dir, 'wait_event_names-{}.txt'.format(tag))
        english = parse_names_txt(fetch_text(NAMES_TXT_URL.format(tag), path, fetch,
                                             report['upstream']))
        inventories[major], methods[major] = upstream_inventory(
            major, english, atlas, report, collisions)
        report['stamps'][major] = file_stamp(path)

    return inventories, methods


def check_generated_names(inventories, atlas, report):
    """19 / 20 的名字是按枚举名生成的，拿 18 图谱里的实际名字核对生成规则。"""
    reference = {key: row['name'] for key, row in (inventories.get('18') or {}).items()}
    compared, mismatched = 0, []
    for major in NAMES_TXT_TAGS:
        for key, row in (inventories.get(major) or {}).items():
            if key not in reference:
                continue
            compared += 1
            if reference[key] != row['name']:
                mismatched.append({'major': major, 'key': key,
                                   'generated': row['name'], 'atlas': reference[key]})
                # 生成规则与图谱不一致时以图谱名为准。
                row['name'] = reference[key]
    report['name_check'] = {'compared': compared, 'mismatched': mismatched}


# ------------------------------------------------------------------ 组装事件

def fill_atlas_zh(event, atlas_record):
    """图谱的中文官方描述填进 13 – 18 的快照：只在该版英文与图谱最后一版英文一致时。"""
    chinese = (atlas_record or {}).get('official_description_zh') or ''
    if not chinese:
        return
    official = (atlas_record or {}).get('official_descriptions') or {}
    present = [major for major in ATLAS_MAJORS if major in official]
    if not present:
        return
    reference = normal_text(official[present[-1]])
    for major in ATLAS_MAJORS:
        snapshot = event['versions'].get(major)
        if snapshot is None or snapshot['description_zh']:
            continue
        if normal_text(snapshot['description']) == reference:
            snapshot['description_zh'] = chinese
            snapshot['zh_from'] = 'atlas'


def inherit_zh(event):
    """本版无译文时跨版本借用：只在另一版英文归一后完全相同才借，就近优先。"""
    order = event['present_in']
    for index, major in enumerate(order):
        snapshot = event['versions'][major]
        english = snapshot['description']
        if not english or snapshot['description_zh']:
            continue
        best, best_key = '', None
        for other_index, other in enumerate(order):
            if other == major:
                continue
            source = event['versions'][other]
            if source['zh_from'] not in ('doc', 'atlas') or not source['description_zh']:
                continue
            if normal_text(source['description']) != normal_text(english):
                continue
            rank = (abs(other_index - index), -other_index)
            if best_key is None or rank < best_key:
                best, best_key = source['description_zh'], rank
        if best:
            snapshot['description_zh'] = best
            snapshot['zh_from'] = 'inherited'


def event_changes(event):
    """相邻版本变化记录。

    按整条版本序走，不是只走 present：缺席后重新出现记一条 added，最后存在版本的下一版记一条
    removed，两侧都不在时不记。9.6 是机制起点，那一版出现的事件也有一条 `{'to': '9.6'}` added。
    """
    changes = []
    for index, major in enumerate(LIVE_ORDER):
        previous = event['versions'].get(LIVE_ORDER[index - 1]) if index else None
        change = compare_snapshots(previous, event['versions'].get(major),
                                   LIVE_ORDER[index - 1] if index else '', major)
        if change is not None:
            changes.append(change)
    return changes


def assemble(inventories, atlas, report):
    """把逐版本清单拼成事件记录。"""
    keys = sorted({key for major in LIVE_ORDER for key in inventories.get(major) or {}})
    events = []
    for key in keys:
        versions = {major: inventories[major][key] for major in LIVE_ORDER
                    if key in (inventories.get(major) or {})}
        present = [major for major in LIVE_ORDER if major in versions]
        last = versions[present[-1]]
        type_label = canonical_type(last['type'])
        # 同版撞 key 的第二条是另一个事件，不能借用本名那条的档案，所以只按完整 key 查。
        record = atlas['records'].get(key)
        dossier = dossier_of(record)
        names = {snapshot['name'] for snapshot in versions.values()}
        labels = {snapshot['type'] for snapshot in versions.values()}
        event = {
            'key': key,
            'type': type_label,
            'type_slug': type_label.lower(),
            'name': last['name'],
            'slug': (record or {}).get('slug') or slug_of(last['name']),
            'aliases': sorted(names - {last['name']}),
            'type_variants': sorted(labels - {type_label}),
            'summary': last['description'],
            'summary_zh': '',
            'first_version': present[0],
            'last_version': present[-1],
            'present_in': present,
            'versions': versions,
            'dossier': dossier,
            'has_dossier': bool(dossier),
            'source_rev': atlas['source_rev'],
        }
        fill_atlas_zh(event, record)
        inherit_zh(event)
        event['changes'] = event_changes(event)
        event['changed_in'] = [change['to'] for change in event['changes']
                               if change['status'] == 'changed']
        latest_zh = next((versions[major]['description_zh'] for major in reversed(present)
                          if versions[major]['description_zh']), '')
        event['summary_zh'] = (record or {}).get('official_description_zh') or latest_zh
        events.append(event)

    ranks = {}
    for event in sorted(events, key=lambda item: (item['type'], item['name'].lower(), item['key'])):
        rank = ranks.get(event['type'], 0)
        event['position'] = position_of(event['type'], rank)
        ranks[event['type']] = rank + 1
    events.sort(key=lambda item: item['position'])
    unique_slugs(events, atlas['records'])
    report['events'] = len(events)
    return events


def unique_slugs(events, records):
    """slug 在类型内唯一：图谱给的 slug 先占位，生成的撞上了再加序号。

    同版撞 key 的那一对（`ReplicationOriginLock` 与 tranche `replication_origin`）名字不同、
    生成的 slug 却一样，页面按 slug 找事件时不能两条都命中。
    """
    taken = {(event['type_slug'], event['slug']) for event in events if event['key'] in records}
    for event in events:
        if event['key'] in records:
            continue
        if (event['type_slug'], event['slug']) not in taken:
            taken.add((event['type_slug'], event['slug']))
            continue
        index = 2
        while (event['type_slug'], '{}-{}'.format(event['slug'], index)) in taken:
            index += 1
        event['slug'] = '{}-{}'.format(event['slug'], index)
        taken.add((event['type_slug'], event['slug']))


# ------------------------------------------------------------------ 版本汇总

def build_transition(previous, current, from_major, to_major):
    """一版相对上一版的汇总，口径与逐事件的变化记录同出一源。"""
    out = {'from': from_major, 'added': [], 'removed': [], 'renamed': [], 'moved': [],
           'reworded': [], 'added_types': [], 'removed_types': [],
           'event_count_delta': len(current) - len(previous)}
    for key in sorted(set(previous) | set(current)):
        change = compare_snapshots(previous.get(key), current.get(key), from_major, to_major)
        if change is None:
            continue
        if change['status'] == 'added':
            out['added'].append(key)
        elif change['status'] == 'removed':
            out['removed'].append(key)
            continue
        if change['renamed']:
            out['renamed'].append(dict(change['renamed'], key=key))
        if change['moved']:
            out['moved'].append(dict(change['moved'], key=key))
        if change['reworded']:
            out['reworded'].append(key)
    before = {row['type'] for row in previous.values()}
    after = {row['type'] for row in current.values()}
    out['added_types'] = sorted(after - before)
    out['removed_types'] = sorted(before - after)
    return out


def version_notes(major, method, atlas, report):
    """来源说明：用了哪一版手册、哪个 tag、来源文件的时间戳。

    `fetched_at` 取来源文件的修改时间而不是导出时刻，同一批源文件重复导出得到同一份快照。
    """
    notes = {'doc_version': '', 'doc_tag': '', 'fetched_at': '', 'sources': []}
    if major in ATLAS_MAJORS:
        item = (atlas['manifest'].get('versions') or {}).get(major) or {}
        notes['doc_tag'] = item.get('source_release', '') or ''
        notes['sources'].append('wait.pg.center 图谱：{}'.format(item.get('method', 'atlas')))
    if major in NAMES_TXT_TAGS:
        notes['doc_tag'] = NAMES_TXT_TAGS[major]
        notes['sources'].append('wait_event_names.txt@' + NAMES_TXT_TAGS[major])
    if major in UPSTREAM_HTML_MAJORS:
        notes['sources'].append(UPSTREAM_HTML_URL.format(major))
    # 13 – 18 的清单出自图谱，译文仍采自本站手册，也要记一笔。
    if major in report['doc_used']:
        notes['doc_version'] = 'devel' if major == DEVEL_MAJOR else major
        notes['sources'].append('本站手册 {} 的 {}'.format(notes['doc_version'], DOC_FILE))
    if notes['sources']:
        notes['fetched_at'] = report['stamps'].get(major, '')
    return notes


def build_versions(inventories, methods, atlas, report):
    rows = []
    for position, (major, label, status, support, doc_slug, live) in enumerate(VERSION_SPEC):
        inventory = inventories.get(major) or {}
        counts = {}
        for row in inventory.values():
            counts[row['type']] = counts.get(row['type'], 0) + 1
        previous = LIVE_ORDER[LIVE_ORDER.index(major) - 1] if live and LIVE_ORDER.index(major) else ''
        transition = {}
        if previous:
            transition = build_transition(inventories.get(previous) or {}, inventory, previous, major)
        rows.append({
            'major': major, 'label': label, 'status': status, 'support_status': support,
            'doc_slug': doc_slug, 'has_wait_events': live,
            'method': methods.get(major, '') if live else 'none',
            'event_count': len(inventory),
            'type_counts': dict(sorted(counts.items())),
            'transition': transition, 'position': position,
            'notes': version_notes(major, methods.get(major, ''), atlas, report) if live
            else {'doc_version': '', 'doc_tag': '', 'fetched_at': '', 'sources': []},
        })
    return rows


# ------------------------------------------------------------------ 导出

def export_snapshot(root=DEFAULT_ROOT, fetch=True, cache_dir=CACHE_DIR):
    """把图谱 + 本站手册 + 上游文档读成一份自包含快照。"""
    root = os.path.expanduser(root)
    atlas = read_atlas(root)
    report = {'collisions': [], 'doc_only': {}, 'absent': [], 'name_check': {}, 'stamps': {},
              'doc_used': [], 'upstream': {'fetched': [], 'skipped': [], 'failed': []}}

    inventories, methods = build_inventories(atlas, fetch, os.path.expanduser(cache_dir), report)
    check_generated_names(inventories, atlas, report)
    events = assemble(inventories, atlas, report)
    versions = build_versions(inventories, methods, atlas, report)

    return {
        'format': FORMAT,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'root': root,
        'source_rev': atlas['source_rev'],
        'default_major': '18',
        'harvest': report,
        'stats': {
            'version_count': len(versions),
            'event_count': len(events),
            'snapshots': sum(len(event['versions']) for event in events),
            'changes': sum(len(event['changes']) for event in events),
            'dossiers': sum(1 for event in events if event['has_dossier']),
        },
        'versions': versions,
        'events': events,
    }


# ------------------------------------------------------------------ 导入

VERSION_FIELDS = ('label', 'status', 'support_status', 'doc_slug', 'has_wait_events', 'method',
                  'event_count', 'type_counts', 'transition', 'position', 'notes')
EVENT_FIELDS = ('type', 'type_slug', 'name', 'slug', 'aliases', 'type_variants', 'summary',
                'summary_zh', 'first_version', 'last_version', 'present_in', 'changed_in',
                'versions', 'changes', 'dossier', 'has_dossier', 'position', 'source_rev')
SNAPSHOT_FIELDS = ('type', 'name', 'description', 'description_zh', 'zh_from', 'source', 'doc')


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
    for field in ('versions', 'events'):
        if not isinstance(snapshot.get(field), list) or not snapshot[field]:
            raise ValueError('快照缺少 {}'.format(field))
    majors = set()
    for version in snapshot['versions']:
        if not version.get('major'):
            raise ValueError('版本缺少 major')
        require(version, VERSION_FIELDS, '版本 {}'.format(version['major']))
        majors.add(version['major'])
    if len(majors) != len(snapshot['versions']):
        raise ValueError('版本 major 有重复')
    seen = set()
    for event in snapshot['events']:
        key = event.get('key', '')
        if not KEY_RE.match(key):
            raise ValueError('事件 key 格式不对：{!r}'.format(key))
        if key in seen:
            raise ValueError('事件重复：{}'.format(key))
        seen.add(key)
        require(event, EVENT_FIELDS, '事件 ' + key)
        if event['type'] not in WAITEVENT_TYPE_ORDER:
            raise ValueError('{} 的类型不认识：{!r}'.format(key, event['type']))
        if not event['versions']:
            raise ValueError('{} 没有任何版本快照'.format(key))
        unknown = set(event['versions']) - majors
        if unknown:
            raise ValueError('{} 引用了未知版本：{}'.format(key, sorted(unknown)))
        for major, item in event['versions'].items():
            require(item, SNAPSHOT_FIELDS, '{} 的 {} 快照'.format(key, major))
    for item in snapshot['events']:
        item_hash(WaitEvent, item, EVENT_FIELDS)
    return True


def changed_keys(snapshot):
    """这次导入会改动哪些事件。按稳定内容指纹比对，无变化的整条跳过。"""
    stored = {row.pk: row for row in WaitEvent.objects.only('key', 'content_hash')}
    added, updated, unchanged = [], [], []
    for event in snapshot['events']:
        calculated = item_hash(WaitEvent, event, EVENT_FIELDS)
        row = stored.get(event['key'])
        if row is None:
            added.append(event['key'])
        elif row.content_hash != calculated:
            updated.append(event['key'])
        else:
            unchanged.append(event['key'])
    incoming = {event['key'] for event in snapshot['events']}
    majors = {version['major'] for version in snapshot['versions']}
    missing = {
        'events': sorted(set(stored) - incoming),
        'versions': [row.major for row in WaitEventVersion.objects.all() if row.major not in majors],
    }
    return added, updated, unchanged, missing


def retention_note(missing):
    """没加 --prune 时说清楚库里留了什么，免得以为已经删掉了。"""
    parts = []
    if missing['events']:
        parts.append('{} 个事件'.format(len(missing['events'])))
    if missing['versions']:
        parts.append('版本 ' + '、'.join(missing['versions']))
    if not parts:
        return ''
    return '快照里没有但库里还在：{}。未加 --prune，这些记录保留。'.format('，'.join(parts))


def coverage(snapshot):
    """译文覆盖：每份版本快照的中文从哪来，外加有档案的事件数。"""
    counts = {'zh_atlas': 0, 'zh_doc': 0, 'zh_inherited': 0, 'zh_none': 0}
    field = {'atlas': 'zh_atlas', 'doc': 'zh_doc', 'inherited': 'zh_inherited'}
    for event in snapshot['events']:
        for item in event['versions'].values():
            counts[field.get(item.get('zh_from') or '', 'zh_none')] += 1
    counts['dossiers'] = sum(1 for event in snapshot['events'] if event['has_dossier'])
    return counts


def transition_counts(snapshot):
    out = {}
    for version in snapshot['versions']:
        transition = version.get('transition') or {}
        if not transition:
            continue
        out[version['major']] = {field: len(transition.get(field) or ())
                                 for field in ('added', 'removed', 'renamed', 'moved', 'reworded')}
    return out


def preview(snapshot):
    """不写库，只报告这次导入会改动什么。"""
    validate(snapshot)
    added, updated, unchanged, missing = changed_keys(snapshot)
    harvest = snapshot.get('harvest') or {}
    return {
        'versions': len(snapshot['versions']),
        'events': len(snapshot['events']),
        'created': len(added), 'updated': len(updated), 'unchanged': len(unchanged),
        'missing': missing, 'note': retention_note(missing),
        'snapshots': sum(len(event['versions']) for event in snapshot['events']),
        'collisions': harvest.get('collisions') or [],
        'coverage': coverage(snapshot),
        'transitions': transition_counts(snapshot),
        'harvest': {field: harvest.get(field)
                    for field in ('absent', 'doc_only', 'name_check', 'upstream')},
    }


@transaction.atomic
def import_snapshot(snapshot, prune=False):
    """按 key 原位更新。无变化的事件整条跳过，不重写 JSON 列。"""
    validate(snapshot)
    for version in snapshot['versions']:
        WaitEventVersion.objects.update_or_create(
            major=version['major'],
            defaults={field: version[field] for field in VERSION_FIELDS})

    added, updated, unchanged, missing = changed_keys(snapshot)
    write = set(added) | set(updated)
    for event in snapshot['events']:
        if event['key'] not in write:
            continue
        WaitEvent.objects.update_or_create(
            key=event['key'], defaults=hashed_defaults(WaitEvent, event, EVENT_FIELDS))

    harvest = snapshot.get('harvest') or {}
    report = {
        'versions': len(snapshot['versions']), 'events': len(snapshot['events']),
        'created': len(added), 'updated': len(updated), 'unchanged': len(unchanged),
        'missing': missing, 'pruned': bool(prune),
        'collisions': harvest.get('collisions') or [],
        'coverage': coverage(snapshot), 'transitions': transition_counts(snapshot),
        'harvest': {field: harvest.get(field)
                    for field in ('absent', 'doc_only', 'name_check', 'upstream')},
    }
    if prune:
        stale = WaitEvent.objects.filter(key__in=missing['events'])
        report['removed'] = {'events': stale.count(), 'versions': list(missing['versions'])}
        stale.delete()
        WaitEventVersion.objects.filter(major__in=missing['versions']).delete()
    else:
        report['removed'] = {'events': 0, 'versions': []}
        report['note'] = retention_note(missing)
    from . import waitevent
    transaction.on_commit(waitevent.forget)
    return report


def digest(snapshot):
    """一份快照的内容指纹，方便核对两端加载的是同一份。"""
    payload = json.dumps({'versions': snapshot['versions'], 'events': snapshot['events']},
                         ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
