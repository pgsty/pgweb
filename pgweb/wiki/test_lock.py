"""Shipped facts, versioned matrices, navigation and unified search."""

import json
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from pgweb.core.models import Version
from pgweb.search import indexer, service
from pgweb.search.models import SearchEntry
from pgweb.util.contexts import _source_url
from pgweb.wiki import lock, lock_importer
from pgweb.wiki.models import LockMode
from pgweb.wiki.test_sqlcmd_importer import version


class LockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        snapshot = json.loads((Path(__file__).resolve().parents[2] / 'data/wiki/locks.json').read_text())
        lock_importer.import_snapshot(snapshot)
        Version.objects.bulk_create([version(major if major < 20 else 0, major == 18,
                                             2 if major in (19, 20) else 0)
                                     for major in range(10, 21)])

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_all_versions_expand_row_locks_under_their_table_modes(self):
        for major in range(10, 21):
            with self.subTest(major=major):
                data = lock.index(str(major))
                self.assertEqual(len(data['table_modes']), 8)
                self.assertEqual(len(data['row_modes']), 4)
                grid = data['full_matrix']['rows']
                self.assertEqual(len(grid), 14)
                self.assertTrue(all(len(row['cells']) == 14 for row in grid))
                self.assertEqual([g['span'] for g in data['full_matrix']['groups']], [1, 5, 3, 1, 1, 1, 1, 1])
                children = [row['mode'] for row in grid if row['mode']['is_child']]
                self.assertEqual([m['table_slug'] for m in children], ['row-share'] * 4 + ['row-exclusive'] * 2)
                self.assertEqual(len(data['modes']), 12)  # profiles do not create lock types
                self.assertEqual(data['table_matrix']['rows'][0]['cells'][7]['state'], 'conflict')
                for row in range(14):
                    for column in range(14):
                        self.assertEqual(grid[row]['cells'][column]['state'], grid[column]['cells'][row]['state'])
                # Every original table-only cell remains the same after expansion.
                parent_indices = [i for i, row in enumerate(grid) if not row['mode']['is_child']]
                for i, row in enumerate(parent_indices):
                    for j, column in enumerate(parent_indices):
                        self.assertEqual(grid[row]['cells'][column]['state'],
                                         data['table_matrix']['rows'][i]['cells'][j]['state'])

    def test_combined_conflicts_distinguish_table_from_same_row_waits(self):
        grid = lock.index('18')['full_matrix']['rows']
        cells = {(row['mode']['slug'], cell['col_slug']): cell for row in grid for cell in row['cells']}
        cases = [
            ('row-share--for-update', 'exclusive', 'conflict'),
            ('row-share--for-update', 'share', 'compatible'),
            ('row-exclusive--for-no-key-update', 'share', 'conflict'),
            ('row-share--for-update', 'row-exclusive--for-no-key-update', 'row-conflict'),
            ('row-exclusive--for-update', 'row-exclusive--for-update', 'row-conflict'),
            ('row-share--for-key-share', 'row-exclusive--for-no-key-update', 'compatible'),
            ('row-share--for-share', 'row-exclusive--for-no-key-update', 'row-conflict'),
            ('row-exclusive', 'row-exclusive--for-update', 'compatible'),
            ('share-update-exclusive', 'row-share--for-update', 'compatible'),
        ]
        for requested, held, expected in cases:
            with self.subTest(requested=requested, held=held):
                self.assertEqual(cells[requested, held]['state'], expected)
        self.assertIn('不同的行', cells['row-share--for-update', 'exclusive']['label'])
        self.assertIn('同一行', cells['row-exclusive--for-update', 'row-exclusive--for-update']['label'])

    def test_version_defaults_status_and_rejecting_unknown(self):
        self.assertEqual(lock.index()['major'], '18')
        self.assertEqual(lock.index('19')['version']['status'], 'preview')
        self.assertEqual(lock.index('devel')['manual_base'], '/docs/devel/')
        self.assertIn('尚未正式发布', lock.index('20')['notice'])
        for major in ('9', '99', '<script>'):
            with self.subTest(major=major), self.assertRaises(LockMode.DoesNotExist):
                lock.index(major)

    def test_versioned_command_boundaries_and_reverse_links(self):
        self.assertFalse(lock.for_command('merge', '14'))
        self.assertTrue(lock.for_command('merge', '15'))
        self.assertFalse(lock.for_command('repack', '18'))
        self.assertTrue(lock.for_command('repack', '19'))
        self.assertFalse(any('CONCURRENTLY' in c['label'] for c in lock.index('11')['commands']
                             if c['slug'] == 'reindex'))
        self.assertTrue(any('CONCURRENTLY' in c['label'] for c in lock.index('12')['commands']
                            if c['slug'] == 'reindex'))
        for major in ('10', '18', '19', '20'):
            for command in lock.index(major)['commands']:
                self.assertEqual(command['url'], '/docs/sql/{}/?v={}'.format(command['slug'], major))
        for row in lock.for_command('select', '18'):
            self.assertTrue(row['url'].endswith('?v=18'))

    def test_command_selection_combines_all_associated_modes(self):
        data = lock.index('18')
        for choice in data['command_choices']:
            expected = {mode['slug'] for command in data['commands'] if command['choice_key'] == choice['key']
                        for mode in command['modes']}
            self.assertEqual({mode['slug'] for mode in choice['modes']}, expected)
        choices = {choice['label']: {m['slug'] for m in choice['modes']}
                   for choice in data['command_choices']}
        self.assertEqual(choices['UPDATE（不修改键值）'], {'row-exclusive', 'for-no-key-update'})
        self.assertEqual(choices['UPDATE（修改键值）'], {'row-exclusive', 'for-update'})
        self.assertEqual(choices['INSERT … ON CONFLICT DO UPDATE（键）'], {'row-exclusive', 'for-update'})

    def test_pages_render_full_matrices_and_selected_version_links(self):
        response = self.client.get('/docs/lock/?v=10')
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertEqual(len(soup.select('#lock-table-matrix [data-lock-cell]')), 64)
        self.assertEqual(len(soup.select('#lock-full-matrix [data-lock-cell]')), 196)
        self.assertEqual(soup.select_one('#lock-version option[selected]')['value'], '10')
        self.assertFalse(soup.select('#locks [style], #locks [onclick], script:not([src])'))
        for anchor in soup.select('#locks a[href^="/docs/sql/"]'):
            self.assertIn('?v=10', anchor['href'])
        self.assertEqual(_source_url('/docs/lock/'), '')
        self.assertEqual(reverse('wiki:lock'), '/docs/lock/')
        self.assertEqual(self.client.post('/docs/lock/').status_code, 405)
        self.assertEqual(self.client.get('/docs/lock/?v=99').status_code, 404)
        self.assertEqual(self.client.get('/docs/lock/unknown/').status_code, 404)

    def test_every_mode_detail_retains_version(self):
        for row in LockMode.objects.all():
            response = self.client.get(row.url + '?v=20')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, row.name)
            self.assertContains(response, '/docs/devel/')
            data = lock.detail(row.slug, '20')
            self.assertTrue(all('?v=' in item['url'] and row.slug in item['url'] for item in data['versions']))

    def test_search_index_and_preview_follow_selected_version(self):
        self.assertEqual(indexer.rebuild_locks(), {'locks': 12})
        indexer.rebuild_locks()
        self.assertEqual(SearchEntry.objects.filter(source='lock').count(), 12)
        with patch.object(service, 'catalog', return_value=(18, [{'version': 10}, {'version': 18}])):
            result = service.search('ACCESS EXCLUSIVE', scope='pg10', kind='lock')
        self.assertFalse(result['error'])
        self.assertTrue(result['results'])
        self.assertEqual(result['results'][0]['url'], '/docs/lock/access-exclusive/?v=10')
        entry = SearchEntry.objects.get(source='lock', name='ROW EXCLUSIVE')
        preview = service.preview(entry, '10')
        self.assertNotIn('MERGE', preview['html'])
        self.assertIn('?v=10', preview['url'])
        self.assertIn('MERGE', service.preview(entry, '18')['html'])
        self.assertEqual(service.preview(entry, '18.0')['version'], 18)

    def test_warm_page_reads_no_mode_rows_again(self):
        lock.index()
        with self.assertNumQueries(1):  # shared Version status; mode data is cached
            lock.index('10')


