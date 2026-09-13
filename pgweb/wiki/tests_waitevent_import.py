"""等待事件百科的导入侧测试。

用手工样本，不读 `~/pg.center` 与真实手册：三层来源（图谱、本站手册、上游）各造一小份，
覆盖解析、身份归一、译文借用、变化记录、版本汇总与幂等导入。
"""

import json
import os
import tempfile
from datetime import date

from django.test import SimpleTestCase, TestCase

from . import waitevent_importer as importer
from .models import WaitEvent, WaitEventVersion
from .waitevent_common import compare_snapshots, identity


# ------------------------------------------------------------------ 手册样本

def total_table(rows):
    """三列总表：类型列带 rowspan，和 9.6 – 12 的手册同形。"""
    out = ['<div class="table" id="WAIT-EVENT-TABLE"><table class="table"><thead><tr>',
           '<th>等待事件类型</th><th>等待事件名称</th><th>描述</th></tr></thead><tbody>']
    index = 0
    while index < len(rows):
        label = rows[index][0]
        span = 1
        while index + span < len(rows) and rows[index + span][0] == label:
            span += 1
        for offset in range(span):
            _, name, description = rows[index + offset]
            out.append('<tr>')
            if offset == 0:
                out.append('<td rowspan="{}"><code class="literal">{}</code></td>'.format(span, label))
            out.append('<td><code class="literal">{}</code></td><td>{}</td></tr>'.format(
                name, description))
        index += span
    out.append('</tbody></table></div>')
    return ''.join(out)


def typed_tables(rows):
    """13 起每类一张两列表，外加一张叫 WAIT-EVENT-TABLE 的「等待事件类型」两列表。"""
    labels = []
    for label, _, _ in rows:
        if label not in labels:
            labels.append(label)
    out = ['<div class="table" id="WAIT-EVENT-TABLE"><table class="table"><thead><tr>',
           '<th>等待事件类型</th><th>描述</th></tr></thead><tbody>']
    for label in labels:
        out.append('<tr><td><code class="literal">{}</code></td><td>{}类的等待。</td></tr>'.format(
            label, label))
    out.append('</tbody></table></div>')
    for label in labels:
        out.append('<div class="table" id="WAIT-EVENT-{}-TABLE"><table class="table"><thead><tr>'
                   '<th><code class="literal">{}</code> 等待事件</th><th>描述</th></tr></thead>'
                   '<tbody>'.format(label.upper(), label))
        for item, name, description in rows:
            if item != label:
                continue
            out.append('<tr><td><code class="literal">{}</code></td><td>{}</td></tr>'.format(
                name, description))
        out.append('</tbody></table></div>')
    return ''.join(out)


def old_style_table(rows):
    """9.6 的老版式：锚点是表前的 `<a>`，单元格用 `<tt>`。"""
    html = total_table(rows)
    html = html.replace('<div class="table" id="WAIT-EVENT-TABLE">',
                        '<div class="TABLE"><a id="WAIT-EVENT-TABLE" name="WAIT-EVENT-TABLE"></a>')
    return html.replace('code class="literal"', 'tt class="LITERAL"').replace('</code>', '</tt>')


# 每版的中文行：(原始类型标签, 原名, 中文描述)
DOC_10 = [
    ('LWLock', 'WALWriteLock', '等待 WAL 缓冲区写入磁盘。'),
    ('LWLock', 'FooCtlLock', '等待记录相互冲突的可串行化事务。'),
    ('LWLock', 'fooctl', '等待 fooctl 缓冲区上的 I/O。'),
    ('LWLock', 'buffer_content', '等待读取或写入内存中的数据页。'),
    ('BufferPin', 'BufferPin', '等待获取缓冲区上的独占 pin。'),
    ('Lock', 'relation', '等待获取关系上的锁。'),
    ('Activity', 'AutoVacuumMain', '在自动清理启动进程的主循环中等待。'),
    ('IPC', 'Blip', '等待一次闪断。'),
]
DOC_11 = [row for row in DOC_10 if row[1] != 'Blip']
DOC_12 = DOC_10

DOC_13 = [
    ('LWLock', 'WALWrite', '等待 WAL 缓冲区写入磁盘。'),
    ('LWLock', 'BufferContent', '等待访问内存中的数据页。'),
    ('BufferPin', 'BufferPin', '等待获取缓冲区上的独占 pin。'),
    ('Lock', 'relation', '等待获取关系上的锁。'),
    ('Activity', 'AutoVacuumMain', '在自动清理启动进程的主循环中等待。'),
    ('Client', 'WalReceiverWaitStart', '等待 startup 进程发送流复制的初始数据。'),
    ('IPC', 'Demo', '等待一件事。'),
]
DOC_18 = [
    ('Timeout', 'BaseBackupThrottle', '在基础备份中等待限流。'),
]
# 19 的中文手册是旧译文的拼盘：名字还是 16 时代的写法，还留着 17 就没有的条目。
DOC_19 = [
    ('Activity', 'AutoVacuumMain', '在自动清理启动进程的主循环中等待。'),
    ('Buffer', 'BufferCleanup', '等待获取缓冲区上的独占 pin。'),
    ('LWLock', 'OldSnapshotTimeMap', '等待读取或更新旧快照控制信息。'),
]
DOC_DEVEL = [
    ('Activity', 'AutovacuumMain', '在自动清理启动进程的主循环中等待。'),
    ('Buffer', 'BufferCleanup', '等待获取缓冲区上的独占 pin。'),
    ('IPC', 'ArchiveCommand', '等待 archive_command 完成。'),
]


