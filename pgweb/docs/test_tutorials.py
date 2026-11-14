from django.test import TestCase


class TutorialsPageTests(TestCase):
    def test_pages_separate_books_from_training_catalogues(self):
        response = self.client.get('/docs/tutorials/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1>PostgreSQL 教程</h1>', html=True)
        self.assertNotContains(response, 'class="tutorials-hero"')
        self.assertNotContains(response, 'href="https://int18.pgsql.cc/"')
        self.assertContains(response, 'href="https://dalibo.pgsql.cc/dba1/"', count=1)
        self.assertContains(response, 'href="https://pgpro.pgsql.cc/qpt/"', count=1)
        self.assertNotContains(response, 'https://www.postgresql.org/docs/tutorials/')
        self.assertNotIn("'unsafe-inline'", response['Content-Security-Policy'])

        response = self.client.get('/docs/books/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '中文书籍')
        self.assertContains(response, 'href="https://int18.pgsql.cc/"')
        self.assertContains(response, 'href="https://pg36g.vonng.com/"')
        self.assertContains(response, 'src="https://pg36g.vonng.com/logo.png"', count=1)
        self.assertContains(response, 'href="https://basic.pgsql.cc/"')
        self.assertNotContains(response, 'href="https://dalibo.pgsql.cc/dba1/"')

    def test_docs_navigation_exposes_the_tutorial_index(self):
        response = self.client.get('/docs/tutorials/')

        self.assertContains(response, 'href="/docs/tutorials/"', count=4)
        entries = [entry['title'] for entry in response.context['navmenu']]
        self.assertEqual(entries[entries.index('书籍') + 1], '教程')
