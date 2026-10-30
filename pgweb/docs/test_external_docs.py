from bs4 import BeautifulSoup
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from pgweb.util.contexts import THIRD_PARTY_DOCS


class ExternalDocumentationTests(TestCase):
    def test_documentation_home_keeps_third_party_navigation_collapsed(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/docs/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<a href="/docs/third-party/">三方文档</a>', count=1, html=True)
        self.assertContains(response, 'href="/docs/third-party/"', count=3)
        self.assertNotIn('submenu', response.context['navmenu'][-1])
        page = BeautifulSoup(response.content, 'html.parser')
        doc_links = [link['href'] for link in page.select('#pgSideNav a, #pgContentWrap a')]
        for component in THIRD_PARTY_DOCS:
            self.assertNotIn(component['link'], doc_links)
        self.assertNotContains(response, 'ecosystem-docs.css')
        for project in ('patroni', 'pgbouncer', 'pgbackrest', 'pgbadger'):
            self.assertNotContains(response, 'href="/docs/{}/'.format(project))
        for query in queries:
            self.assertNotRegex(query['sql'], r'\bdoc_(?:project|revision|page)\b')

    def test_overview_expands_sidebar_and_lists_component_introductions(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/docs/third-party/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['components']), 10)
        entry = next(item for item in response.context['navmenu']
                     if item.get('id') == 'ecosystem-docs')
        self.assertTrue(entry['active'])
        self.assertEqual(entry['submenu'], THIRD_PARTY_DOCS)
        page = BeautifulSoup(response.content, 'html.parser')
        doc_links = [link['href'] for link in page.select('#pgSideNav a, #pgContentWrap a')]
        for component in THIRD_PARTY_DOCS:
            # One external link in the sidebar and one in the overview;
            # neither the desktop dropdown nor the mobile drawer includes it.
            self.assertEqual(doc_links.count(component['link']), 2)
            self.assertContains(response, component['description'])
        for query in queries:
            self.assertNotRegex(query['sql'], r'\b(?:docs|doc_project|doc_revision|doc_page)\b')

        response = self.client.get('/docs/faq/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('submenu', response.context['navmenu'][-1])
        self.assertNotContains(response, 'href="https://doc.pg.center/zh/patroni/"')

    def test_retired_entries_and_chapters_redirect_without_database_queries(self):
        for project in ('patroni', 'pgbouncer', 'pgbackrest'):
            for path in (
                '/docs/{project}',
                '/docs/{project}/',
                '/docs/{project}/config/',
                '/docs/{project}/4.1.5/zh/config/?lang=en',
                '/en/docs/{project}/config/',
                '/zh/docs/{project}/4.1.5/en/',
            ):
                with self.subTest(project=project, path=path), self.assertNumQueries(0):
                    self.assertRedirects(self.client.get(path.format(project=project)),
                                         'https://doc.pg.center/zh/' + project + '/',
                                         status_code=301, fetch_redirect_response=False)

    def test_removed_components_do_not_render_local_manuals(self):
        for path in ('/docs/pgbadger/', '/docs/pgbadger/13.2/zh/', '/en/docs/pgbadger/',
                     '/docs/etcd/', '/docs/haproxy/'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_retired_tables_are_absent_from_fresh_database(self):
        with connection.cursor() as cursor:
            for table in ('doc_project', 'doc_revision', 'doc_page'):
                cursor.execute('SELECT to_regclass(%s)', [table])
                self.assertIsNone(cursor.fetchone()[0])
            cursor.execute("SELECT to_regclass('docs'), to_regclass('pgext.universe')")
            self.assertTrue(all(cursor.fetchone()))
