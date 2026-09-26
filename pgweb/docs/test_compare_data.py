from io import StringIO
import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from .compare_data import branch_key, calibrate_source_entries, classify, commit_aliases, enrich_source_commits, normalize_sgml, parse_release, release_filename, release_parts, safe_html, sgml_commit_entries
from .management.commands.build_compare import build_snapshot, write_snapshot


MAJOR_HTML = '''
<div class="navheader">导航 <a href="release-18-1.html">下一页</a></div>
<div class="sect1" id="RELEASE-18">
<p><strong>发布日期：.&nbsp;</strong>2025-09-25</p>
<div class="sect2" id="RELEASE-18-HIGHLIGHTS"><h3>概述</h3>
<ul><li><p>高亮重复功能，不作为条目</p></li></ul></div>
<div class="sect2" id="RELEASE-18-MIGRATION"><div class="titlepage"><h3>迁移到版本 18</h3></div>
<p>使用 <a href="pgupgrade.html">pg_upgrade</a> 迁移。</p>
<ul><li><p>更改默认行为（Tom Lane）<a href="https://postgr.es/c/012345678">§</a></p>
<p>请先检查设置。</p></li></ul></div>
<div class="sect2" id="RELEASE-18-CHANGES"><h3>E.6.3. 变更</h3>
<div class="sect3" id="RELEASE-18-SERVER"><h4>E.6.3.1. 服务器</h4>
<div class="sect4" id="RELEASE-18-OPTIMIZER"><h5>E.6.3.1.1. 优化器</h5>
<ul>
<li><p>新增 <code>foo()</code> 功能（Tom Lane）<a href="https://postgr.es/c/abcdef123">§</a></p>
<p>完整说明中的 <a href="functions-admin.html#FOO">相关函数</a>。</p></li>
<li><p>修复内存损坏（Jane Doe）</p><p>感谢报告此问题。（CVE-2025-12345）</p>
<ol><li><p>执行修复脚本。</p><pre>SELECT '&lt;safe&gt;';\nSELECT 2;</pre></li>
<li><p>然后重新启动。</p></li></ol></li>
<li><p>提高索引扫描性能（Jane Doe）</p><p>减少磁盘访问。</p></li>
</ul></div></div></div>
<div class="sect2" id="RELEASE-18-ACKNOWLEDGEMENTS"><h3>致谢</h3><ul><li>Somebody</li></ul></div>
</div><div class="navfooter">页脚</div>
'''


