from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from . import compare_store as store
from .models import CompareDataset, CompareEntry, ComparePatch, CompareRelease


def change(identity, prose=None, *, groups=None, part='changes', category='bugfix', source_hash=None):
    prose = prose or identity
    return {'id': identity, 'source_entry_id': '18.1/{}/001'.format(part),
            'title': prose, 'html': '<p><code>' + prose + '</code></p>', 'text': prose,
            'identity_text': prose, 'source_hash': source_hash or store.digest(prose),
            'category': category, 'commit_groups': groups or [], 'cves': [],
            'unknown': {'nested': [1, False, None, {'说明': '完整保留'}]}}


def release(version, *entries, released='2026-08-13'):
    major, minor, _ = store.version_parts(version)
    return {'version': version, 'major': major, 'minor': minor, 'status': 'stable',
            'date': released, 'build': version, 'entries': list(entries), 'entry_count': len(entries),
            'migration_html': '<p>完整迁移说明</p>', 'unknown_release': ['nested', {'field': True}]}


def snapshot(*releases):
    return {'format': 1, 'language': 'zh', 'generated_at': '2026-09-26T00:00:00Z',
            'release_count': len(releases), 'entry_count': sum(len(r['entries']) for r in releases),
            'releases': list(releases), 'unknown_manifest': {'retain': [1, 2, 3]}}


