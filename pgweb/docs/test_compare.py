from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings

from . import compare as engine


def entry(key, title=None, *, category='bugfix', text=None, commits=(), aliases=(), groups=None, cves=()):
    title = title or key
    item = {'id': key, 'title': title, 'text': text or title, 'html': '<p>' + (text or title) + '</p>',
            'category': category, 'commits': list(commits), 'commit_aliases': list(aliases), 'cves': list(cves)}
    if groups is not None:
        item['commit_groups'] = groups
    return item


def release(version, released, *entries, status='stable', **extra):
    major, minor = version.split('.')
    result = {'version': version, 'major': major, 'minor': int(minor), 'date': released,
              'status': status, 'supported': True, 'entries': list(entries), 'migration_html': ''}
    result.update(extra)
    return result


def snapshot(*releases):
    return {'format': 1, 'generated_at': '2026-09-26T00:00:00+00:00', 'releases': list(releases)}


def registry(*cves, covered=('16', '17', '18')):
    return {'format': 1, 'covered_majors': list(covered), 'cves': list(cves)}


def advisory(identifier='CVE-2026-12345', **extra):
    result = {'id': identifier, 'title': 'An English advisory', 'fixed': {'17': '17.3', '18': '18.1'},
              'score': 8.8, 'url': 'https://www.postgresql.org/support/security/' + identifier + '/'}
    result.update(extra)
    return result


def ids(report):
    return [item['id'] for group in report['groups'] for item in group['entries']]


