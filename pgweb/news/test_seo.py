from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve

from pgweb.util.moderation import ModerationState

from .models import NewsArticle, NewsTag
from .struct import get_struct
from .util import news_slug, news_url
from .views import _news_meta_description, archive, item


class NewsSeoTests(SimpleTestCase):
    def test_cjk_news_has_a_stable_nonempty_slug(self):
        self.assertEqual(news_slug('中文新闻'), 'news')
        self.assertEqual(news_url('中文新闻', 3233), '/about/news/news-3233/')
        self.assertEqual(
            NewsArticle(title='中文新闻', id=3233).permanenturl,
            '/about/news/news-3233/',
        )

    def test_legacy_empty_slug_resolves_and_redirects_to_canonical(self):
        match = resolve('/about/news/-3233/')
        self.assertEqual(match.kwargs, {'slug': '', 'itemid': '3233'})

        news = SimpleNamespace(
            id=3233,
            title='中文新闻',
            modstate=ModerationState.APPROVED,
        )
        with patch('pgweb.news.views.get_object_or_404', return_value=news):
            response = item(RequestFactory().get('/about/news/-3233/'), '3233', '')

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, '/about/news/news-3233/')

    @patch('pgweb.news.views.summarize_html', return_value='正文摘要')
    def test_news_description_uses_prose_summary(self, summarize):
        news = SimpleNamespace(title='一条新闻', content='发布日期：2026-09-08\n\n正文内容。')

        self.assertEqual(_news_meta_description(news), '正文摘要')
        summarize.assert_called_once()
        self.assertEqual(summarize.call_args.kwargs['max_length'], 180)

    def test_news_description_drops_imported_source_fields(self):
        news = SimpleNamespace(
            title='一条新闻',
            content='原文：https://example.org\n\n发布日期：2026-09-08\n\n作者：Example\n\n正文内容。',
        )

        description = _news_meta_description(news)
        self.assertEqual(description, '正文内容。')

    def test_sitemap_uses_the_same_news_url_helper(self):
        news = SimpleNamespace(title='中文新闻', id=3233, date=date.today())
        manager = Mock()
        manager.filter.return_value = [news]
        with patch.object(NewsArticle, 'objects', manager):
            entries = list(get_struct())

        self.assertEqual(entries[0][0], 'about/news/news-3233/')

    def test_archive_context_labels_the_next_date_cursor(self):
        class QuerySet:
            def __init__(self, rows):
                self.rows = rows

            def filter(self, **kwargs):
                return self

            def select_related(self, *args):
                return self

            def prefetch_related(self, *args):
                return self

            def order_by(self, *args):
                return self

            def __getitem__(self, key):
                return self.rows[key]

        rows = [SimpleNamespace(date=date(2026, 9, 8)) for _ in range(11)]
        manager = QuerySet(rows)
        with patch.object(NewsArticle, 'objects', manager), \
                patch.object(NewsTag, 'objects', Mock()), \
                patch('pgweb.news.views.render_pgweb', return_value=HttpResponse()) as render_pgweb:
            archive(RequestFactory().get('/about/newsarchive/'))

        context = render_pgweb.call_args.args[3]
        self.assertEqual(context['paginator'], '20260908')
        self.assertEqual(context['paginator_date'], date(2026, 9, 8))
        self.assertIsNone(context['cutoff_date'])

    def test_archive_with_next_page_keeps_current_cutoff_date(self):
        class QuerySet:
            def __init__(self, rows):
                self.rows = rows

            def filter(self, **kwargs):
                return self

            def select_related(self, *args):
                return self

            def prefetch_related(self, *args):
                return self

            def order_by(self, *args):
                return self

            def __getitem__(self, key):
                return self.rows[key]

        rows = [SimpleNamespace(date=date(2026, 9, 8)) for _ in range(11)]
        with patch.object(NewsArticle, 'objects', QuerySet(rows)), \
                patch.object(NewsTag, 'objects', Mock()), \
                patch('pgweb.news.views.render_pgweb', return_value=HttpResponse()) as render_pgweb:
            archive(RequestFactory().get('/about/newsarchive/-/20260909/'), paginator='20260909')

        context = render_pgweb.call_args.args[3]
        self.assertEqual(context['cutoff_date'], date(2026, 9, 9))
        self.assertEqual(context['paginator'], '20260908')
        self.assertIn('截至 2026 年 9 月 9 日', context['page_title'])

    def test_archive_final_page_keeps_current_cutoff_date(self):
        class QuerySet:
            def __init__(self, rows):
                self.rows = rows

            def filter(self, **kwargs):
                return self

            def select_related(self, *args):
                return self

            def prefetch_related(self, *args):
                return self

            def order_by(self, *args):
                return self

            def __getitem__(self, key):
                return self.rows[key]

        rows = [SimpleNamespace(date=date(2026, 9, 8)) for _ in range(3)]
        with patch.object(NewsArticle, 'objects', QuerySet(rows)), \
                patch.object(NewsTag, 'objects', Mock()), \
                patch('pgweb.news.views.render_pgweb', return_value=HttpResponse()) as render_pgweb:
            archive(RequestFactory().get('/about/newsarchive/-/20260909/'), paginator='20260909')

        context = render_pgweb.call_args.args[3]
        self.assertEqual(context['cutoff_date'], date(2026, 9, 9))
        self.assertIsNone(context['paginator'])
        self.assertIsNone(context['paginator_date'])
        self.assertIn('截至 2026 年 9 月 9 日', context['page_title'])