class CompareStorageTests(TestCase):
    def setUp(self):
        store._load_revision.cache_clear()
        self.addCleanup(store._load_revision.cache_clear)

    def test_legacy_sort_coordinates_preserve_nine_minor_branches(self):
        self.assertEqual(store.version_parts('9.0.23'), ('9.0', 23, 90023))
        self.assertEqual(store.version_parts('9.6.24'), ('9.6', 24, 90624))
        self.assertEqual(store.version_parts('10.1'), ('10', 1, 100001))
        for value in ('9.6', '9.6.24.1', '18.1.2', '18beta1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                store.version_parts(value)

    def test_complete_original_json_and_unknown_fields_roundtrip(self):
        source = snapshot(release('9.0.0', change('a')), release('9.0.1', change('b')), release('18.1', change('c')))
        original = deepcopy(source)
        counts = store.import_snapshot(source)
        self.assertEqual(source, original)
        self.assertEqual(counts['entries'], 3)
        self.assertEqual(store.export_database_snapshot(), original)
        self.assertEqual(CompareRelease.objects.get(pk='9.0.1').sort_num, 90001)
        self.assertEqual(CompareEntry.objects.count(), 3)

    def test_identical_import_does_not_rewrite_rows_or_revision(self):
        source = snapshot(release('18.1', change('a', groups=[['aaaaaaa11', 'bbbbbbb22']])))
        store.import_snapshot(source)
        before = store.export_database_archive()
        counts = store.import_snapshot(source)
        self.assertEqual(store.export_database_archive(), before)
        self.assertFalse(counts.get('dataset_updated'))
        self.assertEqual(counts['entry_unchanged'], 1)

    def test_same_branch_duplicate_occurrences_are_separate_rows(self):
        one, two = change('first', 'same prose', groups=[['aaaaaaa11']]), change('second', 'same prose', groups=[['aaaaaaa11']])
        source = snapshot(release('18.1', one, two), release('18.2', change('third', 'same prose', groups=[['aaaaaaa11']])))
        store.import_snapshot(source)
        rows = list(CompareEntry.objects.all())
        self.assertEqual(len({row.id for row in rows}), 3)
        self.assertTrue(all(relation['type'] == 'related' for row in rows for relation in row.relations))
        self.assertEqual(store.export_database_snapshot(), source)

    def test_preview_insertion_keeps_existing_database_ids(self):
        source = snapshot(release('19.0', change('old-a'), change('old-b')))
        source['releases'][0]['status'] = 'preview'
        store.import_snapshot(source)
        before = {row.payloads['zh']['id']: row.id for row in CompareEntry.objects.all()}
        inserted = deepcopy(source)
        inserted['releases'][0]['entries'].insert(0, change('inserted'))
        for position, entry in enumerate(inserted['releases'][0]['entries']):
            entry['source_entry_id'] = '19.0/changes/{:03d}'.format(position + 1)
        inserted['releases'][0]['entry_count'] += 1
        inserted['entry_count'] += 1
        store.import_snapshot(inserted)
        after = {row.payloads['zh']['id']: row.id for row in CompareEntry.objects.all()}
        self.assertEqual({key: after[key] for key in before}, before)

    def test_text_revision_keeps_display_identity_and_full_previous_original(self):
        source = snapshot(release('18.1', change('anchor', 'original body')))
        store.import_snapshot(source)
        row = CompareEntry.objects.get()
        updated = snapshot(release('18.1', change('anchor', 'corrected body')))
        store.import_snapshot(updated)
        row.refresh_from_db()
        self.assertEqual(CompareEntry.objects.count(), 1)
        self.assertEqual(row.payloads['zh'], updated['releases'][0]['entries'][0])
        self.assertEqual(row.revisions[0]['payload'], source['releases'][0]['entries'][0])
        self.assertEqual(store.export_database_snapshot(), updated)

    def test_language_payloads_are_independent_and_have_shared_source_identity(self):
        source = snapshot(release('18.1', change('zh-anchor', 'Canonical English identity')))
        source['releases'][0]['entries'][0].update(title='中文标题', html='<p>中文正文</p>', text='中文正文')
        store.import_snapshot(source, language='zh')
        english = deepcopy(source)
        english['language'] = 'en'
        english['releases'][0]['entries'][0].update(id='en-anchor', title='English title', html='<p>English text</p>', text='English text')
        store.import_snapshot(english, language='en')
        self.assertEqual(CompareEntry.objects.count(), 1)
        self.assertEqual(store.export_database_snapshot(language='zh'), source)
        self.assertEqual(store.export_database_snapshot(language='en'), english)
        self.assertEqual(set(CompareEntry.objects.get().active_languages), {'zh', 'en'})

    def test_missing_entries_retained_unless_complete_prune_retires_them(self):
        source = snapshot(release('18.1', change('a'), change('b')))
        store.import_snapshot(source)
        missing = snapshot(release('18.1', change('a')))
        store.import_snapshot(missing)
        self.assertEqual(len(store.export_database_snapshot()['releases'][0]['entries']), 2)
        with self.assertRaises(ValueError):
            store.import_snapshot(missing, prune=True)
        store.import_snapshot(missing, complete=True, prune=True)
        self.assertEqual(store.export_database_snapshot(), missing)
        retired = CompareEntry.objects.get(payloads__zh__id='b')
        self.assertEqual(retired.active_languages, [])
        self.assertEqual(retired.payloads['zh']['html'], '<p><code>b</code></p>')

    def test_same_statement_distinct_commit_groups_does_not_create_relations(self):
        source = snapshot(release('17.1', change('a', 'same', groups=[['aaaaaaa11']])),
                          release('18.1', change('b', 'same', groups=[['bbbbbbb22']])))
        store.import_snapshot(source)
        self.assertTrue(all(row.relations == [] for row in CompareEntry.objects.all()))

    def test_full_multicommit_match_equivalent_but_partial_overlap_only_related(self):
        source = snapshot(release('16.1', change('a', groups=[['aaaaaaa11'], ['bbbbbbb22']])),
                          release('17.1', change('b', groups=[['aaaaaaa11'], ['bbbbbbb22']])),
                          release('18.1', change('c', groups=[['aaaaaaa11']])))
        store.import_snapshot(source)
        rows = {row.payloads['zh']['id']: row for row in CompareEntry.objects.all()}
        types = {r['target']: r['type'] for r in rows['a'].relations}
        self.assertEqual(types[rows['b'].id], 'equivalent')
        self.assertEqual(types[rows['c'].id], 'related')
        self.assertEqual(len(rows['a'].patch_ids), 2)
        self.assertEqual(CompareEntry.objects.filter(patch_ids__overlap=rows['c'].patch_ids).count(), 3)

    def test_major_feature_partial_backport_is_related_until_full_prose_matches(self):
        source = snapshot(release('17.5', change('fix', 'Fix Snowball crash', groups=[['aaaaaaa11', 'bbbbbbb22']])),
                          release('18.0', change('feature', 'Add Estonian stemming', groups=[['aaaaaaa11', 'bbbbbbb22']])))
        store.import_snapshot(source)
        self.assertTrue(all(row.relations[0]['type'] == 'related' for row in CompareEntry.objects.all()))

    def test_missing_commit_same_day_full_prose_can_be_equivalent(self):
        source = snapshot(release('17.1', change('a', 'Same entire statement')),
                          release('18.1', change('b', 'Same entire statement')))
        store.import_snapshot(source)
        self.assertTrue(all(row.relations[0]['type'] == 'equivalent' for row in CompareEntry.objects.all()))

    def test_patch_alias_growth_preserves_existing_identity(self):
        source = snapshot(release('18.1', change('a', groups=[['bbbbbbb22']])))
        store.import_snapshot(source)
        identity = ComparePatch.objects.get().id
        source['releases'][0]['entries'][0]['commit_groups'] = [['aaaaaaa11', 'bbbbbbb22']]
        store.import_snapshot(source)
        row = ComparePatch.objects.get(pk=identity)
        self.assertEqual(row.commits, ['aaaaaaa11', 'bbbbbbb22'])
        self.assertEqual(CompareEntry.objects.get().patch_ids, [identity])
        self.assertTrue(row.revisions)

    def test_wrong_old_commit_union_can_be_split_by_corrected_complete_source(self):
        source = snapshot(release('17.1', change('a', groups=[['aaaaaaa11', 'bbbbbbb22']])),
                          release('18.1', change('b', groups=[['aaaaaaa11', 'bbbbbbb22']])))
        store.import_snapshot(source)
        old_id = ComparePatch.objects.get().id
        source['releases'][0]['entries'][0]['commit_groups'] = [['aaaaaaa11']]
        source['releases'][1]['entries'][0]['commit_groups'] = [['bbbbbbb22']]
        store.import_snapshot(source, complete=True, prune=True)
        rows = list(CompareEntry.objects.order_by('release_id'))
        self.assertNotEqual(rows[0].patch_ids, rows[1].patch_ids)
        self.assertEqual(rows[0].relations, [])
        self.assertEqual(rows[1].relations, [])
        self.assertIn(old_id, rows[0].patch_ids)
        self.assertTrue(ComparePatch.objects.get(pk=old_id).revisions)

    def test_comment_only_correction_supersedes_other_language_old_commit_edges(self):
        source = snapshot(release('17.1', change('zh-a', groups=[['aaaaaaa11', 'bbbbbbb22']])),
                          release('18.1', change('zh-b', groups=[['aaaaaaa11', 'bbbbbbb22']])))
        store.import_snapshot(source, language='zh')
        english = deepcopy(source)
        english['language'] = 'en'
        for item in english['releases']:
            item['entries'][0]['id'] = item['entries'][0]['id'].replace('zh-', 'en-')
        store.import_snapshot(english, language='en')
        identities = set(CompareEntry.objects.values_list('id', flat=True))
        for index, item in enumerate(source['releases']):
            entry = item['entries'][0]
            entry['id'] += '-changed-by-comment-hash'
            entry['source_hash'] = store.digest('corrected comment ' + item['version'])
            entry['commit_groups'] = [['aaaaaaa11' if index == 0 else 'bbbbbbb22']]
        store.import_snapshot(source, language='zh', complete=True, prune=True)
        rows = list(CompareEntry.objects.order_by('release_id'))
        self.assertEqual(set(row.id for row in rows), identities)
        self.assertNotEqual(rows[0].patch_ids, rows[1].patch_ids)
        self.assertTrue(all(not row.relations for row in rows))
        self.assertEqual(store.export_database_snapshot(language='en'), english)
        self.assertEqual(store.export_database_snapshot(language='zh'), source)

    def test_failed_readback_rolls_back_entities_and_manifest(self):
        source = snapshot(release('18.1', change('a', groups=[['aaaaaaa11']])))
        with patch.object(store, '_read_dataset', side_effect=store.ComparisonDataUnavailable('mismatch')):
            with self.assertRaises(store.ComparisonDataUnavailable):
                store.import_snapshot(source)
        self.assertEqual(sum(model.objects.count() for model in store.ARCHIVE_MODELS.values()), 0)

    def test_changed_shared_relations_bump_revision_even_with_same_raw_source(self):
        source = snapshot(release('17.1', change('a', groups=[['aaaaaaa11']])),
                          release('18.1', change('b', groups=[['bbbbbbb22']])))
        store.import_snapshot(source, language='zh')
        english = deepcopy(source)
        english['language'] = 'en'
        for item in english['releases']:
            item['entries'][0]['commit_groups'] = [['aaaaaaa11', 'bbbbbbb22']]
        store.import_snapshot(english, language='en')
        before = CompareDataset.objects.get(pk='releases:zh').revision
        store.import_snapshot(source, language='zh')
        after = CompareDataset.objects.get(pk='releases:zh').revision
        self.assertEqual(after, before + 1)
        self.assertEqual(store.export_database_snapshot(language='zh'), source)
        self.assertTrue(all(not row.relations for row in CompareEntry.objects.all()))

    def test_check_import_rolls_back_all_rows(self):
        counts = store.import_snapshot(snapshot(release('18.1', change('a'))), check=True)
        self.assertEqual(counts['entries'], 1)
        self.assertEqual(CompareDataset.objects.count(), 0)
        self.assertEqual(CompareEntry.objects.count(), 0)

    def test_database_loader_never_uses_file_fallback_and_detects_missing_rows(self):
        with self.assertRaises(store.ComparisonDataUnavailable):
            store.load_database_snapshot()
        store.import_snapshot(snapshot(release('18.1', change('a'))))
        CompareEntry.objects.all().delete()
        with self.assertRaises(store.ComparisonDataUnavailable):
            store.load_database_snapshot()

    def test_manifest_revision_cache_reloads_after_import(self):
        store.import_snapshot(snapshot(release('18.1', change('a'))))
        first = store.load_database_snapshot()
        with self.assertNumQueries(1):
            self.assertIs(store.load_database_snapshot(), first)
        store.import_snapshot(snapshot(release('18.1', change('a'), change('b'))))
        second = store.load_database_snapshot()
        self.assertIsNot(second, first)
        self.assertEqual(len(second['releases'][0]['entries']), 2)
        self.assertIn('db_id', second['releases'][0]['entries'][0])
        self.assertIn('relations', second['releases'][0]['entries'][0])
        self.assertEqual(len(store._snapshot_cache), 1)
        self.assertIs(store._snapshot_cache[('default', 'releases:zh')][1], second)

    def test_corrupt_stored_original_fails_content_hash_verification(self):
        store.import_snapshot(snapshot(release('18.1', change('a'))))
        row = CompareEntry.objects.get()
        row.payloads['zh']['unknown']['nested'].append('tampered')
        row.save(update_fields=['payloads'])
        with self.assertRaises(store.ComparisonDataUnavailable):
            store.load_database_snapshot()

    def test_security_matrix_roundtrips_unknown_cna_fields(self):
        data = {'format': 1, 'fetched_at': '2026-09-26', 'covered_majors': ['9.0', '18'],
                'cves': [{'id': 'CVE-2026-12345', 'fixed': {'18': '18.1'}, 'unknown': {'proof': [1, 2]}}]}
        store.import_snapshot(data, kind='security')
        self.assertEqual(store.export_database_snapshot('security'), data)
        self.assertEqual(store.load_database_snapshot('security'), data)

    def test_full_database_archive_restores_ids_revisions_and_inactive_originals(self):
        source = snapshot(release('17.1', change('old', groups=[['bbbbbbb22']])),
                          release('18.1', change('a', groups=[['aaaaaaa11']]), change('b')))
        store.import_snapshot(source)
        changed = snapshot(release('17.1', change('old', groups=[['aaaaaaa11', 'bbbbbbb22']])),
                           release('18.1', change('a', 'Changed full text', groups=[['aaaaaaa11', 'bbbbbbb22']])))
        store.import_snapshot(changed, complete=True, prune=True)
        self.assertTrue(ComparePatch.objects.filter(merged_into__isnull=False).exists())
        self.assertTrue(CompareEntry.objects.filter(relations__contains=[{'type': 'equivalent'}]).exists())
        archive = store.export_database_archive()
        restored_revision = CompareDataset.objects.get(pk='releases:zh').revision
        for model in (CompareEntry, ComparePatch, CompareRelease, CompareDataset):
            if model == ComparePatch:
                model.objects.update(merged_into=None)
            model.objects.all().delete()
        store.restore_database_archive(archive)
        self.assertEqual(store.export_database_archive(), archive)
        self.assertEqual(store.export_database_snapshot(), changed)
        self.assertEqual(CompareDataset.objects.get(pk='releases:zh').revision, restored_revision)
        self.assertEqual(CompareEntry.objects.count(), 3)
        self.assertTrue(CompareEntry.objects.get(payloads__zh__id='a').revisions)

    def test_import_export_commands_default_to_reviewable_dry_run(self):
        source = snapshot(release('18.1', change('a')))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'source.json'
            path.write_text(json.dumps(source))
            call_command('import_compare', str(path), stdout=StringIO())
            self.assertEqual(CompareDataset.objects.count(), 0)
            call_command('import_compare', str(path), '--write', stdout=StringIO())
            output = Path(temporary) / 'output.json'
            call_command('export_compare', str(output), stdout=StringIO())
            self.assertEqual(json.loads(output.read_text()), source)
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)
