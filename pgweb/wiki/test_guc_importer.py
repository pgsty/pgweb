"""配置参数导入：版本归一、变化推导、去 Pigsty、手册译文采集、20 推导与写库。

夹具是手工写的最小 guc 数据集（三版 × 七个参数）与几页假手册，不碰真实仓库。
"""

import json
import os
import tempfile

from django.test import SimpleTestCase, TestCase

from pgweb.wiki import guc_importer


# ------------------------------------------------------------------ 假手册

DT = ('<dt{anchor}><span class="term">{terms} (<code class="type">{type}</code>) '
      '<a class="indexterm" id="id-1.{n}" name="id-1.{n}"></a></span>'
      '{link}</dt>\n<dd>{body}</dd>')
TERM = '<code class="varname">{}</code>'
SECTION = ('<div class="sect2" id="{anchor}">\n'
           '<div class="titlepage"><div><div><h3 class="title">{title}</h3></div></div></div>\n'
           '<div class="variablelist"><dl class="variablelist">\n{entries}\n</dl></div>\n</div>')
PAGE = ('<div class="sect1" id="RUNTIME-CONFIG-DEMO">\n'
        '<div class="titlepage"><div><div><h2 class="title">19.1. 示例</h2></div></div></div>\n'
        '{sections}\n</div>')


def entry(names, anchor, type_name, body, number=1):
    """一个 `<dt>` + `<dd>`；anchor 为空时模拟老版本手册里没有 id 的条目。"""
    terms = '，'.join(TERM.format(name) for name in names)
    return DT.format(anchor=' id="{}"'.format(anchor) if anchor else '', terms=terms,
                     type=type_name, body=body, n=number,
                     link=' <a class="id_link" href="#{}">#</a>'.format(anchor) if anchor else '')


def page(sections):
    """sections: [(锚点, 标题, [条目…])]"""
    return PAGE.format(sections='\n'.join(
        SECTION.format(anchor=anchor, title=title, entries='\n'.join(entries))
        for anchor, title, entries in sections))


LEVEL_BODY = ('\n  <p>   设置<code class="varname">demo_level</code>写入的信息级别，详见\n'
              '<a class="xref" href="populate.html#POPULATE-PITR" title="14.4">Section 14.4</a>、'
              '<a class="link" href="charset.html">字符集</a>与'
              '<a class="xref" href="#GUC-DEMO-SIZE">demo_size</a>。</p>\n'
              '  <p>外部资料见 <a href="https://example.com/demo">示例</a>。</p>\n'
              '<div class="note"><h3 class="title">注意</h3><p>这是提示框。</p></div>\n')
SHARED_BODY = '<p>设置示例字符串，没有任何内部链接。</p>'
SIZE_BODY = '<p>设置示例内存量。</p>'
DROPPED_BODY = '<p>这个参数只在 12 手册里有。</p>'
EXTRA_BODY = '<p>两个参数共用一条说明。</p>'
FRESH_BODY = '<p>开发版新增的参数。默认值为 <code class="literal">on</code>。</p>'
ALONE_BODY = '<p>开发版新增、所在小节没有旧参数的参数。</p>'


def manual_pages(major):
    """10 / 11 / 12 三版手册；devel 另建。"""
    developer = [entry(['demo_extra_a', 'demo_extra_b'], 'GUC-DEMO-EXTRA-B', 'boolean', EXTRA_BODY),
                 entry(['demo_dropped'], 'GUC-DEMO-DROPPED', 'boolean', DROPPED_BODY)]
    if major != '12':
        developer.append(entry(['demo_gone'], 'GUC-DEMO-GONE', 'boolean', '<p>后来移除了。</p>'))
    return {
        'runtime-config-wal.html': page([
            ('RUNTIME-CONFIG-WAL-SETTINGS', '19.5.1. 设置',
             [entry(['demo_level'], 'GUC-DEMO-LEVEL', 'enum', LEVEL_BODY)])]),
        'runtime-config-resource.html': page([
            ('RUNTIME-CONFIG-RESOURCE-MEMORY', '19.4.1. 内存',
             [entry(['demo_size'], 'GUC-DEMO-SIZE', 'integer', SIZE_BODY)])]),
        'runtime-config-client.html': page([
            ('RUNTIME-CONFIG-CLIENT-OTHER', '19.11.4. 其他默认值',
             # 10 的手册 <dt> 没有 id：只能按参数名认。
             [entry(['demo_shared'], '' if major == '10' else 'GUC-DEMO-SHARED', 'string',
                    SHARED_BODY)])]),
        'runtime-config-developer.html': page([
            ('RUNTIME-CONFIG-DEVELOPER', '19.18. 开发者选项', developer)]),
    }


