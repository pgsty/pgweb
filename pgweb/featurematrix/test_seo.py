from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from .struct import get_struct
from .views import detail, matrixdata


class FeatureMatrixSeoTests(SimpleTestCase):
    def test_sitemap_contains_every_feature_detail(self):
        entries = list(get_struct())
        self.assertEqual(len(entries), 421)
        self.assertEqual(entries[0][0], 'about/featurematrix/')
        self.assertTrue(all(path.endswith('/') for path, _ in entries))
        self.assertEqual(len({path for path, _ in entries}), len(entries))

    @patch('pgweb.featurematrix.views.summarize_html', return_value='特性摘要')
    @patch('pgweb.featurematrix.views.render_pgweb', return_value=HttpResponse())
    @patch.object(matrixdata, 'feature_from_slug')
    def test_detail_uses_translated_name_in_title_and_og(self, feature_from_slug, render_pgweb, summarize):
        feature_from_slug.return_value = {
            'display_name': '逻辑复制',
            'display_description': 'Replication details',
        }
        detail(RequestFactory().get('/about/featurematrix/detail/logical-replication/'), 'logical-replication')

        context = render_pgweb.call_args.args[3]
        self.assertEqual(context['feature']['display_name'], '逻辑复制')
        self.assertEqual(context['og']['title'], '特性：逻辑复制')
        self.assertEqual(context['og']['url'], '/about/featurematrix/detail/logical-replication/')
        self.assertEqual(context['og']['description'], '特性摘要')
        summarize.assert_called_once()

    @patch('pgweb.featurematrix.views.summarize_html')
    @patch('pgweb.featurematrix.views.render_pgweb', return_value=HttpResponse())
    @patch.object(matrixdata, 'feature_from_slug')
    def test_url_only_feature_description_gets_a_reader_facing_fallback(self, feature_from_slug, render_pgweb, summarize):
        feature_from_slug.return_value = {
            'display_name': '咨询锁',
            'display_description': 'https://www.postgresql.org/docs/current/explicit-locking.html',
            'versions': {'8.2': 'Yes'},
        }
        detail(RequestFactory().get('/about/featurematrix/detail/advisory-locks/'), 'advisory-locks')

        context = render_pgweb.call_args.args[3]
        self.assertEqual(
            context['og']['description'],
            'PostgreSQL 8.2 起支持“咨询锁”特性，详见官方文档。',
        )
        summarize.assert_not_called()