class VersionComparisonTests(SimpleTestCase):
    def test_version_and_select_version_normalization(self):
        versions = {'17.0': {}, '17.11': {}}
        for raw, expected in [('17', '17.0'), (' 017.011 ', '17.11'),
                              ('PostgreSQL 17.11 on aarch64-linux-gnu, compiled by GCC', '17.11')]:
            with self.subTest(raw=raw):
                self.assertEqual(engine.resolve_version(raw, versions), expected)
        for raw in ['', '9.6.24', '17.11.2', '18beta4', 'PostgreSQL 17.11beta1', '17; DROP TABLE docs', '99']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                engine.resolve_version(raw, versions)
        with self.assertRaises(ValueError):
            engine.resolve_version('20', {'20.0': {'placeholder': True}})

    def test_minor_interval_is_open_then_closed_and_keeps_all_published_entries(self):
        repeated = entry('before', '修复查询问题', commits=['aaaaaaa12'])
        data = snapshot(release('17.0', '2024-09-26', repeated),
                        release('17.1', '2024-11-01', entry('first', repeated['title'], commits=['aaaaaaa12']),
                                entry('second', repeated['title'], commits=['aaaaaaa12'])),
                        release('17.2', '2025-02-01', entry('followup', repeated['title'], commits=['aaaaaaa12'])),
                        release('17.3', '2025-05-01', entry('outside')))
        report = engine.build_report(data, registry(), '17.0', '17.2')
        self.assertCountEqual(ids(report), ['first', 'second', 'followup'])
        self.assertEqual(report['total'], 3)
        self.assertEqual(report['excluded_count'], 0)

    def test_identical_versions_have_no_change_or_migration_rows(self):
        data = snapshot(release('17.0', '2024-09-26', entry('feature'), migration_html='<p>Read first</p>'))
        report = engine.build_report(data, registry(), '17.0', '17.0')
        self.assertEqual(report['groups'], [])
        self.assertEqual(report['total'], 0)
        self.assertEqual(report['cve_count'], 0)

    def test_reversed_version_order_rejected_even_if_dates_are_later(self):
        data = snapshot(release('17.4', '2026-01-01'), release('18.0', '2025-09-25'))
        with self.assertRaisesMessage(ValueError, '目标版本须不早于起始版本'):
            engine.build_report(data, registry(), '18.0', '17.4')

    def test_older_branch_releases_after_next_major_initial_are_excluded(self):
        data = snapshot(release('16.0', '2023-09-14'), release('16.1', '2024-01-01', entry('early')),
                        release('17.0', '2024-09-26', entry('major17')),
                        release('16.2', '2024-11-01', entry('late16')),
                        release('17.1', '2025-01-01', entry('early17')),
                        release('17.2', '2025-11-01', entry('late17')),
                        release('18.0', '2025-09-25', entry('major18')))
        report = engine.build_report(data, registry(), '16.0', '18.0')
        self.assertCountEqual(ids(report), ['early', 'major17', 'early17', 'major18'])

    def test_target_release_date_also_bounds_older_branch_inheritance(self):
        data = snapshot(release('17.0', '2024-09-26'), release('17.4', '2026-01-01', entry('futurefix')),
                        release('18.0', '2025-09-25', entry('major18')))
        report = engine.build_report(data, registry(), '17.4', '18.0')
        self.assertEqual(ids(report), ['major18'])
        self.assertTrue(any('发布日期早于' in warning for warning in report['warnings']))

    def test_source_backport_alias_excludes_known_target_change(self):
        data = snapshot(release('17.0', '2024-09-26'),
                        release('17.1', '2025-02-01', entry('source', '旧分支修复', commits=['aaaaaaa12'])),
                        release('18.0', '2025-09-25', entry('target', '新分支不同译文', commits=['bbbbbbb12'],
                                aliases=['aaaaaaa12', 'bbbbbbb12'])))
        report = engine.build_report(data, registry(), '17.1', '18.0')
        self.assertEqual(ids(report), [])
        self.assertEqual(report['excluded_count'], 1)

    def test_entry_with_one_known_and_one_new_commit_keeps_new_work(self):
        data = snapshot(release('17.0', '2024-09-26'),
                        release('17.1', '2025-02-01', entry('source', commits=['aaaaaaa12'])),
                        release('18.0', '2025-09-25', entry('two-fixes', commits=['bbbbbbb12', 'ccccccc12'],
                                groups=[['aaaaaaa12', 'bbbbbbb12'], ['ccccccc12', 'ddddddd12']]),
                                entry('new-fix-alone', commits=['ccccccc12'])))
        report = engine.build_report(data, registry(), '17.1', '18.0')
        self.assertCountEqual(ids(report), ['two-fixes', 'new-fix-alone'])

    def test_multicommit_source_covers_each_backport_without_merging_independent_groups(self):
        data = snapshot(release('17.0', '2024-09-26', entry('source', commits=['aaaaaaa12', 'ccccccc12'],
                                groups=[['aaaaaaa12', 'bbbbbbb12'], ['ccccccc12', 'ddddddd12']])),
                        release('18.0', '2025-09-25', entry('first', commits=['bbbbbbb12']),
                                entry('second', commits=['ddddddd12']), entry('new', commits=['eeeeeee12'])))
        report = engine.build_report(data, registry(), '17.0', '18.0')
        self.assertEqual(ids(report), ['new'])

    def test_commit_groups_from_sgml_work_when_old_html_has_no_commit_links(self):
        data = snapshot(release('17.0', '2024-09-26', entry('source', groups=[['aaaaaaa12', 'bbbbbbb12']])),
                        release('18.0', '2025-09-25', entry('target', commits=['bbbbbbb12'])))
        self.assertEqual(engine.build_report(data, registry(), '17.0', '18.0')['total'], 0)

    def test_matching_hash_prefixes_require_no_collision(self):
        for target_hash, expected in [('abcdef012', 0), ('abcdef099', 1)]:
            data = snapshot(release('17.0', '2024-09-26', entry('source', commits=['abcdef012'])),
                            release('18.0', '2025-09-25', entry('target', commits=[target_hash])))
            self.assertEqual(engine.build_report(data, registry(), '17.0', '18.0')['total'], expected)
        data = snapshot(release('17.0', '2024-09-26', entry('source', commits=['abcdef012'])),
                        release('18.0', '2025-09-25', entry('target', commits=['abcdef01234567890'])))
        self.assertEqual(engine.build_report(data, registry(), '17.0', '18.0')['total'], 0)

    def test_sql_operators_and_parenthetical_qualifiers_are_not_fuzzy_deduplicated(self):
        data = snapshot(release('17.0', '2025-09-25', entry('old', '优化 x < y（排序）')),
                        release('18.0', '2025-09-25', entry('new', '优化 x > y（过滤）')))
        self.assertEqual(ids(engine.build_report(data, registry(), '17.0', '18.0')), ['new'])

    def test_same_title_different_description_retained(self):
        data = snapshot(release('17.0', '2025-09-25', entry('old', '修复查询错误', text='修复查询错误。涉及外连接。')),
                        release('18.0', '2025-09-25', entry('new', '修复查询错误', text='修复查询错误。涉及子查询。')))
        self.assertEqual(ids(engine.build_report(data, registry(), '17.0', '18.0')), ['new'])

    def test_exact_same_day_crossbranch_backports_merge_with_provenance(self):
        data = snapshot(release('16.0', '2023-09-14'),
                        release('16.1', '2024-09-26', entry('oldbranch', '修复共同问题')),
                        release('17.0', '2024-09-26', entry('newbranch', '修复共同问题')))
        report = engine.build_report(data, registry(), '16.0', '17.0')
        self.assertEqual(ids(report), ['oldbranch'])
        self.assertEqual(report['groups'][0]['entries'][0]['also_in'], ['17.0'])

    def test_compatibility_record_does_not_disappear_behind_feature_using_same_commit(self):
        data = snapshot(release('17.0', '2024-09-26', entry('old', category='feature', commits=['aaaaaaa12'])),
                        release('18.0', '2025-09-25', entry('compat', category='compatibility', commits=['aaaaaaa12']),
                                entry('compat-second', category='compatibility', commits=['aaaaaaa12'])))
        self.assertCountEqual(ids(engine.build_report(data, registry(), '17.0', '18.0')), ['compat', 'compat-second'])


