from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from .models import SearchEntry
from .service import preview, search


class WikiVersionScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name, versions in [('abstime', ['10', '11']), ('pg_stat_io', ['16', '17', '18', '19', '20']),
                               ('servicefile', ['20']), ('shared_setting', ['14', '19'])]:
            SearchEntry.objects.create(source='guc', key=name, name=name, name_key=name,
                aliases=[name], entity_key='guc:' + name, kind='guc', wiki_versions=versions,
                heading='参数', body='scope test', url='/wiki/guc/' + name + '/')

    def setUp(self):
        cache.clear()
        self.catalog = patch('pgweb.search.service.catalog', return_value=(19, [
            {'key': 'pg14', 'version': 14, 'label': '14', 'state': 'historical'},
            {'key': 'pg19', 'version': 19, 'label': '19', 'state': 'current'},
            {'key': 'pg20', 'version': 20, 'label': '20 devel', 'state': 'devel'}]))
        self.catalog.start()
        self.addCleanup(self.catalog.stop)
        self.addCleanup(cache.clear)

    def test_removed_new_and_unsampled_entries_are_excluded(self):
        for scope, name in [('pg19', 'abstime'), ('pg14', 'pg_stat_io'), ('pg19', 'servicefile')]:
            with self.subTest(scope=scope, name=name):
                self.assertEqual(search(name, scope=scope)['total'], 0)
        self.assertEqual(search('pg_stat_io', scope='pg19')['results'][0]['url'], '/wiki/guc/pg_stat_io/?v=19')

    def test_membership_precedes_facets_and_pagination(self):
        page = search('', scope='pg19', kind='guc', limit=1)
        self.assertEqual((page['total'], page['all_total'], page['next_offset']), (2, 2, 1))
        self.assertEqual(search('', scope='pg14', kind='guc')['total'], 1)
        self.assertEqual(search('', scope='pg20', kind='guc')['total'], 2)

    def test_fuzzy_fallback_uses_the_same_membership(self):
        self.assertEqual(search('servicefiel', scope='pg19')['total'], 0)
        self.assertEqual(search('servicefiel', scope='pg20')['results'][0]['name'], 'servicefile')

    def test_preview_and_result_use_the_selected_default(self):
        from pgweb.wiki.models import GucParameter
        GucParameter.objects.create(name='jit', key='jit', present_in=['18', '19'], versions={
            '18': {'boot_val': 'on', 'vartype': 'bool', 'context': 'user', 'description_zh': '旧版定义'},
            '19': {'boot_val': 'off', 'vartype': 'bool', 'context': 'user', 'description_zh': '正式版定义'}})
        entry = SearchEntry.objects.create(source='guc', key='jit', name='jit', name_key='jit',
            entity_key='guc:jit', kind='guc', wiki_versions=['18', '19'], url='/wiki/guc/jit/')
        self.assertIn('正式版定义', search('jit', scope='pg19')['results'][0]['snippet'])
        self.assertIn('off', preview(entry, '19')['html'])
        self.assertIn('on', preview(entry, '18')['html'])
        missing = preview(entry, '14')
        self.assertIn('没有此条目', missing['html'])
        self.assertNotIn('正式版定义', missing['html'])

    def test_preview_preserves_historical_major_identifiers(self):
        from pgweb.wiki.models import GucParameter
        GucParameter.objects.create(name='sample', key='sample', present_in=['9.0', '19'], versions={
            '9.0': {'boot_val': '64', 'vartype': 'integer'},
            '19': {'boot_val': '128', 'vartype': 'integer'}})
        entry = SearchEntry.objects.create(source='guc', key='sample', name='sample', name_key='sample',
            entity_key='guc:sample', kind='guc', wiki_versions=['9.0', '19'], url='/wiki/guc/sample/')
        history = preview(entry, '19')['versions'][-1]
        self.assertEqual(history['version'], '9.0')
        self.assertIn('64', preview(entry, str(history['version']))['html'])
