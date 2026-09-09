from copy import deepcopy
from datetime import date

from django.core.cache import cache
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from .catalog import CATEGORIES, browse_url, catalog, detail_url
from .sync import COLUMNS, import_snapshot, validate_snapshot


def snapshot():
    rows = []
    for id, name, category, lang, license in ((1, 'vector', 'RAG', 'C', 'PostgreSQL'), (2, 'tiny', 'UTIL', 'Rust', 'MIT')):
        row = dict.fromkeys(COLUMNS['universe'])
        row.update(id=id, name=name, pkg=name, lead_ext=name, category=category, kind='standard',
                   lang=lang, license=license, version='1.0', url='https://example.org/' + name,
                   packaged=False, contrib=False, need_ddl=True, rpm_build=False, deb_build=False,
                   extra={}, mtime=date(2026, 9, 8), stars=100 - id, pg_ver=['18'],
                   en_desc='Vector search' if id == 1 else 'Utilities', zh_desc='向量检索' if id == 1 else '实用工具',
                   see_also=['tiny'] if id == 1 else None)
        rows.append(row)
    return {'format': 2, 'tables': {'universe': rows}}


class CatalogTests(TestCase):
    def setUp(self):
        cache.clear()
        self.snapshot = snapshot()
        import_snapshot(self.snapshot)

    def tearDown(self):
        cache.clear()

    def test_chinese_catalog_uses_standard_page_and_download_navigation(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='pgext' ORDER BY table_name")
            self.assertEqual(cursor.fetchall(), [('universe',)])
        self.assertEqual(self.client.head('/ext/').status_code, 200)
        response = self.client.get('/ext/')
        self.assertContains(response, '<h1>PostgreSQL 扩展目录</h1>', html=True)
        self.assertTemplateUsed(response, 'base/page.html')
        self.assertContains(response, '收纳了 2 个扩展插件。')
        self.assertContains(response, '<a href="https://pgext.cloud">pgext.cloud</a>', html=True)
        self.assertContains(response, '<a href="https://pigsty.cc">Pigsty</a>', html=True)
        self.assertContains(response, '向量检索')
        self.assertContains(response, 'href="/e/vector/"')
        from pgweb.util.contexts import sitenav
        download = sitenav['download']
        software = next(i for i, item in enumerate(download) if item['title'] == '软件目录')
        self.assertEqual(download[software + 1], {'title': '扩展目录', 'link': '/ext/'})
        self.assertNotIn('ext', sitenav)
        from pgweb.core.templatetags.pgfilters import nav_active
        self.assertTrue(nav_active('/ext/', 'download'))
        self.assertTrue(nav_active('/e/vector/', 'download'))
        self.assertNotContains(response, 'pgext=#')
        self.assertNotContains(response, 'English')
        self.assertNotContains(response, '<figcaption>')
        self.assertNotContains(response, '共 2 个扩展')
        html = response.content.decode()
        self.assertLess(html.index('id="ext-field"'), html.index('id="ext-search-form"'))
        self.assertLess(html.index('id="ext-search-form"'), html.index('id="ext-results"'))

    def test_sidebar_has_all_sixteen_categories_and_combines_filters(self):
        response = self.client.get('/ext/', {'q': '向量', 'language': 'C'})
        categories = response.context['sidebar_categories']
        self.assertEqual([item['code'] for item in categories], list(CATEGORIES))
        rag = next(item for item in categories if item['code'] == 'RAG')
        self.assertEqual(rag['label'], 'AI 与向量')
        filtered = self.client.get(rag['url'])
        self.assertEqual(filtered.context['selected']['category'], 'RAG')
        self.assertEqual(filtered.context['selected']['language'], 'C')
        self.assertEqual(filtered.context['query'], '向量')
        self.assertEqual([row['name'] for row in filtered.context['rows']], ['vector'])
        navigation = response.context['navmenu']
        self.assertEqual([item['title'] for item in navigation], ['下载', '软件目录', '扩展目录', '浏览文件'])
        self.assertEqual(navigation[0]['link'], '/download/')
        self.assertEqual(len(navigation[2]['submenu']), 16)
        self.assertEqual([item['title'] for item in navigation[2]['submenu']], [item['label'] for item in categories])
        from pgweb.util.contexts import get_nav_menu
        self.assertNotIn('submenu', get_nav_menu('download')[2])

    def test_search_four_filters_and_empty_results(self):
        response = self.client.get('/ext/', {'q': '向量', 'category': 'RAG', 'language': 'C',
                                             'license': 'PostgreSQL', 'repo': 'Unknown'})
        self.assertEqual([row['name'] for row in response.context['rows']], ['vector'])
        self.assertEqual(len(response.context['universe']['cells']), 1)
        self.assertEqual(response.context['total'], 2)
        self.assertEqual(response.context['result_count'], 1)
        self.assertEqual([item['key'] for item in response.context['dropdowns']], ['category', 'license', 'language', 'repo'])
        self.assertTrue(response.context['noindex'])
        self.assertContains(response, '<h1>PostgreSQL 扩展目录</h1>', html=True)
        self.assertContains(self.client.get('/ext/?q=nothingmatches'), '没有找到匹配的扩展')
        self.assertEqual(self.client.get('/ext/?page=invalid').status_code, 200)

    def test_legacy_display_parameters_redirect_to_chinese_table(self):
        for query in ('lang=en', 'lang=zh', 'sort=name', 'view=card'):
            self.assertRedirects(self.client.get('/ext/?' + query + '&category=RAG'), '/ext/?category=RAG',
                                 status_code=301, fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/ext/?repository=PGDG'), '/ext/?repo=PGDG', status_code=301,
                             fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/e/vector/?lang=en'), '/e/vector/', status_code=301,
                             fetch_redirect_response=False)

    def test_category_and_value_links_redirect_to_same_page_filters(self):
        for path, target in (('/ext/rag/', '/ext/?category=RAG'), ('/ext/RAG/', '/ext/?category=RAG'),
                             ('/ext/license/MIT/', '/ext/?license=MIT'), ('/ext/language/c/', '/ext/?language=C'),
                             ('/ext/category/RAG/', '/ext/?category=RAG')):
            self.assertRedirects(self.client.get(path), target, status_code=301, fetch_redirect_response=False)
        response = self.client.get('/ext/?license=MIT')
        self.assertEqual([row['name'] for row in response.context['rows']], ['tiny'])
        self.assertEqual(response.context['seo']['canonical'], '/ext/?license=MIT')
        self.assertEqual(self.client.get('/ext/license/Nope/').status_code, 404)

    def test_indexes_redirect_and_missing_pages(self):
        for path in ('/ext/list/', '/ext/category/', '/ext/license/', '/ext/language/', '/ext/repo/',
                     '/ext/list/category/', '/ext/list/repository/', '/e/'):
            self.assertRedirects(self.client.get(path), '/ext/', status_code=301, fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/ext/vector/?lang=en'), '/e/vector/', status_code=301, fetch_redirect_response=False)
        for path in ('/ext/missing/', '/ext/list/pkg/', '/ext/pkg/vector/', '/e/missing/'):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_missing_chinese_copy_does_not_show_english(self):
        with connection.cursor() as cursor:
            cursor.execute("UPDATE pgext.universe SET zh_desc='' WHERE id=1")
        response = self.client.get('/e/vector/')
        self.assertContains(response, '暂无中文简介')
        self.assertNotContains(response, 'Vector search')

    def test_detail_keeps_overview_relationships_and_pgext_link_without_documents(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/e/vector/')
        self.assertEqual(response.context['links'][0], {'label': 'pgext.cloud', 'url': 'https://pgext.cloud/e/vector'})
        self.assertContains(response, '<h2>概览</h2>', html=True)
        self.assertContains(response, '<h2>相关扩展</h2>', html=True)
        self.assertContains(response, 'href="/e/tiny/"')
        self.assertNotContains(response, '使用文档')
        self.assertNotContains(response, '<pre>')
        self.assertNotIn('document', response.context)
        self.assertTrue(all('pgext.doc' not in query['sql'] for query in queries))
        self.assertEqual(len(response.context['navmenu'][2]['submenu']), 16)

    def test_sitemap_has_only_catalog_and_extension_pages(self):
        response = self.client.get('/ext/sitemap.xml')
        self.assertContains(response, '/ext/</loc>')
        self.assertContains(response, '/e/vector/</loc>')
        self.assertContains(response, '/e/tiny/</loc>')
        self.assertNotContains(response, 'lang=')
        self.assertNotContains(response, '/ext/rag/')
        self.assertNotContains(response, '/ext/license/')

    def test_public_sitemap_discovers_extension_catalog(self):
        from django.test import override_settings
        from pgweb.util.sitestruct import get_all_pages_struct

        # Exercise the same app discovery as /sitemap.xml without requiring
        # unrelated apps' fixtures (versions, release notes, and news).
        with override_settings(INSTALLED_APPS=['pgweb.ext']):
            self.assertEqual(list(get_all_pages_struct()), [
                ('ext/', None), ('e/vector/', None), ('e/tiny/', None),
            ])

    def test_dropdown_counts_respect_other_filters(self):
        response = self.client.get('/ext/', {'language': 'Rust'})
        dropdowns = {item['key']: item['options'] for item in response.context['dropdowns']}
        self.assertEqual({item['value']: item['count'] for item in dropdowns['license']}, {'MIT': 1, 'PostgreSQL': 0})
        self.assertEqual({item['value']: item['count'] for item in dropdowns['language']}, {'C': 1, 'Rust': 1})

    def test_pagination_changes_table_but_keeps_complete_filtered_grid(self):
        expanded = deepcopy(self.snapshot)
        for id in range(3, 54):
            row = deepcopy(expanded['tables']['universe'][0])
            row.update(id=id, name='vector_' + str(id), pkg='vector_' + str(id), lead_ext='vector_' + str(id))
            expanded['tables']['universe'].append(row)
        with self.captureOnCommitCallbacks(execute=True):
            import_snapshot(expanded)
        response = self.client.get('/ext/?category=RAG&page=2')
        self.assertEqual(response.context['result_count'], 52)
        self.assertEqual(len(response.context['rows']), 2)
        self.assertEqual(len(response.context['universe']['cells']), 52)
        self.assertEqual(response.context['previous_url'], '/ext/?category=RAG')

    def test_sync_invalidates_the_current_catalog_cache_after_commit(self):
        self.assertEqual(catalog()[0]['version'], '1.0')
        self.snapshot['tables']['universe'][0]['version'] = '1.1'
        with self.captureOnCommitCallbacks(execute=True):
            import_snapshot(self.snapshot)
        self.assertEqual(catalog()[0]['version'], '1.1')

    def test_catalog_query_only_uses_allowed_tables(self):
        with CaptureQueriesContext(connection) as queries:
            catalog()
        self.assertEqual(len(queries), 1)
        self.assertIn('pgext.universe', queries[0]['sql'])
        self.assertNotIn('pgext.doc', queries[0]['sql'])
        self.assertNotIn('pgext.pkg', queries[0]['sql'])

    def test_repeat_sync_does_not_rewrite_rows(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT ctid FROM pgext.universe ORDER BY id')
            before = cursor.fetchall()
        report = import_snapshot(self.snapshot)
        self.assertEqual(report['tables']['universe']['unchanged'], 2)
        self.assertEqual(set(report['tables']), {'universe'})
        with connection.cursor() as cursor:
            cursor.execute('SELECT ctid FROM pgext.universe ORDER BY id')
            self.assertEqual(before, cursor.fetchall())

    def test_changed_metadata_updates_the_current_record(self):
        self.snapshot['tables']['universe'][0]['version'] = '1.1'
        self.snapshot['tables']['universe'][0]['zh_desc'] = '订正'
        report = import_snapshot(self.snapshot)
        self.assertEqual(report['tables']['universe']['updated'], 1)
        self.assertContains(self.client.get('/e/vector/'), '订正')
        self.assertContains(self.client.get('/e/vector/'), '1.1')

    def test_dry_run_and_explicit_prune(self):
        reduced = deepcopy(self.snapshot)
        for table in COLUMNS:
            reduced['tables'][table].pop()
        report = import_snapshot(reduced, prune=True, dry_run=True)
        self.assertEqual(report['tables']['universe']['deleted'], 1)
        self.assertEqual(len(catalog()), 2)
        self.assertEqual(import_snapshot(reduced)['tables']['universe']['retained'], 1)
        import_snapshot(reduced, prune=True)
        with connection.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM pgext.universe')
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_duplicate_identity_does_not_partially_update_universe(self):
        self.snapshot['tables']['universe'][0]['version'] = '2.0'
        self.snapshot['tables']['universe'][1]['name'] = 'vector'
        with self.assertRaises(ValueError):
            import_snapshot(self.snapshot)
        with connection.cursor() as cursor:
            cursor.execute('SELECT version FROM pgext.universe WHERE id=1')
            self.assertEqual(cursor.fetchone()[0], '1.0')


class UrlTests(SimpleTestCase):
    def test_filters_always_use_the_chinese_catalog_query(self):
        self.assertEqual(browse_url({'category': 'GIS'}), '/ext/?category=GIS')
        self.assertEqual(browse_url({'license': 'MIT OR Apache-2.0'}), '/ext/?license=MIT+OR+Apache-2.0')
        self.assertEqual(browse_url({'language': 'C++'}, page=1), '/ext/?language=C%2B%2B')
        self.assertEqual(browse_url({'category': 'GIS', 'language': 'C'}, q='x'), '/ext/?category=GIS&language=C&q=x')
        self.assertEqual(browse_url({'category': 'GIS'}, q='x'), '/ext/?category=GIS&q=x')
        self.assertEqual(browse_url(), '/ext/')
        self.assertEqual(detail_url('a@b'), '/e/a%40b/')


class SnapshotTests(SimpleTestCase):
    def test_snapshot_rejects_unrelated_tables_and_empty_source(self):
        value = snapshot()
        value['tables']['pkg'] = []
        with self.assertRaises(ValueError):
            validate_snapshot(value)
        value = snapshot()
        value['tables']['universe'] = []
        with self.assertRaises(ValueError):
            validate_snapshot(value)

    def test_legacy_document_snapshots_require_a_new_export(self):
        value = snapshot()
        value['format'] = 1
        value['tables']['doc'] = []
        with self.assertRaisesRegex(ValueError, 're-export'):
            validate_snapshot(value)
