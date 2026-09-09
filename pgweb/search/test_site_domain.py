from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from .views import legacy_search


class SiteDomainTests(SimpleTestCase):
    @override_settings(SITE_ROOT='https://pgsql.cc/')
    @patch('pgweb.search.views.render', return_value=HttpResponse())
    @patch('pgweb.search.views.psycopg2.connect')
    def test_primary_site_links_use_canonical_domain_before_recrawl(self, connect, render):
        connect.return_value.cursor.return_value.fetchall.return_value = [
            (1, 'https://pg.center', '/docs/current/index.html', '中文手册', '摘要', 1),
            (2, 'https://www.postgresql.org', '/community/', 'Community', 'Summary', 1),
            (1000, None, None, None, None, 2),
        ]
        request = RequestFactory().get('/search/', {'site': '1', 'q': 'PostgreSQL'})
        legacy_search(request)
        hits = render.call_args[0][2]['hits']
        self.assertEqual(hits[0]['url'], 'https://pgsql.cc/docs/current/index.html')
        self.assertEqual(hits[1]['url'], 'https://www.postgresql.org/community/')