class VersionComparisonSecurityTests(SimpleTestCase):
    def test_cna_explicit_introduction_not_assumed_at_major_zero(self):
        cve = advisory(fixed={'17': '17.5'}, affected_ranges=[{'from': '17.3', 'until': '17.5'}])
        data = snapshot(release('17.2', '2025-01-01'), release('17.3', '2025-02-01'), release('17.5', '2025-05-01'))
        before = engine.build_report(data, registry(cve), '17.2', '17.5')
        self.assertEqual(before['cve_count'], 0)
        fixed = engine.build_report(data, registry(cve), '17.3', '17.5')
        self.assertEqual(fixed['cve_count'], 1)
        introduced = engine.build_report(data, registry(cve), '17.2', '17.3')
        self.assertEqual(len(introduced['security_regressions']), 1)
        self.assertEqual(len(introduced['remaining_cves']), 1)

    def test_cna_spanning_unsupported_branches_has_real_vulnerability_state(self):
        cve = advisory(fixed={'13': '13.22'}, affected_ranges=[{'from': '11.20', 'until': '13.22'}])
        self.assertEqual(engine._security_state(cve, release('11.19', '2023-01-01', supported=False)), 'unaffected')
        self.assertEqual(engine._security_state(cve, release('12.22', '2024-01-01', supported=False)), 'vulnerable')
        self.assertEqual(engine._security_state(cve, release('13.22', '2025-01-01', supported=False)), 'fixed')

    def test_regression_followup_mention_is_not_a_second_cve_fix(self):
        cve = advisory(fixed={'17': '17.3'})
        data = snapshot(release('17.3', '2025-02-01', entry('fix', '修复安全漏洞', cves=[cve['id']])),
                        release('17.4', '2025-02-20', entry('followup', '修复安全补丁引入的问题', cves=[cve['id']])))
        report = engine.build_report(data, registry(cve), '17.3', '17.4')
        self.assertEqual(report['cve_count'], 0)
        self.assertEqual(report['total'], 1)

    def test_newer_major_but_older_patch_level_warns_of_security_regression(self):
        cve = advisory(affected_ranges=[{'from': '17', 'until': '17.3'}, {'from': '18', 'until': '18.1'}])
        data = snapshot(release('17.3', '2025-11-01', entry('fix', '修复安全漏洞', cves=[cve['id']])),
                        release('18.0', '2025-09-25'), release('18.1', '2025-11-01'))
        report = engine.build_report(data, registry(cve), '17.3', '18.0')
        self.assertEqual(report['cve_count'], 0)
        self.assertEqual(report['security_regressions'][0]['id'], cve['id'])
        self.assertEqual(report['security_regressions'][0]['title'], '修复安全漏洞')
        self.assertEqual(report['security_regressions'][0]['fixed_version'], '18.1')
        self.assertEqual(report['remaining_cves'][0]['severity'], '高危')

    def test_preview_security_coverage_is_unknown_even_if_major_is_in_matrix(self):
        data = snapshot(release('18.0', '2025-09-25'),
                        release('19.0', '', entry('preview'), status='preview', build='19beta4', source_as_of='2026-09-24'))
        report = engine.build_report(data, registry(advisory(), covered=['18', '19']), '18.0', '19.0')
        self.assertIsNone(report['cve_count'])
        self.assertFalse(report['cve_available'])
        self.assertEqual(report['remaining_cves'], [])
        self.assertEqual(report['to_release']['label'], '19beta4')
        self.assertTrue(any('19beta4' in warning for warning in report['warnings']))

    def test_chinese_title_comes_from_original_fixed_release_not_later_mentions(self):
        cve = advisory(fixed={'18': '18.1'})
        data = snapshot(release('18.0', '2025-09-25'),
                        release('18.1', '2025-11-01', entry('fix', '原始安全修复', cves=[cve['id']])),
                        release('18.2', '2026-01-01', entry('followup', '后续回归修复', cves=[cve['id']])))
        report = engine.build_report(data, registry(cve), '18.0', '18.2')
        self.assertEqual(report['cves'][0]['title'], '原始安全修复')
        self.assertEqual(report['cve_count'], 1)