def devel_pages():
    return {
        'runtime-config-wal.html': page([
            ('RUNTIME-CONFIG-WAL-SETTINGS', '19.5.1. 设置',
             [entry(['demo_level'], 'GUC-DEMO-LEVEL', 'enum', LEVEL_BODY)]),
            ('RUNTIME-CONFIG-WAL-NEW', '19.5.9. 新小节',
             [entry(['demo_fresh_alone'], 'GUC-DEMO-FRESH-ALONE', 'pg_lsn', ALONE_BODY)])]),
        'runtime-config-resource.html': page([
            ('RUNTIME-CONFIG-RESOURCE-MEMORY', '19.4.1. 内存',
             [entry(['demo_size'], 'GUC-DEMO-SIZE', 'integer', SIZE_BODY),
              entry(['demo_fresh'], 'GUC-DEMO-FRESH', 'floating point', FRESH_BODY)])]),
        'runtime-config-client.html': page([
            ('RUNTIME-CONFIG-CLIENT-OTHER', '19.11.4. 其他默认值',
             [entry(['demo_shared'], 'GUC-DEMO-SHARED', 'string', SHARED_BODY)])]),
        'runtime-config-developer.html': page([
            ('RUNTIME-CONFIG-DEVELOPER', '19.18. 开发者选项',
             [entry(['demo_extra_a', 'demo_extra_b'], 'GUC-DEMO-EXTRA-B', 'boolean',
                    EXTRA_BODY)])]),
    }


def load_manuals(devel=True):
    from datetime import date
    from pgweb.core.models import Version
    from pgweb.docs.models import DocPage
    trees = [10, 11, 12] + ([0] if devel else [])
    Version.objects.bulk_create([
        Version(tree=tree, current=tree == 11, supported=tree in (11, 12), testing=2 if tree == 0 else 0,
                reldate=date(2025, 9, 1), firstreldate=date(2025, 9, 1), eoldate=date(2030, 1, 1))
        for tree in trees])
    for major in ('10', '11', '12'):
        for filename, body in manual_pages(major).items():
            DocPage.objects.create(file=filename, version_id=major, title=filename, content=body)
    if devel:
        for filename, body in devel_pages().items():
            DocPage.objects.create(file=filename, version_id=0, title=filename, content=body)


# ------------------------------------------------------------------ 假 guc 数据

KEYS = ('10', '11', '12beta1')


def row(**fields):
    base = {'setting': '', 'unit': None, 'category': '', 'short_desc': '', 'extra_desc': None,
            'context': 'sighup', 'vartype': 'bool', 'min_val': None, 'max_val': None,
            'enumvals': None, 'boot_val': 'off'}
    base.update(fields)
    return base


def docs_for(name, keys=KEYS, file='runtime-config-developer.html'):
    anchor = 'GUC-' + name.upper().replace('_', '-')
    return {key: {'status': 'verified', 'anchor': anchor,
                  'url': 'https://www.postgresql.org/docs/{}/{}#{}'.format(
                      key.replace('beta1', ''), file, anchor)}
            for key in keys}


def record(name, versions, **extra):
    present = [key for key in KEYS if key in versions]
    item = {
        'name': name, 'slug': name.replace('_', '-'),
        'identity': versions[present[-1]],
        'lifecycle': {'first_seen': present[0], 'first_seen_is_scope_boundary': present[0] == '10',
                      'last_seen': present[-1], 'removed_in': None, 'present_in': present,
                      'gaps': []},
        'default_history': [{'from': present[0], 'to': present[-1],
                             'boot_val': versions[present[0]]['boot_val'],
                             'unit': versions[present[0]]['unit'], 'human': ''}],
        'changed_fields': {}, 'official_docs': docs_for(name, present),
        'introduction_commit': None, 'pigsty': {'10': {'oltp': {'status': 'declared'}}},
        'editorial': {'en': {}, 'zh': {}}, 'versions': versions,
        'provenance': {'kind': 'fact'},
    }
    item.update(extra)
    return item


PIGSTY_EDITORIAL = {
    'en': {
        'summary': 'A demo parameter. Pigsty sets it to logical.',
        'official_short_desc_translation': 'Sets the demo level.',
        'mechanism': ['It is fixed at server start.'],
        'advice': {'oltp': 'Measure first.', 'olap': 'Measure first.',
                   'small': 'Start from safe defaults or the measured Pigsty value '
                            'and watch capacity.'},
        'pigsty_rationale_pending_review': 'Fact from the current Pigsty template projection.',
        'pitfalls': ['Do not lower it while slots depend on it.'],
        'related': ['demo_size', 'no_such_parameter'],
        'references': [{'title': 'Manual', 'url': 'https://example.com/en'},
                       {'title': 'Pigsty: Parameter Templates',
                        'url': 'https://pigsty.io/docs/pgsql/template/'}],
    },
    'zh': {
        'summary': '示例参数。Pigsty 模板把它设为 logical。',
        'official_short_desc_translation': '设置示例级别。',
        'mechanism': ['该值在服务器启动时固定。'],
        'advice': {'oltp': '先测量。', 'olap': '先测量。',
                   'small': '从安全默认或实测 Pigsty 值开始，按容量告警。'},
        'pigsty_rationale_pending_review': '当前 Pigsty 模板投影事实。',
        'pitfalls': ['槽仍依赖时不要降低。'],
        'related': ['demo_size', 'no_such_parameter'],
        'references': [{'title': '手册', 'url': 'https://example.com/zh'},
                       {'title': 'Pigsty：参数模板', 'url': 'https://pigsty.io/docs/pgsql/template/'},
                       # 标题里没写 Pigsty，站点认得出来。
                       {'title': '参数模板', 'url': 'https://docs.pigsty.cc/pgsql/template/'}],
    },
}


