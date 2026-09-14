"""等待事件栏目的页面侧：索引、详情、变更页的上下文形状，以及查找与 sitemap。

样本用 ORM 直接造：导入器有自己的一份测试，这里只关心 `waitevent.py` 给出的形状。
版本谱是 9.5（尚无机制）、9.6、12、13、17、18（当前稳定版）、19 beta 3、20 devel。
"""

import os
import unittest

from django.core.cache import cache
from django.test import TestCase

from . import struct, waitevent
from .models import GucParameter, WaitEvent, WaitEventVersion


TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                         'templates', 'wiki')
HAS_TEMPLATES = os.path.exists(os.path.join(TEMPLATES, 'waitevent_index.html'))

# major, label, status, support_status, doc_slug, has_wait_events, method
VERSIONS = [
    ('9.5', '9.5', 'historical', 'end-of-life', '9.5', False, 'none'),
    ('9.6', '9.6', 'historical', 'end-of-life', '9.6', True, 'upstream'),
    ('12', '12', 'historical', 'end-of-life', '12', True, 'manual+upstream'),
    ('13', '13', 'historical', 'end-of-life', '13', True, 'atlas'),
    ('17', '17', 'historical', 'supported', '17', True, 'atlas'),
    ('18', '18', 'stable', 'supported', '18', True, 'atlas'),
    ('19', '19 beta 3', 'preview', 'preview', '19', True, 'manual+upstream'),
    ('20', '20 devel', 'devel', 'devel', 'devel', True, 'manual'),
]
LIVE = [major for major, _, _, _, _, live, _ in VERSIONS if live]

MEMORY = 'Waiting to access a data page in memory.'
SHARED = 'Waiting to access a data page in shared memory.'

DOSSIER = {
    'record_kind': 'trigger', 'source_status': 'live_trigger',
    'mechanism': {'en': 'A backend pins the buffer header.', 'zh': '后端在缓冲区头部加锁。'},
    'normal': {'en': 'Short waits are normal.', 'zh': '短暂等待是正常的。'},
    'trouble': {'en': 'Long waits mean contention.', 'zh': '长时间等待说明有争用。'},
    'incident_pattern': {'en': 'Hot page contention.', 'zh': '热点页争用。'},
    'actions': {'en': ['Spread the hot page.'], 'zh': ['分散热点页。', '加大 shared_buffers。']},
    'diagnostic_sql': [
        {'id': 'waiters', 'title': 'Current waiters', 'title_zh': '当前等待者',
         'min_version': '13', 'sql': 'SELECT * FROM pg_stat_activity;'},
        {'id': 'pages', 'title': 'Hot pages', 'title_zh': '热点页', 'min_version': '13',
         'sql': 'SELECT 1;'},
    ],
    'gucs': ['work_mem', 'shared_buffers', 'no_such_setting'],
    'metrics': ['pg_stat_activity_count', {'name': 'pg_locks_count'}],
    'source_locations': [
        {'major': '18', 'version': '18.0', 'tag': 'REL_18_0', 'commit': 'abcdef1234567890',
         'path': 'src/backend/storage/buffer/bufmgr.c', 'line': 5140, 'kind': 'trigger',
         'status': 'live_trigger', 'symbol': 'LockBufHdr',
         'excerpt': 'LWLockAcquire(BufferDescriptorGetContentLock(buf), mode);',
         'url': 'https://github.com/postgres/postgres/blob/REL_18_0/src/backend/storage/buffer/bufmgr.c#L5140'},
        {'major': '18', 'version': '18.0', 'tag': 'REL_18_0', 'commit': 'abcdef1234567890',
         'path': 'src/backend/utils/activity/wait_event_names.txt', 'line': 42,
         'kind': 'catalog_definition', 'status': 'catalog_only', 'symbol': 'BUFFER_CONTENT',
         'excerpt': 'BUFFER_CONTENT\t"Waiting to access a data page in shared memory."',
         'url': 'https://github.com/postgres/postgres/blob/REL_18_0/names.txt#L42'},
        {'major': '17', 'version': '17.0', 'tag': 'REL_17_0', 'commit': '1234567890abcdef',
         'path': 'src/backend/storage/buffer/bufmgr.c', 'line': 4900, 'kind': 'trigger',
         'status': 'live_trigger', 'symbol': 'LockBufHdr', 'excerpt': '',
         'url': 'https://github.com/postgres/postgres/blob/REL_17_0/bufmgr.c#L4900'},
    ],
    'emission': {'status': 'active', 'verified_release': '18.0'},
    'availability': {'zh': '13 起每个版本都实测到。', 'observed_releases': ['17.0', '18.0'],
                     'not_observed': []},
    'official_descriptions': {'18': SHARED},
}


def doc(major, type_label):
    """本站手册坐标：13 起每类一张表，之前是一张总表。"""
    slug = 'devel' if major == '20' else major
    anchor = 'WAIT-EVENT-TABLE' if major in ('9.6', '12') else \
        'WAIT-EVENT-{}-TABLE'.format(type_label.upper())
    return {'file': 'monitoring-stats.html', 'anchor': anchor, 'slug': slug}


