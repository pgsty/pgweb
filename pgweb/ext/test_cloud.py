from copy import deepcopy
import csv
import io
from urllib.parse import parse_qs, urlsplit

from django.core.cache import cache
from django.db import connection
from django.test import TestCase

from . import cloud
from .cloud_sync import import_snapshot as import_cloud
from .sync import import_snapshot as import_universe
from .test_cloud_sync import snapshot as one_cloud
from .tests import snapshot as universe_snapshot


def fixture():
    source = one_cloud()
    header = source['tables']['cloud'][0]
    fact = source['tables']['cloud_fact'][0]
    for sid, state, coverage in [('partial', 'GA', 'PARTIAL'), ('missing', 'GA', 'MISSING'),
                                  ('unavailable', 'UNAVAILABLE', 'MISSING'), ('pigsty', 'GA', 'PARTIAL')]:
        source['tables']['cloud'].append(dict(header, service=sid, provider=sid.title(), service_name=sid.title(),
                                             engine_status=state, data_status=coverage))
    source['tables']['cloud_fact'].extend([
        dict(fact, service='pigsty', extra={'packaged': True, 'availability': 'SUPPORTED', 'targets': 1,
                                         'available': 1, 'platforms': [], 'package_relation': 'extension'}, version='0.8.6'),
        dict(fact, raw_name='tiny', extension='tiny', status='OTHER', version=None),
        dict(fact, raw_name='ICU module', extension=None, version='60.2'),
        dict(fact, service='partial', raw_name='ICU module', extension=None, version=None),
    ])
    return source


class CloudPagesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.universe = universe_snapshot()
        import_universe(self.universe)
        import_cloud(fixture())

    def tearDown(self):
        cache.clear()

    def test_integrates_with_standard_chinese_shell_and_catalog_links(self):
        response = self.client.get('/ext/cloud/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base/page.html')
        self.assertTemplateUsed(response, 'ext/base.html')
        self.assertContains(response, '云厂商支持')
        self.assertContains(response, '2026-08-24')
        self.assertContains(self.client.get('/ext/'), 'href="/ext/cloud/"')
        self.assertContains(self.client.get('/e/vector/'), '/ext/cloud/?q=vector')
        self.assertEqual(response.context['mode'], 'compare')
        self.assertEqual(response.context['selected_pg'], 18)
        self.assertEqual(response.context['columns'][0]['service'], 'pigsty')
        self.assertEqual(response.context['result_count'], 4)
        self.assertEqual(self.client.head('/ext/cloud/').status_code, 200)

    def test_scope_uses_package_snapshot_and_raw_service_identity(self):
        packaged = self.client.get('/ext/cloud/?scope=packaged')
        self.assertEqual([r['name'] for r in packaged.context['rows']], ['vector'])
        # Universe packaged=false does not erase the authoritative package baseline.
        self.assertFalse(self.universe['tables']['universe'][0]['packaged'])
        raw = self.client.get('/ext/cloud/?scope=raw')
        self.assertEqual(raw.context['result_count'], 2)
        self.assertEqual({r['key'] for r in raw.context['rows']}, {'raw:example:ICU module', 'raw:partial:ICU module'})
        self.assertTrue(all(not r['href'] for r in raw.context['rows']))
        response = self.client.get('/ext/cloud/partial/?scope=raw')
        self.assertEqual([r['key'] for r in response.context['rows']], ['raw:partial:ICU module'])

    def test_complete_partial_missing_engine_unavailable_are_distinct(self):
        data = cloud.snapshot()
        entry = next(e for e in cloud.entry_rows(data) if e['name'] == 'tiny')
        expected = {'example': 'OTHER', 'partial': 'UNKNOWN', 'missing': 'UNKNOWN', 'unavailable': 'UNAVAILABLE'}
        for service, status in expected.items():
            self.assertEqual(cloud.cell(data, entry, service, 18)['status'], status)
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM pgext.cloud_fact WHERE service='example' AND extension='tiny'")
        cache.clear()
        self.assertEqual(cloud.cell(cloud.snapshot(), entry, 'example', 18)['status'], 'UNSUPPORTED')

    def test_column_selection_and_pg_query_parameters(self):
        response = self.client.get('/ext/cloud/?selection=1&service=example&pg=17')
        self.assertEqual([c['service'] for c in response.context['columns']], ['pigsty', 'example'])
        self.assertTrue(all(c['pg'] == 17 for c in response.context['columns']))
        anchor_only = self.client.get('/ext/cloud/?selection=1')
        self.assertEqual([c['service'] for c in anchor_only.context['columns']], ['pigsty'])
        self.assertEqual(anchor_only.context['result_count'], 4)
        invalid = self.client.get('/ext/cloud/?pg=bad&scope=nope&category=INVALID&service=unknown')
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(invalid.context['selected_pg'], 18)
        self.assertEqual(invalid.context['result_count'], 4)

    def test_filters_empty_state_and_single_service_columns(self):
        response = self.client.get('/ext/cloud/?q=向量&category=RAG')
        self.assertEqual([r['name'] for r in response.context['rows']], ['vector'])
        self.assertContains(self.client.get('/ext/cloud/?q=nonexistent'), '没有匹配的扩展')
        single = self.client.get('/ext/cloud/example/?scope=all')
        self.assertEqual([c['pg'] for c in single.context['columns']], [18, 17, 16, 15, 14])
        self.assertEqual(single.context['result_count'], 2)
        self.assertNotIn('service=', single.context['export_url'])
        self.assertNotIn('selection=', single.context['export_url'])
        self.assertNotIn('pg=', single.context['export_url'])
        missing = self.client.get('/ext/cloud/missing/')
        self.assertTrue(missing.context['empty_evidence'])
        self.assertContains(missing, '尚无可核验的扩展支持清单')
        self.assertEqual(self.client.get('/ext/cloud/no_such_provider/').status_code, 404)
        difference = self.client.get('/ext/cloud/?selection=1&status=different')
        self.assertEqual(difference.context['result_count'], 0)
        unknown = self.client.get('/ext/cloud/?status=unknown')
        self.assertEqual(unknown.context['result_count'], 4)

    def test_evidence_is_accessible_as_a_page_and_retains_official_sources(self):
        response = self.client.get('/ext/cloud/evidence/', {'service': 'example', 'entry': 'vector', 'pg': 18})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '0.8.0 / 0.7.4')
        self.assertContains(response, 'https://example.org/extensions')
        self.assertContains(response, 'Instance-specific')
        self.assertContains(response, '2026-08-24')
        self.assertContains(response, 'noindex,follow')
        self.assertEqual(response.context['cell']['raw_name'], 'pgvector')
        for values in ({'service': 'nope', 'entry': 'vector'}, {'service': 'example', 'entry': 'nope'},
                       {'service': 'example', 'entry': 'vector', 'pg': 'bad'}):
            self.assertEqual(self.client.get('/ext/cloud/evidence/', values).status_code, 404)

    def test_difference_ignores_retained_versions_outside_current_coverage(self):
        data = cloud.snapshot()
        data['coverage'][('example', 18)]['data_status'] = 'MISSING'
        columns = [{'service': sid, 'pg': 18} for sid in ('example', 'missing')]
        selected = {'q': '', 'category': '', 'scope': 'all', 'status': 'different'}
        # One service retains a version in its facts, but both cells are unknown.
        self.assertEqual(cloud.filtered_entries(data, selected, columns), [])

    def test_csv_exports_all_filtered_rows_not_only_the_current_page(self):
        expanded = deepcopy(self.universe)
        source = fixture()
        original_fact = source['tables']['cloud_fact'][0]
        for i in range(3, 58):
            row = deepcopy(expanded['tables']['universe'][0])
            row.update(id=i, name='test_' + str(i), pkg='test_' + str(i), lead_ext='test_' + str(i))
            expanded['tables']['universe'].append(row)
            source['tables']['cloud_fact'].append(dict(original_fact, raw_name=row['name'], extension=row['name']))
        import_universe(expanded)
        import_cloud(source)
        cache.clear()
        response = self.client.get('/ext/cloud/?selection=1&service=example&page=2')
        self.assertEqual(response.context['result_count'], 59)
        self.assertEqual(len(response.context['rows']), 9)
        query = parse_qs(urlsplit(response.context['previous_url']).query)
        self.assertEqual(query['service'], ['example'])
        download = self.client.get(response.context['export_url'])
        self.assertEqual(download['Content-Type'], 'text/csv; charset=utf-8')
        rows = list(csv.DictReader(io.StringIO(download.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 59 * 2)
        self.assertEqual({r['pg_major'] for r in rows}, {'18'})
        self.assertEqual({r['service'] for r in rows}, {'pigsty', 'example'})
        raw_rows = [r for r in rows if r['canonical'] == 'False']
        self.assertEqual({r['entry_key'] for r in raw_rows}, {'raw:example:ICU module', 'raw:partial:ICU module'})
        self.assertEqual({r['raw_name'] for r in raw_rows}, {'ICU module'})

    def test_new_service_generates_route_and_sitemap_without_provider_code(self):
        source = fixture()
        header = dict(source['tables']['cloud'][0], service='new_vendor', service_name='New Vendor')
        source['tables']['cloud'].append(header)
        with self.captureOnCommitCallbacks(execute=True):
            import_cloud(source)
        self.assertEqual(self.client.get('/ext/cloud/new_vendor/').status_code, 200)
        sitemap = self.client.get('/ext/sitemap.xml')
        self.assertContains(sitemap, '/ext/cloud/new_vendor/</loc>')
        self.assertNotContains(sitemap, '/ext/cloud/evidence/')

    def test_snapshot_cache_is_invalidated_on_cloud_import(self):
        self.assertEqual(cloud.snapshot()['facts'][('example', 18, 'vector')]['version'], '0.8.0 / 0.7.4')
        source = fixture()
        source['tables']['cloud_fact'][0]['version'] = '0.9.0'
        with self.captureOnCommitCallbacks(execute=True):
            import_cloud(source)
        self.assertEqual(cloud.snapshot()['facts'][('example', 18, 'vector')]['version'], '0.9.0')