def guc_records():
    """七个参数 × 三版：一个改默认值、一个只换了措辞、一个被移除、一个从未进手册。"""
    level = {
        '10': row(setting='minimal', boot_val='minimal', vartype='enum', context='postmaster',
                  category='Write-Ahead Log / Settings', short_desc='Sets the level.',
                  enumvals=['minimal', 'archive']),
        '11': row(setting='replica', boot_val='replica', vartype='enum', context='postmaster',
                  category='Write-Ahead Log / Settings', short_desc='Sets the level.',
                  enumvals=['minimal', 'replica']),
        '12beta1': row(setting='replica', boot_val='replica', vartype='enum', context='postmaster',
                       category='Write-Ahead Log / Settings', short_desc='Sets the WAL level.',
                       enumvals=['minimal', 'replica']),
    }
    # 10 把无单位写成空串、11 起写成 null；运行值每版都不同，都不算变化。
    size = {
        '10': row(setting='1024', boot_val='1024', unit='', vartype='integer', context='postmaster',
                  category='Resource Usage / Memory', short_desc='Sets the memory.',
                  min_val='16', max_val='1073741823'),
        '11': row(setting='2048', boot_val='1024', unit=None, vartype='integer',
                  context='postmaster', category='Resource Usage / Memory',
                  short_desc='Sets the memory.', min_val='16', max_val='1073741823'),
        '12beta1': row(setting='4096', boot_val='1024', unit=None, vartype='integer',
                       context='postmaster', category='Resource Usage / Memory',
                       short_desc='Sets the memory.', min_val='16', max_val='1073741823'),
    }
    everywhere = {key: row(category='Developer Options', short_desc='Demo flag.') for key in KEYS}
    shared = {key: row(category='Client Connection Defaults / Other Defaults', vartype='string',
                       boot_val='demo', context='user', short_desc='Demo string.') for key in KEYS}
    gone = {key: row(category='Developer Options', short_desc='Demo flag.')
            for key in ('10', '11')}
    return [
        record('demo_level', level, editorial=PIGSTY_EDITORIAL,
               official_docs=docs_for('demo_level', KEYS, 'runtime-config-wal.html'),
               introduction_commit={'status': 'verified', 'hash': 'a' * 40,
                                    'authored_at': '2017-03-29T08:44:45-04:00',
                                    'subject': 'Add demo_level.', 'url': 'https://git/demo',
                                    'discussion': ['https://postgr.es/m/demo'],
                                    'search_method': 'guc_table_paths_exact'}),
        record('demo_size', size,
               official_docs=docs_for('demo_size', KEYS, 'runtime-config-resource.html')),
        record('demo_gone', gone),
        record('demo_undocumented', dict(everywhere),
               official_docs={key: {'status': 'not_documented_in_runtime_config',
                                    'anchor': 'GUC-DEMO-UNDOCUMENTED'} for key in KEYS},
               introduction_commit={'status': 'predates_history_boundary', 'note': 'x'}),
        record('demo_dropped', dict(everywhere)),
        record('demo_extra_a', dict(everywhere)),
        record('demo_shared', shared,
               official_docs=docs_for('demo_shared', KEYS, 'runtime-config-client.html')),
    ]


def guc_diffs():
    return {
        '10-11': {'from': '10', 'to': '11', 'added': [], 'removed': [],
                  'default_changed': [{'name': 'demo_level',
                                       'from': {'boot_val': 'minimal', 'unit': None},
                                       'to': {'boot_val': 'replica', 'unit': None}}]},
        '11-12beta1': {'from': '11', 'to': '12beta1', 'added': [], 'removed': ['demo_gone'],
                       'default_changed': []},
    }


def write_root(root, records=None, diffs=None):
    os.makedirs(os.path.join(root, 'data'), exist_ok=True)
    os.makedirs(os.path.join(root, 'raw'), exist_ok=True)
    with open(os.path.join(root, 'data', 'guc.json'), 'w', encoding='utf-8') as handle:
        json.dump(records or guc_records(), handle, ensure_ascii=False)
    with open(os.path.join(root, 'data', 'diffs.json'), 'w', encoding='utf-8') as handle:
        json.dump(diffs or guc_diffs(), handle, ensure_ascii=False)
    with open(os.path.join(root, 'data', 'catalog.json'), 'w', encoding='utf-8') as handle:
        json.dump({'scope': {'from': '10', 'to': '12beta1'},
                   'version_counts': {'10': 7, '11': 7, '12beta1': 6}}, handle)
    with open(os.path.join(root, 'raw', 'manifest.json'), 'w', encoding='utf-8') as handle:
        json.dump({'snapshots': {
            '10': {'server_version': '10.23 (Debian 10.23-1.pgdg110+1)'},
            '11': {'server_version': '11.22'},
            '12beta1': {'server_version': '12beta1 (Debian 12~beta1-1)'}}}, handle)
    return root


def export(records=None, diffs=None):
    with tempfile.TemporaryDirectory() as root:
        write_root(root, records, diffs)
        return guc_importer.export_snapshot(root)


def named(snapshot):
    return {item['name']: item for item in snapshot['parameters']}


# ------------------------------------------------------------------ 不碰库的部分

