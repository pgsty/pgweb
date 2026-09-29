"""Versions keep branch identity, source boundaries, and original occurrences."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from pathlib import Path
from tempfile import TemporaryDirectory

from bs4 import BeautifulSoup
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings

from pgweb.core.models import Version
from pgweb.docs.compare_store import ComparisonDataUnavailable
from . import version_data as data, version_views as views


def version(tree='9.6', **kwargs):
    fields = dict(tree=Decimal(tree), latestminor=24, current=False, supported=False,
                  testing=0, firstreldate=date(2016, 9, 29), reldate=date(2021, 11, 11),
                  eoldate=date(2021, 11, 11), docsgit='', docsloaded=None)
    fields.update(kwargs)
    return Version(**fields)


def entry(key, title, category='feature', part='changes', cves=None):
    return {'id': key, 'source_entry_id': '9.6.0/{}/{}'.format(part, key),
            'title': title, 'text': title, 'html': '<p>' + title + '</p>',
            'category': category, 'cves': cves or []}


def release(ver='9.6.0', **kwargs):
    fields = dict(version=ver, major='9.6', minor=int(ver.rsplit('.', 1)[1]),
                  status='stable', build=ver, date='2016-09-29',
                  manual_url='/docs/9.6/release-9-6.html', placeholder=False,
                  entries=[entry('parallel', 'Parallel query support')], migration_html='')
    fields.update(kwargs)
    return fields


def catalog():
    releases = [release(), release('9.6.24', entries=[entry('fix', 'Fix a planner crash', 'bugfix')])]
    row = data.present_branch(version(), releases, 500, 'index.html')
    return {'rows': [row], 'by_branch': {'9.6': releases},
            'release_snapshot': {'releases': releases},
            'security_snapshot': {'cves': [], 'covered_majors': ['9.6']},
            'release_as_of': '2026-09-26', 'security_as_of': '2026-09-26'}


class VersionDataTests(SimpleTestCase):
    def test_historical_major_is_not_truncated_or_float_sorted(self):
        rows = [data.present_branch(version(tree), []) for tree in ('9.6', '9.0', '10')]
        rows.sort(key=lambda row: data.version_key(row['branch']))
        self.assertEqual([row['branch'] for row in rows], ['9.0', '9.6', '10'])
        self.assertEqual(rows[1]['url'], '/wiki/versions/9.6/')
        self.assertEqual(rows[1]['build'], '9.6.24')

    def test_preview_does_not_turn_first_beta_or_provisional_eol_into_lifecycle(self):
        row = data.present_branch(version('19', testing=2, latestminor=4), [])
        self.assertEqual((row['state'], row['build']), ('beta', '19beta4'))
        self.assertEqual((row['first_release'], row['end_of_life'], row['latest_release_date']), ('', '', ''))

    def test_devel_is_twenty_and_placeholder_is_not_selectable_release(self):
        row = data.present_branch(version('0', testing=2),
                                  [release('20.0', major='20', placeholder=True, status='devel')], 42, 'index.html')
        self.assertEqual((row['branch'], row['build'], row['manual_url']),
                         ('20', '20devel', '/docs/devel/index.html'))
        self.assertEqual(row['release_count'], 0)
        self.assertIsNone(row['latest'])
        self.assertEqual(row['first_release'], '')

    def test_recorded_date_before_initial_release_is_not_advertised(self):
        row = data.present_branch(version('6.3', reldate=date(1998, 2, 23),
                                          firstreldate=date(1998, 3, 1)), [])
        self.assertEqual(row['latest_release_date'], '')

    def test_release_history_preserves_gaps_and_numeric_order(self):
        releases = [release('18.0', major='18'), release('18.4', major='18'), release('18.6', major='18')]
        row = data.present_branch(version('18'), releases)
        self.assertEqual(row['release_count'], 3)
        self.assertEqual(row['latest']['version'], '18.6')
        self.assertIn('from=18.0&to=18.6', row['comparison_url'])

    def test_security_mention_never_infers_branch_fix(self):
        rows = data.branch_security('9.6', [release(entries=[entry('fix', 'CVE follow-up', 'security',
                                                                   cves=['CVE-2026-1001'])])],
                                    {'cves': [{'id': 'CVE-2026-1001', 'fixed': {'18': '18.6'}}]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['evidence'], 'release-note-mention')
        self.assertEqual(rows[0]['fixed'], '')
        self.assertEqual(rows[0]['fixed_url'], '')
        self.assertEqual(len(rows[0]['mentions']), 1)

    def test_security_branch_matrix_is_available_even_without_note_mentions(self):
        rows = data.branch_security('9.6', [release('9.6.24')],
                                    {'cves': [{'id': 'CVE-2021-1001', 'fixed': {'9.6': '9.6.24'}}]})
        self.assertEqual(rows[0]['fixed_url'], '/docs/compare/?release=9.6.24')
        self.assertEqual(rows[0]['evidence'], 'branch-matrix')
        self.assertEqual(rows[0]['mentions'], [])

    def test_migration_scope_remains_independent_of_security_category(self):
        note = release(entries=[entry('operation', 'Rebuild an index', 'security', 'migration')])
        self.assertEqual(data.release_summary(note)['compatibility_count'], 1)
        self.assertEqual(data.release_summary(note)['categories'], {'security': 1})

    def test_original_occurrences_and_snapshot_are_preserved(self):
        source = catalog()
        source['by_branch']['9.6'][0]['entries'] = [entry('one', 'Same title'), entry('two', 'Same title')]
        before = deepcopy(source)
        result = data.detail_payload(source, '9.6')
        self.assertEqual([e['id'] for e in result['initial_entries']], ['one', 'two'])
        self.assertEqual(source, before)

    def test_feature_filter_searches_minor_fixes_and_lifecycle_filter_is_independent(self):
        source = catalog()
        self.assertEqual(len(data.filter_branches(source, 'planner crash', 'eol')), 1)
        self.assertEqual(data.filter_branches(source, 'planner crash', 'supported'), [])
        self.assertEqual(data.detail_payload(source, '9.6', 'planner crash')['initial_entries'], [])

    def test_only_nonempty_local_pdf_editions_are_linked(self):
        with TemporaryDirectory() as root, override_settings(STATIC_CHECKOUT=root):
            directory = Path(root) / 'documentation/pdf/9.6'
            directory.mkdir(parents=True)
            (directory / 'postgresql-9.6-A4.pdf').write_bytes(b'%PDF-1.7')
            (directory / 'postgresql-9.6-US.pdf').write_bytes(b'')
            result = data.manual_resources({'branch': '9.6'})
        self.assertEqual(result, [{'label': 'A4 PDF', 'bytes': 8,
                                  'url': '/files/documentation/pdf/9.6/postgresql-9.6-A4.pdf'}])

    def test_security_prose_retains_explicit_language(self):
        releases = [release('9.6.24')]
        security = {'cves': [{'id': 'CVE-2021-1001', 'fixed': {'9.6': '9.6.24'},
                              'description_en': 'English original'}]}
        result = data.branch_security('9.6', releases, security)[0]
        self.assertEqual((result['description'], result['description_language']), ('English original', 'en'))
        security['cves'][0]['description_zh'] = '已核验中文'
        result = data.branch_security('9.6', releases, security)[0]
        self.assertEqual((result['description'], result['description_language']), ('已核验中文', 'zh'))


@override_settings(REFERENCE_LANGUAGE='zh')
class VersionReaderTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        for target, value in (('pgweb.util.contexts._get_doc_majors', [18, 17]),
                              ('pgweb.util.contexts._get_topbar_news', None)):
            mocked = patch(target, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)

    @patch.object(data, 'load_catalog', side_effect=ComparisonDataUnavailable('missing'))
    def test_missing_activated_data_returns_503_without_file_fallback(self, load):
        response = views.index(self.rf.get('/wiki/versions/?format=json'))
        self.assertEqual(response.status_code, 503)
        self.assertIn('暂不可用', json.loads(response.content)['error'])

    @patch.object(data, 'load_catalog', side_effect=AssertionError('must not load'))
    def test_invalid_filter_returns_400_before_data_access(self, load):
        self.assertEqual(views.index(self.rf.get('/wiki/versions/?format=json&state=unsafe')).status_code, 400)
        self.assertEqual(views.detail(self.rf.get('/wiki/versions/9.6/?format=json&kind=unsafe'), '9.6').status_code, 400)

    @patch.object(data, 'load_catalog', side_effect=catalog)
    @patch.object(data, 'manual_resources', return_value=[])
    def test_json_detail_retains_source_occurrences_and_major_identity(self, pdf, load):
        response = views.detail(self.rf.get('/wiki/versions/9.6/?format=json'), '9.6')
        result = json.loads(response.content)
        self.assertEqual(result['version']['branch'], '9.6')
        self.assertEqual(result['initial_entries'][0]['source_entry_id'], '9.6.0/changes/parallel')
        self.assertEqual([r['version'] for r in result['releases']], ['9.6.24', '9.6.0'])

    @patch.object(data, 'load_catalog', side_effect=catalog)
    def test_patch_coordinate_is_not_a_major_branch(self, load):
        with self.assertRaises(Http404):
            views.detail(self.rf.get('/wiki/versions/9.6.24/'), '9.6.24')
        with self.assertRaises(Http404):
            views.detail(self.rf.get('/wiki/versions/18.0/'), '18.0')

    def test_devel_alias_preserves_query_and_writes_are_rejected(self):
        response = views.detail(self.rf.get('/wiki/versions/devel/?format=json'), 'devel')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/wiki/versions/20/?format=json')
        self.assertEqual(views.index(self.rf.post('/wiki/versions/')).status_code, 405)

    @patch.object(data, 'load_catalog', side_effect=catalog)
    def test_index_export_preserves_search_and_lifecycle_filters(self, load):
        response = views.index(self.rf.get('/wiki/versions/', {'q': 'planner crash', 'state': 'eol'}))
        soup = BeautifulSoup(response.content, 'html.parser')
        href = soup.find('a', string='导出版本清单 JSON')['href']
        self.assertEqual(parse_qs(urlsplit(href).query),
                         {'q': ['planner crash'], 'state': ['eol'], 'format': ['json']})
        exported = json.loads(views.index(self.rf.get('/wiki/versions/' + href)).content)
        self.assertEqual((exported['query'], exported['selected_state'], exported['filtered']),
                         ('planner crash', 'eol', 1))

    @patch.object(data, 'load_catalog', side_effect=catalog)
    @patch.object(data, 'manual_resources', return_value=[])
    def test_branch_export_preserves_search_and_change_kind_filters(self, pdf, load):
        response = views.detail(self.rf.get('/wiki/versions/9.6/', {'q': 'planner crash', 'kind': 'bugfix'}), '9.6')
        soup = BeautifulSoup(response.content, 'html.parser')
        href = soup.find('a', string='导出此分支 JSON')['href']
        self.assertEqual(parse_qs(urlsplit(href).query),
                         {'q': ['planner crash'], 'kind': ['bugfix'], 'format': ['json']})
        exported = json.loads(views.detail(self.rf.get(href), '9.6').content)
        self.assertEqual((exported['version']['branch'], exported['query'], exported['selected_kind']),
                         ('9.6', 'planner crash', 'bugfix'))

    @patch.object(data, 'load_catalog', side_effect=catalog)
    @patch.object(data, 'manual_resources', return_value=[])
    def test_server_rendered_readers_have_complete_links_and_unique_ids(self, pdf, load):
        for response in (views.index(self.rf.get('/wiki/versions/')),
                         views.detail(self.rf.get('/wiki/versions/9.6/'), '9.6')):
            self.assertEqual(response.status_code, 200)
            soup = BeautifulSoup(response.content, 'html.parser')
            ids = [tag['id'] for tag in soup.select('[id]')]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertIsNotNone(soup.select_one('a[href="/wiki/versions/9.6/"]'))
            self.assertIn('9.6.24', soup.get_text())
