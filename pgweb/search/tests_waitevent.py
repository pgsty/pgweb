"""等待事件词条进文档检索：条目形状、重建与别名命中。

手册里没有逐个等待事件的定义行，所以这些词条自成实体（`waitevent:<key>`），
`Type/Name` 与历史拼写都做别名——那正是人们从 pg_stat_activity 里粘出来的写法。
"""

from django.core.cache import cache
from django.test import TestCase

from pgweb.docs.models import DocPage
from .indexer import rebuild_waitevents, waitevent_entry
from .models import IndexedPage, SearchEntry
from .service import parse_query, preview, search
from .taxonomy import resolve_group


class WaitEventSearchTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        from pgweb.wiki import tests_waitevent as wiki_tests
        wiki_tests.build()
        wiki_tests.load_manual()
        # 检索页要至少一个已建索引的手册版本才肯工作。
        page = DocPage.objects.get(file='monitoring-stats.html', version_id=18)
        IndexedPage.objects.create(page=page, source_hash='x')
        cls.report = rebuild_waitevents()

    def setUp(self):
        cache.clear()

    def test_every_event_becomes_one_entry(self):
        self.assertEqual(self.report,
                         {'waitevents': SearchEntry.objects.filter(source='wait').count()})
        self.assertEqual(self.report['waitevents'], 5)
        entry = SearchEntry.objects.get(source='wait', name='BufferContent')
        self.assertEqual((entry.kind, entry.subtype), ('waitevent', 'lwlock'))
        self.assertEqual(entry.entity_key, 'waitevent:lwlock/buffercontent')
        self.assertEqual(entry.url, '/docs/waitevent/lwlock/BufferContent/')
        self.assertEqual(entry.weight, 0.5)
        self.assertEqual(entry.heading, '轻量级锁 · 等待事件')

    def test_aliases_cover_every_spelling_people_paste(self):
        entry = SearchEntry.objects.get(source='wait', name='BufferContent')
        for alias in ('buffercontent', 'lwlock/buffercontent', 'buffer_content',
                      'lwlock/buffer_content', 'lwlocktranche/buffercontent'):
            self.assertIn(alias, entry.aliases, alias)

    def test_the_body_and_preview_carry_the_descriptions_and_the_dossier(self):
        entry = SearchEntry.objects.get(source='wait', name='BufferContent')
        self.assertIn('等待访问共享内存中的数据页。', entry.body)
        self.assertIn('Waiting to access a data page in shared memory.', entry.body)
        self.assertIn('后端在缓冲区头部加锁。', entry.body)
        self.assertIn('等待访问共享内存中的数据页。', entry.preview)
        self.assertIn('LWLock/BufferContent', entry.preview)
        self.assertIn('9.6 – 20', entry.preview)
        self.assertIn('实测触发', entry.preview)
        self.assertIn('当前等待者', entry.preview)

    def test_an_event_without_a_dossier_still_indexes(self):
        entry = SearchEntry.objects.get(source='wait', name='DataFileRead')
        self.assertIn('等待从数据文件读取。', entry.body)
        self.assertNotIn('触发路径', entry.preview)

    def test_the_entry_builder_escapes_what_it_renders(self):
        from pgweb.wiki.models import WaitEvent
        event = WaitEvent.objects.get(key='io/datafileread')
        event.summary_zh = '<script>alert(1)</script>'
        entry = waitevent_entry(event)
        self.assertNotIn('<script>', entry['preview'])
        self.assertIn('&lt;script&gt;', entry['preview'])

    def test_the_name_and_the_pair_both_find_the_event(self):
        for query in ('BufferContent', 'LWLock/BufferContent', 'buffer_content', 'buffercontent'):
            results = search(query)['results']
            self.assertTrue(results, query)
            first = results[0]
            self.assertEqual(first['name'], 'BufferContent', query)
            self.assertEqual((first['source'], first['source_label']), ('wait', '本站词条'), query)
            self.assertEqual(first['url'], '/docs/waitevent/lwlock/BufferContent/', query)
            self.assertEqual((first['kind'], first['group']), ('waitevent', 'waitevent'), query)
            self.assertEqual(first['kind_label'], '等待事件', query)

    def test_the_chinese_description_is_searchable(self):
        names = [hit['name'] for hit in search('数据文件')['results']]
        self.assertIn('DataFileRead', names)

    def test_the_category_filter_and_its_aliases(self):
        self.assertEqual(resolve_group('waitevent'), 'waitevent')
        self.assertEqual(resolve_group('wait'), 'waitevent')
        self.assertEqual(resolve_group('waits'), 'waitevent')
        self.assertEqual(resolve_group('wait_event'), 'waitevent')
        result = search('BufferContent', kind='wait')
        self.assertEqual([hit['name'] for hit in result['results']], ['BufferContent'])
        facets = {facet['key']: facet['count'] for facet in result['facets']}
        self.assertEqual(facets.get('waitevent'), 1)

    def test_the_preview_opens_the_column_entry(self):
        entry = SearchEntry.objects.get(source='wait', name='BufferContent')
        detail = preview(entry)
        self.assertEqual(detail['source_label'], '本站词条')
        self.assertEqual(detail['url'], '/docs/waitevent/lwlock/BufferContent/')
        # 词条自己没有版本，手册也没有逐事件的定义行。
        self.assertEqual(detail['versions'], [])
        self.assertIn('等待访问共享内存中的数据页。', detail['html'])

    def test_the_scope_includes_the_column(self):
        self.assertIn('wait', parse_query('BufferContent', 'pg', '', [18], 18)['sources'])
        self.assertIn('wait', parse_query('BufferContent', 'pg18', '', [18], 18)['sources'])

    def test_rebuilding_replaces_the_previous_entries(self):
        before = SearchEntry.objects.filter(source='wait').count()
        self.assertEqual(rebuild_waitevents(), {'waitevents': before})
        self.assertEqual(SearchEntry.objects.filter(source='wait').count(), before)
        self.assertEqual(rebuild_waitevents(dry_run=True), {'waitevents': before})

    def test_a_dry_run_writes_nothing(self):
        SearchEntry.objects.filter(source='wait').delete()
        self.assertEqual(rebuild_waitevents(dry_run=True), {'waitevents': 5})
        self.assertEqual(SearchEntry.objects.filter(source='wait').count(), 0)