def snapshot(major, type_label, name, description, description_zh, source='atlas'):
    return {'type': type_label, 'name': name, 'description': description,
            'description_zh': description_zh, 'zh_from': 'atlas' if description_zh else '',
            'source': source, 'doc': doc(major, type_label)}


def changed(from_major, to_major, renamed=None, moved=None, reworded=None):
    return {'from': from_major, 'to': to_major, 'status': 'changed',
            'renamed': renamed, 'moved': moved, 'reworded': reworded}


def plain(status, from_major, to_major):
    return {'from': from_major, 'to': to_major, 'status': status,
            'renamed': None, 'moved': None, 'reworded': None}


def build():
    WaitEventVersion.objects.bulk_create([
        WaitEventVersion(major=major, label=label, status=status, support_status=support,
                         doc_slug=slug, has_wait_events=live, method=method, position=index,
                         event_count=0)
        for index, (major, label, status, support, slug, live, method) in enumerate(VERSIONS)])

    # LWLock/BufferContent：9.6 属 LWLockTranche，12 归并到 LWLock，13 改驼峰名，18 改措辞。
    content = {'9.6': snapshot('9.6', 'LWLockTranche', 'buffer_content', MEMORY, '等待访问内存中的数据页。'),
               '12': snapshot('12', 'LWLock', 'buffer_content', MEMORY, '等待访问内存中的数据页。'),
               '13': snapshot('13', 'LWLock', 'BufferContent', MEMORY, '等待访问内存中的数据页。'),
               '17': snapshot('17', 'LWLock', 'BufferContent', MEMORY, '等待访问内存中的数据页。'),
               '18': snapshot('18', 'LWLock', 'BufferContent', SHARED, '等待访问共享内存中的数据页。'),
               '19': snapshot('19', 'LWLock', 'BufferContent', SHARED, '等待访问共享内存中的数据页。'),
               '20': snapshot('20', 'LWLock', 'BufferContent', SHARED, '等待访问共享内存中的数据页。')}
    WaitEvent.objects.create(
        key='lwlock/buffercontent', type='LWLock', type_slug='lwlock', name='BufferContent',
        slug='buffer-content', aliases=['buffer_content'], type_variants=['LWLockTranche'],
        summary=SHARED, summary_zh='等待访问共享内存中的数据页。',
        first_version='9.6', last_version='20', present_in=LIVE,
        changed_in=['12', '13', '18'], versions=content,
        changes=[changed('9.6', '12', moved={'from': 'LWLockTranche', 'to': 'LWLock'}),
                 changed('12', '13', renamed={'from': 'buffer_content', 'to': 'BufferContent'}),
                 changed('17', '18', reworded={'from': MEMORY, 'to': SHARED})],
        dossier=DOSSIER, has_dossier=True, position=7000)

    # Activity/AutovacuumMain：17 改了大小写，没有图谱档案。
    main = {major: snapshot(major, 'Activity',
                            'AutoVacuumMain' if major in ('9.6', '12', '13') else 'AutovacuumMain',
                            'Waiting in main loop of autovacuum launcher process.',
                            '自动清理启动进程在主循环里等待。')
            for major in LIVE}
    WaitEvent.objects.create(
        key='activity/autovacuummain', type='Activity', type_slug='activity',
        name='AutovacuumMain', slug='autovacuum-main', aliases=['AutoVacuumMain'],
        type_variants=[], summary='Waiting in main loop of autovacuum launcher process.',
        summary_zh='自动清理启动进程在主循环里等待。',
        first_version='9.6', last_version='20', present_in=LIVE, changed_in=['17'],
        versions=main,
        changes=[changed('13', '17', renamed={'from': 'AutoVacuumMain', 'to': 'AutovacuumMain'})],
        dossier={}, has_dossier=False, position=0)

    # Buffer/BufferPin：19 之前类型叫 BufferPin。
    pin = {major: snapshot(major, 'BufferPin' if major in ('9.6', '12', '13', '17', '18') else 'Buffer',
                           'BufferPin', 'Waiting to acquire an exclusive pin on a buffer.',
                           '等待取得缓冲区的独占 pin。')
           for major in LIVE}
    WaitEvent.objects.create(
        key='buffer/bufferpin', type='Buffer', type_slug='buffer', name='BufferPin',
        slug='buffer-pin', aliases=[], type_variants=['BufferPin'],
        summary='Waiting to acquire an exclusive pin on a buffer.',
        summary_zh='等待取得缓冲区的独占 pin。',
        first_version='9.6', last_version='20', present_in=LIVE, changed_in=['19'],
        versions=pin,
        changes=[changed('18', '19', moved={'from': 'BufferPin', 'to': 'Buffer'})],
        dossier={}, has_dossier=False, position=1000)

    # IO/DataFileRead：13 才有。
    read = {major: snapshot(major, 'IO', 'DataFileRead', 'Waiting for a read from a data file.',
                            '等待从数据文件读取。')
            for major in ('13', '17', '18', '19', '20')}
    WaitEvent.objects.create(
        key='io/datafileread', type='IO', type_slug='io', name='DataFileRead',
        slug='data-file-read', aliases=[], type_variants=[],
        summary='Waiting for a read from a data file.', summary_zh='等待从数据文件读取。',
        first_version='13', last_version='20',
        present_in=['13', '17', '18', '19', '20'], changed_in=[], versions=read,
        changes=[plain('added', '12', '13')], dossier={}, has_dossier=False, position=4000)

    # Lock/Gone：13 之后不再有。
    gone = {major: snapshot(major, 'Lock', 'Gone', 'Waiting for something long gone.',
                            '等待一个早已消失的东西。')
            for major in ('9.6', '12', '13')}
    WaitEvent.objects.create(
        key='lock/gone', type='Lock', type_slug='lock', name='Gone', slug='gone',
        aliases=[], type_variants=[], summary='Waiting for something long gone.',
        summary_zh='等待一个早已消失的东西。', first_version='9.6', last_version='13',
        present_in=['9.6', '12', '13'], changed_in=[], versions=gone,
        changes=[plain('removed', '13', '17')], dossier={}, has_dossier=False, position=6000)


