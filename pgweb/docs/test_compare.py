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
    major, minor = version.rsplit('.', 1)
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

    def test_pre_ten_major_and_patch_versions_are_distinct(self):
        versions = {'9.0.0': {}, '9.6.0': {}, '9.6.24': {}, '10.0': {}, '10.23': {}}
        for raw, expected in [('9.0', '9.0.0'), ('9.6', '9.6.0'), ('9.6.0', '9.6.0'),
                              ('009.06.024', '9.6.24'), ('10', '10.0'),
                              ('PostgreSQL 9.6.24 on x86_64-pc-linux-gnu, compiled by gcc', '9.6.24')]:
            with self.subTest(raw=raw):
                self.assertEqual(engine.resolve_version(raw, versions), expected)
        for raw in ['9', '9.7', '9.6.24.1', '10.0.0', '8.4.22', 'PostgreSQL 9.6.24beta1']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                engine.resolve_version(raw, versions)

    def test_pre_ten_initial_release_has_canonical_id_and_historical_display(self):
        initial = release('9.6.0', '2016-09-29', supported=False)
        summary = engine._release_summary(initial)
        self.assertEqual(summary['version'], '9.6.0')
        self.assertEqual(summary['label'], '9.6')
        self.assertEqual(engine._release_summary(release('9.6.24', '2021-11-11'))['label'], '9.6.24')
        self.assertEqual(engine._release_summary(release('10.0', '2017-10-05'))['label'], '10.0')

    def test_pre_ten_patch_interval_and_numeric_patch_order(self):
        data = snapshot(release('9.6.8', '2018-03-01', entry('before')),
                        release('9.6.9', '2018-05-10', entry('patch-nine')),
                        release('9.6.10', '2018-08-09', entry('patch-ten')))
        report = engine.build_report(data, registry(covered=['9.6']), '9.6.8', '9.6.10')
        self.assertEqual(ids(report), ['patch-ten', 'patch-nine'])
        self.assertFalse(report['cross_major'])
        self.assertEqual(report['excluded_count'], 0)

    def test_each_pre_ten_major_has_its_own_inheritance_cutoff(self):
        data = snapshot(release('9.0.0', '2010-09-20'),
                        release('9.0.1', '2010-10-04', entry('early90')),
                        release('9.0.5', '2011-09-26', entry('late90')),
                        release('9.1.0', '2011-09-12', entry('major91')),
                        release('9.1.1', '2011-09-26', entry('early91')),
                        release('9.1.6', '2012-09-24', entry('late91')),
                        release('9.2.0', '2012-09-10', entry('major92')))
        report = engine.build_report(data, registry(covered=['9.0', '9.1', '9.2']), '9.0.0', '9.2.0')
        self.assertEqual(ids(report), ['major92', 'early91', 'major91', 'early90'])
        self.assertTrue(report['cross_major'])
        self.assertEqual(report['history']['candidates'], ['9.0.1', '9.1.0', '9.1.1', '9.2.0'])

    def test_pre_ten_to_ten_uses_major_order_and_target_date(self):
        data = snapshot(release('9.6.0', '2016-09-29'),
                        release('9.6.5', '2017-08-31', entry('early')),
                        release('9.6.24', '2021-11-11', entry('late')),
                        release('10.0', '2017-10-05', entry('major10')))
        report = engine.build_report(data, registry(covered=['9.6', '10']), '9.6.24', '10.0')
        self.assertEqual(ids(report), ['major10'])
        self.assertTrue(report['cross_major'])
        self.assertTrue(any('发布日期早于' in warning for warning in report['warnings']))
        with self.assertRaises(ValueError):
            engine.build_report(data, registry(), '10.0', '9.6.24')

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
                        release('18.1', '2025-09-25', entry('target', '新分支不同译文', commits=['bbbbbbb12'],
                                aliases=['aaaaaaa12', 'bbbbbbb12'])))
        report = engine.build_report(data, registry(), '17.1', '18.1')
        self.assertEqual(ids(report), [])
        self.assertEqual(report['excluded_count'], 1)

    def test_entry_with_one_known_and_one_new_commit_keeps_new_work(self):
        data = snapshot(release('17.0', '2024-09-26'),
                        release('17.1', '2025-02-01', entry('source', commits=['aaaaaaa12'])),
                        release('18.1', '2025-09-25', entry('two-fixes', commits=['bbbbbbb12', 'ccccccc12'],
                                groups=[['aaaaaaa12', 'bbbbbbb12'], ['ccccccc12', 'ddddddd12']]),
                                entry('new-fix-alone', commits=['ccccccc12'])))
        report = engine.build_report(data, registry(), '17.1', '18.1')
        self.assertCountEqual(ids(report), ['two-fixes', 'new-fix-alone'])

    def test_multicommit_source_covers_each_backport_without_merging_independent_groups(self):
        data = snapshot(release('17.1', '2024-09-26', entry('source', commits=['aaaaaaa12', 'ccccccc12'],
                                groups=[['aaaaaaa12', 'bbbbbbb12'], ['ccccccc12', 'ddddddd12']])),
                        release('18.1', '2025-09-25', entry('first', commits=['bbbbbbb12']),
                                entry('second', commits=['ddddddd12']), entry('new', commits=['eeeeeee12'])))
        report = engine.build_report(data, registry(), '17.1', '18.1')
        self.assertEqual(ids(report), ['new'])

    def test_commit_groups_from_sgml_work_when_old_html_has_no_commit_links(self):
        data = snapshot(release('17.1', '2024-09-26', entry('source', groups=[['aaaaaaa12', 'bbbbbbb12']])),
                        release('18.1', '2025-09-25', entry('target', commits=['bbbbbbb12'])))
        self.assertEqual(engine.build_report(data, registry(), '17.1', '18.1')['total'], 0)

    def test_matching_hash_prefixes_require_no_collision(self):
        for target_hash, expected in [('abcdef012', 0), ('abcdef099', 1)]:
            data = snapshot(release('17.1', '2024-09-26', entry('source', commits=['abcdef012'])),
                            release('18.1', '2025-09-25', entry('target', commits=[target_hash])))
            self.assertEqual(engine.build_report(data, registry(), '17.1', '18.1')['total'], expected)
        data = snapshot(release('17.1', '2024-09-26', entry('source', commits=['abcdef012'])),
                        release('18.1', '2025-09-25', entry('target', commits=['abcdef01234567890'])))
        self.assertEqual(engine.build_report(data, registry(), '17.1', '18.1')['total'], 0)

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
        self.assertEqual(report['duplicate_count'], 1)
        self.assertEqual(report['already_in_source_count'], 0)
        self.assertEqual(report['groups'][0]['entries'][0]['variants'][0]['html'], '<p>修复共同问题</p>')

    def test_crossbranch_merge_retains_full_different_prose_and_commit_evidence(self):
        first = entry('oldbranch', '修复共同问题', text='旧分支：使用旧命令。', commits=['aaaaaaa12'])
        newer = entry('newbranch', '修复同一问题', text='新分支：必须先重建索引。', commits=['bbbbbbb12'],
                      groups=[['aaaaaaa12', 'bbbbbbb12']])
        data = snapshot(release('17.0', '2024-09-26'), release('17.1', '2025-02-01', first),
                        release('18.1', '2025-09-25', newer))
        report = engine.build_report(data, registry(), '17.0', '18.1')
        self.assertEqual(report['total'], 1)
        item = report['groups'][0]['entries'][0]
        self.assertEqual(item['html'], first['html'])
        self.assertEqual(item['variants'][0]['html'], newer['html'])
        self.assertEqual(item['variants'][0]['version'], '18.1')
        self.assertEqual(report['exclusions'][0]['method'], 'commits')
        self.assertEqual(report['candidate_count'], report['total'] + report['excluded_count'])

    def test_same_day_identical_prose_cannot_override_distinct_known_commits(self):
        data = snapshot(release('17.0', '2025-09-25', entry('source', '更新数据文件', commits=['aaaaaaa12'])),
                        release('18.0', '2025-09-25', entry('target', '更新数据文件', commits=['bbbbbbb12'])))
        self.assertEqual(ids(engine.build_report(data, registry(), '17.0', '18.0')), ['target'])
        data['releases'].insert(0, release('16.0', '2023-09-14'))
        self.assertCountEqual(ids(engine.build_report(data, registry(), '16.0', '18.0')), ['source', 'target'])

    def test_identical_upstream_prose_makes_fallback_independent_of_translation(self):
        old = entry('source', '旧译文')
        new = entry('target', '重新翻译')
        old['identity_text'] = new['identity_text'] = 'Fix the same bug.'
        data = snapshot(release('17.0', '2025-09-25', old), release('18.0', '2025-09-25', new))
        self.assertEqual(engine.build_report(data, registry(), '17.0', '18.0')['total'], 0)

    def test_multi_statement_commit_cannot_merge_distinct_followups(self):
        data = snapshot(release('16.0', '2023-09-14'),
                        release('16.1', '2024-01-01', entry('old', commits=['aaaaaaa12'])),
                        release('17.1', '2024-09-26', entry('new', commits=['aaaaaaa12']),
                                entry('second-section', commits=['aaaaaaa12'])))
        report = engine.build_report(data, registry(), '16.0', '17.1')
        self.assertCountEqual(ids(report), ['old', 'new', 'second-section'])
        self.assertEqual(report['duplicate_count'], 0)

    def test_shared_commit_with_two_fixes_matches_only_the_same_full_statement(self):
        data = snapshot(release('15.6', '2024-02-08', entry('old-shared', 'Report ownership changes', commits=['aaaaaaa12'])),
                        release('16.0', '2023-09-14'),
                        release('16.2', '2024-02-08',
                                entry('new-only', 'Fix ownership checks in the new version', commits=['aaaaaaa12']),
                                entry('new-shared', 'Report ownership changes', commits=['aaaaaaa12'])))
        report = engine.build_report(data, registry(), '15.6', '16.2')
        self.assertEqual(ids(report), ['new-only'])
        self.assertEqual([item['id'] for item in report['exclusions']], ['new-shared'])

    def test_security_category_does_not_hide_a_migration_statement(self):
        old = entry('ordinary', 'Fix security issue', commits=['aaaaaaa12'], category='security')
        new = entry('migration', 'Fix security issue', commits=['aaaaaaa12'], category='security')
        old['source_entry_id'] = '14.1/changes/001'
        new['source_entry_id'] = '15.1/migration/001'
        data = snapshot(release('14.1', '2022-02-08', old), release('15.1', '2023-02-08', new))
        self.assertEqual(ids(engine.build_report(data, registry(), '14.1', '15.1')), ['migration'])

    def test_mixed_known_and_reported_commits_adds_variant_without_double_counting(self):
        data = snapshot(release('16.1', '2023-09-14', entry('known', commits=['aaaaaaa12'])),
                        release('16.2', '2024-01-01', entry('new-fix', commits=['bbbbbbb12'])),
                        release('17.1', '2024-09-26', entry('both', commits=['aaaaaaa12', 'bbbbbbb12'])))
        report = engine.build_report(data, registry(), '16.1', '17.1')
        self.assertEqual(ids(report), ['new-fix'])
        self.assertEqual(report['groups'][0]['entries'][0]['variants'][0]['id'], 'both')

    def test_known_source_exclusions_preserve_note_and_exact_source_references(self):
        data = snapshot(release('17.1', '2024-09-26', entry('known', commits=['aaaaaaa12'])),
                        release('18.1', '2025-09-25', entry('backport', commits=['bbbbbbb12'],
                                groups=[['aaaaaaa12', 'bbbbbbb12']])))
        report = engine.build_report(data, registry(), '17.1', '18.1')
        self.assertEqual(report['total'], 0)
        self.assertEqual(report['already_in_source_count'], 1)
        excluded = report['exclusions'][0]
        self.assertEqual(excluded['entry']['html'], '<p>backport</p>')
        self.assertEqual(excluded['matches'][0]['id'], 'known')
        self.assertEqual(excluded['matches'][0]['version'], '17.1')
        self.assertEqual(report['history']['candidates'], ['18.1'])

    def test_compatibility_record_does_not_disappear_behind_feature_using_same_commit(self):
        data = snapshot(release('17.0', '2024-09-26', entry('old', category='feature', commits=['aaaaaaa12'])),
                        release('18.0', '2025-09-25', entry('compat', category='compatibility', commits=['aaaaaaa12']),
                                entry('compat-second', category='compatibility', commits=['aaaaaaa12'])))
        self.assertCountEqual(ids(engine.build_report(data, registry(), '17.0', '18.0')), ['compat', 'compat-second'])