class LiveLockMatrixTests(TestCase):
    """Check individual and combined modes against two PostgreSQL sessions."""

    def test_shipped_matrix_matches_running_postgres(self):
        import psycopg2
        snapshot = json.loads((Path(__file__).resolve().parents[2] / 'data/wiki/locks.json').read_text())
        with connection.cursor() as cursor:
            cursor.execute('SHOW server_version_num')
            major = str(int(cursor.fetchone()[0]) // 10000)
            if major not in {v['major'] for v in snapshot['versions']}:
                self.skipTest('Running PostgreSQL version is outside the collected baseline')
        first = psycopg2.connect(**connection.get_connection_params())
        second = psycopg2.connect(**connection.get_connection_params())
        try:
            # Commit only this probe via its own session; the site has legacy
            # unmanaged FK tables which prevent TransactionTestCase's global flush.
            first.autocommit = True
            with first.cursor() as cursor:
                cursor.execute('CREATE TABLE test_lock_matrix_probe (id integer PRIMARY KEY)')
                cursor.execute('INSERT INTO test_lock_matrix_probe VALUES (1)')
            first.autocommit = False
            for scope in ('table', 'row'):
                modes = [mode for mode in snapshot['modes'] if mode['scope'] == scope]
                for held in modes:
                    for requested in modes:
                        with self.subTest(scope=scope, held=held['name'], requested=requested['name']):
                            with first.cursor() as a, second.cursor() as b:
                                # Mode names come from the validated, committed reference fixture.
                                command = ('LOCK TABLE test_lock_matrix_probe IN {} MODE' if scope == 'table'
                                           else 'SELECT id FROM test_lock_matrix_probe WHERE id=1 {}')
                                a.execute(command.format(held['name']))
                                b.execute("SET LOCAL lock_timeout='20ms'")
                                blocked = False
                                try:
                                    b.execute(command.format(requested['name']))
                                except psycopg2.errors.LockNotAvailable:
                                    blocked = True
                                self.assertEqual(blocked, held['slug'] in requested['versions'][major]['conflicts'])
                            second.rollback()
                            first.rollback()
        finally:
            second.close()
            first.rollback()
            first.autocommit = True
            with first.cursor() as cursor:
                cursor.execute('DROP TABLE IF EXISTS test_lock_matrix_probe')
            first.close()

    def test_expanded_matrix_same_and_different_rows(self):
        import psycopg2
        snapshot = json.loads((Path(__file__).resolve().parents[2] / 'data/wiki/locks.json').read_text())
        with connection.cursor() as cursor:
            cursor.execute('SHOW server_version_num')
            major = str(int(cursor.fetchone()[0]) // 10000)
        if major not in {v['major'] for v in snapshot['versions']}:
            self.skipTest('Running PostgreSQL version is outside the collected baseline')
        modes = [dict(mode, url='/docs/lock/' + mode['slug'] + '/',
                      conflicts=[{'slug': other} for other in mode['versions'][major]['conflicts']])
                 for mode in snapshot['modes']]
        matrix = lock.expanded_matrix(modes)
        names = {mode['slug']: mode['name'] for mode in modes}
        first = psycopg2.connect(**connection.get_connection_params())
        second = psycopg2.connect(**connection.get_connection_params())

        def acquire(cursor, profile, row_id):
            cursor.execute('LOCK TABLE test_lock_combination_probe IN {} MODE'.format(names[profile['table_slug']]))
            if profile['row_slug']:
                cursor.execute('SELECT id FROM test_lock_combination_probe WHERE id=%s ' + names[profile['row_slug']],
                               [row_id])

        try:
            first.autocommit = True
            with first.cursor() as cursor:
                cursor.execute('CREATE TABLE test_lock_combination_probe (id integer PRIMARY KEY)')
                cursor.execute('INSERT INTO test_lock_combination_probe VALUES (1), (2)')
            first.autocommit = False
            for same_row in (True, False):
                for requested in matrix['rows']:
                    for held, cell in zip(matrix['columns'], requested['cells']):
                        with self.subTest(same_row=same_row, held=held['slug'], requested=requested['mode']['slug']):
                            with first.cursor() as a, second.cursor() as b:
                                acquire(a, held, 1)
                                b.execute("SET LOCAL lock_timeout='20ms'")
                                blocked = False
                                try:
                                    acquire(b, requested['mode'], 1 if same_row else 2)
                                except psycopg2.errors.LockNotAvailable:
                                    blocked = True
                                self.assertEqual(blocked, cell['state'] == 'conflict' or
                                                 (same_row and cell['state'] == 'row-conflict'))
                            second.rollback()
                            first.rollback()
        finally:
            second.close()
            first.rollback()
            first.autocommit = True
            with first.cursor() as cursor:
                cursor.execute('DROP TABLE IF EXISTS test_lock_combination_probe')
            first.close()