# ------------------------------------------------------------------ 上游样本

EN_96 = [
    ('LWLockNamed', 'WALWriteLock', 'Waiting for WAL buffers to be written to disk.'),
    ('LWLockNamed', 'FooCtlLock', 'Waiting to record conflicting serializable transactions.'),
    ('LWLockTranche', 'fooctl', 'Waiting for I/O on an fooctl buffer.'),
    ('LWLockTranche', 'buffer_content', 'Waiting to read or write a data page in memory.'),
    ('BufferPin', 'BufferPin', 'Waiting to acquire an exclusive pin on a buffer.'),
    ('Lock', 'relation', 'Waiting to acquire a lock on a relation.'),
]
EN_10 = [
    ('LWLock', 'WALWriteLock', 'Waiting for WAL buffers to be written to disk.'),
    ('LWLock', 'FooCtlLock', 'Waiting to record conflicting serializable transactions.'),
    ('LWLock', 'fooctl', 'Waiting for I/O on an fooctl buffer.'),
    ('LWLock', 'buffer_content', 'Waiting to read or write a data page in memory.'),
    ('BufferPin', 'BufferPin', 'Waiting to acquire an exclusive pin on a buffer.'),
    ('Lock', 'relation', 'Waiting to acquire a lock on a relation.'),
    ('Activity', 'AutoVacuumMain', 'Waiting in main loop of autovacuum launcher process.'),
    ('IPC', 'Blip', 'Waiting for a blip.'),
]
EN_11 = [row for row in EN_10 if row[1] != 'Blip']
EN_12 = EN_10

NAMES_TXT = '''#
# wait_event_names.txt
#

Section: ClassName - WaitEventActivity

AUTOVACUUM_MAIN\t"Waiting in main loop of autovacuum launcher process"

ABI_compatibility:

#
# Wait Events - IPC
#

Section: ClassName - WaitEventIPC

ARCHIVE_COMMAND\t"Waiting for <xref linkend="guc-archive-command"/> to complete."
DEMO\t"Waiting for another thing."
WAL_RECEIVER_WAIT_START\t"Waiting for startup process to send initial data for streaming replication."

ABI_compatibility:

Section: ClassName - WaitEventBuffer

BUFFER_CLEANUP\t"Waiting to acquire an exclusive pin on a buffer."
BUFFER_EXCLUSIVE\t"Waiting to acquire a exclusive lock on a buffer."

ABI_compatibility:

Section: ClassName - WaitEventLWLock

WALWrite\t"Waiting for WAL buffers to be written to disk."
ControlFile\t"Waiting to read or update the <filename>pg_control</filename> file."

Section: ClassName - WaitEventLock

relation\t"Waiting to acquire a lock on a relation."
virtualxid\t"Waiting to acquire a virtual transaction ID lock; see <xref linkend="transaction-id"/>."
'''
# master 只改了一处措辞，用来验证 19 → 20 只报一条 reworded。
NAMES_TXT_MASTER = NAMES_TXT.replace('Waiting to acquire a exclusive lock on a buffer.',
                                     'Waiting to acquire an exclusive lock on a buffer.')


# ------------------------------------------------------------------ 图谱样本

def atlas_entry(type_label, name, majors, description, last_description=None):
    """一条矩阵身份：逐版本英文描述。`last_description` 只改最后一版（去句号、改措辞）。"""
    descriptions = {}
    for major in majors:
        text = description
        if last_description is not None and major == majors[-1]:
            text = last_description
        descriptions[str(major)] = text
    return {'type': type_label, 'name': name, 'versions': list(majors),
            'version_range': '{}-{}'.format(majors[0], majors[-1]),
            'descriptions': descriptions, 'sources': {}, 'canonical': ''}


ALL = [13, 14, 15, 16, 17, 18]

MATRIX = [
    atlas_entry('LWLock', 'WALWrite', ALL, 'Waiting for WAL buffers to be written to disk.'),
    atlas_entry('LWLock', 'BufferContent', ALL, 'Waiting to access a data page in memory.'),
    atlas_entry('BufferPin', 'BufferPin', ALL, 'Waiting to acquire an exclusive pin on a buffer.'),
    atlas_entry('Lock', 'relation', ALL, 'Waiting to acquire a lock on a relation.'),
    # 17 起改拼写，同时整批去掉句号：只算更名，不算措辞变化。
    atlas_entry('Activity', 'AutoVacuumMain', [13, 14, 15, 16],
                'Waiting in main loop of autovacuum launcher process.'),
    atlas_entry('Activity', 'AutovacuumMain', [17, 18],
                'Waiting in main loop of autovacuum launcher process'),
    # 13 在 Client 下，14 起迁到 IPC：靠图谱的规范映射认成同一个。
    atlas_entry('Client', 'WalReceiverWaitStart', [13],
                'Waiting for startup process to send initial data for streaming replication.'),
    atlas_entry('IPC', 'WalReceiverWaitStart', [14, 15, 16, 17, 18],
                'Waiting for startup process to send initial data for streaming replication.'),
    # 14 改了措辞。
    atlas_entry('IPC', 'Demo', [13], 'Waiting for a thing.'),
    atlas_entry('IPC', 'Demo', [14, 15, 16, 17, 18], 'Waiting for another thing.'),
    atlas_entry('Timeout', 'BaseBackupThrottle', ALL, 'Waiting during base backup throttling.'),
]