def load_manual():
    """本站只收了 18 与 devel 的监控统计页，其余版本不给死链。"""
    from datetime import date
    from pgweb.core.models import Version
    from pgweb.docs.models import DocPage
    Version.objects.bulk_create([
        Version(tree=tree, current=tree == 18, reldate=date(2025, 9, 1),
                firstreldate=date(2025, 9, 1), eoldate=date(2030, 1, 1))
        for tree in (18, 0)])
    for tree in (18, 0):
        DocPage.objects.create(file='monitoring-stats.html', version_id=tree,
                               title='监控数据库活动', content='<p>等待事件</p>')
        DocPage.objects.create(file='runtime-config-resource.html', version_id=tree,
                               title='资源消耗', content='<p>shared_buffers</p>')


class WaitEventIndexTests(TestCase):
    """索引页的分组、轨迹、筛选与统计。"""

    @classmethod
    def setUpTestData(cls):
        build()
        load_manual()

    def setUp(self):
        cache.clear()

    def test_versions_keep_the_na_majors_and_the_default(self):
        payload = waitevent.index()
        self.assertEqual([v['major'] for v in payload['versions']],
                         [major for major, *_ in VERSIONS])
        self.assertEqual(payload['default_major'], '18')
        self.assertEqual((payload['earliest_major'], payload['latest_major']), ('9.6', '20'))
        self.assertEqual(payload['na_majors'], ['9.5'])
        na = next(v for v in payload['versions'] if v['major'] == '9.5')
        self.assertFalse(na['has_wait_events'])
        self.assertEqual(na['url'], '/docs/waitevent/changes/9.5/')

    def test_groups_follow_the_canonical_type_order(self):
        payload = waitevent.index()
        self.assertEqual([group['type'] for group in payload['groups']],
                         ['Activity', 'Buffer', 'IO', 'Lock', 'LWLock'])
        lwlock = payload['groups'][-1]
        self.assertEqual((lwlock['anchor'], lwlock['type_slug'], lwlock['en']),
                         ('type-lwlock', 'lwlock', 'LWLock'))
        self.assertEqual(lwlock['label'], '轻量级锁')
        self.assertEqual(payload['total'], 5)
        self.assertEqual(payload['type_count'], 5)

    def test_count_latest_only_counts_the_newest_version(self):
        groups = {group['type']: group for group in waitevent.index()['groups']}
        self.assertEqual((groups['Lock']['count'], groups['Lock']['count_latest']), (1, 0))
        self.assertEqual((groups['IO']['count'], groups['IO']['count_latest']), (1, 1))

    def rows(self):
        return {row['key']: row for group in waitevent.index()['groups'] for row in group['rows']}

    def test_strip_marks_na_added_changed_and_present(self):
        strip = {cell['major']: cell['state']
                 for cell in self.rows()['lwlock/buffercontent']['strip']}
        self.assertEqual(strip, {'9.5': 'na', '9.6': 'added', '12': 'changed', '13': 'changed',
                                 '17': 'present', '18': 'changed', '19': 'present',
                                 '20': 'present'})

    def test_the_first_version_is_added_because_the_mechanism_starts_at_9_6(self):
        """系统目录的收录基线不算「引入」，等待事件的 9.6 算：机制本身就是 9.6 来的。"""
        row = self.rows()['lwlock/buffercontent']
        self.assertEqual(row['strip'][1]['state'], 'added')
        self.assertEqual(row['strip'][1]['major'], '9.6')

    def test_strip_marks_absent_and_removed(self):
        gone = {cell['major']: cell['state'] for cell in self.rows()['lock/gone']['strip']}
        self.assertEqual(gone['13'], 'present')
        self.assertEqual(gone['17'], 'removed')
        self.assertEqual(gone['18'], 'absent')
        self.assertTrue(self.rows()['lock/gone']['removed'])
        self.assertEqual(self.rows()['lock/gone']['removed_in'], '17')
        read = {cell['major']: cell['state'] for cell in self.rows()['io/datafileread']['strip']}
        self.assertEqual((read['12'], read['13']), ('absent', 'added'))

    def test_na_absent_and_removed_cells_carry_no_link(self):
        cells = {cell['major']: cell for cell in self.rows()['lock/gone']['strip']}
        self.assertEqual(cells['9.5']['url'], '')
        self.assertEqual(cells['17']['url'], '')
        self.assertEqual(cells['18']['url'], '')
        self.assertEqual(cells['13']['url'], '/docs/waitevent/lock/Gone/?v=13')

    def test_row_carries_the_names_it_ever_used(self):
        row = self.rows()['lwlock/buffercontent']
        self.assertEqual(row['aliases'], ['buffer_content'])
        self.assertEqual(row['type_variants'], ['LWLockTranche'])
        self.assertEqual((row['change_count'], row['last_change']), (3, '18'))
        self.assertTrue(row['has_dossier'])
        self.assertIn('buffer_content', row['text'])
        self.assertIn('轻量级锁', row['text'])

    def test_filters_count_types_versions_and_first_version(self):
        filters = {item['param']: item for item in waitevent.index()['filters']}
        self.assertEqual(list(filters), ['type', 'present', 'first'])
        types = {option['value']: option['count'] for option in filters['type']['options']}
        self.assertEqual(types, {'Activity': 1, 'Buffer': 1, 'IO': 1, 'Lock': 1, 'LWLock': 1})
        present = {option['value']: option['count'] for option in filters['present']['options']}
        self.assertEqual(present['9.6'], 4)
        self.assertEqual(present['20'], 4)
        # 9.0 – 9.5 没有等待事件，不进筛选。
        self.assertNotIn('9.5', present)
        first = {option['value']: option['count'] for option in filters['first']['options']}
        self.assertEqual(first, {'9.6': 4, '13': 1})

    def test_stats_count_snapshots_changes_and_dossiers(self):
        stats = waitevent.index()['stats']
        self.assertEqual(stats['events'], 5)
        self.assertEqual(stats['types'], 5)
        self.assertEqual(stats['snapshots'], 7 + 7 + 7 + 5 + 3)
        self.assertEqual(stats['changes'], 3 + 1 + 1)
        self.assertEqual(stats['dossiers'], 1)

    def test_type_nav_and_sibling_groups(self):
        nav = waitevent.type_nav('lwlock')
        self.assertEqual(nav[-1], {'title': '轻量级锁', 'link': '/docs/waitevent/#type-lwlock',
                                   'active': True})
        groups = waitevent.sibling_groups('LWLock', 'lwlock/buffercontent')
        self.assertEqual([group['type'] for group in groups], ['LWLock'])
        self.assertEqual(groups[0]['current'], 'lwlock/buffercontent')