class ReleaseComparisonParserTests(SimpleTestCase):
    def test_complete_changes_and_incompatibilities_without_overview_duplicates(self):
        release = parse_release(MAJOR_HTML, '18.0', '18')
        self.assertEqual(release['date'], '2025-09-25')
        self.assertEqual(release['entry_count'], 4)
        self.assertEqual(release['changes_count'], 3)
        self.assertEqual(release['compatibility_count'], 1)
        self.assertEqual([entry['category'] for entry in release['entries']], [
            'compatibility', 'feature', 'security', 'performance',
        ])
        self.assertNotIn('高亮重复', json.dumps(release, ensure_ascii=False))
        self.assertNotIn('Somebody', json.dumps(release))
        self.assertIn('href="/docs/18/pgupgrade.html"', release['migration_html'])
        self.assertNotIn('更改默认行为', release['migration_html'])

    def test_full_body_nested_procedure_and_cves_survive(self):
        release = parse_release(MAJOR_HTML, '18.0', '18')
        security = release['entries'][2]
        self.assertEqual(security['cves'], ['CVE-2025-12345'])
        self.assertIn('<ol>', security['html'])
        self.assertIn("SELECT '&lt;safe&gt;';\nSELECT 2;", security['html'])
        self.assertIn('然后重新启动', security['text'])
        self.assertEqual(security['title'], '修复内存损坏')

    def test_source_links_use_manual_coordinates_and_native_anchors(self):
        release = parse_release(MAJOR_HTML, '18.0', '18')
        entry = release['entries'][1]
        self.assertEqual(entry['section'], '服务器 / 优化器')
        self.assertEqual(entry['commits'], ['abcdef123'])
        self.assertEqual(entry['source_url'], '/docs/release/18.0/#RELEASE-18-OPTIMIZER')
        self.assertIn('href="/docs/18/functions-admin.html#FOO"', entry['html'])
        self.assertIn('href="https://postgr.es/c/abcdef123"', entry['html'])
        self.assertNotIn('Tom Lane', entry['title'])
        self.assertIn('Tom Lane', entry['html'])

    def test_generated_legacy_section_ids_use_chinese_headings(self):
        legacy = MAJOR_HTML.replace('RELEASE-18-MIGRATION', 'id-1.11.6.28.4').replace('RELEASE-18-CHANGES', 'id-1.11.6.28.5')
        release = parse_release(legacy, '18.0', '18')
        self.assertEqual(len(release['entries']), 4)

    def test_entry_ids_ignore_section_numbers_and_added_sibling_entries(self):
        before = parse_release(MAJOR_HTML, '18.0', '18')
        changed = MAJOR_HTML.replace('E.6.3.', 'E.7.3.').replace(
            '<li><p>新增', '<li><p>另一个新功能</p></li><li><p>新增',
        )
        after = parse_release(changed, '18.0', '18')
        self.assertEqual(before['entries'][1]['id'], after['entries'][2]['id'])

    def test_preview_as_of_is_not_a_release_date(self):
        content = MAJOR_HTML.replace('2025-09-25', '2026-??-??，截至 2026-09-14')
        release = parse_release(content, '18.0', '18', 'preview', build='18beta4')
        self.assertEqual(release['date'], '')
        self.assertEqual(release['source_as_of'], '2026-09-14')
        self.assertEqual(release['build'], '18beta4')

    def test_development_placeholder_is_explicit(self):
        release = parse_release('<p>发布日期：2026-??-??</p><p>目前这只是一个占位条目。</p>', '20.0', 'devel', 'devel')
        self.assertEqual(release['entries'], [])
        self.assertTrue(release['placeholder'])
        self.assertEqual(release['date'], '')
        self.assertEqual(release['source_url'], '/docs/devel/release-20.html')
        self.assertIn('占位条目', release['summary_html'])

    def test_date_requires_valid_calendar_date(self):
        self.assertEqual(parse_release(MAJOR_HTML.replace('2025-09-25', '2025-02-30'), '18.0', '18')['date'], '')
        self.assertEqual(parse_release(MAJOR_HTML.replace('2025-09-25', '2025年9月25日'), '18.0', '18')['date'], '2025-09-25')

    def test_sanitization_keeps_code_and_rejects_active_content(self):
        result = safe_html('''<p style="color:red" onclick="bad()">Text<script>bad()</script>
        <a href="javascript:alert(1)">bad</a><a href="data:text/html,bad">bad</a>
        <a href="//example.org/info">external</a><a href="#GUC-X">manual anchor</a>
        <code onmouseover="bad()">&lt;tag&gt;</code><svg onload="bad()">bad</svg></p>''', '/docs/18/release-18.html')
        for unsafe in ['script', 'javascript:', 'data:', 'onclick', 'style=', 'onmouseover', '<svg']:
            self.assertNotIn(unsafe, result)
        self.assertIn('<code>&lt;tag&gt;</code>', result)
        self.assertIn('href="https://example.org/info"', result)
        self.assertIn('href="/docs/18/release-18.html#GUC-X"', result)

    def test_classification_is_conservative_and_security_precedes_bugfix(self):
        self.assertEqual(classify('修复授权错误', '变更', ['CVE-2026-12345'], 2), 'security')
        self.assertEqual(classify('修复索引性能回归', '一般性能', [], 2), 'bugfix')
        self.assertEqual(classify('更新时区数据文件', '变更', [], 2), 'improvement')
        self.assertEqual(classify('新增函数', '函数', [], 0), 'feature')

    def test_backport_equivalence_splits_independent_author_blocks(self):
        source = '''<!--
Author: Jane
Branch: master Release: REL_19_BR [aaaaaaa11] today
Branch: REL_18_STABLE [bbbbbbb22] today
Author: Jane
Branch: master [ccccccc33] today
Branch: REL_18_STABLE [ddddddd44] today
--><!--
Author: Jane
Branch: master [aaaaaaa11] today
Branch: REL_17_STABLE [eeeeeee55] today
-->'''
        aliases = commit_aliases([source])
        self.assertEqual(aliases['bbbbbbb22'], ['aaaaaaa11', 'bbbbbbb22', 'eeeeeee55'])
        self.assertEqual(aliases['ccccccc33'], ['ccccccc33', 'ddddddd44'])
        self.assertNotIn('ddddddd44', aliases['aaaaaaa11'])

    def test_legacy_comment_enrichment_requires_title_section_order_and_count(self):
        source = '''<sect1 id="release-11-1"><sect2><title>变更</title><itemizedlist>
<listitem><!--
Author: Jane
Branch: master [aaaaaaa11]
Branch: REL_11_STABLE [bbbbbbb22]
Author: John
Branch: master [ccccccc33]
Branch: REL_11_STABLE [ddddddd44]
--><para>修复<quote>错误</quote>（Jane Doe）</para></listitem>
<listitem><!--
2017-02-15 [eeeeeee55] Another fix.
--><para>另一个修复（John Doe）</para></listitem>
</itemizedlist></sect2></sect1>'''
        html = '''<div class="sect2" id="RELEASE-11-1-CHANGES"><h3>变更</h3><ul>
<li><p>修复“错误”（Jane Doe）</p></li><li><p>另一个修复（John Doe）</p></li></ul></div>'''
        release = parse_release(html, '11.1', '11')
        records = sgml_commit_entries(source, 11)
        counts = enrich_source_commits(release, records)
        self.assertEqual(counts['enriched'], 2)
        self.assertEqual(release['entries'][0]['commits'], [])
        self.assertEqual(release['entries'][0]['source_commits'], ['bbbbbbb22', 'ddddddd44'])
        self.assertEqual(release['entries'][1]['source_commits'], ['eeeeeee55'])

        changed_title = parse_release(html.replace('另一个修复', '不同的修复'), '11.1', '11')
        counts = enrich_source_commits(changed_title, records)
        self.assertEqual(counts['title_mismatch'], 1)
        self.assertNotIn('source_commits', changed_title['entries'][1])

        wrong_count = parse_release(html.replace('<li><p>另一个修复（John Doe）</p></li>', ''), '11.1', '11')
        counts = enrich_source_commits(wrong_count, records)
        self.assertEqual(counts['section_count_mismatch'], 1)
        self.assertNotIn('source_commits', wrong_count['entries'][0])

    def test_one_author_can_have_several_independent_backport_sequences(self):
        source = '''<!--
Author: Tom
Branch: master [aaaaaaa11]
Branch: REL_18_STABLE Release: REL_18_0 [bbbbbbb22]
Branch: master [ccccccc33]
Branch: REL_18_STABLE [ddddddd44]
-->'''
        aliases = commit_aliases([source])
        self.assertEqual(aliases['aaaaaaa11'], ['aaaaaaa11', 'bbbbbbb22'])
        self.assertEqual(aliases['ccccccc33'], ['ccccccc33', 'ddddddd44'])

    def test_legacy_empty_xrefs_do_not_swallow_following_prose_or_commits(self):
        source = '''<sect1 id="release-10"><sect2><title>Changes</title><itemizedlist>
<listitem><!--
2017-01-01 [aaaaaaa11] First change.
--><para>Add <xref linkend="guc-something"> with a safe default.</para>
<para>Keep the entire explanation after the reference.</para></listitem>
</itemizedlist></sect2></sect1>'''
        entry = sgml_commit_entries(source, 10)['10.0']['changes'][0]
        self.assertIn('with a safe default.', entry['title'])
        self.assertIn('guc-something', entry['identity_text'])
        self.assertIn('entire explanation', entry['identity_text'])
        self.assertEqual(entry['commits'], ['aaaaaaa11'])

    def test_nine_branch_coordinates_and_filenames_are_not_decimal_patch_numbers(self):
        self.assertEqual(release_parts('9.6.0'), ('9.6', 0))
        self.assertEqual(release_parts('9.0.23'), ('9.0', 23))
        self.assertEqual(release_filename('9.6.0'), 'release-9-6.html')
        self.assertEqual(release_filename('9.6.24'), 'release-9-6-24.html')
        self.assertEqual(release_filename('10.0'), 'release-10.html')
        self.assertEqual(sorted(['10', '9.6', '9.0', '19'], key=branch_key), ['9.0', '9.6', '10', '19'])
        for invalid in ['9.6', '9.7.0', '8.4.22', '10.0.1']:
            with self.assertRaises(ValueError):
                release_parts(invalid)

    def test_nine_release_date_can_be_a_note_heading_before_the_date_paragraph(self):
        html = '''<div id="RELEASE-9-0"><div class="note"><h3>发行日期</h3><p>2010-09-20</p></div>
<div class="sect2"><h3>变更</h3><ul><li><p>添加流复制。</p></li></ul></div></div>'''
        release = parse_release(html, '9.0.0', '9.0')
        self.assertEqual(release['date'], '2010-09-20')
        self.assertEqual(release['major'], '9.0')
        self.assertEqual(release['manual_url'], '/docs/9.0/release-9-0.html')
        self.assertEqual(release['entries'][0]['category'], 'feature')

    def test_shorttag_closes_only_the_current_inline_element(self):
        source = '''<sect1 id="release-9-6-1"><sect2><title>Changes</title><itemizedlist><listitem>
<!--
Author: Jane
Branch: master [aaaaaaa11]
Branch: REL9_6_STABLE [bbbbbbb22]
--><para>Fix <function>example()</> when <literal>strict</> is disabled.</para>
<para>See <xref linkend="functions-admin"> for more information.</para>
</listitem></itemizedlist></sect2></sect1>'''
        normalized = normalize_sgml(source)
        self.assertIn('<function>example()</function>', normalized)
        self.assertIn('<literal>strict</literal> is disabled.', normalized)
        record = sgml_commit_entries(source, '9.6')['9.6.1']['changes'][0]
        self.assertEqual(record['commits'], ['bbbbbbb22'])
        self.assertIn('when strict is disabled.', record['title'])
        self.assertIn('functions-admin', record['identity_text'])

    def test_original_dsssl_classes_and_heading_anchors_select_the_release_container(self):
        html = '''<div class="NAVHEADER">Previous release</div><div class="SECT1">
<h1 class="SECT1"><a name="RELEASE-9-6-24" id="RELEASE-9-6-24">E.1. Release 9.6.24</a></h1>
<div class="FORMALPARA"><p><b>Release date:</b> 2021-11-11</p></div>
<div class="SECT2"><h2 class="SECT2"><a name="AEN131864" id="AEN131864">E.1.1. Migration to Version 9.6.24</a></h2>
<p>Update standby servers first.</p></div>
<div class="SECT2"><h2 class="SECT2"><a name="AEN131871" id="AEN131871">E.1.2. Changes</a></h2><ul><li>
<p>Make the server reject extraneous data after an SSL handshake.</p><p>CVE-2021-23214</p></li></ul></div>
</div><div class="NAVFOOTER">Next release</div>'''
        release = parse_release(html, '9.6.24', '9.6')
        self.assertEqual(release['date'], '2021-11-11')
        self.assertEqual(release['entry_count'], 1)
        self.assertEqual(release['entries'][0]['cves'], ['CVE-2021-23214'])
        self.assertEqual(release['entries'][0]['source_url'], '/docs/release/9.6.24/#AEN131871')
        self.assertEqual(release['entries'][0]['section'], 'Changes')
        self.assertEqual(release['entries'][0]['section_path'], ['Changes'])
        self.assertIn('Update standby servers first.', release['migration_html'])
        self.assertNotIn('Migration to Version', release['migration_html'])
        self.assertNotIn('Previous release', str(release))
        self.assertNotIn('Next release', str(release))
        self.assertNotIn('Previous release', safe_html(html, '/docs/9.6/release-9-6-24.html'))

    def test_preceding_major_comments_and_unlinked_independent_commits_are_preserved(self):
        source = '''<sect1 id="release-18"><sect2><title>Changes</title><itemizedlist>
<!--
Author: Jane
2025-01-01 [aaaaaaa11] One implementation.
2025-01-02 [bbbbbbb22] Another implementation.
-->
<listitem><para>Add functionality. <ulink url="&commit_baseurl;aaaaaaa11">&sect;</ulink></para></listitem>
<listitem><para>A separate functionality.</para></listitem>
</itemizedlist></sect2></sect1>'''
        entries = sgml_commit_entries(source, 18)['18.0']['changes']
        self.assertEqual(entries[0]['commits'], ['aaaaaaa11', 'bbbbbbb22'])
        self.assertEqual(entries[1]['commits'], [])
        self.assertEqual(entries[0]['source_entry_id'], '18.0/changes/001')

    def test_calibration_preserves_translation_and_uses_canonical_independent_groups(self):
        source = '''<sect1 id="release-18-1"><sect2><title>Changes</title><itemizedlist>
<listitem><!--
Author: Jane
Branch: master [aaaaaaa11]
Branch: REL_18_STABLE [bbbbbbb22]
Author: John
Branch: master [ccccccc33]
Branch: REL_18_STABLE [ddddddd44]
--><para>Fix a failure.</para></listitem></itemizedlist></sect2></sect1>'''
        html = '<div class="sect2" id="RELEASE-18-1-CHANGES"><h3>变更</h3><ul><li><p>避免操作失败。</p></li></ul></div>'
        release = parse_release(html, '18.1', '18')
        before = release['entries'][0]['html']
        stats = calibrate_source_entries(release, sgml_commit_entries(source, 18), commit_aliases([source]))
        entry = release['entries'][0]
        self.assertEqual(stats['entries'], 1)
        self.assertEqual(entry['html'], before)
        self.assertEqual(entry['category'], 'bugfix')
        self.assertEqual(entry['identity_text'], 'Fix a failure.')
        self.assertEqual(entry['commit_groups'], [['aaaaaaa11', 'bbbbbbb22'], ['ccccccc33', 'ddddddd44']])

    def test_calibration_refuses_missing_or_shifted_source_records(self):
        release = parse_release(MAJOR_HTML, '18.0', '18')
        with self.assertRaisesMessage(ValueError, 'Missing canonical release source'):
            calibrate_source_entries(release, {}, {})
        with self.assertRaisesMessage(ValueError, 'Canonical entry count mismatch'):
            calibrate_source_entries(release, {'18.0': {'migration': [], 'changes': []}}, {})