CANONICAL_MAP = {'Client/WalReceiverWaitStart': 'IPC/WalReceiverWaitStart',
                 'Activity/AutoVacuumMain': 'Activity/AutovacuumMain'}

DOSSIER = {
    'schema_version': 1, 'record_kind': 'event', 'id': 'lwlock-buffer-content',
    'type': 'LWLock', 'name': 'BufferContent', 'slug': 'buffer-content',
    'url': '/lwlock/buffer-content/', 'versions': ALL,
    'official_descriptions': {str(m): 'Waiting to access a data page in memory.' for m in ALL},
    'official_description_zh': '等待访问内存中的数据页。',
    'mechanism': {'en': 'Buffer content lock.', 'zh': '缓冲区内容锁。'},
    'normal': {'en': 'Brief.', 'zh': '短暂。'},
    'trouble': {'en': 'Hot page.', 'zh': '热页。'},
    'actions': {'en': ['Spread hot keys.'], 'zh': ['分散热点键。']},
    'incident_pattern': {'en': 'Rightmost leaf.', 'zh': '最右叶子页。'},
    'diagnostic_sql': [{'id': 'sessions', 'title': 'Sessions', 'title_zh': '会话',
                        'min_version': '13', 'sql': 'SELECT 1;'}],
    'gucs': ['shared_buffers'], 'metrics': ['waiting_sessions'],
    'source_locations': [{'major': 18, 'tag': 'REL_18_6', 'path': 'src/x.c', 'line': 1,
                          'kind': 'resource_path', 'status': 'dynamic_trigger',
                          'symbol': 'BufferContent', 'excerpt': '', 'url': 'https://example/'}],
    'source_status': 'dynamic_trigger', 'emission': {'status': 'active', 'verified_release': '18.6'},
    'availability': {},
    # 本地路径与抓取痕迹不该进快照。
    'grep_log': 'local only',
}

MANIFEST = {'schema_version': 1, 'union_rows': len(MATRIX),
            'versions': {str(major): {'method': 'official_documentation',
                                      'source_release': '{}.1'.format(major)} for major in ALL}}


def write_atlas(root):
    os.makedirs(os.path.join(root, 'data'), exist_ok=True)
    os.makedirs(os.path.join(root, 'facts'), exist_ok=True)
    with open(os.path.join(root, 'data', 'wait_events.jsonl'), 'w', encoding='utf-8') as handle:
        handle.write(json.dumps(DOSSIER, ensure_ascii=False) + '\n')
    with open(os.path.join(root, 'facts', 'wait_event_matrix.json'), 'w', encoding='utf-8') as handle:
        json.dump(MATRIX, handle, ensure_ascii=False)
    with open(os.path.join(root, 'facts', 'wait_event_canonical_map.json'), 'w',
              encoding='utf-8') as handle:
        json.dump(CANONICAL_MAP, handle, ensure_ascii=False)
    with open(os.path.join(root, 'facts', 'inventory_manifest.json'), 'w', encoding='utf-8') as handle:
        json.dump(MANIFEST, handle, ensure_ascii=False)


def write_cache(cache, names_txt=True):
    os.makedirs(cache, exist_ok=True)
    pages = {'9.6': old_style_table(EN_96), '10': total_table(EN_10),
             '11': total_table(EN_11), '12': total_table(EN_12)}
    for major, html in pages.items():
        with open(os.path.join(cache, 'monitoring-stats-{}.html'.format(major)), 'w',
                  encoding='utf-8') as handle:
            handle.write('<html><body>' + html + '</body></html>')
    if not names_txt:
        return
    for tag, text in (('REL_19_BETA3', NAMES_TXT), ('master', NAMES_TXT_MASTER)):
        with open(os.path.join(cache, 'wait_event_names-{}.txt'.format(tag)), 'w',
                  encoding='utf-8') as handle:
            handle.write(text)


def load_manuals():
    """本站手册：10 – 12 三列总表，13 与 18 分表，19 与 devel 分表。14 – 17 没有这一页。"""
    from pgweb.core.models import Version
    from pgweb.docs.models import DocPage
    pages = {10: total_table(DOC_10), 11: total_table(DOC_11), 12: total_table(DOC_12),
             13: typed_tables(DOC_13), 18: typed_tables(DOC_18),
             19: typed_tables(DOC_19), 0: typed_tables(DOC_DEVEL)}
    Version.objects.bulk_create([
        Version(tree=tree, current=tree == 18, reldate=date(2025, 9, 1),
                firstreldate=date(2025, 9, 1), eoldate=date(2030, 1, 1))
        for tree in sorted(pages)])
    for tree, body in pages.items():
        DocPage.objects.create(file='monitoring-stats.html', version_id=tree,
                               title='monitoring-stats.html', content=body)


def export(names_txt=True, fetch=False):
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as cache:
        write_atlas(root)
        write_cache(cache, names_txt=names_txt)
        return importer.export_snapshot(root, fetch=fetch, cache_dir=cache)


# ------------------------------------------------------------------ 解析

