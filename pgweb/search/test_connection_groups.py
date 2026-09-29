"""Client group membership is stable before/after curated deduplication."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from pgweb.core.models import Version
from pgweb.docs.models import DocPage
from pgweb.wiki.test_sqlcmd_importer import version
from . import service
from .models import IndexedPage, SearchEntry


class ConnectionGroupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Version.objects.bulk_create([version(18, True)])
        page = DocPage.objects.create(version_id=18, file='libpq-connect.html', title='Connection keywords', content='')
        document = IndexedPage.objects.create(page=page, source_hash='a' * 64)
        cls.manual = SearchEntry.objects.create(source='pg', document=document, version=18, key='sslmode',
                                                kind='option', subtype='connection', entity_key='option:sslmode',
                                                name='sslmode', name_key='sslmode', aliases=['sslmode'],
                                                heading='Connection keywords', body='TLS negotiation.', preview='<p>TLS negotiation.</p>')
        SearchEntry.objects.create(source='tool', key='pg-dump', kind='tool', entity_key='tool:pg_dump',
                                   name='pg_dump', name_key='pg_dump', aliases=['pg_dump'],
                                   heading='Command-line Tools', body='', preview='', url='/wiki/tool/pg-dump/')

    def setUp(self):
        cache.clear()
        self.catalog = patch.object(service, 'catalog', return_value=(18, [
            {'key': 'pg18', 'version': 18, 'label': '18', 'state': 'current'}]))
        self.catalog.start()
        self.addCleanup(self.catalog.stop)
        self.addCleanup(cache.clear)

    def curated(self):
        return SearchEntry.objects.create(source='conn', key='sslmode', kind='conn', entity_key='option:sslmode',
                                          name='sslmode', name_key='sslmode', aliases=['sslmode'],
                                          heading='Connection Parameters', body='TLS negotiation.', preview='', url='/wiki/conn/sslmode/')

    def check_groups(self, source):
        for kind in ('', 'tool', 'conn'):
            with self.subTest(kind=kind, source=source):
                result = service.search('sslmode', scope='pg18', kind=kind)
                self.assertFalse(result['error'])
                self.assertEqual((result['total'], result['all_total']), (1, 1))
                self.assertEqual(len(result['results']), 1)
                hit = result['results'][0]
                self.assertEqual((hit['source'], hit['group'], hit['kind']), (source, 'conn', 'conn'))
                facets = {f['key']: f['count'] for f in result['facets']}
                self.assertEqual((facets['tool'], facets['conn']), (1, 1))

    def test_manual_and_curated_share_broad_and_specific_membership(self):
        self.check_groups('pg')
        self.curated()
        self.check_groups('conn')

    def test_overlapping_facets_do_not_inflate_browse_or_pagination_totals(self):
        self.curated()
        expected = {'': 2, 'tool': 2, 'conn': 1}
        for kind, count in expected.items():
            result = service.search('', scope='pg18', kind=kind, limit=1)
            self.assertEqual(result['all_total'], 2)
            self.assertEqual(result['total'], count)
            self.assertEqual(result['next_offset'], 1 if count == 2 else None)

    def test_fuzzy_connection_names_obey_both_memberships(self):
        for source in ('pg', 'conn'):
            if source == 'conn':
                self.curated()
            for kind in ('tool', 'conn'):
                result = service.search('sslmdo', scope='pg18', kind=kind)
                self.assertEqual(result['results'][0]['source'], source)
                self.assertEqual(result['results'][0]['group'], 'conn')
                self.assertTrue(result['notice'])