class GucVersionKeyTests(SimpleTestCase):
    """版本键归一：'19beta3' 是 19 的预发行，不是另一个大版本。"""

    def test_prerelease_key_splits_into_major_kind_and_number(self):
        self.assertEqual(guc_importer.split_key('19beta3'), ('19', 'beta', '3'))
        self.assertEqual(guc_importer.split_key('9.6'), ('9.6', '', ''))
        self.assertEqual(guc_importer.split_key('18'), ('18', '', ''))

    def test_major_and_label(self):
        self.assertEqual(guc_importer.major_of('19beta3'), '19')
        self.assertEqual(guc_importer.label_of('19beta3'), '19 beta 3')
        self.assertEqual(guc_importer.label_of('19rc1'), '19 rc 1')
        self.assertEqual(guc_importer.label_of('9.6'), '9.6')

    def test_versions_sort_by_number_then_prerelease(self):
        keys = ['10', '19beta3', '9.0', '9.6', '18', '19']
        self.assertEqual(sorted(keys, key=guc_importer.version_sort_key),
                         ['9.0', '9.6', '10', '18', '19beta3', '19'])

    def test_doc_slug_and_manual_tree_send_the_devel_major_to_devel(self):
        self.assertEqual(guc_importer.doc_slug('18'), '18')
        self.assertEqual(guc_importer.doc_slug(guc_importer.DEVEL_MAJOR), 'devel')
        self.assertEqual(guc_importer.manual_tree(guc_importer.DEVEL_MAJOR),
                         guc_importer.DEVEL_TREE)


class GucChangeTests(SimpleTestCase):
    """相邻两版的变化记录。"""

    def snapshots(self):
        return {'10': {'boot_val': '1024', 'unit': '', 'setting': '1024', 'enumvals': None,
                       'context': 'user', 'short_desc': 'a'},
                '11': {'boot_val': '1024', 'unit': None, 'setting': '2048', 'enumvals': [],
                       'context': 'user', 'short_desc': 'a'},
                '12': {'boot_val': '2048', 'unit': None, 'setting': '4096', 'enumvals': [],
                       'context': 'sighup', 'short_desc': 'b'}}

    def test_empty_string_null_and_empty_list_are_the_same_empty(self):
        changes = guc_importer.build_changes(self.snapshots(), ['10', '11', '12'])
        self.assertEqual([change['to'] for change in changes], ['12'])

    def test_the_running_value_never_counts_as_a_change(self):
        changes = guc_importer.build_changes(self.snapshots(), ['10', '11', '12'])
        self.assertNotIn('setting', changes[0]['fields'])

    def test_a_substantive_change_also_reports_the_default(self):
        change = guc_importer.build_changes(self.snapshots(), ['10', '11', '12'])[0]
        self.assertEqual(sorted(change['fields']), ['boot_val', 'context', 'short_desc'])
        self.assertTrue(change['substantive'])
        self.assertTrue(change['default_changed'])
        self.assertFalse(change['carried'])

    def test_added_is_recorded_from_the_second_version_on(self):
        changes = guc_importer.build_changes({'11': {'boot_val': 'on'}}, ['10', '11', '12'])
        self.assertEqual([(c['from'], c['to'], c['status']) for c in changes],
                         [('10', '11', 'added'), ('11', '12', 'removed')])

    def test_the_first_version_of_the_dataset_is_never_an_addition(self):
        changes = guc_importer.build_changes({'10': {'boot_val': 'on'}, '11': {'boot_val': 'on'}},
                                             ['10', '11'])
        self.assertEqual(changes, [])


class GucScrubTests(SimpleTestCase):
    """编辑文字去 Pigsty：删得掉的短语先删，剩下的整句丢掉。"""

    def test_a_phrase_is_removed_and_the_sentence_survives(self):
        self.assertEqual(guc_importer.scrub('从安全默认或实测 Pigsty 值开始，按容量告警。'),
                         '从安全默认开始，按容量告警。')
        self.assertEqual(guc_importer.scrub('先保持默认或 Pigsty 矩阵值；小表更看阈值。'),
                         '先保持默认；小表更看阈值。')
        self.assertEqual(
            guc_importer.scrub('Start with upstream or the measured Pigsty matrix value. '
                               'Fixed thresholds dominate.'),
            'Start with upstream. Fixed thresholds dominate.')

    def test_a_sentence_that_still_mentions_pigsty_is_dropped_whole(self):
        self.assertEqual(guc_importer.scrub('示例参数。Pigsty 模板把它设为 logical。'), '示例参数。')
        self.assertEqual(guc_importer.scrub('默认 -1；Pigsty 使用有限上限。'), '默认 -1；')
        self.assertEqual(
            guc_importer.scrub('A demo parameter. Pigsty sets it to logical.'),
            'A demo parameter.')

    def test_a_decimal_point_does_not_split_a_sentence(self):
        self.assertEqual(guc_importer.scrub('Use 0.5 here. Pigsty uses 0.2.'), 'Use 0.5 here.')

    def test_text_without_pigsty_is_left_alone(self):
        self.assertEqual(guc_importer.scrub('先测量再改。'), '先测量再改。')

    def test_a_reference_is_dropped_by_its_site_or_its_title(self):
        for title, url in (('Pigsty：参数模板', 'https://pigsty.io/docs/pgsql/template/'),
                           ('参数模板', 'https://pigsty.io/docs/node/param/'),
                           ('参数模板', 'https://docs.pigsty.cc/pgsql/'),
                           ('Pigsty 模板', 'https://example.com/x')):
            self.assertTrue(guc_importer.is_pigsty_reference({'title': title, 'url': url}),
                            (title, url))

    def test_an_ordinary_reference_is_kept(self):
        for title, url in (('PostgreSQL 19 手册', 'https://www.postgresql.org/docs/19/x.html'),
                           ('发行说明', 'https://example.com/pigsty-notes')):
            self.assertFalse(guc_importer.is_pigsty_reference({'title': title, 'url': url}),
                             (title, url))

    def test_references_count_what_they_drop(self):
        report = {'pigsty_references_dropped': 0}
        block = {'references': [{'title': '手册', 'url': 'https://example.com/zh'},
                                {'title': 'Pigsty：参数模板', 'url': 'https://pigsty.io/docs/'},
                                {'title': '没有地址的条目', 'url': ''}]}
        self.assertEqual(guc_importer.references_of(block, report),
                         [{'title': '手册', 'url': 'https://example.com/zh'}])
        self.assertEqual(report['pigsty_references_dropped'], 1)


