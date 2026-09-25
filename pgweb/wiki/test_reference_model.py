from copy import deepcopy
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from . import errcode, importer
from .documents import expand_presence, pack_legacy
from .models import ErrorCode
from .snapshot import content_hash
from .tests import snapshot


class DocumentContractTests(SimpleTestCase):
    def test_conversion_preserves_intervals_and_does_not_mutate_input(self):
        old = snapshot()
        code = old['codes'][0]
        code['facts']['presence_intervals'] = [{'start': '18.0', 'end': '18.6', 'extra': {'proof': 1}}]
        code['presence'] = [dict(era='modern', start='18.0', end='18.6', start_tag='a', end_tag='b',
                                 start_major='18', end_major='18', position=0, evidence_count=7)]
        before = deepcopy(old)
        result = importer.prepare(old)
        self.assertEqual(old, before)
        self.assertEqual(result['format'], 2)
        self.assertEqual(expand_presence(result['codes'][0]['facts']), code['presence'])
        self.assertEqual(result['codes'][0]['facts']['presence_intervals'][0]['extra'], {'proof': 1})
        self.assertEqual(importer.prepare(result), result)

    def test_conflicting_facts_fail_before_writing(self):
        old = snapshot()['codes'][0]
        old['facts']['presence_intervals'] = [{'start': '17.0'}]
        old['presence'] = [dict(era='modern', start='18.0', position=0)]
        with self.assertRaisesRegex(ValueError, '冲突'):
            pack_legacy(old)

    def test_hash_is_order_stable_but_array_order_matters(self):
        self.assertEqual(content_hash({'a': 1, 'b': [2, 3]}), content_hash({'b': [2, 3], 'a': 1}))
        self.assertNotEqual(content_hash({'a': [2, 3]}), content_hash({'a': [3, 2]}))
        self.assertEqual(content_hash({'a': 1, 'source_rev': 'x'}), content_hash({'a': 1, 'source_rev': 'y'}))

    def test_corrupt_hash_and_class_mismatch_fail(self):
        data = importer.prepare(snapshot())
        data['codes'][0]['texts']['zh']['summary'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'content_hash'):
            importer.prepare(data)
        data = snapshot()
        data['codes'][0]['class_code'] = '22'
        with self.assertRaisesRegex(ValueError, '类别'):
            importer.prepare(data)

    def test_import_never_reads_local_summary_overrides(self):
        with patch.object(importer, 'summary_overrides', side_effect=AssertionError('not self contained')):
            result = importer.prepare(snapshot())
        self.assertEqual(result['codes'][0]['summary_zh'], '一句话。')


class DocumentPageTests(TestCase):
    def setUp(self):
        cache.clear()
        importer.import_snapshot(snapshot())

    def test_metadata_only_changes_do_not_rewrite_entities(self):
        before = ErrorCode.objects.get(pk='23505').imported_at
        incoming = snapshot()
        incoming['generated_at'] = 'another day'
        for item in incoming['codes']:
            item['source_rev'] = 'different provenance'
        report = importer.import_snapshot(incoming)
        self.assertEqual(report['unchanged'], 3)
        self.assertEqual(report['updated'], 0)
        self.assertEqual(ErrorCode.objects.get(pk='23505').imported_at, before)
        incoming['codes'][0]['texts'][0]['summary'] = '新的摘要'
        report = importer.import_snapshot(incoming)
        self.assertEqual(report['updated'], 1)
        self.assertEqual(ErrorCode.objects.get(pk='23505').summary_zh, '新的摘要')

    def test_index_does_not_load_large_documents(self):
        with CaptureQueriesContext(connection) as queries:
            errcode.index_payload()
        for field in ('facts', 'texts', 'evidence'):
            self.assertNotIn('"sqlstate"."' + field + '"', '\n'.join(q['sql'] for q in queries))

    def test_detail_reads_documents_and_labels_real_boundaries(self):
        code = ErrorCode.objects.get(pk='23505')
        self.assertEqual(errcode.card(code)['since_label'], '最早已知存在')
        code.introduced = {'release': '9.0.4'}
        self.assertEqual(errcode.card(code)['since'], '9.0.4')
        self.assertEqual(errcode.card(code)['since_label'], '引入版本')
        code.status = 'removed'
        code.present_in = ['16']
        self.assertEqual(errcode.until_of(code, ['16', '17']), '')
        self.assertIn('边界未取证', errcode.card(code)['status_text'])
        with patch.object(errcode, 'doc_majors', return_value=['18', '0']), patch(
                'pgweb.docs.versions.manual_groups', return_value={
                    'supported': [18], 'historical': [], 'testing': [], 'devel': 20}):
            groups = errcode.version_groups(code)
        self.assertEqual(groups[-1]['items'][0]['state'], 'unknown')
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(code.url).status_code, 200)
        self.assertNotIn('wiki_errcode', '\n'.join(q['sql'] for q in queries))

    def test_polymorphic_refs_keep_all_targets_and_unresolved_ids(self):
        code = ErrorCode.objects.get(pk='23505')
        code.evidence['runtimes'] = [dict(runtime_id='s1', target='pg18', status='passed',
                                         server_version='18.6', cases=[], limits='only this run')]
        code.evidence['claims'][0]['sources'] += ['c1', 'manifest.missing']
        code.evidence['claims'][0]['runtime'] = ['s1']
        records = errcode.evidence_records(code)
        refs = records['claims'][0]['references']
        self.assertEqual({r.get('kind') for r in refs if r['id'] == 's1'}, {'sources', 'runtimes'})
        self.assertEqual([r['id'] for r in refs if r['unresolved']], ['manifest.missing'])
        code.save()
        html = self.client.get(code.url).content.decode()
        self.assertIn('manifest.missing（引用材料缺失）', html)
        self.assertIn('id="' + records['runtimes'][0]['anchor'] + '"', html)
        self.assertIn('href="#' + records['claims'][0]['anchor'] + '"', html)