class WaitEventLookupTests(TestCase):
    """四级查找与非规范地址的 301。"""

    @classmethod
    def setUpTestData(cls):
        build()

    def setUp(self):
        cache.clear()

    def test_the_canonical_pair_needs_no_redirect(self):
        event, canonical = waitevent.lookup('lwlock', 'BufferContent')
        self.assertEqual(event.key, 'lwlock/buffercontent')
        self.assertIsNone(canonical)

    def test_case_slug_and_alias_all_resolve_with_a_canonical_url(self):
        for wanted in ('buffercontent', 'BUFFERCONTENT', 'buffer-content', 'buffer_content',
                       'BUFFER_CONTENT'):
            event, canonical = waitevent.lookup('lwlock', wanted)
            self.assertEqual(event.key, 'lwlock/buffercontent', wanted)
            self.assertEqual(canonical, '/docs/waitevent/lwlock/BufferContent/', wanted)

    def test_an_unknown_type_or_name_finds_nothing(self):
        self.assertEqual(waitevent.lookup('mystery', 'BufferContent'), (None, None))
        self.assertEqual(waitevent.lookup('lwlock', 'NoSuchEvent'), (None, None))
        # 曾用名只在自己的类型里认：类型对不上就不是同一个事件。
        self.assertEqual(waitevent.lookup('io', 'buffer_content'), (None, None))

    def test_detail_reports_the_canonical_url_instead_of_a_payload(self):
        payload = waitevent.detail('lwlock', 'buffer_content')
        self.assertEqual(payload['canonical'], '/docs/waitevent/lwlock/BufferContent/')
        self.assertEqual(waitevent.detail('lwlock', 'BufferContent')['canonical'], '')
        with self.assertRaises(WaitEvent.DoesNotExist):
            waitevent.detail('lwlock', 'NoSuchEvent')