class GucDocCleanTests(SimpleTestCase):
    """手册译文清洗：白名单、去 id、三种链接改写。"""

    def clean(self, body, slug='18', filename='runtime-config-wal.html'):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup('<dd>{}</dd>'.format(body), 'html.parser')
        return guc_importer.clean_doc(soup.dd, slug, filename)

    def test_three_link_shapes_are_rewritten_and_external_ones_are_left(self):
        html = self.clean(LEVEL_BODY)
        self.assertIn('href="/docs/18/populate.html#POPULATE-PITR"', html)
        self.assertIn('href="/docs/18/charset.html"', html)
        self.assertIn('href="/docs/18/runtime-config-wal.html#GUC-DEMO-SIZE"', html)
        self.assertIn('href="https://example.com/demo"', html)

    def test_index_anchors_ids_and_whitespace_are_gone(self):
        html = self.clean('<p id="x">  甲   <a class="indexterm" id="id-1"></a>'
                          '<a class="id_link" href="#X">#</a>乙  </p>')
        self.assertEqual(html, '<p>甲 乙</p>')

    def test_the_note_box_and_its_class_survive(self):
        html = self.clean(LEVEL_BODY)
        self.assertIn('<div class="note">', html)
        self.assertIn('<code class="varname">demo_level</code>', html)

    def test_tags_outside_the_allowlist_lose_their_markup_but_keep_the_text(self):
        self.assertEqual(self.clean('<p><font size="2">正文</font></p>'), '<p>正文</p>')

    def test_the_same_text_cleans_identically_under_the_same_slug(self):
        self.assertEqual(self.clean(SHARED_BODY), self.clean(SHARED_BODY, filename='other.html'))


class GucVartypeTests(SimpleTestCase):
    """手册写的类型名映射成 pg_settings.vartype。"""

    def vartype(self, written):
        from bs4 import BeautifulSoup
        markup = '<dt><code class="varname">x</code> (<code class="type">{}</code>)</dt>'
        return guc_importer.vartype_of(BeautifulSoup(markup.format(written), 'html.parser').dt)

    def test_every_shape_the_manual_writes(self):
        for written, expected in (('boolean', 'bool'), ('floating point', 'real'),
                                  ('integer', 'integer'), ('string', 'string'), ('enum', 'enum'),
                                  ('pg_lsn', 'string'), ('timestamp', 'string')):
            self.assertEqual(self.vartype(written), expected)


# ------------------------------------------------------------------ 导出

