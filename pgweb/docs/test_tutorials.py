from django.test import TestCase


class TutorialsPageTests(TestCase):
    def test_page_links_curated_books_and_training_catalogues(self):
        response = self.client.get('/docs/tutorials/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PostgreSQL 书籍与教程')
        self.assertContains(response, 'href="https://pg36g.vonng.com/"')
        self.assertContains(response, 'src="https://pg36g.vonng.com/logo.png"', count=1)
        self.assertContains(response, 'href="https://dalibo.pgsql.cc/dba1/"', count=1)
        self.assertContains(response, 'href="https://pgpro.pgsql.cc/qpt/"', count=1)
        self.assertContains(response, 'href="https://basic.pgsql.cc/"')
        self.assertNotContains(response, 'https://www.postgresql.org/docs/tutorials/')
        self.assertNotIn("'unsafe-inline'", response['Content-Security-Policy'])

    def test_docs_navigation_exposes_the_tutorial_index(self):
        response = self.client.get('/docs/tutorials/')

        self.assertContains(response, 'href="/docs/tutorials/"', count=4)
        entries = [entry['title'] for entry in response.context['navmenu']]
        self.assertEqual(entries[entries.index('书籍') + 1], '教程')
