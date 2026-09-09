"""Regression checks for the reviewed static-page SEO metadata map."""

from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
METADATA = ROOT / 'data' / 'page_metadata.yaml'
LANGUAGE = re.compile(r'^[a-z]{2,3}(?:-[A-Z]{2})?$')


def template_route(path):
    relative = path.relative_to(ROOT / 'templates' / 'pages').with_suffix('')
    if relative.name == 'base' or 'account' in relative.parts or 'include' in relative.parts:
        return None
    return '/' + '/'.join(relative.parts) + '/'


class PageMetadataMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with METADATA.open(encoding='utf8') as stream:
            cls.pages = yaml.safe_load(stream)['pages']

    def test_every_public_pages_template_has_metadata(self):
        routes = set()
        for path in (ROOT / 'templates' / 'pages').rglob('*.html'):
            route = template_route(path)
            if route:
                routes.add(route)
        missing = sorted(routes - set(self.pages))
        self.assertEqual(missing, [], 'unmapped public pages templates: ' + ', '.join(missing))

    def test_static_entry_points_have_metadata(self):
        routes = {
            '/about/', '/community/', '/developer/beta/', '/download/product-categories/',
            '/community/contributors/', '/community/user-groups/', '/support/versioning/',
            '/support/professional_support/', '/support/professional_hosting/', '/docs/',
            '/docs/books/', '/docs/manuals/archive/', '/docs/release/',
        }
        self.assertEqual(sorted(routes - set(self.pages)), [])

    def test_each_entry_is_complete_and_uses_a_single_brand_prefix(self):
        self.assertNotIn('/', self.pages, 'homepage metadata is owned by the homepage task')
        for path, value in self.pages.items():
            with self.subTest(path=path):
                self.assertTrue(path.startswith('/') and path.endswith('/'))
                self.assertTrue(value.get('title'))
                self.assertTrue(value.get('description'))
                self.assertRegex(value.get('lang', ''), LANGUAGE)
                self.assertNotRegex(value['title'], r'PostgreSQL[：:]\s*PostgreSQL[：:]')

    def test_presskit_roots_are_real_fallback_aliases(self):
        for version in ('10', '11', '12', '13', '14', '15', '16', '17', '18', '90', '91', '92', '93', '94', '95', '96'):
            path = f'/about/press/presskit{version}/'
            with self.subTest(path=path):
                self.assertIn(path, self.pages)
                self.assertEqual(self.pages[path]['canonical'], f'{path}en/')
                self.assertEqual(self.pages[path]['alternates']['en'], f'{path}en/')

    def test_localized_groups_have_language_specific_titles(self):
        self.assertIn('新闻资料包', self.pages['/about/press/presskit18/zh/']['title'])
        self.assertIn('Pressemappe', self.pages['/about/press/presskit18/de/']['title'])
        self.assertIn('Dossier de presse', self.pages['/about/press/presskit18/fr/']['title'])
        self.assertEqual(self.pages['/about/press/presskit93/ua/']['canonical'], '/about/press/presskit93/uk/')
        self.assertEqual(self.pages['/about/policies/coc/zh/']['canonical'], '/about/policies/coc/')
        self.assertEqual(self.pages['/about/policies/coc/']['alternates']['de'], '/about/policies/coc/de/')


if __name__ == '__main__':
    unittest.main()
