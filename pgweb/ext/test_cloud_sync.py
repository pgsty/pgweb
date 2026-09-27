from copy import deepcopy
import json

from django.db import connection
from django.test import SimpleTestCase, TestCase

from .cloud_sync import COLUMNS, FORMAT, import_snapshot, package_anchor, validate_snapshot
from .sync import import_snapshot as import_universe
from .tests import snapshot as universe_snapshot


def snapshot():
    return {'format': FORMAT, 'tables': {
        'cloud': [{'service': 'example', 'pg_major': 18, 'provider': 'Example', 'service_name': 'Example PG',
                   'engine_status': 'GA', 'data_status': 'COMPLETE', 'list_scope': 'PG_MAJOR',
                   'source_url': 'https://example.org/extensions', 'engine_url': 'https://example.org/versions',
                   'checked_at': '2026-08-24T00:00:00+00:00', 'note': None,
                   'provenance': {'capture': {'sha256': 'original-evidence', 'custom': [1, 2]}}}],
        'cloud_fact': [{'service': 'example', 'pg_major': 18, 'raw_name': 'pgvector', 'extension': 'vector',
                        'status': 'SUPPORTED', 'version': '0.8.0 / 0.7.4', 'note': 'Instance-specific',
                        'extra': {'custom': {'regions': ['eu']}}}],
    }}


class CloudSnapshotValidationTests(SimpleTestCase):
    def test_rejects_duplicate_canonical_and_raw_names(self):
        for raw in ('pgvector', 'vector'):
            value = snapshot()
            other = deepcopy(value['tables']['cloud_fact'][0])
            other['raw_name'] = raw
            value['tables']['cloud_fact'].append(other)
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                validate_snapshot(value)

    def test_rejects_missing_coverage_and_invalid_semantics(self):
        value = snapshot()
        value['tables']['cloud_fact'][0]['pg_major'] = 17
        with self.assertRaisesRegex(ValueError, 'coverage'):
            validate_snapshot(value)
        value = snapshot()
        value['tables']['cloud'][0]['engine_status'] = 'UNAVAILABLE'
        with self.assertRaisesRegex(ValueError, 'Complete evidence'):
            validate_snapshot(value)
        value = snapshot()
        value['tables']['cloud'][0]['checked_at'] = '2026-08-24'
        with self.assertRaisesRegex(ValueError, 'timezone'):
            validate_snapshot(value)

    def test_rejects_additional_tables_and_preserves_arbitrary_metadata(self):
        value = snapshot()
        validate_snapshot(value)
        value['tables']['extension'] = []
        with self.assertRaisesRegex(ValueError, 'only cloud'):
            validate_snapshot(value)

    def test_package_evidence_does_not_guess_child_or_missing_versions(self):
        baseline = [
            {'name': name, 'pkg': pkg, 'rpm_pkg': rpm, 'deb_pkg': None, 'pg_ver': ['18']}
            for name, pkg, rpm in (('vector', 'vector', 'vector_$v'), ('vector_child', 'vector', 'vector_$v'),
                                   ('contrib', 'contrib', 'postgresql$v-contrib'), ('blocked', 'blocked', 'blocked_$v'))
        ]
        baseline.append(dict(baseline[1], name='child_unknown_major', pg_ver=['17']))
        packages = [
            {'pg': 18, 'os': os, 'name': 'vector_18', 'pkg': 'vector', 'ext': 'vector', 'state': state,
             'hide': False, 'org': 'pgdg', 'version': version, 'count': 1}
            for os, state, version in (('el9.x86_64', 'AVAIL', '0.8.0'), ('u24.x86_64', 'AVAIL', '0.8.1'),
                                       ('el8.aarch64', 'MISS', None))
        ]
        packages.append(dict(packages[0], name='blocked_18', pkg='blocked', ext='blocked', state='N/A', version=None))
        coverage, facts = package_anchor(baseline, packages, {18}, '2026-09-26T00:00:00+00:00')
        facts = {row['extension']: row for row in facts}
        self.assertEqual(facts['vector']['version'], '0.8.0, 0.8.1')
        self.assertEqual(facts['vector']['extra']['platforms'], sorted(packages[:3], key=lambda row: row['os']))
        self.assertEqual(facts['vector_child']['status'], 'SUPPORTED')
        self.assertIsNone(facts['vector_child']['version'])
        self.assertEqual(facts['vector_child']['extra']['package_relation'], 'distribution')
        self.assertEqual(facts['child_unknown_major']['status'], 'OTHER')
        self.assertEqual(facts['child_unknown_major']['extra']['availability'], 'UNKNOWN')
        self.assertEqual(facts['child_unknown_major']['extra']['compatibility_boundary'], 'unverified_major')
        self.assertEqual(facts['contrib']['status'], 'OTHER')
        self.assertEqual(facts['contrib']['extra']['availability'], 'UNKNOWN')
        self.assertEqual(facts['blocked']['status'], 'UNSUPPORTED')
        self.assertEqual(coverage[0]['checked_at'], '2026-09-26T00:00:00+00:00')
        self.assertTrue(all(row['extra']['packaged'] for row in facts.values()))