class ComparisonNativeSourceRegressions(SimpleTestCase):
    """Real upstream Author blocks link related, not necessarily equal changes."""

    def test_bundled_ownership_commit_keeps_the_version_specific_fix(self):
        data = engine.load_snapshot('releases.json.gz')
        report = engine.build_report(data, registry(), '15.6', '16.2')
        kept = {item['source_entry_id'] for group in report['groups'] for item in group['entries']}
        excluded = {item['source_entry_id'] for item in report['exclusions']}
        self.assertIn('16.2/changes/033', kept)
        self.assertIn('16.2/changes/034', excluded)

    def test_partial_backports_do_not_hide_distinct_major_release_features(self):
        data = engine.load_snapshot('releases.json.gz')
        by_version = {r['version']: r for r in data['releases']}
        cases = (
            ('17.5', '18.0', '17.5/changes/033', '18.0/changes/105'),
            ('15.4', '16.0', '15.4/changes/022', '16.0/changes/067'),
            ('12.3', '13.0', '12.3/changes/021', '13.0/changes/094'),
        )
        for older, newer, old_id, new_id in cases:
            with self.subTest(older=older, newer=newer):
                old = next(x for x in by_version[older]['entries'] if x.get('source_entry_id') == old_id)
                new = next(x for x in by_version[newer]['entries'] if x.get('source_entry_id') == new_id)
                # The shared upstream commit is the regression trigger. The
                # assertions concern different release-note statements, not
                # merely a self-consistent hash calculated by the comparator.
                old_hashes = {h for group in old['commit_groups'] for h in group}
                new_hashes = {h for group in new['commit_groups'] for h in group}
                self.assertTrue(old_hashes & new_hashes)
                self.assertNotEqual(old.get('identity_text', old['text']), new.get('identity_text', new['text']))
                report = engine.build_report(data, registry(), older, newer)
                self.assertIn(new['id'], ids(report))

    def test_current_source_patch_already_includes_shared_output_plugin_cve_fix(self):
        data = engine.load_snapshot('releases.json.gz')
        report = engine.build_report(data, registry(), '17.11', '18.6')
        duplicate = next(x for x in report['exclusions']
                         if x['version'] == '18.6' and 'output_plugin_libraries' in x['title'])
        self.assertEqual(duplicate['reason'], 'already_in_source')
        self.assertEqual(duplicate['method'], 'commits')
        self.assertTrue(all(x['version'] == '17.11' for x in duplicate['matches']))
        self.assertIn('CVE-2026-6471', duplicate['entry']['cves'])
        self.assertNotIn(duplicate['id'], ids(report))
        buffercache = next(x for x in report['exclusions'] if x['source_entry_id'] == '18.1/changes/048')
        self.assertEqual(buffercache['reason'], 'already_in_source')
        self.assertTrue(any(x['source_entry_id'] == '17.7/changes/059' for x in buffercache['matches']))
        self.assertEqual(report['history']['candidates'], ['18.0', '18.1', '18.2', '18.3', '18.4', '18.6'])