class WaitEventDetailTests(TestCase):
    """详情页上下文：版本选择、措辞、分段描述、事实卡与图谱档案。"""

    @classmethod
    def setUpTestData(cls):
        build()
        load_manual()
        GucParameter.objects.create(name='work_mem', key='work_mem', group='Resource Usage',
                                    group_slug='resource')

    def setUp(self):
        cache.clear()

    def test_version_defaults_to_stable_and_honours_v(self):
        self.assertEqual(waitevent.detail('lwlock', 'BufferContent')['version']['major'], '18')
        self.assertEqual(waitevent.detail('lwlock', 'BufferContent', '13')['version']['major'], '13')
        # 无效的 ?v= 落回默认版本；默认版本没有这个事件时取它最后存在的版本。
        self.assertEqual(waitevent.detail('lwlock', 'BufferContent', 'nope')['version']['major'], '18')
        self.assertEqual(waitevent.detail('lock', 'Gone')['version']['major'], '13')

    def test_change_note_wording(self):
        note = lambda major: waitevent.detail('lwlock', 'BufferContent', major)['change_note']  # noqa: E731
        self.assertEqual(note('9.6'), '9.6 引入等待事件机制，此为本事件的首个版本。')
        self.assertEqual(note('12'), 'PostgreSQL 12：类型由 LWLockTranche 改为 LWLock。')
        self.assertEqual(note('13'), 'PostgreSQL 13：由 buffer_content 更名为 BufferContent。')
        self.assertEqual(note('17'), '相对 PostgreSQL 13 无变化。')
        self.assertEqual(note('18'), 'PostgreSQL 18：描述措辞更新。')
        self.assertEqual(waitevent.detail('io', 'DataFileRead', '13')['change_note'],
                         'PostgreSQL 13 新增此等待事件。')
        self.assertEqual(waitevent.detail('buffer', 'BufferPin', '19')['change_note'],
                         'PostgreSQL 19：类型由 BufferPin 改为 Buffer。')

    def test_runs_merge_adjacent_versions_that_say_the_same_thing(self):
        runs = waitevent.detail('lwlock', 'BufferContent', '18')['runs']
        self.assertEqual([run['majors'] for run in runs],
                         [['9.6'], ['12'], ['13', '17'], ['18', '19', '20']])
        self.assertEqual(runs[0]['name'], 'buffer_content')
        self.assertEqual(runs[0]['type'], 'LWLockTranche')
        self.assertTrue(runs[0]['renamed'])
        self.assertTrue(runs[0]['moved'])
        self.assertEqual(runs[-1]['description'], SHARED)
        self.assertEqual(runs[-1]['description_zh'], '等待访问共享内存中的数据页。')
        self.assertFalse(runs[-1]['renamed'])
        self.assertEqual((runs[-1]['first'], runs[-1]['last']), ('18', '20'))
        self.assertEqual([run['majors'] for run in
                          waitevent.detail('io', 'DataFileRead', '18')['runs']],
                         [['13', '17', '18', '19', '20']])

    def test_a_gap_in_the_versions_breaks_the_run(self):
        """中间缺了一版就不是一段：并段只看相邻版本。"""
        event = WaitEvent.objects.get(key='io/datafileread')
        event.present_in = ['13', '18', '19', '20']
        event.versions.pop('17')
        event.save(update_fields=['present_in', 'versions'])
        cache.clear()
        self.assertEqual([run['majors'] for run in
                          waitevent.detail('io', 'DataFileRead', '18')['runs']],
                         [['13'], ['18', '19', '20']])

    def test_ribbon_marks_the_current_version_and_links_the_local_manual(self):
        ribbon = {cell['major']: cell
                  for cell in waitevent.detail('lwlock', 'BufferContent', '18')['ribbon']}
        self.assertTrue(ribbon['18']['current'])
        self.assertFalse(ribbon['17']['current'])
        self.assertEqual(ribbon['18']['doc_url'],
                         '/docs/18/monitoring-stats.html#WAIT-EVENT-LWLOCK-TABLE')
        self.assertEqual(ribbon['20']['doc_url'],
                         '/docs/devel/monitoring-stats.html#WAIT-EVENT-LWLOCK-TABLE')
        # 本站没有 13 的手册，不给死链。
        self.assertEqual(ribbon['13']['doc_url'], '')
        self.assertEqual(ribbon['9.5']['state'], 'na')

    def test_links_point_at_the_manual_upstream_and_the_source(self):
        links = waitevent.detail('lwlock', 'BufferContent', '18')['links']
        self.assertEqual(links['doc'], '/docs/18/monitoring-stats.html#WAIT-EVENT-LWLOCK-TABLE')
        self.assertEqual(links['doc_label'], 'PostgreSQL 18 手册')
        self.assertEqual(links['official'],
                         'https://www.postgresql.org/docs/18/monitoring-stats.html'
                         '#WAIT-EVENT-LWLOCK-TABLE')
        self.assertIn('bufmgr.c#L5140', links['source'])
        self.assertIn('names.txt#L42', links['definition'])
        self.assertEqual(links['atlas'], 'https://wait.pg.center/lwlock/buffer-content/')
        # 本站没有 13 的手册页，链接与标签一起留空。
        thirteen = waitevent.detail('lwlock', 'BufferContent', '13')['links']
        self.assertEqual((thirteen['doc'], thirteen['doc_label']), ('', ''))

    def test_doc_versions_only_lists_pages_the_site_has(self):
        payload = waitevent.detail('lwlock', 'BufferContent', '18')
        self.assertEqual([item['major'] for item in payload['doc_versions']], ['18', '20'])
        self.assertEqual(payload['doc_versions'][1]['label'], '20 devel')

    def test_facts_report_type_first_version_coverage_and_names(self):
        facts = {row['label']: row for row in
                 waitevent.detail('lwlock', 'BufferContent', '18')['facts']}
        self.assertEqual(facts['类型']['value'], '轻量级锁')
        self.assertEqual(facts['类型']['url'], '/docs/waitevent/#type-lwlock')
        self.assertEqual(facts['引入版本']['value'], '9.6（机制起点）')
        self.assertEqual(facts['版本状态']['value'], '当前稳定版')
        self.assertEqual(facts['版本状态']['url'], '/docs/waitevent/changes/18/')
        self.assertEqual(facts['覆盖版本']['value'], '7 个 · 9.6 – 20')
        self.assertEqual(facts['触发路径']['value'], '实测触发')
        self.assertEqual(facts['实测发行版']['value'], '18.0')
        self.assertEqual(facts['名称变动']['value'], '曾用名 buffer_content · 曾属 LWLockTranche')
        self.assertEqual(facts['手册章节']['url'],
                         '/docs/18/monitoring-stats.html#WAIT-EVENT-LWLOCK-TABLE')
        plain_facts = {row['label']: row['value']
                       for row in waitevent.detail('io', 'DataFileRead', '18')['facts']}
        self.assertEqual(plain_facts['引入版本'], '13')
        self.assertEqual(plain_facts['名称变动'], '无')
        self.assertNotIn('触发路径', plain_facts)

    def test_dossier_derives_sources_sql_actions_and_metrics(self):
        dossier = waitevent.detail('lwlock', 'BufferContent', '18')['dossier']
        self.assertEqual(dossier['kind_label'], '触发点')
        self.assertEqual(dossier['status_label'], '实测触发')
        # 原键原样带出。
        self.assertEqual(dossier['mechanism']['zh'], '后端在缓冲区头部加锁。')
        self.assertEqual(dossier['actions_zh'], ['分散热点页。', '加大 shared_buffers。'])
        self.assertEqual([item['dom_id'] for item in dossier['sql']],
                         ['we-sql-waiters', 'we-sql-pages'])
        self.assertEqual(dossier['sql'][0]['title_zh'], '当前等待者')
        self.assertEqual([metric['name'] for metric in dossier['metrics']],
                         ['pg_stat_activity_count', 'pg_locks_count'])
        self.assertEqual(dossier['availability_note'], '13 起每个版本都实测到。')
        self.assertEqual(dossier['emission_note'], '')
        self.assertEqual(dossier['wait_url'], 'https://wait.pg.center/lwlock/buffer-content/')
        groups = dossier['sources_by_major']
        self.assertEqual([group['major'] for group in groups], ['18', '17'])
        self.assertEqual([row['kind'] for row in groups[0]['rows']],
                         ['trigger', 'catalog_definition'])
        self.assertEqual(groups[0]['rows'][0]['path_line'],
                         'src/backend/storage/buffer/bufmgr.c:5140')
        self.assertEqual(groups[0]['rows'][0]['commit_short'], 'abcdef123')
        self.assertEqual(groups[0]['rows'][1]['kind_label'], '目录定义')
        self.assertEqual(groups[0]['rows'][1]['status_label'], '仅定义')

    def test_a_dormant_event_explains_itself(self):
        event = WaitEvent.objects.get(key='lwlock/buffercontent')
        event.dossier = dict(event.dossier,
                             emission={'status': 'dormant', 'reason': 'never reported',
                                       'evidence': 'no rows in 10 runs'})
        event.save(update_fields=['dossier'])
        cache.clear()
        dossier = waitevent.detail('lwlock', 'BufferContent', '18')['dossier']
        self.assertEqual(dossier['emission_note'], '已编目但未见上报。')
        self.assertEqual(dossier['emission_reason'], 'never reported')
        self.assertEqual(dossier['emission_evidence'], 'no rows in 10 runs')

    def test_an_event_without_a_dossier_is_empty_not_broken(self):
        payload = waitevent.detail('io', 'DataFileRead', '18')
        self.assertEqual(payload['dossier'], {})
        self.assertFalse(payload['has_dossier'])
        self.assertEqual(payload['links']['atlas'], 'https://wait.pg.center/')
        self.assertEqual(payload['links']['source'], '')

    def test_guc_links_land_on_the_column_the_manual_or_the_search_page(self):
        from pgweb.docs.models import DocPage
        from pgweb.search.models import IndexedPage, SearchEntry
        page = DocPage.objects.get(file='runtime-config-resource.html', version_id=18)
        indexed = IndexedPage.objects.create(page=page, source_hash='x')
        SearchEntry.objects.create(source='pg', document=indexed, version=18, key='sb',
                                   entity_key='guc:shared_buffers', kind='guc',
                                   name='shared_buffers', name_key='shared_buffers', aliases=[],
                                   anchor='GUC-SHARED-BUFFERS', heading='', signature='',
                                   body='', preview='', url='')
        cache.clear()
        gucs = {row['name']: row['url']
                for row in waitevent.detail('lwlock', 'BufferContent', '18')['dossier']['gucs']}
        self.assertEqual(gucs['work_mem'], '/docs/guc/work_mem/')
        self.assertEqual(gucs['shared_buffers'],
                         '/docs/18/runtime-config-resource.html#GUC-SHARED-BUFFERS')
        self.assertEqual(gucs['no_such_setting'], '/search/?q=no_such_setting&kind=guc')

    def test_timeline_is_newest_first(self):
        timeline = waitevent.detail('lwlock', 'BufferContent', '18')['timeline']
        self.assertEqual([item['to'] for item in timeline], ['18', '13', '12'])
        self.assertEqual(timeline[0]['reworded']['to'], SHARED)
        self.assertEqual(timeline[0]['url'], '/docs/waitevent/lwlock/BufferContent/?v=18')
        self.assertEqual(timeline[1]['renamed'],
                         {'from': 'buffer_content', 'to': 'BufferContent'})
        self.assertEqual(timeline[0]['description_zh_to'], '等待访问共享内存中的数据页。')

    def test_preview_and_devel_versions_carry_a_notice(self):
        self.assertIn('预发行', waitevent.detail('lwlock', 'BufferContent', '19')['notice'])
        self.assertIn('开发版', waitevent.detail('lwlock', 'BufferContent', '20')['notice'])
        self.assertEqual(waitevent.detail('lwlock', 'BufferContent', '18')['notice'], '')

    def test_siblings_keep_only_the_same_type(self):
        payload = waitevent.detail('lwlock', 'BufferContent', '18')
        self.assertEqual([group['type'] for group in payload['siblings']], ['LWLock'])
        self.assertEqual(payload['siblings'][0]['current'], 'lwlock/buffercontent')
        self.assertEqual(payload['sibling_groups'], payload['siblings'])


