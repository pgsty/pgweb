"""Complete snapshot validation, provenance and transactional import coverage."""

from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.test import SimpleTestCase, TestCase

from pgweb.docs.versions import DEVEL_MAJOR_VERSION
from pgweb.wiki import lock_importer as importer
from pgweb.wiki.models import LockMode, SqlCommand


def fixture():
    """Explicit locking matrices, independent from the importer's validation."""
    table = [
        ('access-share', 'AS', [7]),
        ('row-share', 'RS', [6, 7]),
        ('row-exclusive', 'RX', [4, 5, 6, 7]),
        ('share-update-exclusive', 'SUE', [3, 4, 5, 6, 7]),
        ('share', 'S', [2, 3, 5, 6, 7]),
        ('share-row-exclusive', 'SRX', [2, 3, 4, 5, 6, 7]),
        ('exclusive', 'X', [1, 2, 3, 4, 5, 6, 7]),
        ('access-exclusive', 'AX', [0, 1, 2, 3, 4, 5, 6, 7]),
    ]
    row = [('for-key-share', 'FKS', [3]), ('for-share', 'FS', [2, 3]),
           ('for-no-key-update', 'FNKU', [1, 2, 3]), ('for-update', 'FU', [0, 1, 2, 3])]
    revision = 'a' * 40
    sources = [{'kind': 'documentation',
                'url': 'https://raw.githubusercontent.com/postgres/postgres/{}/doc/src/sgml/mvcc.sgml'.format(revision),
                'revision': revision, 'sha256': 'b' * 64},
               {'kind': 'source',
                'url': 'https://raw.githubusercontent.com/postgres/postgres/{}/src/backend/storage/lmgr/lock.c'.format(revision),
                'revision': revision, 'sha256': 'c' * 64}]
    versions = [{'major': str(major), 'label': str(major), 'revision': revision,
                 'status': 'devel' if major == DEVEL_MAJOR_VERSION else 'historical',
                 'doc_slug': 'devel' if major == DEVEL_MAJOR_VERSION else str(major),
                 'sources': deepcopy(sources), 'fetched_at': '2026-09-26T00:00:00Z'}
                for major in range(10, DEVEL_MAJOR_VERSION + 1)]
    modes = []
    for scope, group in [('table', table), ('row', row)]:
        for slug, abbrev, conflicts in group:
            modes.append({
                'slug': slug, 'name': slug.upper().replace('-', ' '), 'name_zh': slug + '锁',
                'abbrev': abbrev, 'scope': scope, 'position': len(modes), 'summary': '锁模式说明。',
                'versions': {version['major']: {
                    'conflicts': [group[index][0] for index in conflicts],
                    'commands': [{'slug': 'select', 'label': 'SELECT', 'note': '取得此模式。',
                                  'source_url': 'https://www.postgresql.org/docs/{}/explicit-locking.html'.format(version['doc_slug'])}],
                    'sources': deepcopy(sources),
                } for version in versions},
            })
    return {'format': 1, 'default_major': '18', 'versions': versions, 'modes': modes,
            'generated_at': '2026-09-26T00:00:00Z'}


