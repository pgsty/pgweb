"""用三版、五条命令的手工参考页检验采集、比较、校验与幂等写入。"""

from copy import deepcopy
from datetime import date
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.test import SimpleTestCase, TestCase

from pgweb.core.models import Version
from pgweb.docs.models import DocPage
from pgweb.wiki import sqlcmd, sqlcmd_importer as importer
from pgweb.wiki.models import (SECTION_KEYS, SQLCMD_GROUPS, SqlCommand,
                               sqlcmd_group_of, sqlcmd_slug, sqlcmd_split)
from pgweb.wiki.sqlcmd_common import compare, line_changes, sections_at


def version(tree, current=False, testing=0):
    return Version(tree=tree, current=current, testing=testing, latestminor=3,
                   supported=tree in (18, 19), reldate=date(2026, 8, 13),
                   firstreldate=date(2020, 1, 1), eoldate=date(2030, 1, 1))


def reference(name, synopsis='', description='说明正文。', extra='', purpose='示例用途'):
    return ('<div class="refentry" id="SQL-DEMO"><div class="refnamediv">'
            '<h2><span class="refentrytitle">' + name + '</span></h2><p>' + name +
            ' — ' + purpose + '</p></div><div class="refsynopsisdiv"><h2>Synopsis</h2>'
            '<pre class="synopsis">\n' + (synopsis or name) + '\n</pre></div>'
            '<div class="refsect1" id="DESCRIPTION"><h2>描述</h2><p>' + description +
            '</p></div>' + extra + '</div>')


def toc(pages):
    return '<dl>' + ''.join('<dt><span class="refentrytitle"><a href="{}">{}</a></span>'
        '<span class="refpurpose">— 目录用途</span></dt>'.format(file, name)
        for file, name in pages) + '</dl>'


LINKS = ('<a id="local" href="other.html#X">其它</a> '
         '<a href="other.html">其它页</a> <a href="#X">本页锚点</a> '
         '<a href="https://example.com/">外站</a>'
         '<a class="indexterm" id="id-1"></a><a class="id_link" href="#X">#</a>'
         '<script>evil()</script><a href="javascript:evil()">坏链接</a>')
PARAMETERS = ('<div class="refsect1"><h2>参数</h2><dl class="variablelist" style="color:red">'
              '<dt><code class="parameter">name</code></dt><dd><p>参数说明。</p>'
              '<pre class="programlisting">select  1;\n  select 2;</pre></dd></dl></div>')


def load_manuals():
    Version.objects.bulk_create([version(18, True), version(19, testing=2), version(0, testing=2)])
    for major, tree in [('18', 18), ('19', 19), ('20', 0)]:
        pages = {
            'sql-createtable.html': ('CREATE TABLE', reference('CREATE TABLE',
                'CREATE TABLE <em class="replaceable"><code>name</code></em>\n  (id int)' +
                ('\n  [ NEW OPTION ]' if major != '18' else ''), LINKS, PARAMETERS)),
            'sql-select.html': ('SELECT', reference('SELECT', description=
                '新正文。' if major == '20' else '共享正文。')),
            ('sql-waitfor.html' if major == '20' else 'sql-wait-for.html'):
                ('WAIT FOR', reference('Wait   For' if major == '18' else 'WAIT FOR', 'WAIT FOR LSN',
                    extra='<div class="refsect1"><h2>另见</h2><p><a href="sql-createtable.html">'
                          'CREATE TABLE</a></p></div>')),
        }
        if major != '20':
            pages['sql-createpropertygraph.html'] = ('CREATE PROPERTY GRAPH', reference('CREATE PROPERTY GRAPH'))
        if major != '18':
            pages['sql-merge.html'] = ('MERGE', reference('MERGE'))
        DocPage.objects.create(version_id=tree, file='sql-commands.html', content=toc(
            (file, name) for file, (name, _) in pages.items()))
        for file, (_, content) in pages.items():
            DocPage.objects.create(version_id=tree, file=file, title=file, content=content)
        DocPage.objects.create(version_id=tree, file='sql-syntax.html', content='<p>非参考页</p>')