class GucExportTests(TestCase):
    """完整导出：版本行、译文采集、去重、20 推导。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()

    def setUp(self):
        self.snapshot = export()
        self.items = named(self.snapshot)

    def test_version_rows_normalise_the_prerelease_key(self):
        versions = {v['major']: v for v in self.snapshot['versions']}
        self.assertEqual([v['major'] for v in self.snapshot['versions']], ['10', '11', '12', '20'])
        self.assertEqual([v['position'] for v in self.snapshot['versions']], [0, 1, 2, 3])
        self.assertEqual((versions['12']['label'], versions['12']['status'],
                          versions['12']['support_status'], versions['12']['source_key']),
                         ('12 beta 1', 'preview', 'preview', '12beta1'))
        self.assertEqual(versions['12']['server_version'], '12beta1')
        self.assertEqual(versions['10']['server_version'], '10.23')
        self.assertEqual((versions['11']['status'], versions['11']['support_status']),
                         ('stable', 'supported'))
        self.assertEqual((versions['10']['status'], versions['10']['support_status']),
                         ('historical', 'end-of-life'))
        self.assertEqual((versions['20']['label'], versions['20']['status'],
                          versions['20']['support_status'], versions['20']['doc_slug'],
                          versions['20']['schema_source']),
                         ('20 devel', 'devel', 'devel', 'devel', 'documentation'))
        self.assertEqual(self.snapshot['default_major'], '11')

    def test_the_transition_counts_match_the_lists(self):
        versions = {v['major']: v for v in self.snapshot['versions']}
        eleven = versions['11']['transition']
        self.assertEqual([item['name'] for item in eleven['default_changed']], ['demo_level'])
        self.assertEqual(versions['11']['default_changed_count'], 1)
        twelve = versions['12']['transition']
        self.assertEqual(twelve['removed'], ['demo_gone'])
        self.assertEqual(twelve['reworded'], ['demo_level'])
        self.assertEqual((versions['12']['removed_count'], versions['12']['reworded_count']),
                         (1, 1))
        self.assertEqual(versions['20']['transition']['added'],
                         ['demo_fresh', 'demo_fresh_alone'])

    def test_a_default_change_lands_in_changed_in_and_default_changed_in(self):
        level = self.items['demo_level']
        self.assertEqual(level['changed_in'], ['11'])
        self.assertEqual(level['default_changed_in'], ['11'])
        self.assertEqual(self.items['demo_size']['changed_in'], [])
        self.assertEqual(self.items['demo_size']['default_changed_in'], [])

    def test_hot_fields_come_from_the_last_version_present(self):
        size = self.items['demo_size']
        self.assertEqual((size['first_version'], size['last_version']), ('10', '20'))
        self.assertEqual(size['present_in'], ['10', '11', '12', '20'])
        self.assertEqual(size['boot_human'], '1024')
        self.assertEqual((size['group'], size['group_slug'], size['category_zh']),
                         ('Resource Usage', 'resource', '资源消耗 / 内存'))
        gone = self.items['demo_gone']
        self.assertEqual((gone['first_version'], gone['last_version']), ('10', '11'))
        self.assertTrue(gone['baseline'])

    def test_position_is_group_then_category_then_name(self):
        order = [item['name'] for item in self.snapshot['parameters']]
        self.assertLess(order.index('demo_size'), order.index('demo_level'))
        self.assertLess(order.index('demo_level'), order.index('demo_shared'))
        self.assertLess(order.index('demo_dropped'), order.index('demo_extra_a'))

    def test_editorial_loses_pigsty_and_keeps_both_languages(self):
        editorial = self.items['demo_level']['editorial']
        self.assertEqual(editorial['summary_zh'], '示例参数。')
        self.assertEqual(editorial['summary'], 'A demo parameter.')
        self.assertEqual(editorial['advice_zh']['small'], '从安全默认开始，按容量告警。')
        self.assertEqual(editorial['advice']['small'],
                         'Start from safe defaults and watch capacity.')
        self.assertNotIn('pigsty_rationale_pending_review', editorial)
        self.assertEqual(editorial['related'], ['demo_size'])
        self.assertEqual(editorial['references_zh'], [{'title': '手册',
                                                       'url': 'https://example.com/zh'}])
        self.assertEqual(editorial['references'], [{'title': 'Manual',
                                                    'url': 'https://example.com/en'}])
        self.assertEqual(self.snapshot['harvest']['pigsty_references_dropped'], 3)
        self.assertEqual(self.snapshot['harvest']['pigsty_left'], [])
        blob = json.dumps(self.items['demo_level'], ensure_ascii=False).lower()
        self.assertNotIn('pigsty', blob)

    def test_intro_commit_keeps_facts_only_when_verified(self):
        self.assertEqual(self.items['demo_level']['intro_commit'],
                         {'hash': 'a' * 40, 'authored_at': '2017-03-29T08:44:45-04:00',
                          'subject': 'Add demo_level.', 'url': 'https://git/demo',
                          'discussion': ['https://postgr.es/m/demo']})
        self.assertEqual(self.items['demo_undocumented']['intro_commit'],
                         {'status': 'predates_history_boundary'})
        self.assertEqual(self.items['demo_size']['intro_commit'], {})

    def test_the_manual_translation_is_harvested_per_version(self):
        level = self.items['demo_level']['versions']
        self.assertIn('href="/docs/10/populate.html#POPULATE-PITR"', level['10']['doc_html'])
        self.assertIn('href="/docs/12/populate.html#POPULATE-PITR"', level['12']['doc_html'])
        self.assertIn('href="/docs/devel/populate.html#POPULATE-PITR"', level['20']['doc_html'])
        self.assertEqual(level['10']['doc']['file'], 'runtime-config-wal.html')
        self.assertEqual(level['10']['doc']['anchor'], 'GUC-DEMO-LEVEL')
        self.assertEqual(level['10']['doc']['slug'], '10')

    def test_an_identical_translation_is_stored_once_and_pointed_at(self):
        shared = self.items['demo_shared']['versions']
        self.assertTrue(shared['10']['doc_html'])
        self.assertEqual(shared['10']['doc_same_as'], '')
        for major in ('11', '12', '20'):
            self.assertEqual(shared[major]['doc_html'], '')
            self.assertEqual(shared[major]['doc_same_as'], '10')

    def test_a_dt_without_an_id_is_still_found_by_the_parameter_name(self):
        # 10 的手册里 demo_shared 的 <dt> 没有 id，锚点两条路都走不通。
        self.assertEqual(self.snapshot['harvest']['doc']['10']['name'], 2)
        self.assertTrue(self.items['demo_shared']['versions']['10']['doc_html'])

    def test_one_dt_documents_both_of_its_parameters(self):
        versions = self.items['demo_extra_a']['versions']
        self.assertIn('两个参数共用一条说明', versions['10']['doc_html'])
        self.assertEqual(versions['12']['doc_same_as'], '10')
        self.assertEqual(versions['12']['doc']['anchor'], 'GUC-DEMO-EXTRA-B')

    def test_a_parameter_no_manual_ever_documented_is_reported_unlocated(self):
        unlocated = self.snapshot['harvest']['unlocated']
        self.assertIn('demo_undocumented @ 10', unlocated)
        self.assertEqual(self.items['demo_undocumented']['versions']['10']['doc_html'], '')

    def test_diffs_are_cross_checked_against_the_source(self):
        self.assertEqual(self.snapshot['harvest']['diffs'],
                         {'pairs': 2, 'matched': True, 'compared': ['10-11', '11-12beta1']})


class GucDevelTests(TestCase):
    """20 推导的四种情形。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()

    def setUp(self):
        self.snapshot = export()
        self.items = named(self.snapshot)
        self.devel = self.snapshot['harvest']['devel']

    def test_a_parameter_the_devel_manual_documents_carries_the_previous_facts(self):
        level = self.items['demo_level']['versions']
        self.assertEqual(level['20']['carried_from'], '12')
        self.assertEqual(level['20']['carry_reason'], '手册不含 pg_settings 事实，沿用 12')
        for field in ('boot_val', 'context', 'vartype', 'enumvals', 'category'):
            self.assertEqual(level['20'][field], level['12'][field])
        self.assertNotEqual(level['20']['doc_html'], level['12']['doc_html'])
        self.assertEqual(self.items['demo_level']['docs']['20'],
                         {'status': 'derived', 'anchor': 'GUC-DEMO-LEVEL',
                          'url': 'https://www.postgresql.org/docs/devel/'
                                 'runtime-config-wal.html#GUC-DEMO-LEVEL'})
        change = self.items['demo_level']['changes'][-1]
        self.assertEqual((change['from'], change['to'], change['status'], change['fields']),
                         ('12', '20', 'changed', {}))
        self.assertTrue(change['carried'])

    def test_a_parameter_no_manual_documents_is_carried_not_removed(self):
        snapshot = self.items['demo_undocumented']['versions']['20']
        self.assertEqual(snapshot['carry_reason'], '手册从未收录此参数，沿用 12')
        self.assertEqual(self.devel['undocumented'], ['demo_undocumented'])
        self.assertNotIn('20', self.items['demo_undocumented']['docs'])

    def test_a_parameter_the_devel_manual_dropped_is_removed_in_20(self):
        self.assertNotIn('20', self.items['demo_dropped']['versions'])
        self.assertEqual(self.items['demo_dropped']['last_version'], '12')
        self.assertEqual(self.devel['removed'], ['demo_dropped'])
        self.assertEqual(self.items['demo_dropped']['changes'][-1]['status'], 'removed')

    def test_a_parameter_only_the_devel_manual_has_is_new_in_20(self):
        fresh = self.items['demo_fresh']
        self.assertEqual((fresh['first_version'], fresh['last_version']), ('20', '20'))
        self.assertEqual(fresh['vartype'], 'real')
        self.assertEqual(fresh['category'], 'Resource Usage / Memory')
        self.assertEqual(fresh['short_desc_zh'], '开发版新增的参数。')
        self.assertEqual((fresh['short_desc'], fresh['context'], fresh['boot_val'],
                          fresh['unit'], fresh['enumvals']), ('', '', None, '', []))
        self.assertEqual(fresh['editorial'], {})
        self.assertEqual(fresh['intro_commit'], {})
        self.assertEqual(fresh['default_history'], [])
        self.assertEqual(fresh['docs']['20']['status'], 'derived')
        self.assertEqual(fresh['changes'], [{'from': '12', 'to': '20', 'status': 'added',
                                             'fields': {}, 'substantive': False,
                                             'default_changed': False, 'carried': False}])

    def test_a_new_parameter_falls_back_to_the_page_group_for_its_category(self):
        alone = self.items['demo_fresh_alone']
        self.assertEqual(alone['category'], 'Write-Ahead Log')
        self.assertEqual(alone['group_slug'], 'wal')
        self.assertEqual(alone['vartype'], 'string')

    def test_a_name_only_the_manual_knows_is_not_a_new_parameter(self):
        # demo_extra_b 在 12 与 devel 手册里都有，pg_settings 从来没有：这是手册的老账。
        self.assertNotIn('demo_extra_b', self.items)
        self.assertEqual(self.devel['added'], ['demo_fresh', 'demo_fresh_alone'])

    def test_the_default_history_runs_through_to_20(self):
        self.assertEqual(self.items['demo_level']['default_history'][-1]['to'], '20')
        self.assertEqual(self.items['demo_gone']['default_history'][-1]['to'], '11')

    def test_without_a_devel_manual_version_20_is_skipped(self):
        from pgweb.docs.models import DocPage
        DocPage.objects.filter(version=0).delete()
        snapshot = export()
        self.assertEqual([v['major'] for v in snapshot['versions']], ['10', '11', '12'])
        self.assertFalse(snapshot['harvest']['devel']['derived'])
        self.assertIn('devel', snapshot['harvest']['devel']['reason'])
        self.assertNotIn('demo_fresh', named(snapshot))