@override_settings(MIDDLEWARE=['pgweb.util.middleware.PgMiddleware'], DEBUG_TOOLBAR=False)
class ComparisonViewTests(SimpleTestCase):
    def setUp(self):
        self.data = snapshot(release('17.0', '2024-09-26'),
                             release('17.1', '2024-11-01', entry('fix', '修复测试问题')),
                             release('18.0', '2025-09-25', entry('major18')),
                             release('18.1', '2025-11-01', entry('patch18')),
                             release('19.0', '', entry('preview'), status='preview', build='19beta4'))
        self.loader = patch.object(engine, 'load_snapshot', side_effect=lambda name: self.data if name.startswith('releases') else registry())
        self.loader.start()
        self.addCleanup(self.loader.stop)

    def test_real_url_and_middleware_preserve_requested_pair_and_json_export(self):
        response = self.client.get('/docs/compare/', {'from': '17', 'to': '17.1', 'format': 'json', 'ignored': 'noise'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['from_release']['version'], '17.0')
        self.assertEqual(body['to_release']['version'], '17.1')
        self.assertEqual(body['total'], 1)
        self.assertIn('postgresql-17.0-to-17.1.json', response['Content-Disposition'])

    @patch.object(engine, 'render_pgweb', return_value=HttpResponse('Rendered'))
    def test_filters_preserved_in_share_url_and_context_with_stable_canonical(self, render):
        response = self.client.get('/docs/compare/', {'from': '17', 'to': '18', 'q': '索引 & VACUUM', 'kind': 'bugfix', 'junk': 'x'})
        self.assertEqual(response.status_code, 200)
        context = render.call_args.args[3]
        self.assertEqual(context['query'], '索引 & VACUUM')
        self.assertEqual(context['category'], 'bugfix')
        self.assertIn('kind=bugfix', context['share_url'])
        self.assertIn('q=', context['share_url'])
        self.assertEqual(context['seo']['canonical'], '/docs/compare/?from=17.0&to=18.0')
        self.assertEqual(context['seo']['title'], 'PostgreSQL 17.0 → 18.0 版本对比')
        self.assertEqual(context['og']['sitename'], 'PGSQL.CC')
        self.assertNotIn('junk', render.call_args.args[0].GET)
        self.assertIn('19beta4（尚未正式发布）', [option['label'] for group in context['release_groups'] for option in group['options']])

    @patch.object(engine, 'render_pgweb', return_value=HttpResponse('Rendered'))
    def test_invalid_category_falls_back_and_query_is_bounded(self, render):
        self.client.get('/docs/compare/', {'q': 'x' * 250, 'kind': 'not-a-category'})
        context = render.call_args.args[3]
        self.assertEqual(len(context['query']), 200)
        self.assertEqual(context['category'], 'all')
        self.assertNotIn('kind=', context['share_url'])

    def test_bad_inputs_return_json_400_and_missing_source_returns_503(self):
        for parameters in [{'from': 'bogus'}, {'from': '18.1', 'to': '17'}]:
            response = self.client.get('/docs/compare/', dict(parameters, format='json'))
            self.assertEqual(response.status_code, 400)
            self.assertTrue(response.json()['error'])
        with patch.object(engine, 'load_snapshot', side_effect=FileNotFoundError()):
            response = self.client.get('/docs/compare/?format=json')
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json()['error'])


class ComparisonSnapshotCacheTests(SimpleTestCase):
    def test_file_change_invalidates_json_and_compiled_identity_cache(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(engine, 'DATA_DIR', Path(temporary)):
            path = Path(temporary) / 'releases.json.gz'

            def write(data):
                with gzip.open(path, 'wt') as stream:
                    json.dump(data, stream)

            write(snapshot(release('17.0', '2024-09-26', entry('one'))))
            first = engine.load_snapshot('releases.json.gz')
            prepared = engine._release_index(first)
            self.assertIs(engine.load_snapshot('releases.json.gz'), first)
            self.assertIs(engine._release_index(first), prepared)
            write(snapshot(release('17.0', '2024-09-26', entry('one'), entry('two'))))
            stat = path.stat()
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
            updated = engine.load_snapshot('releases.json.gz')
            self.assertIsNot(updated, first)
            self.assertIsNot(engine._release_index(updated), prepared)
            self.assertEqual(len(engine._release_index(updated).identities), 2)
