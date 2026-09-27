"""Historical manual links must keep the version stored by the encyclopedia."""

from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from pgweb.core.models import Version
from pgweb.docs.models import DocPage

from . import catalog, guc


class HistoricalManualLinkTests(TestCase):
    versions = (('9.0', '9.0'), ('9.6', '9.6'), ('10.0', '10'), ('0.0', 'devel'))

    @classmethod
    def setUpTestData(cls):
        for tree, slug in cls.versions:
            version = Version(
                tree=Decimal(tree), reldate=date(2026, 1, 1),
                firstreldate=date(2026, 1, 1), eoldate=date(2026, 1, 1))
            Version.objects.bulk_create([version])
            for filename, anchor in (
                    ('catalog-pg-class.html', 'CATALOG-PG-CLASS'),
                    ('runtime-config-resource.html', 'GUC-WORK-MEM')):
                DocPage.objects.create(
                    version=version, file=filename, title='Manual ' + slug,
                    content='<div id="{}">Version {}</div>'.format(anchor, slug))

    def setUp(self):
        cache.delete(catalog.DOC_CACHE_KEY)
        cache.delete(guc.DOC_CACHE_KEY)

    def tearDown(self):
        cache.delete(catalog.DOC_CACHE_KEY)
        cache.delete(guc.DOC_CACHE_KEY)

    def test_catalog_links_keep_each_historical_tree(self):
        pages = catalog.doc_pages()
        for _, slug in self.versions:
            with self.subTest(slug=slug):
                snapshot = {'doc': {'file': 'catalog-pg-class.html', 'slug': slug,
                                    'anchor': 'CATALOG-PG-CLASS'}}
                self.assertEqual(
                    catalog.doc_url(snapshot, pages),
                    '/docs/{}/catalog-pg-class.html#CATALOG-PG-CLASS'.format(slug))
        self.assertNotIn(('9', 'catalog-pg-class.html'), pages)

    def test_guc_links_and_titles_keep_each_historical_tree(self):
        pages = guc.doc_pages()
        for _, slug in self.versions:
            with self.subTest(slug=slug):
                snapshot = {'doc': {'file': 'runtime-config-resource.html', 'slug': slug,
                                    'anchor': 'GUC-WORK-MEM'}}
                self.assertEqual(
                    guc.doc_url(snapshot, pages),
                    '/docs/{}/runtime-config-resource.html#GUC-WORK-MEM'.format(slug))
                self.assertEqual(guc.doc_title(snapshot, pages), 'Manual ' + slug)
        self.assertNotIn(('9', 'runtime-config-resource.html'), pages)

    def test_missing_manual_pages_still_have_no_local_link(self):
        snapshot = {'doc': {'file': 'missing.html', 'slug': '9.6', 'anchor': 'MISSING'}}
        self.assertEqual(catalog.doc_url(snapshot), '')
        self.assertEqual(guc.doc_url(snapshot), '')