class GucDiffCheckTests(TestCase):
    """与 diffs.json 对不上就不要导出。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()

    def test_a_missing_removal_is_caught(self):
        diffs = guc_diffs()
        diffs['11-12beta1']['removed'] = []
        with self.assertRaises(ValueError) as caught:
            export(diffs=diffs)
        self.assertIn('removed', str(caught.exception))
        self.assertIn('demo_gone', str(caught.exception))

    def test_a_default_change_the_source_does_not_know_is_caught(self):
        diffs = guc_diffs()
        diffs['10-11']['default_changed'] = []
        with self.assertRaises(ValueError) as caught:
            export(diffs=diffs)
        self.assertIn('default_changed', str(caught.exception))


# ------------------------------------------------------------------ 导入

class GucImportTests(TestCase):
    """校验、预览、幂等与 prune。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()
        cls.payload = export()

    def setUp(self):
        from pgweb.wiki.models import GucParameter, GucVersion
        self.GucParameter, self.GucVersion = GucParameter, GucVersion
        self.snapshot = json.loads(json.dumps(self.payload))

    def test_import_lands_versions_and_parameters(self):
        report = guc_importer.import_snapshot(self.snapshot)
        self.assertEqual(report['versions'], 4)
        self.assertEqual(report['added'], len(self.snapshot['parameters']))
        self.assertEqual(self.GucVersion.objects.count(), 4)
        self.assertEqual(self.GucParameter.objects.count(), 9)
        row = self.GucParameter.objects.get(name='demo_level')
        self.assertEqual(row.key, 'demo_level')
        self.assertEqual(row.group_slug, 'wal')
        self.assertEqual(row.present_in, ['10', '11', '12', '20'])
        self.assertEqual(row.url, '/docs/guc/demo_level/')

    def test_import_is_idempotent_and_rewrites_nothing(self):
        guc_importer.import_snapshot(self.snapshot)
        stamp = self.GucParameter.objects.get(name='demo_level').imported_at
        report = guc_importer.import_snapshot(json.loads(json.dumps(self.payload)))
        self.assertEqual((report['added'], report['updated']), (0, 0))
        self.assertEqual(report['unchanged'], len(self.snapshot['parameters']))
        self.assertEqual(self.GucParameter.objects.get(name='demo_level').imported_at, stamp)

    def test_only_the_changed_parameter_is_rewritten(self):
        guc_importer.import_snapshot(self.snapshot)
        stamp = self.GucParameter.objects.get(name='demo_size').imported_at
        changed = json.loads(json.dumps(self.payload))
        for item in changed['parameters']:
            if item['name'] == 'demo_level':
                item['short_desc_zh'] = '改过的简述。'
        report = guc_importer.import_snapshot(changed)
        self.assertEqual((report['added'], report['updated']), (0, 1))
        self.assertEqual(self.GucParameter.objects.get(name='demo_level').short_desc_zh,
                         '改过的简述。')
        self.assertEqual(self.GucParameter.objects.get(name='demo_size').imported_at, stamp)

    def test_preview_writes_nothing(self):
        report = guc_importer.preview(self.snapshot)
        self.assertEqual(report['parameters'], len(self.snapshot['parameters']))
        self.assertEqual(len(report['added']), len(self.snapshot['parameters']))
        self.assertEqual(self.GucParameter.objects.count(), 0)
        counts = report['coverage']['snapshots']
        self.assertEqual(sum(counts.values()), report['snapshots'])
        self.assertEqual(counts['same_as'],
                         sum(1 for item in self.snapshot['parameters']
                             for version in item['versions'].values()
                             if version['doc_same_as']))

    def smaller(self):
        """手册里的 devel 没了：20 那一版与两个只在 20 出现的参数跟着消失。"""
        from pgweb.docs.models import DocPage
        DocPage.objects.filter(version=0).delete()
        return export()

    def test_without_prune_missing_records_are_kept_and_reported(self):
        guc_importer.import_snapshot(self.snapshot)
        report = guc_importer.import_snapshot(self.smaller())
        self.assertEqual(report['missing'],
                         {'parameters': ['demo_fresh', 'demo_fresh_alone'], 'versions': ['20']})
        self.assertIn('未加 --prune', report['note'])
        self.assertEqual(self.GucParameter.objects.count(), 9)
        self.assertEqual(self.GucVersion.objects.count(), 4)

    def test_prune_removes_what_the_snapshot_dropped(self):
        guc_importer.import_snapshot(self.snapshot)
        report = guc_importer.import_snapshot(self.smaller(), prune=True)
        self.assertEqual(report['removed'], {'parameters': 2, 'versions': ['20']})
        self.assertEqual(self.GucParameter.objects.count(), 7)
        self.assertEqual(self.GucVersion.objects.count(), 3)

    def test_validate_says_which_field_is_missing(self):
        broken = json.loads(json.dumps(self.payload))
        del broken['parameters'][0]['position']
        with self.assertRaises(ValueError) as caught:
            guc_importer.validate(broken)
        self.assertIn('position', str(caught.exception))
        self.assertIn(broken['parameters'][0]['name'], str(caught.exception))

    def test_validate_rejects_other_broken_shapes(self):
        for mangle, needle in (
                (lambda s: s.update({'format': 99}), '快照格式'),
                (lambda s: s.update({'parameters': []}), 'parameters'),
                (lambda s: s['parameters'][0].update({'name': '1bad'}), '参数名'),
                (lambda s: s['parameters'][0]['versions'].update({'99': {}}), '未知版本'),
                (lambda s: s['versions'][0].pop('label'), 'label')):
            broken = json.loads(json.dumps(self.payload))
            mangle(broken)
            with self.assertRaises(ValueError) as caught:
                guc_importer.validate(broken)
            self.assertIn(needle, str(caught.exception))

    def test_digest_is_stable_and_notices_a_change(self):
        other = json.loads(json.dumps(self.payload))
        self.assertEqual(guc_importer.digest(self.payload), guc_importer.digest(other))
        other['parameters'][0]['position'] += 1
        self.assertNotEqual(guc_importer.digest(self.payload), guc_importer.digest(other))