class LockSnapshotTests(SimpleTestCase):
    def test_complete_versioned_snapshot_and_embedded_provenance(self):
        snapshot = fixture()
        self.assertTrue(importer.validate(snapshot))
        prepared = list(importer.prepared_modes(snapshot))
        self.assertEqual(len(prepared), 12)
        self.assertEqual(prepared[0]['versions']['10']['provenance'], snapshot['versions'][0])
        self.assertNotIn('provenance', snapshot['modes'][0]['versions']['10'])

    def test_incomplete_modes_and_versions_are_rejected(self):
        for mutation in ('mode', 'version', 'snapshot-version', 'duplicate-version'):
            with self.subTest(mutation=mutation):
                snapshot = fixture()
                if mutation == 'mode':
                    snapshot['modes'].pop()
                elif mutation == 'version':
                    snapshot['modes'][-1]['versions'].pop('10')
                elif mutation == 'snapshot-version':
                    snapshot['versions'].pop(0)
                else:
                    snapshot['versions'][-1] = deepcopy(snapshot['versions'][0])
                with self.assertRaises(ValueError):
                    importer.validate(snapshot)

    def test_matrix_requires_known_same_scope_symmetric_conflicts(self):
        cases = {
            'unknown': ['nonexistent'],
            'cross-scope': ['for-update'],
            'asymmetric': ['exclusive', 'access-exclusive'],
            'missing': [],
            'duplicate': ['access-exclusive', 'access-exclusive'],
        }
        for mutation, conflicts in cases.items():
            with self.subTest(mutation=mutation):
                snapshot = fixture()
                snapshot['modes'][0]['versions']['10']['conflicts'] = conflicts
                with self.assertRaises(ValueError):
                    importer.validate(snapshot)

    def test_command_links_require_safe_slugs_and_authoritative_sources(self):
        for field, value in [('slug', '../select'), ('source_url', 'javascript:alert(1)'),
                             ('source_url', 'https://example.com/locks'),
                             ('source_url', 'https://github.com/other/project/blob/main/lock.c')]:
            with self.subTest(field=field, value=value):
                snapshot = fixture()
                snapshot['modes'][0]['versions']['10']['commands'][0][field] = value
                with self.assertRaises(ValueError):
                    importer.validate(snapshot)

    def test_every_version_requires_pinned_source_evidence(self):
        for mutation in ('missing', 'unpinned', 'sha256', 'revision', 'no-code'):
            with self.subTest(mutation=mutation):
                snapshot = fixture()
                if mutation == 'missing':
                    snapshot['modes'][0]['versions']['10']['sources'] = []
                elif mutation == 'unpinned':
                    snapshot['versions'][0]['sources'][0]['url'] = 'https://raw.githubusercontent.com/postgres/postgres/master/doc/src/sgml/mvcc.sgml'
                elif mutation == 'sha256':
                    snapshot['versions'][0]['sources'][0]['sha256'] = 'bad'
                elif mutation == 'revision':
                    snapshot['versions'][0]['sources'][0]['revision'] = 'd' * 40
                else:
                    snapshot['versions'][0]['sources'].pop()
                with self.assertRaises(ValueError):
                    importer.validate(snapshot)

    def test_supplied_business_hash_must_match(self):
        snapshot = fixture()
        snapshot['modes'][0]['content_hash'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'content_hash'):
            list(importer.prepared_modes(snapshot))