class CloudSyncTests(TestCase):
    def setUp(self):
        import_universe(universe_snapshot())

    def rows(self, table):
        with connection.cursor() as cursor:
            cursor.execute('SELECT {} FROM pgext.{} ORDER BY service, pg_major'.format(', '.join(COLUMNS[table]), table))
            rows = [dict(zip(COLUMNS[table], row)) for row in cursor.fetchall()]
        for row in rows:
            for field in ('provenance', 'extra'):
                if isinstance(row.get(field), str):
                    row[field] = json.loads(row[field])
        return rows

    def test_dry_run_is_read_only_then_roundtrip_and_repeat_are_exact(self):
        value = snapshot()
        report = import_snapshot(value, dry_run=True)
        self.assertEqual(report['tables']['cloud']['created'], 1)
        self.assertEqual(self.rows('cloud'), [])
        import_snapshot(value)
        self.assertEqual(self.rows('cloud')[0]['provenance'], value['tables']['cloud'][0]['provenance'])
        self.assertEqual(self.rows('cloud_fact'), value['tables']['cloud_fact'])
        with connection.cursor() as cursor:
            cursor.execute('SELECT ctid FROM pgext.cloud_fact')
            before = cursor.fetchall()
        report = import_snapshot(value)
        self.assertEqual(report['tables']['cloud_fact']['unchanged'], 1)
        with connection.cursor() as cursor:
            cursor.execute('SELECT ctid FROM pgext.cloud_fact')
            self.assertEqual(before, cursor.fetchall())

    def test_updates_and_retains_target_only_evidence(self):
        value = snapshot()
        other = deepcopy(value['tables']['cloud_fact'][0])
        other.update(raw_name='undocumented module', extension=None, version=None)
        value['tables']['cloud_fact'].append(other)
        import_snapshot(value)
        value['tables']['cloud_fact'].pop()
        value['tables']['cloud_fact'][0]['version'] = '0.8.2'
        report = import_snapshot(value)
        self.assertEqual(report['tables']['cloud_fact']['retained'], 1)
        self.assertEqual(report['tables']['cloud_fact']['updated'], 1)
        self.assertEqual(len(self.rows('cloud_fact')), 2)

    def test_missing_universe_name_rolls_back_the_whole_import(self):
        value = snapshot()
        value['tables']['cloud_fact'][0]['extension'] = 'not-in-universe'
        for dry_run in (True, False):
            with self.assertRaisesRegex(ValueError, 'Sync Universe first'):
                import_snapshot(value, dry_run=dry_run)
            self.assertEqual(self.rows('cloud'), [])

    def test_raw_name_conflict_fails_preflight_without_partial_metadata_updates(self):
        value = snapshot()
        import_snapshot(value)
        value['tables']['cloud'][0]['note'] = 'changed'
        value['tables']['cloud_fact'][0]['raw_name'] = 'vector'
        for dry_run in (True, False):
            with self.assertRaisesRegex(ValueError, 'conflicts require review'):
                import_snapshot(value, dry_run=dry_run)
        self.assertIsNone(self.rows('cloud')[0]['note'])