class SqlcmdPureTests(SimpleTestCase):
    def test_identity_and_all_groups(self):
        self.assertEqual(len(SQLCMD_GROUPS), 17)
        self.assertEqual(sqlcmd_slug('Create  Table'), 'create-table')
        self.assertEqual(sqlcmd_split('create table as'), ('CREATE', 'TABLE AS'))
        self.assertEqual(sqlcmd_split('SELECT'), ('SELECT', ''))
        samples = {'REFRESH MATERIALIZED VIEW': 'table', 'CREATE INDEX': 'index',
                   'ALTER PROCEDURE': 'routine', 'DROP OPERATOR CLASS': 'type',
                   'CREATE TABLESPACE': 'schema', 'SET ROLE': 'role',
                   'CREATE EVENT TRIGGER': 'trigger', 'LOAD': 'extension',
                   'ALTER TEXT SEARCH DICTIONARY': 'textsearch', 'IMPORT FOREIGN SCHEMA': 'foreign',
                   'ALTER SUBSCRIPTION': 'replication', 'SELECT INTO': 'query', 'PREPARE': 'cursor',
                   'PREPARE TRANSACTION': 'transaction', 'ALTER SYSTEM': 'session',
                   'VACUUM': 'maintenance', 'CREATE PROPERTY GRAPH': 'misc', 'UNKNOWN': 'misc'}
        for name, group in samples.items():
            with self.subTest(name=name):
                self.assertEqual(sqlcmd_group_of(name), group)

    def test_line_diff_ignores_indent_and_marks_repeated_lines_by_position(self):
        self.assertIsNone(line_changes(' a  b\n  c', 'a b\nc')[0])
        diff, positions = line_changes('X\nY', 'X\nX\nY')
        self.assertEqual(diff, {'added': ['X'], 'removed': []})
        self.assertEqual(positions, {0})  # SequenceMatcher aligns the final X/Y pair.

    def test_section_keys_and_unknown_title(self):
        titles = list(SECTION_KEYS) + ['文件格式']
        extra = ''.join('<div class="refsect1"><h2>{}</h2><p>内容</p></div>'.format(t) for t in titles)
        snap = importer.parse_page(reference('COPY', extra=extra), 'sql-copy.html',
                                   {'major': '18', 'doc_slug': '18'})
        self.assertEqual([s['key'] for s in snap['sections'][1:]],
                         [SECTION_KEYS.get(t, 'other') for t in titles])
        self.assertEqual(snap['sections'][-1]['title'], '文件格式')

    def test_missing_title_can_use_toc(self):
        html = reference('SELECT').replace('<span class="refentrytitle">SELECT</span>', '')
        snap = importer.parse_page(html, 'sql-select.html', {'major': '18', 'doc_slug': '18'},
                                   {'name': 'SELECT'})
        self.assertEqual(snap['name'], 'SELECT')

    def test_non_reference_page_is_not_a_command(self):
        self.assertIsNone(importer.parse_page('<p>SQL syntax</p>', 'sql-syntax.html',
                                              {'major': '18', 'doc_slug': '18'}))

    def test_multiline_inline_html_remains_balanced(self):
        lines = sqlcmd.html_lines('A <em class="replaceable"><code>x\ny</code></em> B')
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(line.count('<em'), line.count('</em>'))
            self.assertEqual(line.count('<code'), line.count('</code>'))


class SqlcmdImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        load_manuals()
        cls.snapshot = importer.export_snapshot()

    def setUp(self):
        sqlcmd.forget()
        self.items = {c['slug']: c for c in self.snapshot['commands']}

    def tearDown(self):
        sqlcmd.forget()

    def test_three_versions_and_five_identities(self):
        self.assertEqual(len(self.items), 5)
        self.assertEqual([v['major'] for v in self.snapshot['versions']], ['18', '19', '20'])
        self.assertEqual([v['command_count'] for v in self.snapshot['versions']], [4, 5, 4])
        self.assertEqual(self.snapshot['default_major'], '18')
        self.assertEqual(self.snapshot['versions'][1]['label'], '19 beta 3')
        self.assertEqual(self.snapshot['versions'][2]['doc_slug'], 'devel')

    def test_waitfor_identity_and_rename(self):
        item = self.items['wait-for']
        self.assertEqual(item['aliases'], ['wait-for', 'waitfor'])
        self.assertEqual(item['name'], 'WAIT FOR')
        rename = item['changes'][-1]
        self.assertEqual(rename['renamed'], {'from_file': 'sql-wait-for.html', 'to_file': 'sql-waitfor.html'})
        self.assertFalse(rename['synopsis'])
        self.assertEqual(item['changed_in'], [])

    def test_clean_html_and_all_links(self):
        snap = self.items['create-table']['versions']['18']
        body = '\n'.join(s['html'] for s in snap['sections'])
        soup = BeautifulSoup(body, 'html.parser')
        self.assertFalse(soup.select('[id], [style], script, a.indexterm, a.id_link'))
        self.assertNotIn('evil()', body)
        links = [a.get('href') for a in soup.select('a')]
        for href in ['/docs/18/other.html#X', '/docs/18/other.html',
                     '/docs/18/sql-createtable.html#X', 'https://example.com/']:
            self.assertIn(href, links)
        self.assertEqual(soup.select_one('pre.programlisting').get_text(), 'select  1;\n  select 2;')
        self.assertTrue(soup.select_one('dl.variablelist dt code.parameter'))
        self.assertIn('<em class="replaceable"><code>name</code></em>', snap['synopsis_html'])
        self.assertIn('\n  (id int)', snap['synopsis_html'])

    def test_see_also_is_versioned_local_link_and_related(self):
        snap = self.items['wait-for']['versions']['20']
        self.assertEqual(snap['related'], ['create-table'])
        self.assertIn('href="/docs/sql/create-table/?v=20"', snap['sections'][-1]['html'])

    def test_synopsis_vs_body_change_and_add_remove(self):
        self.assertEqual(self.items['create-table']['changed_in'], ['19'])
        table = self.items['create-table']['changes'][0]
        self.assertEqual(table['synopsis'], {'added': ['[ NEW OPTION ]'], 'removed': []})
        select = self.items['select']
        self.assertEqual(select['changed_in'], [])
        self.assertEqual(select['changes'][0]['sections']['changed'], ['description'])
        self.assertEqual(select['changes'][0]['to'], '20')
        self.assertEqual(self.items['merge']['changes'][0]['status'], 'added')
        self.assertEqual(self.items['create-property-graph']['changes'][-1]['status'], 'removed')
        self.assertEqual(self.items['create-property-graph']['last_version'], '19')

    def test_exact_sections_are_deduplicated(self):
        snapshots = self.items['select']['versions']
        self.assertEqual(snapshots['19']['sections_same_as'], '18')
        self.assertEqual(snapshots['19']['sections'], [])
        self.assertEqual(sections_at(snapshots, '19'), snapshots['18']['sections'])

    def test_report_and_position(self):
        self.assertEqual(self.snapshot['harvest']['orphans'], [])
        self.assertEqual(self.snapshot['harvest']['upstream'], {'fetched': False})
        self.assertEqual(self.snapshot['harvest']['unmapped_groups'], ['CREATE PROPERTY GRAPH'])
        self.assertEqual(len(self.snapshot['harvest']['renamed']), 1)
        self.assertEqual(self.snapshot['harvest']['sections']['18']['keys']['description'], 4)
        self.assertGreater(self.snapshot['harvest']['dedupe']['same_as'], 0)
        positions = [c['position'] for c in self.snapshot['commands']]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(self.snapshot['commands'][0]['name'], 'CREATE TABLE')

    def test_create_alter_drop_order_is_by_object_then_verb(self):
        items = [dict(name=n, verb=sqlcmd_split(n)[0], object=sqlcmd_split(n)[1], group='table')
                 for n in ['DROP TABLE', 'CREATE VIEW', 'ALTER TABLE', 'CREATE TABLE']]
        importer.assign_positions(items)
        self.assertEqual([c['name'] for c in items], ['CREATE TABLE', 'ALTER TABLE', 'DROP TABLE', 'CREATE VIEW'])

    def test_orphan_is_collected_but_missing_toc_page_fails(self):
        DocPage.objects.create(version_id=18, file='sql-call.html', content=reference('CALL'))
        snap = importer.export_snapshot()
        self.assertEqual(snap['harvest']['orphans'], [{'major': '18', 'file': 'sql-call.html', 'name': 'CALL'}])
        DocPage.objects.filter(version=18, file='sql-select.html').delete()
        with self.assertRaisesRegex(ValueError, '参考页缺失'):
            importer.export_snapshot()

    def test_validate_missing_fields_and_bad_pointer(self):
        for field in ('aliases', 'versions', 'related', 'position'):
            snapshot = deepcopy(self.snapshot)
            del snapshot['commands'][0][field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                importer.validate(snapshot)
        snapshot = deepcopy(self.snapshot)
        snap = snapshot['commands'][0]['versions']['18']
        snap.update(sections=[], sections_same_as='19')
        with self.assertRaisesRegex(ValueError, 'sections_same_as'):
            importer.validate(snapshot)

    def test_import_is_idempotent_preserves_timestamp_and_prune_is_explicit(self):
        first = importer.import_snapshot(self.snapshot)
        timestamps = dict(SqlCommand.objects.values_list('slug', 'imported_at'))
        second = importer.import_snapshot(self.snapshot)
        self.assertEqual((first['added'], second['updated'], second['unchanged']), (5, 0, 5))
        self.assertEqual(timestamps, dict(SqlCommand.objects.values_list('slug', 'imported_at')))
        reduced = deepcopy(self.snapshot)
        reduced['commands'] = [c for c in reduced['commands'] if c['slug'] != 'merge']
        for v in reduced['versions']:
            v['command_count'] = sum(v['major'] in c['versions'] for c in reduced['commands'])
        self.assertEqual(importer.import_snapshot(reduced)['missing'], ['merge'])
        self.assertEqual(SqlCommand.objects.count(), 5)
        self.assertEqual(importer.import_snapshot(reduced, prune=True)['removed'], 1)
        self.assertEqual(SqlCommand.objects.count(), 4)

    def test_import_snapshot_never_reads_manual_bodies(self):
        with patch.object(importer, 'export_snapshot', side_effect=AssertionError('no harvesting')):
            report = importer.import_snapshot(self.snapshot)
        self.assertEqual(report['added'], 5)

    def test_preview_does_not_write_and_digest_tracks_content(self):
        self.assertEqual(importer.preview(self.snapshot)['added'], 5)
        self.assertFalse(SqlCommand.objects.exists())
        other = deepcopy(self.snapshot)
        other['commands'][0]['purpose_zh'] = '改动'
        self.assertNotEqual(importer.digest(self.snapshot), importer.digest(other))

    def test_arbitrary_compare_resolves_shared_sections(self):
        snapshots = self.items['select']['versions']
        a = dict(snapshots['19'], sections=sections_at(snapshots, '19'))
        c = compare(a, snapshots['20'], '19', '20')
        self.assertEqual(c['sections']['changed'], ['description'])

    def test_fetch_is_explicitly_reported_as_not_implemented(self):
        snapshot = importer.export_snapshot(fetch=True)
        self.assertFalse(snapshot['harvest']['upstream']['fetched'])
        self.assertTrue(snapshot['harvest']['upstream']['requested'])