class LockImportTests(TestCase):
    def setUp(self):
        self.snapshot = fixture()

    def test_preview_then_import_and_idempotence_preserve_timestamps(self):
        self.assertEqual(importer.preview(self.snapshot)['added'], 12)
        self.assertFalse(LockMode.objects.exists())
        with self.captureOnCommitCallbacks(execute=True), patch.object(importer, 'forget') as forget:
            report = importer.import_snapshot(self.snapshot)
        self.assertEqual(report['added'], 12)
        forget.assert_called_once()
        first = dict(LockMode.objects.values_list('slug', 'imported_at'))
        with self.captureOnCommitCallbacks(execute=True), patch.object(importer, 'forget') as forget:
            report = importer.import_snapshot(self.snapshot)
        self.assertEqual(report['unchanged'], 12)
        forget.assert_not_called()
        self.assertEqual(first, dict(LockMode.objects.values_list('slug', 'imported_at')))
        row = LockMode.objects.get(slug='access-share')
        self.assertEqual(row.versions['10']['provenance']['revision'], 'a' * 40)
        self.assertEqual(row.url, '/wiki/lock/access-share/')

    def test_provenance_changes_do_not_rewrite_business_content(self):
        self.snapshot['modes'][0]['versions']['10']['commands'][0]['source'] = deepcopy(
            self.snapshot['versions'][0]['sources'][0])
        importer.import_snapshot(self.snapshot)
        first = dict(LockMode.objects.values_list('slug', 'imported_at'))
        updated = json.loads(json.dumps(self.snapshot).replace('a' * 40, 'd' * 40)
                             .replace('b' * 64, 'e' * 64).replace('2026-09-26', '2026-09-27'))
        updated['modes'][0]['versions']['10']['commands'][0]['source_url'] += '#LOCKING-TABLES'
        self.assertEqual(importer.import_snapshot(updated)['unchanged'], 12)
        self.assertEqual(first, dict(LockMode.objects.values_list('slug', 'imported_at')))

    def test_business_change_updates_only_affected_mode(self):
        importer.import_snapshot(self.snapshot)
        first = dict(LockMode.objects.values_list('slug', 'imported_at'))
        self.snapshot['modes'][0]['versions']['10']['commands'][0]['note'] = '补充取得条件。'
        report = importer.import_snapshot(self.snapshot)
        self.assertEqual((report['updated'], report['unchanged']), (1, 11))
        self.assertNotEqual(LockMode.objects.get(slug='access-share').imported_at, first['access-share'])
        self.assertEqual(LockMode.objects.get(slug='row-share').imported_at, first['row-share'])

    def test_invalid_last_mode_prevents_every_write(self):
        importer.import_snapshot(self.snapshot)
        self.snapshot['modes'][0]['summary'] = '不应该写入。'
        self.snapshot['modes'][-1]['versions']['10']['sources'] = []
        with self.assertRaises(ValueError):
            importer.import_snapshot(self.snapshot)
        self.assertEqual(LockMode.objects.get(slug='access-share').summary, '锁模式说明。')
        self.assertEqual(LockMode.objects.count(), 12)

    def test_failure_midway_rolls_back_all_changes(self):
        original = LockMode.objects.update_or_create
        calls = []

        def failing(**kwargs):
            calls.append(kwargs['slug'])
            if len(calls) == 2:
                raise RuntimeError('模拟写入中断')
            return original(**kwargs)

        with patch.object(LockMode.objects, 'update_or_create', side_effect=failing):
            with self.assertRaises(RuntimeError):
                importer.import_snapshot(self.snapshot)
        self.assertEqual(len(calls), 2)
        self.assertFalse(LockMode.objects.exists())

    def test_management_check_and_invalid_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'locks.json'
            path.write_text(json.dumps(self.snapshot), encoding='utf-8')
            output = StringIO()
            call_command('wiki_import_locks', '--input', str(path), '--check', stdout=output)
            self.assertEqual(json.loads(output.getvalue())['added'], 12)
            self.assertFalse(LockMode.objects.exists())
            path.write_text('{}', encoding='utf-8')
            with self.assertRaises(CommandError):
                call_command('wiki_import_locks', '--input', str(path), stdout=StringIO())

    def test_sql_acceptance_checks_command_versions_and_index_urls(self):
        from pgweb.search.indexer import rebuild_locks

        importer.import_snapshot(self.snapshot)
        SqlCommand.objects.create(slug='select', name='SELECT',
                                  versions={v['major']: {} for v in self.snapshot['versions']})
        rebuild_locks()
        source = (Path(__file__).resolve().parents[2] / 'tools/wiki/check_data.sql').read_text()
        block = source.split('    -- Lock modes keep version metadata', 1)[1].split(
            '    -- These four domains embed source builds', 1)[0]
        sql = ('DO $check$ DECLARE total bigint; inconsistent bigint; missing text[]; '
               'expected_urls text[]; indexed_urls text[]; BEGIN\n'
               '    -- Lock modes keep version metadata' + block + 'END $check$;')
        with connection.cursor() as cursor:
            cursor.execute(sql)
        SqlCommand.objects.filter(slug='select').update(versions={})
        with self.assertRaisesRegex(DatabaseError, '命令引用'):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql)
