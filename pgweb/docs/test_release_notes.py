from decimal import Decimal
from unittest.mock import patch

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from .views import (
    _doc_meta_description,
    _official_release_target,
    _release_note_neighbors,
    _release_notes_description,
    release_notes,
    release_notes_list,
)


class ReleaseNotesGapTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/docs/release/')

    def test_unreleased_version_redirects_to_following_release(self):
        response = release_notes(self.request, '18.5')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/docs/release/18.6/')

    @patch('pgweb.docs.views.render_pgweb', return_value=HttpResponse())
    @patch('pgweb.docs.views.exec_to_dict')
    def test_archive_excludes_unreleased_version(self, exec_to_dict, render_pgweb):
        exec_to_dict.return_value = [
            {'major': Decimal('18'), 'minor': minor}
            for minor in range(6, -1, -1)
        ]

        release_notes_list(self.request)

        releases = render_pgweb.call_args.args[3]['releases']
        self.assertFalse(any(
            release['major'] == Decimal('18') and release['minor'] == 5
            for release in releases
        ))

    @patch('pgweb.docs.views.exec_to_dict')
    def test_missing_stable_release_redirects_to_exact_upstream_archive(self, exec_to_dict):
        exec_to_dict.side_effect = [
            [{'latestminor': 19, 'testing': 0}],
            [],
        ]

        response = release_notes(self.request, '15.19')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://www.postgresql.org/docs/release/15.19/')

    @patch('pgweb.docs.views.exec_to_dict')
    def test_missing_beta_release_is_not_redirected_to_a_guessed_page(self, exec_to_dict):
        exec_to_dict.side_effect = [
            [{'latestminor': 3, 'testing': 2}],
            [],
        ]

        response = release_notes(self.request, '19.1')

        self.assertEqual(response.status_code, 404)

    @patch('pgweb.docs.views.exec_to_dict')
    def test_release_navigator_for_beta_uses_loaded_files_only(self, exec_to_dict):
        exec_to_dict.side_effect = [
            [{'latestminor': 3, 'testing': 2}],
            [{'content': '<div class="navheader"></div><p>Beta release notes.</p>'}],
            [{'file': 'release-19.html'}, {'file': 'release-prior.html'}],
        ]
        with patch('pgweb.docs.views.render_pgweb', return_value=HttpResponse()) as render_page:
            release_notes(self.request, '19.0')

        self.assertEqual(render_page.call_args.args[3]['release_title'], 'PostgreSQL 19 发布说明（开发预览）')

        context = exec_to_dict.mock_calls
        self.assertEqual(len(context), 3)
        self.assertIn("file FROM docs", context[2].args[0])

    @patch('pgweb.docs.views.exec_to_dict')
    def test_unknown_branch_is_not_external_redirect(self, exec_to_dict):
        exec_to_dict.side_effect = [[], []]

        response = release_notes(self.request, '2.0.1')

        self.assertEqual(response.status_code, 404)

    def test_release_title_and_heading_include_full_version(self):
        rendered = render_to_string('docs/release_notes.html', {
            'major_version': Decimal('15'),
            'minor_version': Decimal('19'),
            'release_version': '15.19',
            'release_title': 'PostgreSQL 15.19 发布说明',
            'release_note': {'content': '<p>本次发布包含修复。</p>'},
            'available_minor_versions': [{'minor': Decimal('19')}],
            'previous_minor_release': None,
            'next_minor_release': None,
        })

        self.assertIn('<h1>PostgreSQL 15.19 发布说明', rendered)

    def test_release_target_uses_archive_route_for_legacy_versions(self):
        self.assertEqual(
            _official_release_target(Decimal('0'), 1),
            'https://www.postgresql.org/docs/release/0.01/',
        )

    @patch('pgweb.docs.views.exec_to_dict', side_effect=[[], []])
    def test_postgres95_release_is_not_blocked_by_devel_version_row(self, exec_to_dict):
        response = release_notes(self.request, '0.01')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://www.postgresql.org/docs/release/0.01/')

    @patch('pgweb.docs.views.exec_to_dict', side_effect=[[{'latestminor': 999, 'testing': 1}], []])
    def test_unknown_postgres95_release_is_not_allowed_by_tree_zero_row(self, exec_to_dict):
        response = release_notes(self.request, '0.999')

        self.assertEqual(response.status_code, 404)

    def test_empty_doc_description_uses_its_own_title(self):
        page = type('Page', (), {'content': '<div class="toc"><ul><li>索引</li></ul></div>', 'title': '法律声明'})()
        self.assertEqual(_doc_meta_description(page), '法律声明')

    def test_navigation_skips_unreleased_version(self):
        versions = [{'minor': minor} for minor in (6, 4, 3)]

        self.assertEqual(
            _release_note_neighbors(versions, Decimal('6')),
            (4, None),
        )
        self.assertEqual(
            _release_note_neighbors(versions, Decimal('4')),
            (3, 6),
        )