class WaitEventChangesTests(TestCase):
    """变更页：按类型分组的五类变化、9.6 基线、9.x 不适用与任意两版比较。"""

    @classmethod
    def setUpTestData(cls):
        build()
        load_manual()

    def setUp(self):
        cache.clear()

    def test_an_adjacent_version_reports_every_kind_of_change(self):
        payload = waitevent.changes('13')
        self.assertEqual(payload['previous']['major'], '12')
        self.assertFalse(payload['arbitrary'])
        self.assertEqual(payload['summary'],
                         {'added': 1, 'removed': 0, 'renamed': 1, 'moved': 0, 'reworded': 0,
                          'total': 2, 'types': 2})
        self.assertEqual([(group['type'], [card['name'] for card in group['cards']])
                          for group in payload['added']], [('IO', ['DataFileRead'])])
        self.assertEqual([(group['type_label'], [card['name'] for card in group['cards']])
                          for group in payload['renamed']], [('轻量级锁', ['BufferContent'])])
        card = payload['renamed'][0]['cards'][0]
        self.assertEqual((card['from_name'], card['to_name']),
                         ('buffer_content', 'BufferContent'))
        self.assertEqual(card['url'], '/docs/waitevent/lwlock/BufferContent/?v=13')

    def test_removed_and_moved_land_in_their_own_buckets(self):
        seventeen = waitevent.changes('17')
        self.assertEqual([card['name'] for group in seventeen['removed'] for card in group['cards']],
                         ['Gone'])
        self.assertEqual(seventeen['summary']['removed'], 1)
        # 移除的事件链到它最后存在的那一版。
        card = seventeen['removed'][0]['cards'][0]
        self.assertEqual(card['url'], '/docs/waitevent/lock/Gone/?v=13')
        nineteen = waitevent.changes('19')
        self.assertEqual([card['name'] for group in nineteen['moved'] for card in group['cards']],
                         ['BufferPin'])
        moved = nineteen['moved'][0]['cards'][0]
        self.assertEqual((moved['from_type'], moved['to_type']), ('BufferPin', 'Buffer'))
        self.assertEqual(nineteen['summary']['moved'], 1)

    def test_reworded_carries_both_english_texts(self):
        payload = waitevent.changes('18')
        card = payload['reworded'][0]['cards'][0]
        self.assertEqual((card['from_text'], card['to_text']), (MEMORY, SHARED))
        self.assertEqual(payload['summary']['reworded'], 1)

    def test_the_first_version_lists_the_whole_baseline(self):
        payload = waitevent.changes('9.6')
        self.assertTrue(payload['baseline'])
        self.assertIsNone(payload['previous'])
        self.assertIn('引入等待事件机制', payload['baseline_note'])
        rows = {row['key']: row for group in payload['baseline_groups'] for row in group['rows']}
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows['lwlock/buffercontent']['name_at'], 'buffer_content')
        self.assertEqual(rows['lwlock/buffercontent']['type_at'], 'LWLockTranche')
        self.assertEqual(payload['summary']['added'], 4)
        self.assertEqual(payload['summary']['types'], 4)

    def test_a_version_without_the_mechanism_only_explains_itself(self):
        payload = waitevent.changes('9.5')
        self.assertTrue(payload['na'])
        self.assertEqual(payload['na_note'], waitevent.NA_NOTE)
        self.assertEqual(payload['first_url'], '/docs/waitevent/changes/9.6/')
        self.assertEqual(payload['summary']['total'], 0)
        self.assertEqual(payload['added'], [])

    def test_a_non_adjacent_comparison_is_computed_on_the_spot(self):
        payload = waitevent.changes('18', from_major='12')
        self.assertTrue(payload['arbitrary'])
        self.assertEqual(payload['from_major'], '12')
        names = lambda rows: sorted(card['name'] for group in rows for card in group['cards'])  # noqa: E731
        self.assertEqual(names(payload['added']), ['DataFileRead'])
        self.assertEqual(names(payload['removed']), ['Gone'])
        self.assertEqual(names(payload['renamed']), ['AutovacuumMain', 'BufferContent'])
        self.assertEqual(names(payload['reworded']), ['BufferContent'])
        self.assertEqual(payload['summary']['total'], 4)

    def test_an_unknown_from_falls_back_to_the_adjacent_comparison(self):
        payload = waitevent.changes('13', from_major='nope')
        self.assertFalse(payload['arbitrary'])
        self.assertEqual(payload['from_major'], '')

    def test_the_version_list_marks_the_current_one(self):
        payload = waitevent.changes('18')
        current = [item['major'] for item in payload['versions'] if item['is_current']]
        self.assertEqual(current, ['18'])
        self.assertEqual(payload['notice'], '')
        self.assertIn('预发行', waitevent.changes('19')['notice'])

    def test_an_unknown_version_raises(self):
        with self.assertRaises(WaitEventVersion.DoesNotExist):
            waitevent.changes('99')

    def test_compare_reports_only_real_differences(self):
        left = {'type': 'LWLock', 'name': 'A', 'description': 'Waiting.'}
        right = {'type': 'LWLock', 'name': 'B', 'description': 'Waiting'}
        change = waitevent.compare(left, right)
        self.assertEqual(change['renamed'], {'from': 'A', 'to': 'B'})
        # 末尾句号不算措辞变化。
        self.assertIsNone(change['reworded'])
        self.assertIsNone(waitevent.compare(left, dict(left)))