class ReleaseComparisonSnapshotTests(SimpleTestCase):
    @patch('pgweb.docs.management.commands.build_compare.DocPage')
    @patch('pgweb.docs.management.commands.build_compare.Version')
    def test_missing_published_patch_refuses_incomplete_snapshot(self, version_model, page_model):
        metadata = SimpleNamespace(tree=18, latestminor=1, testing=0, supported=True,
                                   versionstring='18.1', docsloaded=None, docsgit='')
        version_model.objects.filter.side_effect = [[metadata], Mock(first=Mock(return_value=None))]
        page_model.objects.filter.return_value.exclude.return_value.iterator.return_value = [
            SimpleNamespace(file='release-18.html', version_id=18, content=MAJOR_HTML),
        ]
        with self.assertRaisesMessage(CommandError, 'Missing Chinese release note: 18.1'):
            build_snapshot()

    def test_compressed_snapshot_roundtrips_and_is_deterministic(self):
        snapshot = {'format': 1, 'releases': [{'version': '18.0', 'text': '完整中文'}]}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'data/releases.json.gz'
            write_snapshot(snapshot, path)
            first = path.read_bytes()
            self.assertEqual(json.loads(gzip.decompress(first)), snapshot)
            write_snapshot(snapshot, path)
            self.assertEqual(path.read_bytes(), first)
            self.assertEqual(list(path.parent.iterdir()), [path])

    @patch('pgweb.docs.management.commands.build_compare.write_snapshot')
    @patch('pgweb.docs.management.commands.build_compare.build_snapshot', return_value={'release_count': 1, 'entry_count': 4})
    def test_check_validates_without_writing(self, build, write):
        stdout = StringIO()
        call_command('build_compare', '--check', stdout=stdout)
        build.assert_called_once()
        write.assert_not_called()
        self.assertIn('Validated 1 releases / 4 entries', stdout.getvalue())
