from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.http import Http404
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.utils.html import escape

from pgweb.core.struct import get_struct
from pgweb.core.views import fallback, robots
from pgweb.downloads.views import ftpbrowser
from pgweb.util.seo import page_metadata, summarize_html


class HeadParser(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source.split('</head>')[0])

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def values(self, tag, attr, **match):
        return [attrs.get(attr) for name, attrs in self.elements
                if tag == name and all(attrs.get(key) == value for key, value in match.items())]


class SummaryTests(SimpleTestCase):
    def test_doc_summary_skips_chrome_syntax_and_decodes_entities(self):
        html = '<div class="navheader"><p>Previous</p></div><h1>SELECT</h1>'
        html += '<div class="refsynopsisdiv"><p>Synopsis</p><pre>SELECT ...</pre></div>'
        html += '<p>SELECT&nbsp;检索 &amp;nbsp;表或视图中的数据。</p><p>另一个段落。</p>'
        self.assertEqual(summarize_html(html), 'SELECT 检索 表或视图中的数据。')

    def test_news_summary_skips_migration_fields_but_keeps_author_prose(self):
        html = '<p>原文：<a href="https://example.org">https://example.org</a></p>'
        html += '<p>发布日期：2026-09-08</p><p>作者：Example</p>'
        html += '<p>Author contributions improve PostgreSQL reliability.</p>'
        self.assertEqual(summarize_html(html), 'Author contributions improve PostgreSQL reliability.')

    def test_plain_text_and_inline_code_retain_meaning(self):
        self.assertEqual(summarize_html('支持逻辑复制。'), '支持逻辑复制。')
        self.assertEqual(summarize_html('<p>Use <code>SELECT</code> to retrieve rows.</p>'),
                         'Use SELECT to retrieve rows.')
        self.assertEqual(summarize_html('<div class="toc"><p>目录</p></div>'), '')

    def test_summary_skips_legacy_link_only_contents_paragraph(self):
        contents = '<p><a href="#release">Original release</a><br><a href="#more">More information</a></p>'
        self.assertEqual(summarize_html(contents + '<h2>Release</h2><p>PostgreSQL adds streaming replication.</p>'),
                         'PostgreSQL adds streaming replication.')
        self.assertEqual(summarize_html(contents), '')
        self.assertEqual(summarize_html('<p><a href="/">PostgreSQL</a> supports logical replication.</p>'),
                         'PostgreSQL supports logical replication.')

    def test_summary_is_bounded_without_splitting_english_words(self):
        result = summarize_html('<p>Useful details about PostgreSQL transactions and isolation.</p>', 35)
        self.assertEqual(result, 'Useful details about PostgreSQL…')


class PublicMetadataTests(SimpleTestCase):
    def test_html_and_sharing_titles_use_one_brand_and_preserve_explicit_metadata(self):
        cases = (
            ({'og': {'title': '特性：全文检索'}}, 'PostgreSQL 特性：全文检索'),
            ({'og': {'title': 'PostgreSQL 18 发布'}}, 'PostgreSQL 18 发布'),
            ({'og': {'title': 'SQL UPDATE 2026'}}, 'PostgreSQL SQL UPDATE 2026'),
            ({'og': {'title': '专业服务 - 亚洲'}}, 'PostgreSQL 专业服务 - 亚洲'),
            ({'og': {'title': '测试 "引号" <SQL> & 标题'}}, 'PostgreSQL 测试 "引号" <SQL> & 标题'),
            ({'seo': {'title': 'PostgreSQL 18 文档 · ECPG PREPARE'},
              'og': {'title': 'PREPARE'}}, 'PostgreSQL 18 文档 · ECPG PREPARE'),
            ({'seo': {'title': 'PostgreSQL: Documentation', 'lang': 'en'},
              'og': {'title': 'Documentation'}}, 'PostgreSQL: Documentation'),
            ({'seo': {'title': 'Planet PostgreSQL 博客收录政策'}}, 'Planet PostgreSQL 博客收录政策'),
        )
        for context, expected in cases:
            with self.subTest(title=expected):
                source = render_to_string('base/base.html', context)
                self.assertIn('<title>' + escape(expected) + '</title>', source)
                self.assertEqual(HeadParser(source).values('meta', 'content', property='og:title'), [expected])

    def test_static_and_dynamic_metadata_each_render_once_and_escape_safely(self):
        description = '引号 " 与 SQL a < b & c > d '
        for context in (
            {'seo': {'title': 'PostgreSQL：特性：测试', 'description': description,
                     'canonical': '/example/', 'lang': 'fr', 'alternates': {'fr': '/example/'}}},
            {'og': {'title': '新闻标题', 'description': description, 'url': '/example/'}},
        ):
            context['link_root'] = 'https://pg.center'
            source = render_to_string('base/base.html', context)
            head = HeadParser(source)
            self.assertEqual(head.values('meta', 'content', name='description'), [description])
            self.assertEqual(head.values('meta', 'content', property='og:description'), [description])
            self.assertEqual(head.values('link', 'href', rel='canonical'), ['https://pg.center/example/'])
            self.assertNotIn('< b', source)
        self.assertIn('lang="fr"', render_to_string('base/base.html', {'seo': {'lang': 'fr'}}))

    def test_metadata_cache_refreshes_without_changing_missing_pages(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'metadata.yaml'
            path.write_text('pages:\n  /example/:\n    title: First\n', encoding='utf8')
            with patch('pgweb.util.seo.METADATA_FILE', path):
                self.assertEqual(page_metadata('/example/')['canonical'], '/example/')
                self.assertEqual(page_metadata('/missing/'), {})
                path.write_text('pages:\n  /example/:\n    title: Changed title\n', encoding='utf8')
                self.assertEqual(page_metadata('/example/')['title'], 'Changed title')

    def test_internal_templates_are_not_public_routes_or_sitemap_entries(self):
        for path in ['include/topbar', 'about/press/presskit18/base']:
            with self.subTest(path=path), self.assertRaises(Http404):
                fallback(RequestFactory().get('/' + path + '/'), path)
        paths = {path for path, *_ in get_struct()}
        self.assertIn('about/', paths)
        self.assertIn('download/', paths)
        self.assertNotIn('include/topbar/', paths)
        self.assertNotIn('account/markdown_submission/', paths)
        self.assertNotIn('about/press/presskit18/base/', paths)
        self.assertNotIn('community/lists/', paths)

    def test_submission_help_remains_available_without_being_indexed(self):
        with patch('pgweb.core.views.loader.get_template') as template:
            template.return_value.render.return_value = '<h1>Markdown 提交</h1>'
            response = fallback(RequestFactory().get('/account/markdown_submission/'), 'account/markdown_submission')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Robots-Tag'], 'noindex,follow')

    def test_missing_ftp_inventory_uses_same_upstream_directory(self):
        with patch('pgweb.downloads.views.open', side_effect=FileNotFoundError):
            response = ftpbrowser(RequestFactory().get('/ftp/source/'), 'source/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://www.postgresql.org/ftp/source/')

    def test_search_can_be_crawled_to_observe_noindex(self):
        body = robots(RequestFactory().get('/robots.txt')).content.decode()
        self.assertNotIn('Disallow: /search/', body)
        html = render_to_string('search/sitesearch.html', {})
        self.assertEqual(HeadParser(html).values('meta', 'content', name='robots'), ['noindex,follow'])