class VersionComparisonSecurityTests(SimpleTestCase):
    def test_pre_ten_security_patch_comparison_uses_three_numeric_components(self):
        cve = advisory(fixed={'9.6': '9.6.9'})
        self.assertEqual(engine._security_state(cve, release('9.6.8', '2018-03-01', supported=False)), 'vulnerable')
        self.assertEqual(engine._security_state(cve, release('9.6.10', '2018-08-09', supported=False)), 'fixed')
        self.assertEqual(engine._security_state(cve, release('9.5.25', '2021-02-11', supported=False)), 'unknown')

    def test_historical_major_inherits_dated_prior_security_fix(self):
        cve = advisory('CVE-2010-3433', fixed={'9.0': '9.0.1'}, published={})
        data = snapshot(release('9.0.0', '2010-09-20', supported=False),
                        release('9.0.1', '2010-10-04', supported=False),
                        release('9.1.0', '2011-09-12', supported=False))
        report = engine.build_report(data, registry(cve, covered=['9.0', '9.1']), '9.0.0', '9.1.0')
        self.assertEqual(report['cve_count'], 1)
        evidence = report['cves'][0]['target_state_evidence']
        self.assertEqual(evidence['kind'], 'major_inherits_prior_security_fixes')
        self.assertEqual(evidence['fixed_version'], '9.0.1')
        self.assertEqual(evidence['fixed_date'], '2010-10-04')
        self.assertEqual(evidence['target_initial_version'], '9.1.0')
        self.assertEqual(evidence['target_initial_date'], '2011-09-12')
        self.assertEqual(evidence['policy_url'], 'https://www.postgresql.org/support/security/')

    def test_historical_omission_after_initial_release_is_not_inferred_safe(self):
        cve = advisory(fixed={'9.0': '9.0.20'}, published={'9.0': '2014-04-03'})
        data = {r['version']: r for r in [
            release('9.1.0', '2011-09-12', supported=False),
            release('9.1.24', '2016-10-27', supported=False),
        ]}
        self.assertEqual(engine._security_state(cve, data['9.1.0'], data), 'unknown')
        self.assertEqual(engine._security_state(cve, data['9.1.24'], data), 'unknown')
        later_cve = advisory(fixed={'18': '18.6'}, published={'18': '2026-08-13'})
        self.assertEqual(engine._security_state(later_cve, data['9.1.24'], data), 'unknown')

    def test_historical_evidence_does_not_depend_on_json_object_key_order(self):
        target = release('9.2.0', '2012-09-10', supported=False)
        dates = {'9.0': '2011-09-26', '9.1': '2011-09-26'}
        first = advisory(fixed={'9.0': '9.0.5', '9.1': '9.1.1'}, published=dates)
        second = advisory(fixed={'9.1': '9.1.1', '9.0': '9.0.5'}, published=dates)
        expected = engine._inherited_security_fix(first, target, {})
        self.assertEqual(engine._inherited_security_fix(second, target, {}), expected)
        self.assertEqual(expected['fixed_version'], '9.1.1')

    def test_historical_inheritance_needs_fix_date_and_respects_explicit_cna_ranges(self):
        target = release('9.1.0', '2011-09-12', supported=False)
        cve = advisory(fixed={'9.0': '9.0.1'})
        self.assertEqual(engine._security_state(cve, target), 'unknown')
        cve['published'] = {'9.0': '2010-10-04'}
        self.assertEqual(engine._security_state(cve, target), 'unaffected')
        cve['affected_ranges'] = [{'from': '9.0', 'until': '9.2'}]
        self.assertEqual(engine._security_state(cve, target), 'vulnerable')

    def test_old_patch_to_ten_initial_does_not_hide_security_regression(self):
        cve = advisory('CVE-2018-1058', fixed={'9.6': '9.6.8', '10': '10.3'})
        data = snapshot(release('9.6.24', '2021-11-11', supported=False),
                        release('10.0', '2017-10-05', supported=False))
        report = engine.build_report(data, registry(cve, covered=['9.6', '10']), '9.6.24', '10.0')
        self.assertEqual(report['cve_count'], 0)
        self.assertEqual(report['security_regressions'][0]['id'], 'CVE-2018-1058')
        self.assertEqual(report['security_regressions'][0]['fixed_version'], '10.3')

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
        self.loader = patch.object(engine, 'load_active_snapshot', side_effect=lambda name: self.data if name.startswith('releases') else registry())
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

    def test_single_release_includes_initial_release_and_persisted_relationships(self):
        initial = self.data['releases'][0]
        initial['entries'] = [dict(entry('initial', '初始功能', category='feature'), db_id='original',
                                   relations=[{'target': 'backport', 'type': 'related', 'evidence': {'patch_ids': ['p1']}}])]
        self.data['releases'][1]['entries'][0].update(db_id='backport')
        response = self.client.get('/docs/compare/', {'release': '17', 'format': 'json'})
        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report['mode'], 'release')
        self.assertIsNone(report['from_release'])
        self.assertEqual(report['total'], 1)
        shown = report['groups'][0]['entries'][0]
        self.assertEqual(shown['id'], 'initial')
        self.assertEqual(shown['related_changes'][0]['kind'], 'related')
        self.assertEqual(shown['related_changes'][0]['url'], '/docs/compare/?release=17.1#fix')
        self.assertIn('postgresql-17.0-changes.json', response['Content-Disposition'])

    @patch.object(engine, 'render_pgweb', return_value=HttpResponse('Rendered'))
    def test_single_release_has_own_canonical_and_filtered_share_url(self, render):
        response = self.client.get('/docs/compare/', {'release': '17.1', 'q': '修复', 'kind': 'bugfix'})
        self.assertEqual(response.status_code, 200)
        context = render.call_args.args[3]
        self.assertTrue(context['single_release'])
        self.assertEqual(context['canonical_url'], '/docs/compare/?release=17.1')
        self.assertIn('kind=bugfix', context['share_url'])
        self.assertEqual(context['seo']['title'], 'PostgreSQL 17.1 的版本变更')

    @patch.object(engine, 'render_pgweb', return_value=HttpResponse('Rendered'))
    def test_pre_ten_versions_appear_with_canonical_values_and_branch_labels(self, render):
        self.data['releases'].extend([release('9.0.0', '2010-09-20', supported=False),
                                      release('9.6.0', '2016-09-29', entry('major96'), supported=False)])
        response = self.client.get('/docs/compare/', {'from': '9.0', 'to': '9.6'})
        self.assertEqual(response.status_code, 200)
        context = render.call_args.args[3]
        self.assertEqual(context['from_version'], '9.0.0')
        self.assertEqual(context['to_version'], '9.6.0')
        self.assertIn('PostgreSQL 9.0 起', context['dataset_summary'])
        self.assertEqual(context['seo']['canonical'], '/docs/compare/?from=9.0.0&to=9.6.0')
        self.assertEqual(context['report']['from_release']['label'], '9.0')
        self.assertEqual(context['report']['to_release']['label'], '9.6')
        self.assertIn({'value': '9.6.0', 'label': '9.6（历史版本）'},
                      [option for group in context['release_groups'] for option in group['options']])

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
        with patch.object(engine, 'load_active_snapshot', side_effect=FileNotFoundError()):
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