class WaitEventParseTests(SimpleTestCase):
    """三种表格式与源码里的事件清单。"""

    def soup(self, html):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, 'html.parser')

    def test_total_table_spreads_the_rowspan_type_over_its_rows(self):
        rows = importer.parse_event_tables(self.soup(total_table(EN_10)))
        self.assertEqual(len(rows), len(EN_10))
        self.assertEqual(rows[0], ('LWLock', 'WALWriteLock',
                                   'Waiting for WAL buffers to be written to disk.'))
        self.assertEqual([label for label, _, _ in rows][:4], ['LWLock'] * 4)
        self.assertEqual(rows[4][0], 'BufferPin')
        self.assertEqual(rows[-1][0], 'IPC')

    def test_the_old_9_6_markup_is_read_through_the_anchor_before_the_table(self):
        rows = importer.parse_event_tables(self.soup(old_style_table(EN_96)))
        self.assertEqual([label for label, _, _ in rows][:3],
                         ['LWLockNamed', 'LWLockNamed', 'LWLockTranche'])
        self.assertEqual(rows[3][1], 'buffer_content')

    def test_typed_tables_win_over_the_two_column_type_summary(self):
        """13 起也有一张叫 WAIT-EVENT-TABLE 的表，但那是类型说明，不是事件清单。"""
        rows = importer.parse_event_tables(self.soup(typed_tables(DOC_13)))
        self.assertEqual(len(rows), len(DOC_13))
        self.assertNotIn('类的等待。', [description for _, _, description in rows])
        self.assertIn(('Client', 'WalReceiverWaitStart', '等待 startup 进程发送流复制的初始数据。'),
                      rows)

    def test_the_19_buffer_table_is_read(self):
        rows = importer.parse_event_tables(self.soup(typed_tables(DOC_19)))
        self.assertIn(('Buffer', 'BufferCleanup', '等待获取缓冲区上的独占 pin。'), rows)

    def test_a_total_table_is_found_without_its_anchor(self):
        html = total_table(EN_10).replace(' id="WAIT-EVENT-TABLE"', '')
        rows = importer.parse_event_tables(self.soup(html))
        self.assertEqual(len(rows), len(EN_10))

    def test_names_txt_reads_sections_skips_comments_and_keeps_abi_rows(self):
        rows = importer.parse_names_txt(NAMES_TXT)
        self.assertEqual(len(rows), 10)
        self.assertIn(('Activity', 'AutovacuumMain',
                       'Waiting in main loop of autovacuum launcher process'), rows)
        # LWLock、Lock 两节的名字已是最终形式，不再转驼峰。
        self.assertIn('WALWrite', [name for _, name, _ in rows])
        self.assertIn('virtualxid', [name for _, name, _ in rows])
        self.assertNotIn('ABI_compatibility', [name for _, name, _ in rows])

    def test_enum_names_become_camel_case(self):
        for enum, expected in (('ARCHIVER_MAIN', 'ArchiverMain'), ('IO_WORKER_MAIN', 'IoWorkerMain'),
                               ('WAL_RECEIVER_WAIT_START', 'WalReceiverWaitStart'),
                               ('DEMO', 'Demo')):
            self.assertEqual(importer.camel_name(enum), expected)

    def test_docbook_markup_is_restored(self):
        rows = {name: description for _, name, description in importer.parse_names_txt(NAMES_TXT)}
        self.assertEqual(rows['ArchiveCommand'], 'Waiting for archive_command to complete.')
        self.assertEqual(rows['ControlFile'],
                         'Waiting to read or update the pg_control file.')
        # 交叉引用不是参数时整条去掉，连带 “; see” 的残句。
        self.assertEqual(rows['virtualxid'], 'Waiting to acquire a virtual transaction ID lock.')
        self.assertEqual(importer.docbook_text('A <quote>b</quote> c.'), 'A “b” c.')

    def test_slug_is_generated_from_the_name(self):
        for name, expected in (('BufferContent', 'buffer-content'), ('WALWriteLock', 'wal-write-lock'),
                               ('fooctl', 'fooctl'), ('GSSOpenServer', 'gss-open-server')):
            self.assertEqual(importer.slug_of(name), expected)


class WaitEventIdentityTests(SimpleTestCase):
    """身份归一与快照比较，规则来自 waitevent_common。"""

    def test_lwlock_names_line_up_across_versions(self):
        self.assertEqual(identity('LWLockNamed', 'WALWriteLock'), 'lwlock/walwrite')
        self.assertEqual(identity('LWLock', 'WALWrite'), 'lwlock/walwrite')
        self.assertEqual(identity('LWLockTranche', 'buffer_content'), 'lwlock/buffercontent')
        self.assertEqual(identity('LWLock', 'BufferContent'), 'lwlock/buffercontent')

    def test_bufferpin_folds_into_buffer(self):
        self.assertEqual(identity('BufferPin', 'BufferPin'), 'buffer/bufferpin')
        self.assertEqual(identity('Buffer', 'BufferCleanup'), 'buffer/buffercleanup')

    def test_the_canonical_map_moves_a_type(self):
        self.assertEqual(identity('Client', 'WalReceiverWaitStart', CANONICAL_MAP),
                         'ipc/walreceiverwaitstart')

    def test_the_map_is_followed_through_several_hops(self):
        chained = {'LWLock/buffer_io': 'LWLock/BufferIO', 'LWLock/BufferIO': 'IPC/BufferIO'}
        self.assertEqual(identity('LWLockTranche', 'buffer_io', chained), 'ipc/bufferio')
        self.assertEqual(identity('LWLock', 'BufferIO', chained), 'ipc/bufferio')
        self.assertEqual(identity('IPC', 'BufferIO', chained), 'ipc/bufferio')

    def test_curated_renames_join_the_12_and_13_spellings(self):
        curated = importer.CURATED_RENAMES
        self.assertEqual(identity('LWLockNamed', 'CLogControlLock', curated), identity('LWLock', 'XactSLRU'))
        self.assertEqual(identity('LWLockTranche', 'clog', curated), identity('LWLock', 'XactBuffer'))
        self.assertEqual(identity('IPC', 'Hash/Batch/Allocating', curated),
                         identity('IPC', 'HashBatchAllocate'))
        self.assertEqual(identity('Lock', 'speculative token', curated), identity('Lock', 'spectoken'))
        # 没有列入的名字不受影响。
        self.assertEqual(identity('Activity', 'RecoveryWalAll', curated), 'activity/recoverywalall')

    def test_dropping_a_trailing_period_is_not_a_wording_change(self):
        left = {'type': 'Activity', 'name': 'AutoVacuumMain', 'description': 'Waiting in a loop.'}
        right = {'type': 'Activity', 'name': 'AutovacuumMain', 'description': 'Waiting in a loop'}
        change = compare_snapshots(left, right, '16', '17')
        self.assertEqual(change['status'], 'changed')
        self.assertEqual(change['renamed'], {'from': 'AutoVacuumMain', 'to': 'AutovacuumMain'})
        self.assertIsNone(change['reworded'])