class WaitEventSitemapTests(TestCase):
    """索引、每个事件、每个变更页都要进 sitemap。"""

    @classmethod
    def setUpTestData(cls):
        build()

    def setUp(self):
        cache.clear()

    def test_every_page_is_listed(self):
        paths = {path for path, _ in struct.get_struct()}
        self.assertIn('docs/waitevent/', paths)
        self.assertIn('docs/waitevent/lwlock/BufferContent/', paths)
        self.assertIn('docs/waitevent/lock/Gone/', paths)
        self.assertIn('docs/waitevent/changes/18/', paths)
        self.assertIn('docs/waitevent/changes/9.5/', paths)


@unittest.skipUnless(HAS_TEMPLATES, '模板由前端代理并行编写，尚未落地')
class WaitEventPageTests(TestCase):
    """三种页面都要能渲染出来。"""

    @classmethod
    def setUpTestData(cls):
        build()
        load_manual()

    def setUp(self):
        cache.clear()

    def test_index_renders_every_group(self):
        response = self.client.get('/docs/waitevent/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('PostgreSQL 等待事件', html)
        self.assertIn('id="type-lwlock"', html)
        self.assertIn('BufferContent', html)

    def test_detail_renders_the_change_note_and_honours_v(self):
        html = self.client.get('/docs/waitevent/lwlock/BufferContent/').content.decode()
        self.assertIn('LWLOCK', html)
        self.assertIn('PostgreSQL 18：描述措辞更新。', html)
        response = self.client.get('/docs/waitevent/lwlock/BufferContent/?v=13')
        self.assertEqual(response.context['version']['major'], '13')

    def test_a_non_canonical_name_redirects_once(self):
        response = self.client.get('/docs/waitevent/lwlock/buffer_content/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/docs/waitevent/lwlock/BufferContent/')
        response = self.client.get('/docs/waitevent/lwlock/buffer-content/?v=13')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/docs/waitevent/lwlock/BufferContent/?v=13')

    def test_unknown_type_or_event_is_404(self):
        self.assertEqual(self.client.get('/docs/waitevent/mystery/BufferContent/').status_code, 404)
        self.assertEqual(self.client.get('/docs/waitevent/lwlock/NoSuchEvent/').status_code, 404)

    def test_changes_root_redirects_to_the_default_version(self):
        response = self.client.get('/docs/waitevent/changes/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/docs/waitevent/changes/18/')

    def test_changes_pages_render_including_the_na_one(self):
        self.assertEqual(self.client.get('/docs/waitevent/changes/13/').status_code, 200)
        html = self.client.get('/docs/waitevent/changes/9.5/').content.decode()
        self.assertIn('尚无等待事件机制', html)
        self.assertEqual(self.client.get('/docs/waitevent/changes/99/').status_code, 404)
