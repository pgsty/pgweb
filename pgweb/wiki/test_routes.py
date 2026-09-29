"""The standalone Wiki keeps old links usable and emits canonical URLs."""

from bs4 import BeautifulSoup
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from pgweb.docs import views as docs_views, compare
from pgweb.core.templatetags.pgfilters import nav_active
from pgweb.search.models import SearchEntry
from pgweb.search.service import entry_data
from pgweb.util.contexts import _source_url, sitenav
from .columns import COLUMNS
from .links import canonical_url, rewrite_links


class WikiRoutingTests(SimpleTestCase):
    def test_collections_and_home_resolve_under_wiki(self):
        self.assertEqual(reverse('wiki:reference'), '/wiki/')
        for column in COLUMNS:
            path = '/wiki/' + column['slug'] + '/'
            with self.subTest(path=path):
                match = resolve(path)
                self.assertEqual(match.namespace, 'wiki')
                self.assertEqual(reverse(match.view_name), path)

    def test_legacy_collections_preserve_paths_and_queries(self):
        query = '?v=18&from=17&q=a%2Bb&q=c'
        for column in COLUMNS:
            for tail in ('', 'example/', 'changes/9.6/'):
                old = '/docs/' + column['slug'] + '/' + tail
                with self.subTest(path=old):
                    response = self.client.get(old + query)
                    self.assertEqual(response.status_code, 301)
                    self.assertEqual(response['Location'], old.replace('/docs/', '/wiki/', 1) + query)

    def test_old_home_and_errcode_aliases(self):
        for old, new in (
            ('/docs/reference/', '/wiki/'),
            ('/wiki/reference/', '/wiki/'),
            ('/docs/errcode/23505/', '/wiki/sqlstate/23505/'),
            ('/wiki/errcode/23505/', '/wiki/sqlstate/23505/'),
        ):
            with self.subTest(path=old):
                response = self.client.head(old + '?v=18')
                self.assertEqual(response.status_code, 301)
                self.assertEqual(response['Location'], new + '?v=18')

    def test_manuals_and_comparisons_keep_their_routes(self):
        for path, view in (('/docs/', docs_views.root), ('/docs/18/index.html', docs_views.docpage),
                           ('/docs/devel/index.html', docs_views.docpage), ('/docs/compare/', compare.compare)):
            with self.subTest(path=path):
                self.assertEqual(resolve(path).func, view)

    def test_wiki_has_its_own_navigation(self):
        self.assertFalse(any(item['link'].startswith('/wiki/') for item in sitenav['docs']))
        self.assertEqual({item['link'] for item in sitenav['wiki']},
                         {'/wiki/'} | {'/wiki/' + c['slug'] + '/' for c in COLUMNS})
        for path in ('/wiki/', '/wiki/guc/work_mem/'):
            self.assertTrue(nav_active(path, 'wiki'))
            self.assertFalse(nav_active(path, 'docs'))
            self.assertEqual(_source_url(path), '')

    def test_desktop_and_mobile_menus_use_new_links(self):
        for mode, selector in (('desktop', '.pg-nav__link'), ('mobile', '.pg-drawer__link')):
            html = render_to_string('base/navitems.html', {
                'sitenav': sitenav, 'mode': mode, 'doc_majors': [],
                'request': RequestFactory().get('/wiki/guc/work_mem/'),
            })
            soup = BeautifulSoup(html, 'html.parser')
            self.assertEqual([a['href'] for a in soup.select(selector + '.active')], ['/wiki/'])
            self.assertTrue(soup.select('a[href="/wiki/guc/"]'))
            self.assertFalse(soup.select('a[href^="/docs/guc/"]'))


class StoredWikiLinkTests(SimpleTestCase):
    def test_canonicalization_preserves_queries_and_fragments(self):
        for prefix in ('', 'https://pg.center', 'https://pgsql.cc'):
            self.assertEqual(canonical_url(prefix + '/docs/guc/work_mem/?v=18#history'),
                             prefix + '/wiki/guc/work_mem/?v=18#history')
        self.assertEqual(canonical_url('/docs/reference/?q=lock'), '/wiki/?q=lock')
        self.assertEqual(canonical_url('/wiki/errcode/23505/'), '/wiki/sqlstate/23505/')

    def test_unrelated_urls_are_unchanged(self):
        for url in ('/docs/18/sql-select.html#SQL-SELECT', '/docs/compare/?from=17&to=18',
                    'https://example.com/docs/guc/work_mem/', '//example.com/docs/reference/',
                    '/docs/sqlcmd/', '/wiki/guc/work_mem/', '#history'):
            self.assertEqual(canonical_url(url), url)

    def test_stored_html_links_are_updated_without_rewriting_prose(self):
        html = '<p>/docs/sql/select/ href=&quot;/docs/sql/select/&quot; <a href="/docs/sql/select/?v=18&amp;q=x#notes">SELECT</a></p>'
        expected = html.replace('href="/docs/', 'href="/wiki/')
        self.assertEqual(rewrite_links(html), expected)
        preview = render_to_string('wiki/sqlcmd_preview.html', {'description': html})
        self.assertIn(expected, preview)
        self.assertNotIn('href="/docs/sql/', preview)

    def test_html_rewriter_matches_only_the_anchor_href_attribute(self):
        cases = (
            ('<a data-href="/docs/guc/work_mem/" href="/docs/sql/select/">SELECT</a>',
             '<a data-href="/docs/guc/work_mem/" href="/wiki/sql/select/">SELECT</a>'),
            ("<a title=\"href='/docs/sql/select/'\" href=\"/docs/guc/work_mem/\">Memory</a>",
             "<a title=\"href='/docs/sql/select/'\" href=\"/wiki/guc/work_mem/\">Memory</a>"),
            ("<a href=\"/docs/sql/select/?q=it's\">SELECT</a>",
             "<a href=\"/wiki/sql/select/?q=it's\">SELECT</a>"),
            ('<a-example href="/docs/guc/work_mem/">Memory</a-example>',
             '<a-example href="/docs/guc/work_mem/">Memory</a-example>'),
        )
        for html, expected in cases:
            with self.subTest(html=html):
                self.assertEqual(rewrite_links(html), expected)

    def test_snapshot_importer_accepts_wiki_links_and_rejects_unsafe_urls(self):
        from .topic_importer import links
        for url in ('/wiki/sql/create-index/?v=18', '/docs/18/sql-createindex.html'):
            links([{'label': 'CREATE INDEX', 'url': url}], 'related', required=True)
        for url in ('javascript:alert(1)', '//example.com/wiki/sql/create-index/'):
            with self.assertRaises(ValueError):
                links([{'label': 'Invalid', 'url': url}], 'related', required=True)

    def test_existing_search_rows_emit_new_urls(self):
        row = SearchEntry(source='guc', name='work_mem', name_key='work_mem', kind='guc',
                          url='/docs/guc/work_mem/', heading='work_mem', body='Memory for a query')
        self.assertEqual(entry_data(row)['url'], '/wiki/guc/work_mem/')