# ------------------------------------------------------------------ 导出

class WaitEventExportTests(TestCase):
    """三层合并：清单、译文、变化记录与版本汇总。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()

    def setUp(self):
        self.snapshot = export()
        self.events = {event['key']: event for event in self.snapshot['events']}
        self.versions = {version['major']: version for version in self.snapshot['versions']}

    def test_eighteen_version_rows_in_order(self):
        self.assertEqual([v['major'] for v in self.snapshot['versions']], importer.VERSION_ORDER)
        self.assertEqual([v['position'] for v in self.snapshot['versions']], list(range(18)))
        self.assertEqual(self.versions['18']['status'], 'stable')
        self.assertEqual(self.versions['19']['label'], '19 beta 3')
        self.assertEqual(self.versions['20']['doc_slug'], 'devel')

    def test_9_x_rows_say_there_is_no_wait_event_machinery(self):
        for major in ('9.0', '9.1', '9.2', '9.3', '9.4', '9.5'):
            row = self.versions[major]
            self.assertFalse(row['has_wait_events'])
            self.assertEqual(row['method'], 'none')
            self.assertEqual(row['event_count'], 0)
            self.assertEqual(row['transition'], {})
        self.assertTrue(self.versions['9.6']['has_wait_events'])
        # 9.6 是机制起点，没有上一版可比。
        self.assertEqual(self.versions['9.6']['transition'], {})

    def test_each_version_records_its_method_and_raw_type_counts(self):
        self.assertEqual(self.versions['9.6']['method'], 'upstream')
        self.assertEqual(self.versions['10']['method'], 'manual+upstream')
        self.assertEqual(self.versions['13']['method'], 'atlas')
        self.assertEqual(self.versions['19']['method'], 'manual+upstream')
        self.assertEqual(self.versions['9.6']['type_counts'],
                         {'BufferPin': 1, 'LWLockNamed': 2, 'LWLockTranche': 2, 'Lock': 1})
        self.assertEqual(self.versions['13']['type_counts']['BufferPin'], 1)
        self.assertEqual(self.versions['19']['type_counts']['Buffer'], 2)

    def test_one_event_gathers_every_version_under_one_key(self):
        event = self.events['lwlock/walwrite']
        self.assertEqual(event['present_in'],
                         ['9.6', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20'])
        self.assertEqual(event['name'], 'WALWrite')
        self.assertEqual(event['aliases'], ['WALWriteLock'])
        self.assertEqual(event['type_variants'], ['LWLockNamed'])
        self.assertEqual(event['versions']['9.6']['type'], 'LWLockNamed')
        self.assertEqual(event['versions']['9.6']['name'], 'WALWriteLock')
        self.assertEqual(event['versions']['13']['name'], 'WALWrite')

    def test_bufferpin_keeps_its_original_label_under_the_buffer_type(self):
        event = self.events['buffer/bufferpin']
        self.assertEqual((event['type'], event['type_slug']), ('Buffer', 'buffer'))
        self.assertEqual(event['type_variants'], ['BufferPin'])
        self.assertEqual(event['versions']['18']['type'], 'BufferPin')
        self.assertEqual(event['last_version'], '18')

    def test_the_canonical_map_keeps_a_moved_event_whole(self):
        event = self.events['ipc/walreceiverwaitstart']
        self.assertEqual(event['type'], 'IPC')
        self.assertEqual(event['type_variants'], ['Client'])
        self.assertEqual(event['versions']['13']['type'], 'Client')
        moved = next(c for c in event['changes'] if c['moved'])
        self.assertEqual((moved['to'], moved['moved']), ('14', {'from': 'Client', 'to': 'IPC'}))

    def test_doc_coordinates_point_at_the_right_table(self):
        event = self.events['lwlock/buffercontent']
        self.assertEqual(event['versions']['10']['doc'],
                         {'file': 'monitoring-stats.html', 'anchor': 'WAIT-EVENT-TABLE',
                          'slug': '10'})
        self.assertEqual(event['versions']['13']['doc']['anchor'], 'WAIT-EVENT-LWLOCK-TABLE')
        self.assertEqual(self.events['buffer/bufferpin']['versions']['13']['doc']['anchor'],
                         'WAIT-EVENT-BUFFERPIN-TABLE')
        self.assertEqual(self.events['buffer/buffercleanup']['versions']['20']['doc'],
                         {'file': 'monitoring-stats.html', 'anchor': 'WAIT-EVENT-BUFFER-TABLE',
                          'slug': 'devel'})

    def test_the_manual_translation_lands_on_the_version_it_belongs_to(self):
        event = self.events['lwlock/buffercontent']
        self.assertEqual(event['versions']['10']['zh_from'], 'doc')
        self.assertEqual(event['versions']['10']['description_zh'], '等待读取或写入内存中的数据页。')
        # 13 – 18 的清单出自图谱，译文仍要从本站手册采。
        self.assertEqual(event['versions']['13']['zh_from'], 'doc')
        self.assertEqual(event['versions']['13']['description_zh'], '等待访问内存中的数据页。')

    def test_the_atlas_translation_fills_versions_without_a_manual(self):
        """14 – 17 本地没有那一页手册，图谱的官方中文顶上，英文一致才填。"""
        event = self.events['lwlock/buffercontent']
        for major in ('14', '15', '16', '17'):
            self.assertEqual(event['versions'][major]['zh_from'], 'atlas')
            self.assertEqual(event['versions'][major]['description_zh'], '等待访问内存中的数据页。')

    def test_a_translation_is_borrowed_only_when_the_english_is_identical(self):
        borrowed = self.events['timeout/basebackupthrottle']
        # 只有 18 的手册有它，英文各版相同，其余版本借用。
        self.assertEqual(borrowed['versions']['18']['zh_from'], 'doc')
        self.assertEqual(borrowed['versions']['13']['zh_from'], 'inherited')
        self.assertEqual(borrowed['versions']['13']['description_zh'], '在基础备份中等待限流。')
        demo = self.events['ipc/demo']
        # 13 有译文，14 起英文改了，不借。
        self.assertEqual(demo['versions']['13']['zh_from'], 'doc')
        self.assertEqual(demo['versions']['14']['description_zh'], '')
        self.assertEqual(demo['versions']['14']['zh_from'], '')

    def test_summary_prefers_the_atlas_chinese_and_the_latest_english(self):
        event = self.events['lwlock/buffercontent']
        self.assertEqual(event['summary_zh'], '等待访问内存中的数据页。')
        self.assertEqual(event['summary'], 'Waiting to access a data page in memory.')
        # 没有档案的事件退到最新一版的手册译文。
        self.assertEqual(self.events['ipc/demo']['summary_zh'], '等待一件事。')

    def test_the_9_6_baseline_events_carry_an_added_record(self):
        event = self.events['lock/relation']
        first = event['changes'][0]
        self.assertEqual((first['from'], first['to'], first['status']), ('', '9.6', 'added'))

    def test_a_rename_a_type_change_and_a_wording_change_are_told_apart(self):
        content = self.events['lwlock/buffercontent']
        moved = next(c for c in content['changes'] if c['to'] == '10')
        self.assertEqual(moved['moved'], {'from': 'LWLockTranche', 'to': 'LWLock'})
        renamed = next(c for c in content['changes'] if c['to'] == '13')
        self.assertEqual(renamed['renamed'], {'from': 'buffer_content', 'to': 'BufferContent'})
        self.assertIsNotNone(renamed['reworded'])
        self.assertEqual(content['changed_in'], ['10', '13'])
        demo = self.events['ipc/demo']
        reworded = next(c for c in demo['changes'] if c['to'] == '14')
        self.assertIsNone(reworded['renamed'])
        self.assertEqual(reworded['reworded']['to'], 'Waiting for another thing.')

    def test_dropping_the_final_period_in_17_is_not_a_change(self):
        event = self.events['activity/autovacuummain']
        self.assertEqual(event['changed_in'], ['17'])
        change = next(c for c in event['changes'] if c['to'] == '17')
        self.assertEqual(change['renamed'], {'from': 'AutoVacuumMain', 'to': 'AutovacuumMain'})
        self.assertIsNone(change['reworded'])

    def test_removal_is_recorded_once_and_a_comeback_is_an_add(self):
        gone = self.events['buffer/bufferpin']
        removed = [c for c in gone['changes'] if c['status'] == 'removed']
        self.assertEqual([c['to'] for c in removed], ['19'])
        blip = self.events['ipc/blip']
        self.assertEqual(blip['present_in'], ['10', '12'])
        self.assertEqual([(c['to'], c['status']) for c in blip['changes']],
                         [('10', 'added'), ('11', 'removed'), ('12', 'added'), ('13', 'removed')])

    def test_same_version_collisions_keep_both_events(self):
        collisions = self.snapshot['harvest']['collisions']
        self.assertEqual({item['key'] for item in collisions}, {'lwlock/fooctl'})
        self.assertEqual(collisions[0]['events'],
                         ['LWLockNamed/FooCtlLock', 'LWLockTranche/fooctl'])
        self.assertEqual(self.events['lwlock/fooctl']['name'], 'FooCtlLock')
        self.assertEqual(self.events['lwlock/fooctl~2']['name'], 'fooctl')
        # slug 在类型内唯一，否则页面按 slug 找会两条都命中。
        slugs = [(e['type_slug'], e['slug']) for e in self.snapshot['events']]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_version_transition_buckets_the_same_changes(self):
        transition = self.versions['13']['transition']
        self.assertEqual(transition['from'], '12')
        self.assertIn('ipc/blip', transition['removed'])
        self.assertIn('lwlock/fooctl~2', transition['removed'])
        self.assertIn({'key': 'lwlock/walwrite', 'from': 'WALWriteLock', 'to': 'WALWrite'},
                      transition['renamed'])
        self.assertIn('timeout/basebackupthrottle', transition['added'])
        self.assertEqual(transition['added_types'], ['Client', 'Timeout'])
        self.assertEqual(self.versions['10']['transition']['removed_types'],
                         ['LWLockNamed', 'LWLockTranche'])
        self.assertEqual(self.versions['13']['transition']['event_count_delta'],
                         self.versions['13']['event_count'] - self.versions['12']['event_count'])

    def test_19_takes_its_english_upstream_and_its_chinese_from_the_manual(self):
        event = self.events['activity/autovacuummain']
        snapshot = event['versions']['19']
        self.assertEqual(snapshot['source'], 'upstream')
        self.assertEqual(snapshot['name'], 'AutovacuumMain')
        self.assertEqual(snapshot['description'],
                         'Waiting in main loop of autovacuum launcher process')
        # 手册 19 里还写着 16 时代的拼写，归一后照样对上。
        self.assertEqual(snapshot['zh_from'], 'doc')
        self.assertEqual(snapshot['description_zh'], '在自动清理启动进程的主循环中等待。')

    def test_generated_names_are_checked_against_the_atlas(self):
        check = self.snapshot['harvest']['name_check']
        self.assertGreater(check['compared'], 0)
        self.assertEqual(check['mismatched'], [])

    def test_only_one_wording_change_between_19_and_the_development_version(self):
        transition = self.versions['20']['transition']
        self.assertEqual(transition['added'], [])
        self.assertEqual(transition['removed'], [])
        self.assertEqual(transition['reworded'], ['buffer/bufferexclusive'])

    def test_the_dossier_comes_over_whole_without_the_local_noise(self):
        event = self.events['lwlock/buffercontent']
        self.assertTrue(event['has_dossier'])
        self.assertEqual(event['slug'], 'buffer-content')
        self.assertEqual(event['dossier']['gucs'], ['shared_buffers'])
        self.assertEqual(event['dossier']['diagnostic_sql'][0]['title_zh'], '会话')
        self.assertEqual(event['dossier']['source_status'], 'dynamic_trigger')
        self.assertNotIn('grep_log', event['dossier'])
        self.assertNotIn('url', event['dossier'])
        self.assertFalse(self.events['ipc/demo']['has_dossier'])
        self.assertEqual(self.events['ipc/demo']['dossier'], {})

    def test_events_are_ordered_by_type_then_name(self):
        order = [event['key'] for event in self.snapshot['events']]
        self.assertEqual(order[0], 'activity/autovacuummain')
        positions = [event['position'] for event in self.snapshot['events']]
        self.assertEqual(positions, sorted(positions))

    def test_notes_name_every_source_behind_a_version(self):
        notes = self.versions['13']['notes']
        self.assertEqual(notes['doc_tag'], '13.1')
        self.assertEqual(notes['doc_version'], '13')
        # 13 – 18 的清单出自图谱，译文仍采自本站手册，两条来源都要写上。
        self.assertEqual(notes['sources'], ['wait.pg.center 图谱：official_documentation',
                                            '本站手册 13 的 monitoring-stats.html'])
        self.assertEqual(self.versions['20']['notes']['doc_tag'], 'master')
        self.assertEqual(self.versions['20']['notes']['doc_version'], 'devel')
        self.assertEqual(self.versions['9.0']['notes']['sources'], [])

    def test_repeated_exports_of_the_same_sources_agree(self):
        """来源没变就该导出同一份快照：fetched_at 取的是来源文件的时间，不是导出时刻。"""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as cache:
            write_atlas(root)
            write_cache(cache)
            first = importer.export_snapshot(root, fetch=False, cache_dir=cache)
            second = importer.export_snapshot(root, fetch=False, cache_dir=cache)
        self.assertEqual(importer.digest(first), importer.digest(second))

    def test_manual_rows_the_inventory_does_not_have_are_only_reported(self):
        """本站 19 的手册是旧译文拼盘，对不上的行不硬塞进清单。"""
        self.assertEqual(self.snapshot['harvest']['doc_only']['19'],
                         ['lwlock/oldsnapshottimemap'])
        self.assertNotIn('lwlock/oldsnapshottimemap', self.events)

    def test_without_the_upstream_files_19_and_20_fall_back_to_the_manual(self):
        snapshot = export(names_txt=False)
        versions = {version['major']: version for version in snapshot['versions']}
        self.assertEqual(versions['19']['method'], 'manual')
        self.assertEqual(versions['19']['event_count'], len(DOC_19))
        events = {event['key']: event for event in snapshot['events']}
        self.assertEqual(events['lwlock/oldsnapshottimemap']['present_in'], ['19'])
        self.assertEqual(events['activity/autovacuummain']['versions']['19']['description'], '')


# ------------------------------------------------------------------ 导入

class WaitEventImportTests(TestCase):
    """写库：校验、幂等、--prune。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()

    def setUp(self):
        self.snapshot = export()

    def test_import_writes_versions_and_events(self):
        report = importer.import_snapshot(self.snapshot)
        self.assertEqual(WaitEventVersion.objects.count(), 18)
        self.assertEqual(WaitEvent.objects.count(), len(self.snapshot['events']))
        self.assertEqual(report['created'], len(self.snapshot['events']))
        self.assertEqual(report['updated'], 0)
        row = WaitEvent.objects.get(key='lwlock/buffercontent')
        self.assertEqual((row.type, row.type_slug, row.name), ('LWLock', 'lwlock', 'BufferContent'))
        self.assertEqual(row.url, '/docs/waitevent/lwlock/BufferContent/')
        self.assertEqual(row.aliases, ['buffer_content'])
        self.assertTrue(row.has_dossier)
        version = WaitEventVersion.objects.get(major='9.0')
        self.assertFalse(version.has_wait_events)
        self.assertEqual(version.position, 0)

    def test_a_second_import_of_the_same_snapshot_changes_nothing(self):
        importer.import_snapshot(self.snapshot)
        report = importer.import_snapshot(self.snapshot)
        self.assertEqual(report['created'], 0)
        self.assertEqual(report['updated'], 0)
        self.assertEqual(report['unchanged'], len(self.snapshot['events']))

    def test_only_the_changed_event_is_rewritten(self):
        importer.import_snapshot(self.snapshot)
        target = next(e for e in self.snapshot['events'] if e['key'] == 'ipc/demo')
        target['summary_zh'] = '改过的一句话'
        report = importer.import_snapshot(self.snapshot)
        self.assertEqual(report['updated'], 1)
        self.assertEqual(report['unchanged'], len(self.snapshot['events']) - 1)
        self.assertEqual(WaitEvent.objects.get(key='ipc/demo').summary_zh, '改过的一句话')

    def test_missing_events_are_kept_until_prune(self):
        importer.import_snapshot(self.snapshot)
        dropped = self.snapshot['events'].pop()
        report = importer.import_snapshot(self.snapshot)
        self.assertEqual(report['missing']['events'], [dropped['key']])
        self.assertTrue(WaitEvent.objects.filter(key=dropped['key']).exists())
        self.assertIn('未加 --prune', report['note'])
        report = importer.import_snapshot(self.snapshot, prune=True)
        self.assertEqual(report['removed']['events'], 1)
        self.assertFalse(WaitEvent.objects.filter(key=dropped['key']).exists())

    def test_preview_reports_without_writing(self):
        report = importer.preview(self.snapshot)
        self.assertEqual(report['created'], len(self.snapshot['events']))
        self.assertEqual(report['versions'], 18)
        self.assertEqual(WaitEvent.objects.count(), 0)
        self.assertEqual(report['coverage']['dossiers'], 1)
        self.assertEqual(report['transitions']['20'],
                         {'added': 0, 'removed': 0, 'renamed': 0, 'moved': 0, 'reworded': 1})

    def test_coverage_counts_every_snapshot_translation(self):
        counts = importer.coverage(self.snapshot)
        total = sum(len(event['versions']) for event in self.snapshot['events'])
        tallied = sum(counts[field]
                      for field in ('zh_atlas', 'zh_doc', 'zh_inherited', 'zh_none'))
        self.assertEqual(tallied, total)
        self.assertGreater(counts['zh_doc'], 0)
        self.assertGreater(counts['zh_atlas'], 0)
        self.assertGreater(counts['zh_inherited'], 0)

    def test_digest_only_follows_the_content(self):
        first = importer.digest(self.snapshot)
        self.snapshot['generated_at'] = 'later'
        self.assertEqual(importer.digest(self.snapshot), first)
        self.snapshot['events'][0]['summary'] = 'changed'
        self.assertNotEqual(importer.digest(self.snapshot), first)

    def test_validate_rejects_a_broken_snapshot(self):
        cases = [
            ('快照不是一个对象', []),
            ('快照格式', dict(self.snapshot, format=99)),
            ('快照缺少 events', dict(self.snapshot, events=[])),
        ]
        for message, payload in cases:
            with self.assertRaises(ValueError) as caught:
                importer.validate(payload)
            self.assertIn(message, str(caught.exception))

    def test_validate_checks_keys_types_and_version_references(self):
        broken = json.loads(json.dumps(self.snapshot))
        broken['events'][0]['key'] = 'LWLock/BufferContent'
        with self.assertRaisesMessage(ValueError, '事件 key 格式不对'):
            importer.validate(broken)

        broken = json.loads(json.dumps(self.snapshot))
        broken['events'][0]['type'] = 'BufferPin'
        with self.assertRaisesMessage(ValueError, '类型不认识'):
            importer.validate(broken)

        broken = json.loads(json.dumps(self.snapshot))
        broken['events'][0]['versions'] = {'7.4': broken['events'][0]['versions'].popitem()[1]}
        with self.assertRaisesMessage(ValueError, '引用了未知版本'):
            importer.validate(broken)

        broken = json.loads(json.dumps(self.snapshot))
        del broken['events'][0]['summary_zh']
        with self.assertRaisesMessage(ValueError, '缺少字段'):
            importer.validate(broken)

        broken = json.loads(json.dumps(self.snapshot))
        broken['events'].append(json.loads(json.dumps(broken['events'][0])))
        with self.assertRaisesMessage(ValueError, '事件重复'):
            importer.validate(broken)