class ReleaseNotesDescriptionTests(SimpleTestCase):
    def test_patch_description_uses_date_and_changes_not_migration_intro(self):
        content = '''
        <div class="navheader"><p>导航</p></div>
        <div id="RELEASE-15-19">
          <p><strong>发布日期：.</strong> 2026-08-13</p>
          <p>本次发布包含来自 15.18 的多项修复。有关 15 主版本新特性的说明，请参见 <a class="xref" href="release-15.html">Section E.20</a>。</p>
          <div id="RELEASE-15-19-MIGRATION"><ul><li><p>迁移提示不应进入摘要。</p></li></ul></div>
          <div id="RELEASE-15-19-CHANGES">
            <ul>
              <li><p>修复逻辑解码输出插件（Jane Doe）<a class="ulink" href="https://postgr.es/c/abc">§</a></p><p>详细说明。</p></li>
              <li><p>修复 pgcrypto 的 PGP 加密（John Doe）</p></li>
              <li><p>第三项不应被选中。</p></li>
            </ul>
          </div>
        </div>
        '''

        description = _release_notes_description(
            content,
            'PostgreSQL 15.19 发布说明',
            '15.19',
        )

        self.assertIn('发布日期：2026-08-13', description)
        self.assertIn('修复逻辑解码输出插件', description)
        self.assertIn('修复 pgcrypto 的 PGP 加密', description)
        self.assertNotIn('迁移提示', description)
        self.assertNotIn('Section E.20', description)
        self.assertNotIn('第三项', description)
        self.assertLessEqual(len(description), 180)

    def test_major_description_uses_overview_highlights(self):
        content = '''
        <div class="navheader"><p>导航</p></div>
        <div id="RELEASE-18">
          <p><strong>发布日期：.</strong> 2025-09-25</p>
          <div id="RELEASE-18-HIGHLIGHTS">
            <p>PostgreSQL 18 包含许多新特性。</p>
            <ul>
              <li><p>异步 I/O 子系统。</p></li>
              <li><p>pg_upgrade 现在保留优化器统计信息。</p></li>
            </ul>
          </div>
          <div id="RELEASE-18-MIGRATION"><ul><li><p>迁移说明不应进入摘要。</p></li></ul></div>
          <div id="RELEASE-18-CHANGES"><ul><li><p>变更列表不应替代 Overview。</p></li></ul></div>
        </div>
        '''

        description = _release_notes_description(
            content,
            'PostgreSQL 18.0 发布说明',
            '18.0',
        )

        self.assertIn('发布日期：2025-09-25', description)
        self.assertIn('异步 I/O 子系统', description)
        self.assertIn('pg_upgrade 现在保留优化器统计信息', description)
        self.assertNotIn('迁移说明', description)
        self.assertNotIn('变更列表', description)

    def test_description_falls_back_to_real_body_text_without_target_section(self):
        content = '''
        <div class="navheader"><p>导航</p></div>
        <p><strong>发布日期：.</strong> 2024-05-16</p>
        <p>此版本修复了归档恢复过程中的一个实际问题。</p>
        '''

        description = _release_notes_description(
            content,
            'PostgreSQL 12.18 发布说明',
            '12.18',
        )

        self.assertIn('2024-05-16', description)
        self.assertIn('此版本修复了归档恢复过程中的一个实际问题', description)
