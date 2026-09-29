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
from .columns import COLUMNS, listing, nav_sections
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

    def test_sqlstate_case_redirect_preserves_selected_version(self):
        for prefix in ('/docs/sqlstate/', '/docs/errcode/', '/wiki/errcode/'):
            with self.subTest(prefix=prefix):
                legacy = self.client.get(prefix + '42p01/?v=10')
                self.assertEqual(legacy.status_code, 301)
                self.assertEqual(legacy['Location'], '/wiki/sqlstate/42p01/?v=10')
                canonical = self.client.get(legacy['Location'])
                self.assertEqual(canonical.status_code, 301)
                self.assertEqual(canonical['Location'], '/wiki/sqlstate/42P01/?v=10')

    def test_wait_for_legacy_name_redirects_to_wait(self):
        query = '?v=20&q=a%2Bb&q=c'
        for alias in ('wait-for', 'waitfor', 'WAIT-FOR'):
            with self.subTest(alias=alias):
                old = self.client.get('/docs/sql/' + alias + '/' + query)
                self.assertEqual(old.status_code, 301)
                self.assertEqual(old['Location'], '/wiki/sql/' + alias + '/' + query)
                renamed = self.client.get(old['Location'])
                self.assertEqual(renamed.status_code, 301)
                self.assertEqual(renamed['Location'], '/wiki/sql/wait/' + query)

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

    def test_grouped_home_and_footer_share_only_available_anchors(self):
        sections = nav_sections()
        ids = ['query-language', 'indexes-storage', 'operations', 'client-tools', 'extensibility', 'releases']
        self.assertEqual([section['id'] for section in sections], ids)
        cards = [dict(column, count=12, unit='个条目', first='10', last='20') for column in listing()]
        context = {'columns': cards, 'wiki_sections': sections, 'navmenu': sitenav['wiki']}
        html = render_to_string('wiki/home.html', context)
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual([section['id'] for section in soup.select('.wiki-collection-section')], ids)
        self.assertEqual([a['href'] for a in soup.select('.wiki-section-links a')], ['#' + key for key in ids])
        self.assertEqual([a['href'] for a in soup.select('footer [aria-label="百科"] li a')],
                         ['/wiki/#' + key for key in ids])
        self.assertEqual([a['href'] for a in soup.select('#pgSideNav .wiki-nav-section a')],
                         ['/wiki/#' + key for key in ids])
        self.assertEqual(len(soup.select('a.wiki-card')), len(COLUMNS))
        for card in soup.select('a.wiki-card'):
            self.assertTrue(card.select_one('.wiki-card-heading svg'))
            self.assertTrue(card.select_one('.wiki-card-heading h3'))
            self.assertEqual(card.select_one('.wiki-card-version').get_text(), 'PG 10–20')
        self.assertTrue(soup.select_one('.wiki-language-link a[href="https://pg.center/wiki/"]'))
        self.assertFalse(soup.select('footer a[href^="https://pg.center/"]'))


class StoredWikiLinkTests(SimpleTestCase):
    def test_redundant_empty_links_are_removed_without_losing_anchors(self):
        html = ('<a href="/docs/18/glossary.html#TERM"></a>'
                '<a href="/docs/18/glossary.html#TERM">术语</a>'
                '<a id="definition" href="#TERM"></a><a name="legacy"></a>'
                '<a href="/wiki/" aria-label="百科"></a>')
        self.assertEqual(rewrite_links(html), html.split('</a>', 1)[1])

    def test_missing_sqlstate_cases_keep_a_linkable_empty_state(self):
        from .errcode import blocks
        sections = [{'anchor': 'diagnosis', 'heading': '诊断',
                     'html': '<p><a href="#cases">案例导出</a></p>'}]
        sequence = blocks(sections, [], [], [], [], [])
        self.assertEqual([block['type'] for block in sequence], ['section', 'cases'])
        html = render_to_string('wiki/errcode_detail.html', {'blocks': sequence, 'cases': []})
        soup = BeautifulSoup(html, 'html.parser')
        self.assertIn('当前词条未收录可复现案例', soup.select_one('#cases').get_text())
        self.assertNotIn('在一次性实例上执行过的场景', soup.select_one('#cases').get_text())

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
