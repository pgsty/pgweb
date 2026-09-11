from django.test import SimpleTestCase, TestCase

from .columns import BY_SLUG, COLUMNS, listing, live_columns, nav_items, url


class ColumnTests(SimpleTestCase):
    def test_four_columns_in_reading_order(self):
        self.assertEqual([c['slug'] for c in COLUMNS], ['errcode', 'guc', 'waitevent', 'catalog'])
        self.assertEqual(set(BY_SLUG), {'errcode', 'guc', 'waitevent', 'catalog'})

    def test_a_column_in_preparation_links_to_its_card(self):
        """Navigation must never point at a route that does not exist yet."""
        for column in COLUMNS:
            if column['live']:
                self.assertEqual(url(column), '/wiki/{}/'.format(column['slug']))
            else:
                self.assertEqual(url(column), '/wiki/#' + column['slug'])

    def test_tone_travels_as_a_class(self):
        """The site CSP forbids inline styles, so colour must be a class."""
        for column in listing():
            self.assertTrue(column['tone_class'].startswith('wiki-tone-'))

    def test_nav_starts_at_the_hub(self):
        items = nav_items()
        self.assertEqual(items[0], {'title': '百科', 'link': '/wiki/'})
        self.assertEqual(len(items), len(COLUMNS) + 1)


class HomeTests(TestCase):
    def test_hub_lists_every_column(self):
        response = self.client.get('/wiki/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for column in COLUMNS:
            self.assertIn(column['name'], html)
            self.assertIn('id="{}"'.format(column['slug']), html)
            if not column['live']:
                self.assertIn('筹备中', html)


class SitemapTests(SimpleTestCase):
    def test_only_live_columns_are_listed(self):
        from .struct import get_struct
        pages = [page for page, _ in get_struct()]
        self.assertEqual(pages[0], 'wiki/')
        self.assertEqual(pages[1:], ['wiki/{}/'.format(c['slug']) for c in live_columns()])
