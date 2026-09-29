"""Chinese specialized readers preserve identities, evidence and selections."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
from django.http import Http404
from django.template import Context, Engine
from django.test import RequestFactory, SimpleTestCase

from . import data_types, index_methods, index_method_views
from .index_method_data import CAPABILITIES, STATES


def version(major, position=0, present=True):
    return {'major': major, 'label': major, 'doc_slug': major, 'position': position,
            'present': present, 'is_current': major == '18', 'status': 'stable'}


def type_payload(snapshot):
    current = version('18', 1)
    item = {'slug': 'int4', 'name': 'integer', 'category': '数值类型', 'summary': '整数',
            'aliases': ['int4'], 'versions': {'17': deepcopy(snapshot), '18': snapshot}}
    return {'kind': 'type', 'major': '18', 'root': '/wiki/type/', 'item': item,
            'snapshot': snapshot, 'version': current, 'versions': [version('17'), current],
            'topic': {'name': '数据类型', 'lead': '数据类型', 'tone': 'cat'}}


def render_template(name, payload):
    root = Path(__file__).resolve().parents[2]
    engine = Engine(dirs=[root / 'templates'], libraries={'pgfilters': 'pgweb.core.templatetags.pgfilters'},
                    loaders=[('django.template.loaders.locmem.Loader', {
                        'wiki/reference_base.html': '{% block wiki_content %}{% endblock %}'}),
                        'django.template.loaders.filesystem.Loader'])
    return engine.get_template(name).render(Context(payload))


class DataTypeReaderTests(SimpleTestCase):
    def test_source_manual_absolute_url_is_preserved_and_sanitized(self):
        snapshot = {'manual_path': 'https://pg.center/docs/18/datatype-numeric.html',
                    'manual_language': 'en', 'manual_html': '<script>evil()</script><p onclick="bad()">English <a href="datatype.html#T">definition</a></p>',
                    'description': ['整数'], 'catalog': {}, 'aliases': ['integer', 'int4']}
        payload = type_payload(snapshot)
        with patch.object(data_types.topics, 'detail', return_value=payload), \
                patch.object(data_types.topics, 'records', return_value=[payload['item']]):
            result = data_types.detail_payload('int4', '18')
        self.assertEqual(result['manual_url'], snapshot['manual_path'])
        self.assertEqual(result['manual_language'], 'en')
        self.assertIn('https://pg.center/docs/18/datatype.html#T', result['manual_html'])
        self.assertNotIn('evil()', result['manual_html'])
        self.assertNotIn('onclick', result['manual_html'])
        html = render_template('wiki/data_type_detail.html', result)
        self.assertIn('英文来源手册', html)
        self.assertIn('lang="en"', html)
        self.assertNotIn('中文手册', html)

    def test_localized_manual_uses_chinese_heading(self):
        snapshot = {'manual_path': '/docs/18/datatype.html', 'manual_language': 'zh',
                    'manual_html': '<p>中文定义</p>', 'catalog': {}}
        payload = type_payload(snapshot)
        with patch.object(data_types.topics, 'detail', return_value=payload), \
                patch.object(data_types.topics, 'records', return_value=[payload['item']]):
            result = data_types.detail_payload('int4', '18')
        html = render_template('wiki/data_type_detail.html', result)
        self.assertIn('中文手册', html)
        self.assertIn('lang="zh"', html)

    def test_filtered_export_and_version_links_preserve_selection(self):
        payload = {'kind': 'type', 'major': '17', 'root': '/wiki/type/', 'query': '整数',
                   'category': '数值类型', 'versions': [version('17')], 'version': version('17'),
                   'rows': [], 'total': 0, 'topic': {'name': '数据类型', 'lead': '类型', 'tone': 'cat'}}
        request = RequestFactory().get('/wiki/type/', {'v': '17', 'q': '整数', 'category': '数值类型'})
        with patch.object(data_types.topics, 'index', return_value=payload), \
                patch.object(data_types, 'context', side_effect=lambda result, *args: result), \
                patch.object(data_types, 'render', side_effect=lambda request, template, context: context):
            context = data_types.index(request)
        self.assertEqual(parse_qs(context['page_query']), {'v': ['17'], 'q': ['整数'], 'category': ['数值类型']})
        self.assertEqual(parse_qs(urlsplit(context['versions'][0]['url']).query), parse_qs(context['page_query']))
        html = render_template('wiki/data_type_index.html', context)
        soup = BeautifulSoup(html, 'html.parser')
        export = next(a['href'] for a in soup.select('a[href]') if 'JSON' in a.get_text())
        self.assertEqual(parse_qs(urlsplit(export).query), {
            'v': ['17'], 'q': ['整数'], 'category': ['数值类型'], 'format': ['json']})
        self.assertFalse(soup.select('a[href^="/wiki/type/changes/"]'))

    def test_catalog_comparison_excludes_localized_manual_prose(self):
        left = {'facts': [{'label': '手册说明', 'value': '旧说明'}], 'catalog': {'typlen': '4'}}
        right = {'facts': [{'label': '手册说明', 'value': '新说明'}], 'catalog': {'typlen': '4'}}
        self.assertFalse(data_types.comparison(left, right)['changes'])
        right['catalog']['typlen'] = '8'
        self.assertEqual(data_types.comparison(left, right)['changes'][0]['label'], '系统目录属性')

    def test_unrecorded_compare_version_is_rejected(self):
        payload = type_payload({'catalog': {}})
        with patch.object(data_types.topics, 'detail', return_value=payload):
            with self.assertRaises(ValueError):
                data_types.detail_payload('int4', '18', '9.6')

    def test_unambiguous_alias_redirect_keeps_version_and_export(self):
        payload = type_payload({'catalog': {}})
        with patch.object(data_types.topics, 'records', return_value=[payload['item']]):
            response = data_types.detail(RequestFactory().get('/wiki/type/integer/?v=18&from=17&format=json'), 'integer')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/wiki/type/int4/?v=18&from=17&format=json')


class IndexMethodReaderTests(SimpleTestCase):
    def snapshot(self, state):
        return {'capabilities': [{'key': key, 'label': label, 'state': state, 'value': STATES[state],
                                  'note': '已核验条件', 'evidence': []} for key, label in CAPABILITIES],
                'storage_options': []}

    def test_unknown_transition_is_evidence_change_not_introduction(self):
        result = index_methods.compare(self.snapshot('unknown'), self.snapshot('yes'))
        self.assertEqual(result['presence'], '')
        self.assertTrue(all(row['evidence_changed'] for row in result['capabilities']))
        self.assertEqual(result['capabilities'][0]['before'], '未确定')
        self.assertEqual(result['capabilities'][0]['after'], '支持')

    def test_source_hash_and_prose_do_not_change_capability_comparison(self):
        left = self.snapshot('conditional')
        right = deepcopy(left)
        right['release'] = {'revision': 'different'}
        right['description'] = ['不同说明']
        self.assertFalse(index_methods.changed(index_methods.compare(left, right)))

    def test_empty_filtered_matrix_does_not_reintroduce_methods(self):
        payload = {'rows': [], 'major': '18', 'versions': [version('17'), version('18')]}
        with patch.object(index_methods.topics, 'index', return_value=payload):
            result = index_methods.index('18', 'no matching method')
        self.assertEqual(result['matrix']['methods'], [])
        self.assertEqual(result['comparison']['rows'], [])
        self.assertIn('没有符合筛选条件', render_template('wiki/index_method_matrix.html', result))

    def test_invalid_comparison_is_404_and_mixed_case_keeps_selection(self):
        with patch.object(index_method_views.index_methods, 'index', side_effect=ValueError):
            with self.assertRaises(Http404):
                index_method_views.index(RequestFactory().get('/wiki/indexam/?from=bogus'))
        payload = {'item': {'slug': 'btree'}, 'root': '/wiki/indexam/'}
        with patch.object(index_method_views.index_methods, 'detail', return_value=payload):
            response = index_method_views.detail(RequestFactory().get('/wiki/indexam/BTREE/?v=18&from=17'), 'BTREE')
        self.assertEqual(response['Location'], '/wiki/indexam/btree/?v=18&from=17')

    def test_index_version_picker_preserves_search_category_and_baseline(self):
        payload = {'root': '/wiki/indexam/', 'major': '18', 'versions': [version('17'), version('18')],
                   'topic': {'lead': '索引方法'}, 'query': 'btree', 'category': '有序检索'}
        request = RequestFactory().get('/wiki/indexam/', {'v': '18', 'q': 'btree', 'category': '有序检索', 'from': '16'})
        with patch.object(index_method_views.index_methods, 'index', return_value=payload), \
                patch.object(index_method_views, 'context', side_effect=lambda result, *args: result), \
                patch.object(index_method_views, 'render', side_effect=lambda request, template, context: context):
            result = index_method_views.index(request)
        self.assertEqual(parse_qs(urlsplit(result['versions'][0]['url']).query), {
            'v': ['17'], 'q': ['btree'], 'category': ['有序检索'], 'from': ['16']})
        self.assertEqual(result['compare_from'], '16')

    def test_changes_form_does_not_submit_disallowed_version_parameter(self):
        payload = {'root': '/wiki/indexam/', 'major': '18', 'version': version('18'),
                   'versions': [version('17'), version('18')], 'comparison': {'versions': [version('17')], 'rows': []}}
        with patch.object(index_method_views.index_methods, 'index', return_value=payload), \
                patch.object(index_method_views, 'context', side_effect=lambda result, *args: result), \
                patch.object(index_method_views, 'render', side_effect=lambda request, template, context: context):
            result = index_method_views.changes(RequestFactory().get('/wiki/indexam/changes/18/?from=17'), '18')
        html = render_template('wiki/index_method_comparison.html', result)
        self.assertIsNone(BeautifulSoup(html, 'html.parser').select_one('input[name=v]'))
        self.assertTrue(result['versions'][0]['url'].endswith('/changes/17/?from=17'))

    def test_partial_translation_has_explicit_fallback_and_separate_sources(self):
        payload = {'snapshot': {'localization': {'status': 'partial', 'sources': [
            {'url': '/docs/18/indexes-types.html', 'sha256': 'chinese-page-hash'}]}}}
        html = render_template('wiki/specialized_localization.html', payload)
        self.assertIn('尚无已核验的中文对应内容', html)
        self.assertIn('英文原文', html)
        self.assertIn('/docs/18/indexes-types.html', html)
        self.assertIn('chinese-page-hash', html)
        self.assertIn('哈希对应英文来源', html)
