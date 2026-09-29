"""新增百科与既有中文栏目之间的导入、阅读及搜索边界。"""
from copy import deepcopy
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import resolve

from pgweb.core.models import Version
from pgweb.search import indexer, service
from pgweb.search.models import SearchEntry
from pgweb.wiki import data_types, encyclopedia, topic_importer, topic_views, topics
from pgweb.wiki.models import PgOperator
from pgweb.wiki.test_sqlcmd_importer import version
from pgweb.wiki.topic_registry import DOMAIN_KEYS


def sample(kind='operator'):
    releases = [dict(major=m, label=m, revision='a' * 64, ref='REL_' + m, channel='release')
                for m in ('18', '20')]
    snapshots = {r['major']: dict(description=['逐版本中文定义。'], facts=[{'label': '返回类型', 'value': 'integer'}],
                  signature='integer + integer → integer', sections=[],
                  sources=[{'label': '英文原始手册', 'url': 'https://pg.center/docs/' + ('devel' if r['major'] == '20' else r['major']) + '/functions-math.html'}],
                  related=[], comparison_data={'result': 'int4'}, release=r) for r in releases}
    return {'format': 1, 'language': 'zh', 'kind': kind, 'releases': releases,
            'items': [dict(slug='plus-int4', name='+ (int4, int4)', name_zh='整数加法', category='算术',
                          summary='中文摘要。', aliases=['+'], versions=snapshots)]}


class EncyclopediaContractTests(SimpleTestCase):
    def test_localized_preview_retains_language_without_weakening_sanitization(self):
        from bs4 import BeautifulSoup
        html = '''<p lang="en" class="source">English original.
        <a href="javascript:alert(1)" onclick="alert(2)">unsafe</a></p>
        <p lang="zh" style="color:red">中文译文。<script>alert(3)</script>
        <a href="next.html#part">下一节</a></p>
        <p lang="invalid" class="wiki-source-lang-en">No trusted language.</p>'''
        rendered = encyclopedia.localized_preview_html([html], '/docs/18/current.html')
        soup = BeautifulSoup(rendered, 'html.parser')
        self.assertEqual([node.get('lang') for node in soup.find_all('p')], ['en', 'zh', None])
        self.assertEqual(soup.p.get('class'), ['source'])
        self.assertNotIn('wiki-source-lang-', rendered)
        self.assertIsNone(soup.find('script'))
        self.assertNotIn('alert(', rendered)
        self.assertNotIn('style=', rendered)
        self.assertIsNone(soup.find('a').get('href'))
        self.assertEqual(soup.find_all('a')[1]['href'], '/docs/18/next.html#part')

    def test_language_guard_preserves_legacy_missing_language(self):
        data = sample('hook')
        data.pop('language')
        self.assertEqual(topic_importer.prepare(data)[0], 'hook')
        for language in (None, 'en'):
            data = sample()
            data['language'] = language
            with self.assertRaises(ValueError):
                topic_importer.prepare(data)

    def test_technical_titles_do_not_require_an_invented_chinese_name(self):
        for kind in ('type', 'operator', 'opclass'):
            data = sample(kind)
            data['items'][0]['name_zh'] = ''
            self.assertEqual(topic_importer.prepare(data)[1][0]['name_zh'], '')
            data['items'][0].pop('name_zh')
            self.assertEqual(topic_importer.prepare(data)[1][0]['name_zh'], '')
            data['items'][0]['name'] = ''
            with self.assertRaises(ValueError):
                topic_importer.prepare(data)
        legacy = sample('hook')
        legacy['items'][0]['name_zh'] = ''
        with self.assertRaises(ValueError):
            topic_importer.prepare(legacy)

    def test_comparison_identity_and_external_manual_evidence(self):
        data = sample()
        for major, snap in data['items'][0]['versions'].items():
            snap.update(manual_html='<p>English original.</p>', manual_path=snap['sources'][0]['url'])
        kind, rows = topic_importer.prepare(data)
        self.assertEqual(kind, 'operator')
        for snap in rows[0]['versions'].values():
            self.assertEqual(snap['comparison_hash'], topics.digest({'result': 'int4'}))
            self.assertTrue(snap['manual_path'].startswith('https://pg.center/'))

    def test_tables_reject_unmatched_cells_and_unsafe_links(self):
        data = sample()
        snap = data['items'][0]['versions']['18']
        snap['tables'] = [{'key': 'members', 'title': '成员', 'columns': [{'key': 'operator', 'label': '运算符'}],
                           'rows': [{'operator': {'text': '+', 'url': 'javascript:alert(1)'}}]}]
        with self.assertRaises(ValueError):
            topic_importer.prepare(data)
        snap['tables'][0]['rows'] = [{'unexpected': 'x'}]
        with self.assertRaises(ValueError):
            topic_importer.prepare(data)

    def test_new_routes_and_old_readers_are_distinct(self):
        self.assertIs(resolve('/wiki/hook/').func, topic_views.index)
        self.assertIs(resolve('/wiki/oid/regclass/').func, topic_views.detail)
        for kind in DOMAIN_KEYS:
            self.assertIs(resolve('/wiki/' + kind + '/').func, encyclopedia.index)
            self.assertIs(resolve('/wiki/' + kind + '/changes/18/').func, encyclopedia.changes)
            self.assertIs(resolve('/wiki/' + kind + '/example/').func, encyclopedia.detail)

    def test_existing_topic_summary_remains_editorial(self):
        data = sample('hook')['items']
        versions = [dict(major='18', label='18', status='stable', support_status='supported')]
        with patch.object(topics, 'records', return_value=data), patch.object(topics, 'releases', return_value=versions):
            payload = topics.index('hook', '18')
        self.assertEqual(payload['rows'][0]['summary'], '中文摘要。')
        self.assertEqual(payload['rows'][0]['cells'][0]['label'], '已收录')


class EncyclopediaIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Version.objects.bulk_create([version(18, True), version(0, False, True)])
        data = sample()
        other = deepcopy(data['items'][0])
        other.update(slug='plus-int8', name='+ (int8, int8)', name_zh='长整数加法')
        other['versions'].pop('18')
        data['items'].append(other)
        topic_importer.apply(*topic_importer.prepare(data))

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_projection_and_detail_compare_same_semantics(self):
        row = next(r for r in topics.records('operator') if r['slug'] == 'plus-int4')
        detail = topics.detail('operator', 'plus-int4', '18')
        self.assertEqual(topics.signature_of(row['versions']['18']), topics.signature_of(detail['snapshot']))
        absent = topics.detail('operator', 'plus-int8', '18')
        self.assertIsNone(absent['snapshot'])
        self.assertEqual(absent['major'], '18')
        self.assertEqual(topics.detail('operator', 'plus-int8', '20')['major'], '20')

    def test_reimport_is_idempotent_and_never_removes_other_entities(self):
        before = PgOperator.objects.get(pk='plus-int4').imported_at
        report = topic_importer.apply(*topic_importer.prepare(sample()))
        self.assertEqual(report['unchanged'], 1)
        self.assertEqual(PgOperator.objects.count(), 2)
        self.assertEqual(PgOperator.objects.get(pk='plus-int4').imported_at, before)

    def test_symbol_search_retains_overload_identity_and_version(self):
        indexer.rebuild_topics(kinds=['operator'])
        with patch.object(service, 'catalog', return_value=(18, [{'key': 'pg18', 'version': 18, 'label': '18'}])):
            result = service.search('+', scope='pg18', kind='operator')
        self.assertEqual(result['total'], 2)
        self.assertEqual({r['url'] for r in result['results']}, {'/wiki/operator/plus-int4/?v=18', '/wiki/operator/plus-int8/?v=18'})
        entry = SearchEntry.objects.get(source='operator', entity_key='operator:plus-int8')
        preview = service.preview(entry, '18')
        self.assertIn('没有此版本', preview['html'])
        self.assertEqual(preview['version'], 18)

    def test_generic_json_reader_keeps_requested_absence(self):
        result = self.client.get('/wiki/operator/plus-int8/?v=18&format=json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['major'], '18')
        self.assertIsNone(result.json()['snapshot'])
        self.assertEqual(self.client.get('/wiki/operator/plus-int8/?v=17').status_code, 404)

    def test_type_operator_descriptions_are_batched_and_do_not_mutate_catalog(self):
        from pgweb.wiki.test_specialized_readers import render_template, type_payload
        rows = [dict(oprname='+', oprleft='int4', oprright='int4', descr='add'),
                dict(oprname='-', oprleft='0', oprright='int4', descr='negate')]
        data = sample()
        data['items'] = []
        for entry, translation in zip(rows, ('相加', '取相反数')):
            item = deepcopy(sample()['items'][0])
            item['slug'] = data_types._operator_slug(entry)
            item['versions']['18']['description'] = [translation]
            data['items'].append(item)
        topic_importer.apply(*topic_importer.prepare(data))
        snapshot = {'catalog': {}, 'operators': deepcopy(rows), 'comparison_data': {'operators': deepcopy(rows)}}
        original = deepcopy(snapshot)
        payload = type_payload(snapshot)
        with patch.object(data_types.topics, 'detail', return_value=payload), \
                patch.object(data_types.topics, 'records', return_value=[]), self.assertNumQueries(1):
            result = data_types.detail_payload('int4', '18')
        cells = [row[-1] for row in result['relation_tables'][0]['rows']]
        self.assertEqual([cell['value'] for cell in cells], ['add', 'negate'])
        self.assertEqual([cell['display_descr'] for cell in cells], ['相加', '取相反数'])
        self.assertEqual(snapshot, original)
        rendered = render_template('wiki/data_type_detail.html', result)
        self.assertIn('<span lang="zh">相加</span>', rendered)
        self.assertNotIn('<code>add</code>', rendered)
        with self.assertNumQueries(1):
            self.assertEqual(data_types._operator_descriptions(rows, '17'), {})
