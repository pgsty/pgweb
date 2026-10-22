"""Native sync preserves measured evidence while replacing selected prose."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from django.template.loader import render_to_string
from tools.wiki_center_sync.catalogs import merge_catalog, merge_guc, merge_wait, local_links, _version_rows
from . import catalog, catalog_importer, guc


def selected(collection, key, version, facts, summary='同版本中文。', payload=None):
    return {'collection': collection, 'key': key, 'version': version,
            'definition': {'source_key': key.lower(), 'source_database': 'center',
                           'facts': facts, 'manual_evidence': {'page': 'manual.html'},
                           'measured_evidence': {}, 'source_revision': 'fixed'},
            'text': {'version': version, 'locale': 'zh-Hans', 'summary': summary,
                     'body_html': '<p>' + summary + '</p>', 'payload': payload or {},
                     'content_hash': 'original-text-hash'}}


class CenterCatalogSyncTests(SimpleTestCase):
    def test_explicit_absent_reviewed_guc_version_is_not_a_fallback(self):
        parameter = SimpleNamespace(present_in=['18', '19'], versions={
            '18': {'center_zh': {'body_html': '<p>中文</p>'}}, '19': {}})
        with patch.object(guc.GucParameter.objects, 'get', return_value=parameter), \
                patch.object(guc, 'versions', return_value=[{'major': '18'}, {'major': '19'}, {'major': '20'}]):
            with self.assertRaises(guc.GucParameter.DoesNotExist):
                guc.detail('array_nulls', '20')

    def test_preview_documentation_and_measurement_pins_are_separate_facts(self):
        version = {'major': '19', 'label': '19 rc1', 'documentation_version': '19rc1',
                   'release': '19beta4', 'server_version': '19beta4',
                   'status_label': '预发行', 'url': '/wiki/catalog/changes/19/'}
        relation = SimpleNamespace(kind_label='系统目录', kind='catalog', relkind='r',
                                   first_version='7.4', changed_in=[])
        with patch.object(catalog, 'version_map', return_value={'19': version}):
            rows = catalog.facts_of(relation, '19', {'runtime_verified': True, 'release': '19beta4'}, [version])
        facts = {r['label']: r['value'] for r in rows}
        self.assertEqual(facts['文档版本'], '19rc1')
        self.assertEqual(facts['实测版本'], '19beta4')
        parameter = SimpleNamespace(vartype='integer', context='user', category_zh='',
                                    group_slug='', category='', first_version='7.4',
                                    last_version='19', present_in=['19'])
        rows = guc.facts_of(parameter, '19', {'human': '1'}, [version], None)
        facts = {r['label']: r['value'] for r in rows}
        self.assertEqual(facts['文档版本'], '19 rc1')
        self.assertEqual(facts['实测版本'], '19beta4')

    def test_historical_default_empty_state_names_the_selected_version(self):
        html = render_to_string('wiki/guc_detail.html', {
            'version': {'major': '7.4', 'label': '7.4'},
            'versions': [{'major': '7.4'}, {'major': '20'}],
            'default_track': [], 'parameter': {'name': 'sort_mem'}, 'name': 'sort_mem'})
        self.assertIn('PostgreSQL 7.4 尚无 pg_settings 实测', html)
        self.assertNotIn('20 开发版尚无 pg_settings 实测', html)

    def test_current_doc_label_does_not_relabel_old_measurement(self):
        for collection in ('catalog', 'guc', 'waitevent'):
            old = {'major': '19', 'label': '19 beta 4', 'documentation_version': '19beta4',
                   'release': '19beta4', 'source_tag': 'REL_19_BETA4',
                   'server_version': '19beta4', 'source_key': '19beta4'}
            row = _version_rows([old], [], {'19'}, collection)[0]
            self.assertEqual(row['label'], '19 rc1')
            if collection == 'catalog':
                self.assertEqual(row['documentation_version'], '19rc1')
            for field in ('release', 'source_tag', 'server_version', 'source_key'):
                self.assertEqual(row[field], old[field])

    def test_catalog_alias_spelling_is_not_a_structural_change(self):
        before = {'columns': [{'name': 'x', 'type': 'integer'}, {'name': 'y', 'type': '"char"[]'}]}
        after = {'columns': [{'name': 'x', 'type': 'int4'}, {'name': 'y', 'type': 'char[]'}]}
        self.assertIsNone(catalog_importer.compare_snapshots(before, after, '19', '20', wording=False))
        after['columns'][0]['type'] = 'int8'
        self.assertEqual(len(catalog_importer.compare_snapshots(before, after, '19', '20', wording=False)['type_changes']), 1)

    def test_runtime_columns_keep_type_attributes_and_implicit_oid(self):
        original = {'runtime_verified': True, 'columns': [
            {'name': 'oid', 'type': 'oid', 'attnum': -2, 'not_null': True},
            {'name': 'value', 'type': 'int4', 'attnum': 1, 'not_null': True,
             'description_zh': '旧说明'}]}
        before = deepcopy(original)
        row = selected('catalog', 'pg_test', '18', {'columns': [
            {'name': 'value', 'type': 'integer', 'description': 'Current description'}]},
            payload={'columns': [{'name': 'value', 'description_zh': '完整说明：第一项；第二项。'}]})
        receipts = []
        result = merge_catalog(original, row, receipts)
        self.assertEqual(original, before)
        self.assertEqual(result['columns'][0], original['columns'][0])
        self.assertEqual(result['columns'][1]['type'], 'int4')
        self.assertTrue(result['columns'][1]['not_null'])
        self.assertEqual(result['columns'][1]['description_zh'], '完整说明：第一项；第二项。')
        self.assertEqual(result['center_zh']['body_html'], row['text']['body_html'])
        self.assertEqual(receipts[0]['rule'], 'preserve-native-column-not-in-manual')

    def test_statistic_slots_and_policy_alias_do_not_rename_physical_columns(self):
        for table, native, documented in [('pg_statistic', 'staop3', 'staopN'),
                                           ('pg_policies', 'permissive', 'polpermissive')]:
            row = selected('catalog', table, '20', {'columns': [
                {'name': documented, 'type': 'oid', 'description': 'slot'}]},
                payload={'columns': [{'name': documented, 'description_zh': '槽位操作符'}]})
            out = merge_catalog({'columns': [{'name': native, 'type': 'oid'}]}, row, [])
            self.assertEqual([c['name'] for c in out['columns']], [native])
            self.assertEqual(out['columns'][0]['description_zh'], '槽位操作符')
            self.assertEqual(out['center_zh']['parity_rules'][0]['selected'], documented)

    def test_new_documented_column_has_no_fabricated_runtime_attributes(self):
        row = selected('catalog', 'pg_test', '20', {'columns': [
            {'name': 'new', 'type': 'bool', 'not_null': False, 'attnum': 9}]})
        out = merge_catalog({'columns': []}, row, [])
        self.assertNotIn('not_null', out['columns'][0])
        self.assertNotIn('attnum', out['columns'][0])

    def test_guc_devel_unknown_preserves_prior_measurement_as_evidence_only(self):
        old = {'boot_val': '16384', 'setting': '16384', 'context': 'postmaster',
               'human': '128 MiB', 'unit': '8kB', 'carried_from': '19', 'carry_reason': '沿用19'}
        row = selected('guc', 'shared_buffers', '20', {'vartype': 'integer', 'metadata_version': ''})
        out = merge_guc(old, row, [])
        self.assertIsNone(out['boot_val'])
        self.assertEqual(out['human'], '')
        self.assertEqual(out['context'], '')
        self.assertEqual(out['carried_from'], '')
        self.assertEqual(out['center_previous_runtime']['fields']['boot_val'], '16384')
        self.assertEqual(out['center_previous_runtime']['version'], '19')
        self.assertEqual(old['boot_val'], '16384')

    def test_guc_19_beta_measurement_not_invalidated_by_document_selection(self):
        old = {'boot_val': '16384', 'setting': '8192', 'context': 'postmaster',
               'human': '128 MiB', 'unit': '8kB'}
        row = selected('guc', 'shared_buffers', '19', {'vartype': 'integer', 'metadata_version': '19beta4'})
        out = merge_guc(old, row, [])
        for field in old:
            self.assertEqual(out[field], old[field])
        self.assertNotEqual(out.get('facts_source'), 'documentation')

    def test_wait_type_identity_and_source_evidence_survive_translation(self):
        old = {'type': 'BufferPin', 'name': 'BufferPin', 'source': {'tag': 'REL_18_6'},
               'doc': {'file': 'monitoring-stats.html'}, 'description': 'Waiting'}
        row = selected('waitevent', 'buffer/BufferPin', '18', {'type': 'BufferPin', 'name': 'BufferPin', 'description': 'Waiting'})
        row['definition']['source_key'] = 'buffer/bufferpin'
        out = merge_wait(old, row, [])
        self.assertEqual(out['source'], old['source'])
        self.assertEqual(out['center_zh']['definition']['source_key'], 'buffer/bufferpin')

    def test_new_provenance_categories_do_not_break_native_coverage(self):
        report = catalog_importer.coverage({'relations': [{'summary_zh': '说明', 'versions': {
            '7.4': {'zh_from': 'authored-source-translation', 'columns': [
                {'zh_from': 'same-version-manual'}]}}}]})
        self.assertEqual(report['relations']['authored-source-translation'], 1)
        self.assertEqual(report['columns']['same-version-manual'], 1)

    def test_documented_guc_does_not_borrow_other_version_context(self):
        parameter = SimpleNamespace(vartype='integer', context='postmaster', category_zh='',
                                    group_slug='', category='', first_version='7.4', last_version='18',
                                    present_in=['7.4', '18'])
        facts = guc.facts_of(parameter, '7.4', {'facts_source': 'documentation', 'vartype': 'integer', 'human': ''},
                             [{'major': '7.4'}, {'major': '18'}], None)
        self.assertNotIn('上下文', [f['label'] for f in facts])
        self.assertNotIn('默认值', [f['label'] for f in facts])
        self.assertNotIn('20', guc.documented_notice('7.4'))

    def test_link_rewrite_requires_existing_same_edition_coordinate(self):
        row = selected('catalog', 'pg_test', '7.4', {})
        row['text']['body_html'] = '<a href="/zh/docs/7.4/catalogs.htm#lower">ok</a><a href="/zh/docs/7.4/absent.htm">missing</a>'
        snap = merge_catalog({'columns': []}, row, [])
        receipts = []
        local_links(snap, '7.4', {'7.4': {'catalogs.html': {'LOWER'}}}, receipts, 'catalog', 'pg_test')
        self.assertEqual(snap['center_zh']['link_map']['/zh/docs/7.4/catalogs.htm#lower'], '/docs/7.4/catalogs.html#LOWER')
        self.assertEqual(snap['center_zh']['link_map']['/zh/docs/7.4/absent.htm'], '/docs/7.4/absent.htm')
        self.assertEqual(receipts[0]['rule'], 'unresolved-manual-link')
