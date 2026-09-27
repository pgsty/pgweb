"""Reference imports, version boundaries, native routes and search folding."""

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from pgweb.core.models import Version
from pgweb.search import indexer, service
from pgweb.search.models import SearchEntry
from pgweb.util.contexts import _source_url
from pgweb.wiki import topic_importer, topics
from pgweb.wiki.models import ObjectIdentifierType, PredefinedRole
from pgweb.wiki.test_sqlcmd_importer import version

ROOT = Path(__file__).resolve().parents[2]
FILES = ('roles.json', 'oid_types.json', 'relopts.json', 'hooks.json')


def load(name):
    return json.loads((ROOT / 'data/wiki' / name).read_text())


class TopicSnapshotTests(SimpleTestCase):
    def test_shipped_snapshots_validate_without_mutating_inputs(self):
        for filename in FILES:
            data = load(filename)
            original = deepcopy(data)
            kind, rows = topic_importer.prepare(data)
            self.assertEqual(data, original)
            self.assertEqual(len(rows), len(data['items']))
            self.assertEqual(kind, data['kind'])

    def test_duplicate_identity_and_unproven_versions_fail(self):
        for mutation in ('duplicate', 'unknown', 'sources', 'release', 'revision'):
            data = load('roles.json')
            item = data['items'][0]
            snap = next(iter(item['versions'].values()))
            if mutation == 'duplicate':
                data['items'].append(deepcopy(item))
            elif mutation == 'unknown':
                item['versions']['99'] = deepcopy(snap)
            elif mutation == 'sources':
                snap['sources'] = []
            elif mutation == 'release':
                snap['release']['major'] = '99'
            else:
                snap['release']['revision'] = 'unverified'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                topic_importer.prepare(data)

    def test_unsafe_links_are_rejected_before_writing(self):
        for url in ('javascript:alert(1)', '//example.com/a', 'data:text/html,test',
                    'https://user:secret@example.com/'):
            data = load('roles.json')
            next(iter(data['items'][0]['versions'].values()))['sources'][0]['url'] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                topic_importer.prepare(data)


class TopicIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Version.objects.bulk_create([version(n if n < 20 else 0, n == 18,
                                             2 if n in (19, 20) else 0) for n in range(10, 21)])
        for filename in FILES:
            topic_importer.apply(*topic_importer.prepare(load(filename)))

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_import_preview_and_identical_import_preserve_content_and_time(self):
        kind, rows = topic_importer.prepare(load('roles.json'))
        before = dict(PredefinedRole.objects.values_list('slug', 'imported_at'))
        report = topic_importer.apply(kind, rows)
        self.assertEqual(report['unchanged'], 16)
        rows[0]['summary'] = '仅预览的新说明。'
        rows[0]['content_hash'] = '0' * 64
        self.assertEqual(topic_importer.apply(kind, rows, check=True)['updated'], 1)
        self.assertEqual(dict(PredefinedRole.objects.values_list('slug', 'imported_at')), before)
        self.assertNotEqual(PredefinedRole.objects.get(pk=rows[0]['slug']).summary, rows[0]['summary'])
        # A partial input preserves unrelated entities by default.
        topic_importer.apply(kind, rows[1:])
        self.assertEqual(PredefinedRole.objects.count(), 16)

    def test_versions_and_absence_are_explicit_in_detail_and_preview(self):
        data = topics.detail('oid', 'regdatabase', '18')
        self.assertIsNone(data['snapshot'])
        self.assertEqual([v['major'] for v in data['available']], ['19', '20'])
        self.assertEqual(topics.index('role')['major'], '18')
        for kind in topics.TOPICS:
            response = self.client.get('/docs/{}/?v=99'.format(kind))
            self.assertEqual(response.status_code, 404)
        self.assertContains(self.client.get('/docs/oid/regdatabase/?v=18'), '此版本未收录')
        self.assertContains(self.client.get('/docs/oid/regdatabase/?v=19'), '19beta4')

    def test_four_columns_have_navigation_routes_filters_and_safe_output(self):
        for kind in topics.TOPICS:
            with self.subTest(kind=kind):
                response = self.client.get(reverse('wiki:' + kind))
                self.assertEqual(response.status_code, 200)
                soup = BeautifulSoup(response.content, 'html.parser')
                self.assertEqual(len(soup.select('h1')), 1)
                self.assertTrue(soup.select('.topic-table tbody tr'))
                for column in topics.TOPICS:
                    self.assertTrue(soup.select('a[href="/docs/{}/"]'.format(column)))
                self.assertEqual(_source_url('/docs/' + kind + '/'), '')
        response = self.client.get('/docs/role/?q=pg_monitor&category=监控与统计&v=18')
        self.assertContains(response, '当前匹配 1 个')
        self.assertContains(self.client.get('/docs/role/?q=<script>bad()</script>'), '&lt;script&gt;')
        self.assertEqual(self.client.post('/docs/role/').status_code, 405)
        self.assertEqual(self.client.get('/docs/role/nonexistent/').status_code, 404)

    def test_canonical_names_and_version_query_survive_redirect(self):
        response = self.client.get('/docs/role/PG_MONITOR/?v=17')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/docs/role/pg_monitor/?v=17')

    def test_search_folds_oid_with_manual_and_preserves_selected_version(self):
        report = indexer.rebuild_topics()
        self.assertEqual(report['role'], 16)
        self.assertIn('QueryCompletion', SearchEntry.objects.get(source='hook', name='ProcessUtility_hook').body)
        self.assertIn('nextval', SearchEntry.objects.get(source='oid', name='regclass').body)
        SearchEntry.objects.create(source='pg', version=18, key='manual-regclass',
            entity_key='type:regclass', kind='type', subtype='', name='regclass', name_key='regclass',
            aliases=['regclass'], heading='数据类型', signature='', body='手册定义', preview='', anchor='')
        catalogue = (18, [{'key': 'pg18', 'version': 18, 'label': '18'},
                          {'key': 'pg19', 'version': 19, 'label': '19'}])
        with patch.object(service, 'catalog', return_value=catalogue):
            result = service.search('regclass')
            exact = [r for r in result['results'] if r['name'] == 'regclass']
            self.assertEqual(len(exact), 1)
            self.assertEqual(exact[0]['source'], 'oid')
            self.assertEqual(exact[0]['url'], '/docs/oid/regclass/?v=18')
            roles = service.search('pg_monitor', kind='role')
            self.assertEqual(roles['results'][0]['source'], 'role')
            self.assertEqual(service.search('fillfactor', kind='relopts')['total'], 5)
            self.assertTrue(service.search('planner_hook', kind='hook')['results'])
        entry = SearchEntry.objects.get(source='oid', name='regdatabase')
        preview = service.preview(entry, '18')
        self.assertIn('没有此版本', preview['html'])
        self.assertEqual(preview['url'], '/docs/oid/regdatabase/?v=18')

    def test_all_default_details_render_and_blocks_remain_ordered(self):
        for kind, spec in topics.TOPICS.items():
            for slug in spec['model'].objects.values_list('slug', flat=True):
                with self.subTest(kind=kind, slug=slug):
                    response = self.client.get('/docs/{}/{}/'.format(kind, slug))
                    self.assertEqual(response.status_code, 200)
        text = self.client.get('/docs/oid/regclass/?v=18').content.decode()
        self.assertIn('早绑定', text)
        self.assertNotIn('手册示例（续）', text)
