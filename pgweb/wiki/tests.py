import json

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from . import catalog, catalog_importer, errcode, importer, markup
from .columns import BY_SLUG, COLUMNS, listing, live_columns, nav_items, url
from .models import (CatalogRelation, CatalogVersion, ErrorCode, ErrorCodeClass,
                     ErrorCodeRelease, ErrorCodeText)


class ColumnTests(SimpleTestCase):
    def test_four_columns_in_reading_order(self):
        self.assertEqual([c['slug'] for c in COLUMNS], ['sqlstate', 'guc', 'waitevent', 'catalog'])
        self.assertEqual(set(BY_SLUG), {'sqlstate', 'guc', 'waitevent', 'catalog'})

    def test_a_column_in_preparation_links_to_its_origin_site(self):
        """Navigation must never point at a route that does not exist yet."""
        for column in COLUMNS:
            if column['live']:
                self.assertEqual(url(column), '/docs/{}/'.format(column['slug']))
            else:
                self.assertEqual(url(column), column['origin'])

    def test_tone_travels_as_a_class(self):
        """The site CSP forbids inline styles, so colour must be a class."""
        for column in listing():
            self.assertTrue(column['tone_class'].startswith('wiki-tone-'))

    def test_nav_lists_the_four_columns(self):
        items = nav_items()
        self.assertEqual(items[0], {'title': 'SQL 状态码', 'link': '/docs/sqlstate/'})
        self.assertEqual(len(items), len(COLUMNS))


class MarkupTests(SimpleTestCase):
    def test_sections_split_on_anchored_headings(self):
        sections = markup.split_sections('## 速览 {#at-a-glance}\n正文。\n\n## 诊断 {#diagnosis}\n更多。')
        self.assertEqual([s['anchor'] for s in sections], ['at-a-glance', 'diagnosis'])
        self.assertEqual(sections[0]['heading'], '速览')

    def test_generated_fact_table_is_dropped(self):
        """事实表改由数据库渲染，正文里那份生成块整块摘掉。"""
        body = 'before\n\n<!-- BEGIN SQLSTATE FACTS: generated -->\n| a | b |\n<!-- END SQLSTATE FACTS -->\n\nafter'
        cleaned = markup.strip_generated(body)
        self.assertNotIn('| a | b |', cleaned)
        self.assertIn('before', cleaned)
        self.assertIn('after', cleaned)

    def test_snippet_markers_keep_their_sql(self):
        body = '<!-- BEGIN SQLSTATE SNIPPET: demo -->\n```sql\nSELECT 1;\n```\n<!-- END SQLSTATE SNIPPET -->'
        self.assertEqual(markup.snippet_ids(body), ['demo'])
        self.assertIn('SELECT 1;', markup.strip_generated(body))

    def test_first_sentence_is_plain_text(self):
        """索引页表格里的一句话说明不能漏出 Markdown 标记。"""
        self.assertEqual(
            markup.first_sentence('08000 是 Class 08 中的 **connection_exception**。还有下一句。'),
            '08000 是 Class 08 中的 connection_exception。')
        self.assertEqual(markup.first_sentence('见 [证据](../data/evidence/x.json) 一节。'),
                         '见 证据 一节。')

    def test_tables_survive_rendering(self):
        html = markup.render('| a | b |\n| --- | --- |\n| 1 | 2 |')
        self.assertIn('<table>', html)


class LinkRewriteTests(SimpleTestCase):
    def rewrite(self, body, has_doc=False):
        return importer.rewrite_links(body, lambda version, filename: has_doc)

    def test_code_links_become_uppercase_site_links(self):
        self.assertEqual(self.rewrite('见 [25P02](../25p02/)。'),
                         '见 [25P02](/docs/sqlstate/25P02/)。')
        self.assertEqual(self.rewrite('见 [HV00J](../../hv00j/)。'),
                         '见 [HV00J](/docs/sqlstate/HV00J/)。')

    def test_evidence_and_case_links_point_at_page_anchors(self):
        self.assertEqual(self.rewrite('[证据](../data/evidence/23505.json)'), '[证据](#sources)')
        self.assertEqual(self.rewrite('[用例](../../data/cases/23505.json)'), '[用例](#cases)')

    def test_guides_link_becomes_plain_text(self):
        """驱动指南没有搬进本站，留文字去链接，不留死链。"""
        self.assertEqual(self.rewrite('参见[驱动指南](../guides/)。'), '参见驱动指南。')

    def test_manual_links_go_local_only_when_the_page_exists(self):
        upstream = '见 https://www.postgresql.org/docs/18/errcodes-appendix.html 一节'
        self.assertIn('/docs/18/errcodes-appendix.html', self.rewrite(upstream, has_doc=True))
        self.assertIn('https://www.postgresql.org/docs/18/', self.rewrite(upstream, has_doc=False))

    def test_source_links_are_left_alone(self):
        """源码链接锚在固定提交上，原样保留正是要的效果。"""
        link = 'https://github.com/postgres/postgres/blob/724edf9b/src/x.c#L640-L674'
        self.assertEqual(self.rewrite(link), link)


class TemplateFlattenTests(SimpleTestCase):
    def test_every_template_shape_is_captured(self):
        """565 条报文里只有 539 条走 primary_template，其余形态不能漏。"""
        rows = importer.flatten_templates({
            'id': 'm', 'primary_template': 'a "%s"', 'detail_template': 'd %s',
            'hint_template': 'h', 'primary_template_singular': 'one', 'primary_template_plural': 'many',
            'detail_templates': ['d1', 'd2'], 'roles': [{'role': 'reader', 'template': 'r'}],
            'primary_variants': [{'target': 'pg18', 'template': 'v'}],
        })
        kinds = {(row['kind'], row['role']) for row in rows}
        self.assertIn(('primary', ''), kinds)
        self.assertIn(('primary', 'singular'), kinds)
        self.assertIn(('primary', 'plural'), kinds)
        self.assertIn(('primary', 'reader'), kinds)
        self.assertIn(('primary', 'pg18'), kinds)
        self.assertIn(('detail', ''), kinds)
        self.assertIn(('hint', ''), kinds)
        self.assertEqual(sum(1 for r in rows if r['kind'] == 'detail'), 3)

    def test_literal_strips_placeholders_for_lookup(self):
        rows = importer.flatten_templates({'primary_template': 'duplicate key value violates unique constraint "%s"'})
        self.assertEqual(rows[0]['literal'], 'duplicate key value violates unique constraint " "')

    def test_identical_templates_are_not_repeated(self):
        rows = importer.flatten_templates({'primary_template': 'same', 'message': 'same'})
        self.assertEqual(len(rows), 1)


class EvidenceTierTests(SimpleTestCase):
    def test_a_code_takes_its_strongest_evidence(self):
        """证据状态挂在单条证据上，一个码可以同时有好几档。"""
        self.assertEqual(importer.evidence_tier([
            {'status': 'definition_only'}, {'status': 'observed_runtime'}, {'status': 'unknown'},
        ]), 'observed_runtime')
        self.assertEqual(importer.evidence_tier([{'status': 'unknown'}]), 'unknown')
        self.assertEqual(importer.evidence_tier([]), '')


class FrontMatterTests(SimpleTestCase):
    def test_nested_translation_block_is_read(self):
        data, body = importer.front_matter(
            '---\ntitle: "23505 — x"\ncontent_depth: full\ntranslation:\n  source_lang: en\n'
            '  source_rev: "abc"\n---\n正文')
        self.assertEqual(data['content_depth'], 'full')
        self.assertEqual(data['translation']['source_rev'], 'abc')
        self.assertEqual(body, '正文')

    def test_chinese_name_handles_every_title_shape(self):
        cases = [
            ('23505 — unique_violation：唯一性冲突', 'unique_violation', '唯一性冲突'),
            ('01000 — warning（警告）', 'warning', '警告'),
            ('25P02 — 事务处于失败状态（in_failed_sql_transaction）', 'in_failed_sql_transaction', '事务处于失败状态'),
            ('00000 — successful_completion', 'successful_completion', ''),
        ]
        for title, condition, expected in cases:
            self.assertEqual(importer.chinese_name(title, title[:5], condition), expected)


class FactTrimTests(SimpleTestCase):
    def test_bulk_audit_arrays_stay_out_of_the_留底(self):
        """逐补丁版审计数组压成区间存表，不重复塞进 facts。"""
        trimmed = importer.trim_facts({
            'sqlstate': '23505', 'observed_rows': [1] * 300, 'evidence_refs': ['x'] * 500,
            'author_evidence': {'big': True},
            'presence_intervals': [{'start': '9.0.0', 'evidence_refs': ['x'] * 100}],
        })
        self.assertEqual(trimmed['sqlstate'], '23505')
        for key in ('observed_rows', 'evidence_refs', 'author_evidence'):
            self.assertNotIn(key, trimmed)
        self.assertEqual(trimmed['presence_intervals'], [{'start': '9.0.0'}])


class ErrorCodePageTests(TestCase):
    """用一份最小快照跑通导入与两个页面。"""

    @classmethod
    def setUpTestData(cls):
        importer.import_snapshot(snapshot())

    def setUp(self):
        cache.clear()

    def test_import_lands_every_table(self):
        self.assertEqual(ErrorCode.objects.count(), 3)
        self.assertEqual(ErrorCodeClass.objects.count(), 1)
        self.assertEqual(ErrorCodeRelease.objects.count(), 1)
        self.assertEqual(ErrorCodeText.objects.filter(lang='zh').count(), 1)
        code = ErrorCode.objects.get(sqlstate='23505')
        self.assertEqual(code.evidence_tier, 'observed_runtime')
        self.assertEqual(code.templates.count(), 2)

    def test_import_is_idempotent(self):
        report = importer.import_snapshot(snapshot())
        self.assertEqual(report['unchanged'], 3)
        self.assertEqual(report['updated'], 0)

    def test_index_groups_by_class(self):
        response = self.client.get('/docs/sqlstate/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('导航索引', html)
        self.assertIn('id="class-23"', html)
        self.assertIn('23505', html)
        self.assertIn('唯一性冲突', html)

    def test_detail_renders_prose_and_panels(self):
        html = self.client.get('/docs/sqlstate/23505/').content.decode()
        self.assertIn('unique_violation', html)
        self.assertIn('报文模板', html)
        self.assertIn('duplicate key value', html)
        self.assertIn('证据', html)
        self.assertIn('src/backend/x.c', html)
        self.assertIn('unique_violation condition', html)

    def test_a_code_without_evidence_still_renders(self):
        response = self.client.get('/docs/sqlstate/23000/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('报文模板', response.content.decode())

    def test_lowercase_redirects_to_the_canonical_uppercase(self):
        response = self.client.get('/docs/sqlstate/23505/'.replace('23505', '23p01'.upper().lower()))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/docs/sqlstate/23P01/')

    def test_unknown_code_is_404(self):
        self.assertEqual(self.client.get('/docs/sqlstate/ZZZZZ/').status_code, 404)
        self.assertEqual(self.client.get('/docs/sqlstate/toolong/').status_code, 404)

    def test_sitemap_lists_every_code(self):
        from .struct import get_struct
        pages = [page for page, _ in get_struct()]
        self.assertIn('docs/sqlstate/', pages)
        self.assertIn('docs/sqlstate/23505/', pages)

    def test_panels_fall_back_when_the_matching_section_is_missing(self):
        """正文没有 messages 一节时，报文面板挂到含义那一节后面。"""
        sections = [{'anchor': 'meaning', 'heading': '含义'}, {'anchor': 'versions', 'heading': '版本'}]
        order = [b['type'] for b in errcode.blocks(sections, ['m'], [], [], [], [])]
        self.assertEqual(order, ['section', 'templates', 'section'])

    def test_preview_release_is_not_the_default_version(self):
        code = ErrorCode.objects.get(sqlstate='23505')
        code.present_in = ['17', '18', '19']
        code.preview_in = ['19']
        self.assertEqual(code.version_range, '17 – 18')


def snapshot():
    """两个码的最小快照：一个证据齐全，一个什么都没有。"""
    codes = []
    for sqlstate, tier, with_evidence in (('23505', 'observed_runtime', True),
                                          ('23000', 'definition_only', False),
                                          ('23P01', 'definition_only', False)):
        codes.append({
            'sqlstate': sqlstate, 'class_code': '23', 'condition_name': 'unique_violation',
            'condition_names': ['unique_violation'], 'aliases': [], 'macros': ['ERRCODE_X'],
            'primary_macro': 'ERRCODE_X', 'severity_classes': ['E'], 'status': 'active',
            'introduced': None, 'removed': None, 'known_present_by': '7.4',
            'present_in': ['18'], 'preview_in': [], 'depth': 'full',
            'editorial_review': 'reviewed', 'runtime_verification': 'passed',
            'evidence_tier': tier, 'case_count': 0, 'snippet_count': 0,
            'facts': {'sqlstate': sqlstate}, 'source_rev': 'rev-' + sqlstate,
            'texts': [{'lang': 'zh', 'title': sqlstate + ' — unique_violation：唯一性冲突',
                       'name': '唯一性冲突', 'description': '说明', 'summary': '一句话。',
                       'body_md': '## 含义 {#meaning}\n正文。', 'sections': [
                           {'anchor': 'meaning', 'heading': '含义', 'html': '<p>正文。</p>'}],
                       'translation_source_rev': 'abc'}] if sqlstate == '23505' else [],
            'cases': [], 'presence': [], 'runtimes': [],
            'sources': [{'source_id': 's1', 'kind': 'upstream_source', 'tag': 'REL_18_6',
                         'commit': 'b' * 40, 'path': 'src/backend/x.c', 'location': 'lines 1-2',
                         'url': 'https://github.com/postgres/postgres/blob/bbbb/src/backend/x.c#L1-L2',
                         'docs_url': '', 'sha256': '', 'position': 0}] if with_evidence else [],
            'claims': [{'claim_id': 'c1', 'statement': 'It is the unique_violation condition.',
                        'method': 'Read errcodes.txt.', 'limits': 'Directory identity only.',
                        'sources': ['s1'], 'runtime': [], 'position': 0}] if with_evidence else [],
            'messages': [{
                'message_id': 'm1', 'severity': 'E', 'path': '', 'limits': '', 'sources': [],
                'raw': {}, 'position': 0,
                'templates': [
                    {'kind': 'primary', 'role': '',
                     'template': 'duplicate key value violates unique constraint "%s"',
                     'literal': 'duplicate key value violates unique constraint " "'},
                    {'kind': 'detail', 'role': '', 'template': 'Key %s already exists.',
                     'literal': 'Key already exists.'},
                ],
            }] if with_evidence else [],
        })
    return {
        'format': importer.FORMAT, 'generated_at': '2026-09-11', 'root': '/tmp',
        'classes': [{'code': '23', 'name': 'Integrity Constraint Violation',
                     'name_zh': '完整性约束冲突', 'summary': '类别说明。',
                     'sqlstate_count': 3, 'severity_classes': ['E']}],
        'releases': [{'major': '18', 'channel': 'formal', 'release': '18.6', 'tag': 'REL_18_6',
                      'commit': 'a' * 40, 'path': 'src/x', 'code_count': 263, 'position': 0}],
        'codes': codes,
    }


# ================================================================ 系统目录

# 两种手册表格式各造一份，字段与描述由下面的 spec 生成，读起来和真手册同形。
# 每行 spec：(字段名, 手册写的类型, 中文描述, 引用或 '')。

SINGLE_ROW = '''            <tr>
              <td class="catalog_table_entry">
                <p class="column_definition"><code class="structfield">{name}</code> <code class="type">{type}</code>{reference}</p>

                <p>{description}</p>
              </td>
            </tr>'''
SINGLE_REFERENCE = (' （引用 <a class="link" href="catalog-{target}.html">'
                    '<code class="structname">{relation}</code></a>.<code class="structfield">{column}</code>）')
FOUR_ROW = '''<tr>
<td><code class="structfield">{name}</code></td>
<td><code class="type">{type}</code></td>
<td>{reference}</td>
<td>{description}</td>
</tr>'''
FOUR_REFERENCE = ('<code class="literal"><a class="link" href="catalog-{target}.html">'
                  '<code class="structname">{relation}</code></a>.{column}</code>')


def reference_markup(template, value):
    if not value:
        return '' if 'literal' in template else ''
    relation, _, column = value.partition('.')
    return template.format(target=relation.replace('_', '-'), relation=relation, column=column)


def single_column_page(name, spec, lead, number='52.1'):
    """PG13+ 单列格式：`p.column_definition` 给字段名与类型，后面的 `<p>` 是描述。"""
    rows = '\n'.join(SINGLE_ROW.format(name=field, type=type_name, description=description,
                                       reference=reference_markup(SINGLE_REFERENCE, reference))
                     for field, type_name, description, reference in spec)
    return '''<div class="sect1" id="CATALOG-{upper}">
  <div class="titlepage"><div><div><h2 class="title">{number}.&nbsp;<code class="structname">{name}</code></h2></div></div></div><a id="id-1" class="indexterm" name="id-1"></a>

  <p>{lead}</p>

  <div class="table" id="id-2">
    <p class="title"><strong>Table&nbsp;{number}.&nbsp;<code class="structname">{name}</code> 列</strong></p>

    <div class="table-contents">
      <table class="table" summary="{name} 列" border="1">
        <colgroup><col /></colgroup>
        <thead><tr><th class="catalog_table_entry"><p class="column_definition">列类型</p><p>描述</p></th></tr></thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>
  </div>
</div>'''.format(name=name, upper=name.upper().replace('_', '-'), number=number, lead=lead, rows=rows)


def four_column_page(name, spec, lead, number='51.1'):
    """PG10 – 12 四列格式：名称 / 类型 / 引用 / 描述。"""
    rows = '\n'.join(FOUR_ROW.format(name=field, type=type_name, description=description,
                                     reference=reference_markup(FOUR_REFERENCE, reference) or '&nbsp;')
                     for field, type_name, description, reference in spec)
    return '''<div class="sect1" id="CATALOG-{upper}">
<div class="titlepage"><div><div><h2 class="title">{number}.&nbsp;<code class="structname">{name}</code></h2></div></div></div>
<p>{lead}</p>
<div class="table" id="id-2">
<p class="title"><strong>Table&nbsp;{number}.&nbsp;<code class="structname">{name}</code> 列</strong></p>
<div class="table-contents">
<table class="table" summary="{name} 列" border="1">
<colgroup><col /><col /><col /><col /></colgroup>
<thead><tr><th>Name</th><th>类型</th><th>引用</th><th>描述</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</div>
</div>
</div>'''.format(name=name, upper=name.upper().replace('_', '-'), number=number, lead=lead, rows=rows)


def statistics_page(name, spec, lead, number='27.3'):
    """统计视图落在 monitoring-stats.html 里，表 div 自己带锚点。"""
    page = single_column_page(name, spec, lead, number)
    return page.replace('<div class="table" id="id-2">',
                        '<div class="table" id="{}-VIEW">'.format(name.upper().replace('_', '-')))


DEMO_SPEC = [('oid', 'oid', '行标识符', ''),
             ('demoname', 'name', '演示对象的名字', ''),
             ('demoowner', 'oid', '演示对象的拥有者', 'pg_authid.oid')]
# 12 多一个字段，devel 再多一个。手册与 cat 的快照要对得上，否则会被当成手册老账。
DEMO_12_SPEC = DEMO_SPEC + [('demoextra', 'bool', '12 新增的布尔字段', '')]
DEMO_DEVEL_SPEC = DEMO_12_SPEC + [('demoflags', 'int4', '开发版新增的标志位', '')]
# 手册记着、运行时没有的字段：PG 18 删了 pg_stat_wal.wal_write，中文手册还留着。
GHOST = ('demoghost', 'bool', '手册还记着、运行时已经没有的字段', '')
GONE_SPEC = [('goneid', 'oid', '已移除目录表的标识', '')]
STAT_SPEC = [('pid', 'integer', '后端的进程 ID', ''),
             ('query', 'text', '当前查询', '')]
FRESH_SPEC = [('freshid', 'oid', '新视图的标识', '')]

DEMO_LEAD = '目录<code class="structname">pg_demo</code>记录演示对象。'
DEMO_OLD_LEAD = '目录<code class="structname">pg_demo</code>记录演示对象（旧版措辞）。'

PAGE_DEMO_SINGLE = single_column_page('pg_demo', DEMO_SPEC, DEMO_LEAD)
PAGE_DEMO_12 = single_column_page('pg_demo', DEMO_12_SPEC, DEMO_LEAD)
PAGE_DEMO_FOUR = four_column_page(
    'pg_demo', [(f, t, d + '（四列格式）', r) for f, t, d, r in DEMO_SPEC], DEMO_OLD_LEAD)
PAGE_DEMO_DEVEL = single_column_page('pg_demo', DEMO_DEVEL_SPEC, DEMO_LEAD)
PAGE_GONE_SINGLE = single_column_page('pg_gone', GONE_SPEC, '已经移除的目录表。', '52.2')
PAGE_GONE_FOUR = four_column_page(
    'pg_gone', [(f, t, d + '（四列格式）', r) for f, t, d, r in GONE_SPEC], '已经移除的目录表。', '51.2')
PAGE_STAT = statistics_page('pg_stat_demo', STAT_SPEC, '每个演示对象一行。')
PAGE_FRESH = single_column_page('pg_fresh', FRESH_SPEC, '视图<code class="structname">pg_fresh</code>是开发版新增的视图。', '53.9')

OVERVIEW = '''<div class="sect1" id="CATALOGS-OVERVIEW">
<div class="table" id="CATALOG-TABLE"><p class="title"><strong>Table&nbsp;52.1.&nbsp;系统目录</strong></p>
<div class="table-contents"><table class="table" summary="系统目录" border="1"><colgroup><col /><col /></colgroup>
<thead><tr><th>目录名</th><th>用途</th></tr></thead>
<tbody>
<tr><td><a class="link" href="catalog-pg-demo.html"><code class="structname">pg_demo</code></a></td><td>演示用的目录表</td></tr>
<tr><td><a class="link" href="catalog-pg-gone.html"><code class="structname">pg_gone</code></a></td><td>已经移除的目录表</td></tr>
</tbody></table></div></div></div>'''

VIEWS_OVERVIEW = '''<div class="sect1" id="VIEWS-OVERVIEW">
<div class="table" id="VIEW-TABLE"><p class="title"><strong>Table&nbsp;53.1.&nbsp;系统视图</strong></p>
<div class="table-contents"><table class="table" summary="系统视图" border="1"><colgroup><col /><col /></colgroup>
<thead><tr><th>视图名称</th><th>用途</th></tr></thead>
<tbody><tr><td><a class="link" href="view-pg-fresh.html"><code class="structname">pg_fresh</code></a></td><td>开发版新增的视图</td></tr>
</tbody></table></div></div></div>'''


def column(name, type_name, description, **extra):
    row = {'name': name, 'type': type_name, 'description': description, 'hidden': False,
           'not_null': False, 'attnum': extra.pop('attnum', 1), 'type_modifier': -1,
           'array_dimensions': 0, 'type_oid': 26}
    row.update(extra)
    return row


def cat_snapshot(description, columns, major, filename='catalog-pg-demo.html', anchor=''):
    """cat 原始快照的形状（未裁剪），导出流程会自己裁。"""
    return {
        'description': description, 'columns': columns,
        'source_url': 'https://www.postgresql.org/docs/{}/{}{}'.format(
            major, filename, '#' + anchor if anchor else ''),
        'source_path': 'sources/postgresql/{}/{}'.format(major, filename),
        'schema_source': 'runtime+documentation',
        'definition_source_url': 'https://raw.githubusercontent.com/postgres/postgres/'
                                 'REL_{}_1/src/include/catalog/pg_demo.h'.format(major),
        'definition_source_path': 'sources/x.h', 'documentary_schema_source': 'documentation',
        'source_column_count': len(columns), 'relation_oid': 4242, 'shared': False, 'relkind': 'r',
        'system_columns': [{'name': 'tableoid', 'type': 'oid', 'attnum': -6}],
        'runtime_validation': {'release': major + '.1', 'passed': True, 'sha256': 'x' * 64,
                               'source_path': 'sources/runtime/{}.json'.format(major)},
    }


def cat_payload():
    """三个关系 × 三个版本的最小 cat 数据集，含一个在 12 移除的关系。"""
    demo_10 = [column('oid', 'oid', 'Row identifier'),
               column('demoname', 'name', 'Name of the demo object', attnum=2),
               column('demoowner', 'oid', 'Owner of the demo object', attnum=3,
                      references='pg_authid.oid')]
    demo_11 = [dict(c) for c in demo_10]
    demo_12 = [dict(c) for c in demo_10] + [column('demoextra', 'boolean', 'Added in 12', attnum=4)]
    gone = [column('goneid', 'oid', 'Row identifier')]
    stat = [column('pid', 'integer', 'Process ID'),
            column('query', 'text', 'Current query', attnum=2)]
    relations = [
        {'name': 'pg_demo', 'kind': 'catalog', 'summary': 'demo objects',
         'first_version': '10', 'last_version': '12',
         'versions': {'10': cat_snapshot('The catalog pg_demo records demo objects.', demo_10, '10'),
                      '11': cat_snapshot('The catalog pg_demo records demo objects.', demo_11, '11'),
                      '12': cat_snapshot('The catalog pg_demo records demo objects, reworded.',
                                         demo_12, '12')},
         'changes': [{'from': '11', 'to': '12', 'status': 'changed',
                      'added_columns': [column('demoextra', 'boolean', 'Added in 12', attnum=4)],
                      'removed_columns': [], 'type_changes': [],
                      'description_changes': [], 'reference_changes': [], 'attribute_changes': [],
                      'relation_description_changed': True, 'column_order_changed': False,
                      'structural': True}]},
        {'name': 'pg_gone', 'kind': 'catalog', 'summary': 'removed catalog',
         'first_version': '10', 'last_version': '11',
         'versions': {'10': cat_snapshot('Gone in 12.', gone, '10', 'catalog-pg-gone.html'),
                      '11': cat_snapshot('Gone in 12.', gone, '11', 'catalog-pg-gone.html')},
         'changes': [{'from': '11', 'to': '12', 'status': 'removed', 'added_columns': [],
                      'removed_columns': gone, 'type_changes': [], 'description_changes': [],
                      'reference_changes': [], 'attribute_changes': [],
                      'relation_description_changed': False, 'column_order_changed': False,
                      'structural': True}]},
        {'name': 'pg_stat_demo', 'kind': 'statistics', 'summary': 'demo statistics',
         'first_version': '11', 'last_version': '12',
         'versions': {'11': cat_snapshot('One row per demo.', stat, '11', 'monitoring-stats.html',
                                         'PG-STAT-DEMO-VIEW'),
                      '12': cat_snapshot('One row per demo.', stat, '12', 'monitoring-stats.html',
                                         'PG-STAT-DEMO-VIEW')},
         'changes': [{'from': '10', 'to': '11', 'status': 'added',
                      'added_columns': [dict(c) for c in stat], 'removed_columns': [],
                      'type_changes': [], 'description_changes': [], 'reference_changes': [],
                      'attribute_changes': [], 'relation_description_changed': False,
                      'column_order_changed': False, 'structural': True}]},
    ]
    versions = []
    for major in ('10', '11', '12'):
        present = [r for r in relations if major in r['versions']]
        versions.append({
            'id': major, 'label': major,
            'status': 'stable' if major == '12' else 'historical',
            'support_status': 'supported' if major == '12' else 'end-of-life',
            'source_tag': 'REL_{}_1'.format(major), 'documentation_version': major + '.1',
            'release': major + '.1', 'runtime_verified': True,
            'relation_count': len(present),
            'column_count': sum(len(r['versions'][major]['columns']) for r in present),
            'kinds': {'catalog': sum(1 for r in present if r['kind'] == 'catalog'), 'view': 0,
                      'statistics': sum(1 for r in present if r['kind'] == 'statistics'),
                      'progress': 0},
        })
    transitions = []
    for left, right in (('10', '11'), ('11', '12')):
        transitions.append({'from': left, 'to': right,
                            'added_relations': ['pg_stat_demo'] if right == '11' else [],
                            'removed_relations': ['pg_gone'] if right == '12' else [],
                            'changed_relations': ['pg_demo'] if right == '12' else [],
                            'structurally_changed_relations': ['pg_demo'] if right == '12' else [],
                            'added_columns': 1 if right == '12' else 0, 'removed_columns': 0,
                            'type_changes': 0, 'description_changes': 0})
    return {'schema_version': '1.0', 'generated_at': '2026-09-08', 'snapshot_date': '2026-09-08',
            'default_version': '12', 'preview_version': '', 'scope': {},
            'versions': versions, 'relations': relations, 'transitions': transitions,
            'stats': {'version_count': 3}}


def write_cat(root, payload=None):
    import os as _os
    _os.makedirs(_os.path.join(root, 'data'), exist_ok=True)
    with open(_os.path.join(root, 'data', 'catalog.json'), 'w', encoding='utf-8') as handle:
        json.dump(payload or cat_payload(), handle, ensure_ascii=False)
    return root


def export(payload=None):
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        write_cat(root, payload)
        return catalog_importer.export_snapshot(root)


def load_manuals(devel=True):
    """本站手册：10 四列格式，11 与 12 单列格式，外加一份 devel 手册。"""
    from datetime import date
    from pgweb.core.models import Version
    from pgweb.docs.models import DocPage
    trees = [10, 11, 12] + ([0] if devel else [])
    Version.objects.bulk_create([
        Version(tree=tree, current=tree == 12, reldate=date(2025, 9, 1),
                firstreldate=date(2025, 9, 1), eoldate=date(2030, 1, 1))
        for tree in trees])
    pages = {
        10: [('catalog-pg-demo.html', PAGE_DEMO_FOUR), ('catalog-pg-gone.html', PAGE_GONE_FOUR)],
        11: [('catalog-pg-demo.html', PAGE_DEMO_SINGLE), ('catalog-pg-gone.html', PAGE_GONE_SINGLE),
             ('monitoring-stats.html', PAGE_STAT)],
        12: [('catalog-pg-demo.html', PAGE_DEMO_12), ('catalogs-overview.html', OVERVIEW),
             ('monitoring-stats.html', PAGE_STAT)],
    }
    if devel:
        pages[0] = [('catalog-pg-demo.html', PAGE_DEMO_DEVEL), ('view-pg-fresh.html', PAGE_FRESH),
                    ('catalogs-overview.html', OVERVIEW), ('views-overview.html', VIEWS_OVERVIEW)]
    for tree, items in pages.items():
        for filename, body in items:
            DocPage.objects.create(file=filename, version_id=tree, title=filename, content=body)


class CatalogParseTests(SimpleTestCase):
    """两种手册表格式与类型规范化。"""

    def soup(self, html):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, 'html.parser')

    def test_single_column_format_gives_name_type_reference_and_text(self):
        div = catalog_importer.locate_table(self.soup(PAGE_DEMO_SINGLE), 'pg_demo')
        rows = catalog_importer.parse_columns(div, 'pg_demo')
        self.assertEqual([row['name'] for row in rows], ['oid', 'demoname', 'demoowner'])
        self.assertEqual(rows[1]['documented_type'], 'name')
        self.assertEqual(rows[2]['references'], 'pg_authid.oid')
        self.assertEqual(rows[1]['description_zh'], '演示对象的名字')

    def test_four_column_format_gives_the_same_shape(self):
        div = catalog_importer.locate_table(self.soup(PAGE_DEMO_FOUR), 'pg_demo')
        rows = catalog_importer.parse_columns(div, 'pg_demo')
        self.assertEqual([row['name'] for row in rows], ['oid', 'demoname', 'demoowner'])
        self.assertEqual(rows[2]['references'], 'pg_authid.oid')
        self.assertEqual(rows[0]['description_zh'], '行标识符（四列格式）')

    def test_relation_description_stops_at_the_table(self):
        div = catalog_importer.locate_table(self.soup(PAGE_DEMO_SINGLE), 'pg_demo')
        self.assertEqual(catalog_importer.relation_description(div), '目录pg_demo记录演示对象。')

    def test_documented_type_shorthand_is_normalised(self):
        for written, expected in (('int4', 'integer'), ('bool', 'boolean'), ('char', '"char"'),
                                  ('timestamptz', 'timestamp with time zone'),
                                  ('float4[]', 'real[]'), ('name', 'name')):
            self.assertEqual(catalog_importer.canonical_type(written), expected)

    def test_a_table_is_found_even_when_the_anchor_moved(self):
        """同一关系在不同版本的锚点并不一致，锚点缺失要退回标题匹配。"""
        soup = self.soup(PAGE_DEMO_SINGLE)
        self.assertIsNotNone(catalog_importer.locate_table(soup, 'pg_demo', 'NO-SUCH-ANCHOR'))
        self.assertIsNone(catalog_importer.locate_table(soup, 'pg_other'))


class CatalogExportTests(TestCase):
    """完整导出：中文采集、译文回退、20 推导。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()

    def snapshot(self):
        return export()

    def test_versions_carry_position_and_the_devel_row(self):
        snapshot = self.snapshot()
        self.assertEqual([v['major'] for v in snapshot['versions']], ['10', '11', '12', '20'])
        self.assertEqual([v['position'] for v in snapshot['versions']], [0, 1, 2, 3])
        devel = snapshot['versions'][-1]
        self.assertEqual((devel['label'], devel['status'], devel['support_status']),
                         ('20 devel', 'devel', 'devel'))
        self.assertEqual((devel['source_tag'], devel['documentation_version'], devel['doc_slug']),
                         ('master', 'devel', 'devel'))
        self.assertFalse(devel['runtime_verified'])
        self.assertEqual(devel['schema_source'], 'documentation')

    def test_harvest_reads_both_table_formats(self):
        relation = {r['name']: r for r in self.snapshot()['relations']}['pg_demo']
        self.assertEqual(relation['versions']['10']['columns'][0]['description_zh'],
                         '行标识符（四列格式）')
        self.assertEqual(relation['versions']['10']['columns'][0]['zh_from'], 'doc')
        self.assertEqual(relation['versions']['12']['columns'][0]['description_zh'], '行标识符')
        self.assertEqual(relation['versions']['12']['description_zh'], '目录pg_demo记录演示对象。')

    def test_translation_is_inherited_only_on_identical_english(self):
        """11 没有自己的译文表描述时借 12 的；英文改了的那一版不借。"""
        relations = {r['name']: r for r in self.snapshot()['relations']}
        gone = relations['pg_gone']
        # pg_gone 在 12 已移除，10 与 11 的英文完全相同，10 有四列格式译文。
        self.assertEqual(gone['versions']['10']['columns'][0]['zh_from'], 'doc')
        self.assertEqual(gone['versions']['11']['columns'][0]['zh_from'], 'doc')
        demo = relations['pg_demo']
        # 12 的关系说明英文改过（reworded），不能借 11 的译文。
        self.assertEqual(demo['versions']['11']['description'],
                         demo['versions']['10']['description'])
        self.assertNotEqual(demo['versions']['12']['description'],
                            demo['versions']['11']['description'])

    def test_summary_zh_comes_from_the_overview_table(self):
        relations = {r['name']: r for r in self.snapshot()['relations']}
        self.assertEqual(relations['pg_demo']['summary_zh'], '演示用的目录表')
        self.assertEqual(relations['pg_gone']['summary_zh'], '已经移除的目录表')

    def test_devel_snapshot_is_derived_from_the_local_devel_manual(self):
        snapshot = self.snapshot()
        relations = {r['name']: r for r in snapshot['relations']}
        devel = relations['pg_demo']['versions']['20']
        names = [column['name'] for column in devel['columns']]
        self.assertEqual(names, ['oid', 'demoname', 'demoowner', 'demoextra', 'demoflags'])
        added = next(c for c in devel['columns'] if c['name'] == 'demoflags')
        self.assertEqual(added['type'], 'integer')          # 手册写 int4
        self.assertEqual(added['documented_type'], 'int4')
        self.assertEqual(added['description'], '')          # 20 新增字段英文留空
        self.assertEqual(added['description_zh'], '开发版新增的标志位')
        carried = next(c for c in devel['columns'] if c['name'] == 'demoname')
        self.assertEqual(carried['description'], 'Name of the demo object')
        self.assertEqual(devel['schema_source'], 'documentation')
        self.assertIsNone(devel['relation_oid'])
        self.assertFalse(devel['runtime_verified'])
        self.assertIn('/docs/devel/', devel['source_url'])
        self.assertIn('/postgres/master/', devel['definition_source_url'])

    def test_devel_change_record_only_compares_names_types_and_order(self):
        relations = {r['name']: r for r in self.snapshot()['relations']}
        change = next(c for c in relations['pg_demo']['changes'] if c['to'] == '20')
        self.assertEqual([c['name'] for c in change['added_columns']], ['demoflags'])
        self.assertEqual(change['description_changes'], [])
        self.assertEqual(change['reference_changes'], [])
        self.assertEqual(change['attribute_changes'], [])
        self.assertFalse(change['relation_description_changed'])

    def test_a_relation_only_in_the_devel_manual_is_added_in_20(self):
        snapshot = self.snapshot()
        relations = {r['name']: r for r in snapshot['relations']}
        self.assertIn('pg_fresh', relations)
        fresh = relations['pg_fresh']
        self.assertEqual((fresh['kind'], fresh['first_version'], fresh['last_version']),
                         ('view', '20', '20'))
        self.assertEqual(fresh['summary_zh'], '开发版新增的视图')
        self.assertEqual(fresh['changes'][0]['status'], 'added')
        devel = next(v for v in snapshot['versions'] if v['major'] == '20')
        self.assertIn('pg_fresh', devel['transition']['added_relations'])

    def test_a_relation_the_devel_manual_dropped_is_absent_from_20(self):
        relations = {r['name']: r for r in self.snapshot()['relations']}
        self.assertNotIn('20', relations['pg_stat_demo']['versions'])
        self.assertEqual(relations['pg_stat_demo']['last_version'], '12')

    def alias_snapshot(self):
        """给数据集加一个只在源码里定义的变体：`alias_of` 指向 pg_demo，手册里没有它的表。"""
        payload = cat_payload()
        variant = json.loads(json.dumps(payload['relations'][0]))
        variant['name'] = 'pg_demo_alias'
        variant['kind'] = 'statistics'
        for major, snapshot in variant['versions'].items():
            snapshot['alias_of'] = 'pg_demo'
            snapshot['source_url'] = (
                'https://www.postgresql.org/docs/{}/monitoring-stats.html'.format(major))
        payload['relations'].append(variant)
        return export(payload)

    def test_variants_without_a_documented_table_carry_the_previous_columns(self):
        relation = {r['name']: r for r in self.alias_snapshot()['relations']}['pg_demo_alias']
        devel = relation['versions']['20']
        self.assertEqual(devel['carried_from'], '12')
        self.assertEqual(devel['carry_reason'], '手册没有这张表')
        self.assertEqual([c['name'] for c in devel['columns']],
                         [c['name'] for c in relation['versions']['12']['columns']])
        self.assertFalse(devel['runtime_verified'])
        self.assertIsNone(devel['relation_oid'])

    def test_alias_variants_borrow_the_base_translation_on_identical_english(self):
        relation = {r['name']: r for r in self.alias_snapshot()['relations']}['pg_demo_alias']
        borrowed = relation['versions']['12']['columns'][1]
        self.assertEqual(borrowed['description_zh'], '演示对象的名字')
        self.assertEqual(borrowed['zh_from'], 'inherited')

    def test_without_a_devel_manual_version_20_is_skipped(self):
        from pgweb.docs.models import DocPage
        DocPage.objects.filter(version=0).delete()
        snapshot = self.snapshot()
        self.assertEqual([v['major'] for v in snapshot['versions']], ['10', '11', '12'])
        self.assertFalse(snapshot['harvest']['devel']['derived'])
        self.assertIn('devel', snapshot['harvest']['devel']['reason'])

    def test_trimmed_snapshot_drops_the_bulk_runtime_record(self):
        relation = {r['name']: r for r in self.snapshot()['relations']}['pg_demo']
        snapshot = relation['versions']['12']
        for key in ('runtime_validation', 'source_path', 'definition_source_path',
                    'documentary_schema_source'):
            self.assertNotIn(key, snapshot)
        self.assertTrue(snapshot['runtime_verified'])
        self.assertEqual(snapshot['release'], '12.1')
        self.assertEqual(snapshot['doc'], {'file': 'catalog-pg-demo.html', 'anchor': '',
                                           'slug': '12'})


class CatalogImportTests(TestCase):
    """导入的幂等、校验与预览。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            write_cat(root)
            cls.payload = catalog_importer.export_snapshot(root)

    def setUp(self):
        cache.clear()
        catalog_importer.import_snapshot(json.loads(json.dumps(self.payload)))

    def test_import_lands_versions_and_relations(self):
        self.assertEqual(CatalogVersion.objects.count(), 4)
        self.assertEqual(CatalogRelation.objects.count(), 4)
        demo = CatalogRelation.objects.get(name='pg_demo')
        self.assertEqual(demo.present_in, ['10', '11', '12', '20'])
        self.assertEqual(demo.changed_in, ['12', '20'])
        self.assertEqual(demo.column_count, 5)
        self.assertEqual(demo.kind_label, '系统目录表')
        self.assertEqual(demo.eyebrow, 'SYSTEM CATALOG')

    def test_position_is_kind_order_then_name(self):
        rows = list(CatalogRelation.objects.values_list('name', 'kind'))
        self.assertEqual([kind for _, kind in rows],
                         ['catalog', 'catalog', 'view', 'statistics'])

    def test_import_is_idempotent_and_rewrites_nothing(self):
        report = catalog_importer.import_snapshot(json.loads(json.dumps(self.payload)))
        self.assertEqual(report['unchanged'], 4)
        self.assertEqual((report['added'], report['updated']), (0, 0))

    def test_a_changed_relation_is_the_only_one_rewritten(self):
        payload = json.loads(json.dumps(self.payload))
        target = next(r for r in payload['relations'] if r['name'] == 'pg_demo')
        target['summary_zh'] = '改过的一句话'
        report = catalog_importer.import_snapshot(payload)
        self.assertEqual((report['added'], report['updated'], report['unchanged']), (0, 1, 3))
        self.assertEqual(CatalogRelation.objects.get(name='pg_demo').summary_zh, '改过的一句话')

    def trimmed(self):
        """去掉一个关系和一个版本的快照。"""
        payload = json.loads(json.dumps(self.payload))
        payload['relations'] = [r for r in payload['relations'] if r['name'] != 'pg_gone']
        payload['versions'] = [v for v in payload['versions'] if v['major'] != '10']
        for relation in payload['relations']:
            relation['versions'].pop('10', None)
            relation['present_in'] = [m for m in relation['present_in'] if m != '10']
            relation['first_version'] = relation['present_in'][0]
        return payload

    def test_preview_writes_nothing(self):
        report = catalog_importer.preview(self.trimmed())
        self.assertEqual(report['missing'], {'relations': ['pg_gone'], 'versions': ['10']})
        self.assertIn('未加 --prune', report['note'])
        self.assertTrue(CatalogRelation.objects.filter(name='pg_gone').exists())
        self.assertTrue(CatalogVersion.objects.filter(major='10').exists())

    def test_without_prune_missing_records_are_kept_and_reported(self):
        report = catalog_importer.import_snapshot(self.trimmed())
        self.assertFalse(report['pruned'])
        self.assertEqual(report['missing'], {'relations': ['pg_gone'], 'versions': ['10']})
        self.assertEqual(report['removed'], {'relations': 0, 'versions': []})
        self.assertIn('版本 10', report['note'])
        self.assertTrue(CatalogRelation.objects.filter(name='pg_gone').exists())
        self.assertTrue(CatalogVersion.objects.filter(major='10').exists())

    def test_prune_removes_the_relations_and_versions_the_snapshot_dropped(self):
        report = catalog_importer.import_snapshot(self.trimmed(), prune=True)
        self.assertTrue(report['pruned'])
        self.assertEqual(report['removed'], {'relations': 1, 'versions': ['10']})
        self.assertFalse(CatalogRelation.objects.filter(name='pg_gone').exists())
        self.assertFalse(CatalogVersion.objects.filter(major='10').exists())

    def test_coverage_counts_every_translation_state(self):
        counts = catalog_importer.coverage(self.payload)['columns']
        self.assertEqual(sum(counts.values()),
                         sum(len(s['columns']) for r in self.payload['relations']
                             for s in r['versions'].values()))
        self.assertTrue(counts['doc'])

    def test_validate_rejects_a_broken_snapshot(self):
        for mutate, message in (
                (lambda s: s.update(format=99), '快照格式'),
                (lambda s: s.update(relations=[]), '快照缺少 relations'),
                (lambda s: s['relations'][0].update(name='PgDemo'), '关系名格式不对'),
                (lambda s: s['relations'][0].update(kind='mystery'), '类别不认识'),
                (lambda s: s['relations'][0].update(versions={'99': {}}), '未知版本'),
                (lambda s: s['relations'][0].pop('summary_zh'), '缺少字段：summary_zh'),
                (lambda s: s['versions'][0].pop('doc_slug'), '缺少字段：doc_slug')):
            payload = json.loads(json.dumps(self.payload))
            mutate(payload)
            with self.assertRaises(ValueError) as caught:
                catalog_importer.validate(payload)
            self.assertIn(message, str(caught.exception))


class CatalogPayloadTests(TestCase):
    """索引页、详情页与变更页的上下文形状。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            write_cat(root)
            catalog_importer.import_snapshot(catalog_importer.export_snapshot(root))

    def setUp(self):
        cache.clear()

    def test_index_groups_by_kind_in_reading_order(self):
        payload = catalog.index()
        self.assertEqual([g['kind'] for g in payload['groups']],
                         ['catalog', 'view', 'statistics'])
        self.assertEqual(payload['groups'][0]['anchor'], 'kind-catalog')
        self.assertEqual(payload['total'], 4)
        self.assertEqual(payload['default_major'], '12')
        self.assertEqual((payload['earliest_major'], payload['latest_major']), ('10', '20'))

    def test_strip_marks_added_changed_removed_and_absent(self):
        rows = {row['name']: row for group in catalog.index()['groups'] for row in group['rows']}
        demo = {cell['major']: cell['state'] for cell in rows['pg_demo']['strip']}
        self.assertEqual(demo, {'10': 'present', '11': 'present', '12': 'changed', '20': 'changed'})
        gone = {cell['major']: cell['state'] for cell in rows['pg_gone']['strip']}
        self.assertEqual(gone, {'10': 'present', '11': 'present', '12': 'removed', '20': 'absent'})
        self.assertTrue(rows['pg_gone']['removed'])
        self.assertEqual(rows['pg_gone']['removed_in'], '12')
        stat = {cell['major']: cell['state'] for cell in rows['pg_stat_demo']['strip']}
        self.assertEqual(stat['11'], 'added')
        self.assertEqual(stat['10'], 'absent')
        absent = next(c for c in rows['pg_gone']['strip'] if c['state'] == 'absent')
        self.assertEqual(absent['url'], '')

    def test_the_first_version_of_the_dataset_is_never_marked_added(self):
        """10 是这份数据的收录基线，不说「引入」。"""
        rows = {row['name']: row for group in catalog.index()['groups'] for row in group['rows']}
        self.assertEqual(rows['pg_demo']['strip'][0]['state'], 'present')

    def test_filters_count_kinds_versions_and_first_version(self):
        filters = {dd['param']: dd for dd in catalog.index()['filters']}
        self.assertEqual([dd for dd in filters], ['kind', 'present', 'first'])
        kinds = {o['value']: o['count'] for o in filters['kind']['options']}
        self.assertEqual(kinds, {'catalog': 2, 'view': 1, 'statistics': 1})
        present = {o['value']: o['count'] for o in filters['present']['options']}
        self.assertEqual(present['10'], 2)
        self.assertEqual(present['20'], 2)

    def test_detail_defaults_to_the_stable_version_and_honours_v(self):
        payload = catalog.detail('pg_demo')
        self.assertEqual(payload['version']['major'], '12')
        self.assertEqual(catalog.detail('pg_demo', '10')['version']['major'], '10')
        # 无效或缺席的 ?v= 落回默认版本。
        self.assertEqual(catalog.detail('pg_demo', 'nope')['version']['major'], '12')
        self.assertEqual(catalog.detail('pg_gone', '12')['version']['major'], '11')

    def test_detail_columns_mark_new_columns_and_resolve_references(self):
        payload = catalog.detail('pg_demo', '12')
        columns = {column['name']: column for column in payload['columns']}
        self.assertTrue(columns['demoextra']['added'])
        self.assertFalse(columns['oid']['added'])
        self.assertEqual(columns['oid']['description_zh'], '行标识符')
        self.assertEqual(columns['demoowner']['references']['text'], 'pg_authid.oid')
        # pg_authid 不在这份数据里，只给文字不给链接。
        self.assertEqual(columns['demoowner']['references']['url'], '')

    def test_a_reference_to_a_known_relation_becomes_a_link(self):
        relation = CatalogRelation.objects.get(name='pg_demo')
        relation.versions['11']['columns'][2]['references'] = 'pg_gone.goneid'
        relation.versions['12']['columns'][2]['references'] = 'pg_gone.goneid'
        relation.save(update_fields=['versions'])
        cache.clear()
        reference = catalog.detail('pg_demo', '11')['columns'][2]['references']
        self.assertEqual(reference['url'], '/docs/catalog/pg_gone/?v=11')
        # pg_gone 在 12 已经不存在，只给文字不给链接。
        self.assertEqual(catalog.detail('pg_demo', '12')['columns'][2]['references']['url'], '')

    def test_change_note_wording(self):
        self.assertEqual(catalog.detail('pg_demo', '10')['change_note'],
                         '10 是本数据集的收录基线，不代表该关系首次于 10 引入。')
        self.assertEqual(catalog.detail('pg_demo', '11')['change_note'],
                         '相对 PostgreSQL 10 无变化。')
        self.assertEqual(catalog.detail('pg_demo', '12')['change_note'],
                         '相对 PostgreSQL 11：新增 1 个字段。')
        self.assertEqual(catalog.detail('pg_stat_demo', '11')['change_note'],
                         'PostgreSQL 11 新增此关系，共 2 个字段。')

    def test_devel_and_preview_versions_carry_a_notice(self):
        self.assertIn('devel 手册', catalog.detail('pg_demo', '20')['notice'])
        self.assertEqual(catalog.detail('pg_demo', '12')['notice'], '')

    def test_ribbon_marks_the_current_version_and_offers_doc_links(self):
        ribbon = {cell['major']: cell for cell in catalog.detail('pg_demo', '11')['ribbon']}
        self.assertTrue(ribbon['11']['current'])
        self.assertFalse(ribbon['12']['current'])
        self.assertEqual(ribbon['12']['doc_url'], '/docs/12/catalog-pg-demo.html')
        self.assertEqual(ribbon['20']['doc_url'], '/docs/devel/catalog-pg-demo.html')

    def test_doc_links_only_point_at_pages_the_site_has(self):
        payload = catalog.detail('pg_stat_demo', '12')
        self.assertEqual(payload['links']['doc'],
                         '/docs/12/monitoring-stats.html#PG-STAT-DEMO-VIEW')
        # pg_gone 在 12 已移除，11 的手册页本站有。
        self.assertEqual(catalog.detail('pg_gone', '11')['links']['doc'],
                         '/docs/11/catalog-pg-gone.html')
        # 本站没有的页面不给链接。
        relation = CatalogRelation.objects.get(name='pg_demo')
        relation.versions['12']['doc'] = {'file': 'no-such-page.html', 'anchor': '', 'slug': '12'}
        relation.save(update_fields=['versions'])
        cache.clear()
        self.assertEqual(catalog.detail('pg_demo', '12')['links']['doc'], '')

    def test_matrix_marks_exists_changed_removed_and_absent(self):
        relation = CatalogRelation.objects.get(name='pg_demo')
        relation.versions['12']['columns'][1]['type'] = 'text'
        relation.save(update_fields=['versions'])
        cache.clear()
        matrix = catalog.detail('pg_demo', '12')['matrix']
        self.assertEqual([v['major'] for v in matrix['versions']], ['10', '11', '12', '20'])
        rows = {row['name']: {cell['major']: cell['state'] for cell in row['cells']}
                for row in matrix['rows']}
        self.assertEqual(rows['demoname']['11'], 'exists')
        self.assertEqual(rows['demoname']['12'], 'changed')
        self.assertEqual(rows['demoextra']['11'], 'absent')
        self.assertEqual(rows['demoextra']['12'], 'exists')

    def test_matrix_marks_removed_on_the_version_after_the_last_one(self):
        relation = CatalogRelation.objects.get(name='pg_demo')
        relation.versions['20']['columns'] = [c for c in relation.versions['20']['columns']
                                              if c['name'] != 'demoextra']
        relation.save(update_fields=['versions'])
        cache.clear()
        matrix = catalog.detail('pg_demo', '12')['matrix']
        row = next(r for r in matrix['rows'] if r['name'] == 'demoextra')
        self.assertEqual([cell['state'] for cell in row['cells']],
                         ['absent', 'absent', 'exists', 'removed'])

    def test_removed_columns_come_from_the_previous_snapshot(self):
        relation = CatalogRelation.objects.get(name='pg_demo')
        relation.changes.append({
            'from': '11', 'to': '12', 'status': 'changed', 'added_columns': [],
            'removed_columns': [{'name': 'demoname'}], 'type_changes': [],
            'description_changes': [], 'reference_changes': [], 'attribute_changes': [],
            'relation_description_changed': False, 'column_order_changed': False,
            'structural': True})
        relation.changes = [c for c in relation.changes if not (c['to'] == '12' and c['added_columns'])]
        relation.save(update_fields=['changes'])
        cache.clear()
        removed = catalog.detail('pg_demo', '12')['removed_columns']
        self.assertEqual([column['name'] for column in removed], ['demoname'])
        self.assertEqual(removed[0]['description_zh'], '演示对象的名字')

    def test_timeline_is_newest_first(self):
        timeline = catalog.detail('pg_demo', '12')['timeline']
        self.assertEqual([item['to'] for item in timeline], ['20', '12'])
        self.assertEqual(timeline[0]['added'], ['demoflags'])
        self.assertEqual(timeline[1]['added'], ['demoextra'])

    def test_facts_report_oid_relkind_and_baseline(self):
        facts = {row['label']: row['value'] for row in catalog.detail('pg_demo', '12')['facts']}
        self.assertEqual(facts['类别'], '系统目录表')
        self.assertEqual(facts['关系 OID'], '4242')
        self.assertEqual(facts['关系类型'], 'r（普通表）')
        self.assertEqual(facts['字段数'], '4')
        self.assertEqual(facts['引入版本'], '10（收录基线）')
        self.assertEqual(facts['版本状态'], '当前稳定版')

    def test_sibling_groups_keep_only_the_same_kind(self):
        payload = catalog.detail('pg_demo', '12')
        self.assertEqual([group['kind'] for group in payload['sibling_groups']], ['catalog'])
        self.assertEqual(payload['sibling_groups'][0]['current'], 'pg_demo')

    def test_changes_page_matches_the_stored_transition(self):
        payload = catalog.changes('12')
        self.assertEqual(payload['previous']['major'], '11')
        self.assertFalse(payload['arbitrary'])
        self.assertEqual(payload['summary']['added_relations'], 0)
        self.assertEqual(payload['summary']['removed_relations'], 1)
        self.assertEqual(payload['summary']['structurally_changed'], 1)
        self.assertEqual([card['name'] for card in payload['removed']], ['pg_gone'])
        self.assertEqual([card['name'] for card in payload['changed']], ['pg_demo'])
        self.assertIn({'kind': 'added', 'text': '新增 1 个字段'}, payload['changed'][0]['tags'])

    def test_the_first_version_lists_the_baseline(self):
        payload = catalog.changes('10')
        self.assertTrue(payload['baseline'])
        self.assertIsNone(payload['previous'])
        names = [row['name'] for group in payload['baseline_groups'] for row in group['rows']]
        self.assertEqual(sorted(names), ['pg_demo', 'pg_gone'])
        self.assertIn('收录基线', payload['baseline_note'])

    def test_a_non_adjacent_comparison_is_computed_on_the_spot(self):
        payload = catalog.changes('12', from_major='10')
        self.assertTrue(payload['arbitrary'])
        self.assertEqual(payload['from_major'], '10')
        self.assertEqual([card['name'] for card in payload['changed']], ['pg_demo'])
        self.assertEqual(payload['summary']['removed_relations'], 1)
        # 10 没有 pg_stat_demo，12 有，算新增。
        self.assertEqual([card['name'] for card in payload['added']], ['pg_stat_demo'])

    def test_an_unknown_from_falls_back_to_the_adjacent_comparison(self):
        payload = catalog.changes('12', from_major='nope')
        self.assertFalse(payload['arbitrary'])
        self.assertEqual(payload['from_major'], '')

    def test_compare_reports_only_real_differences(self):
        left = {'columns': [{'name': 'a', 'type': 'oid', 'description': 'x'}]}
        right = {'columns': [{'name': 'a', 'type': 'text', 'description': 'x'}]}
        change = catalog.compare(left, right)
        self.assertEqual(change['type_changes'], [{'name': 'a', 'from': 'oid', 'to': 'text'}])
        self.assertTrue(change['structural'])
        self.assertIsNone(catalog.compare(left, json.loads(json.dumps(left))))

    def test_changes_for_an_unknown_version_raises(self):
        with self.assertRaises(CatalogVersion.DoesNotExist):
            catalog.changes('99')


class CatalogPageTests(TestCase):
    """三种页面都要能渲染出来。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            write_cat(root)
            catalog_importer.import_snapshot(catalog_importer.export_snapshot(root))

    def setUp(self):
        cache.clear()

    def test_index_renders_every_group(self):
        response = self.client.get('/docs/catalog/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('PostgreSQL 系统目录', html)
        self.assertIn('id="kind-catalog"', html)
        self.assertIn('pg_demo', html)
        self.assertIn('演示用的目录表', html)

    def test_detail_renders_columns_and_the_change_note(self):
        html = self.client.get('/docs/catalog/pg_demo/').content.decode()
        self.assertIn('SYSTEM CATALOG', html)
        self.assertIn('demoextra', html)
        self.assertIn('行标识符', html)
        self.assertIn('相对 PostgreSQL 11：新增 1 个字段。', html)

    def test_detail_honours_the_version_parameter(self):
        response = self.client.get('/docs/catalog/pg_demo/?v=10')
        self.assertEqual(response.context['version']['major'], '10')
        self.assertIn('10 是本数据集的收录基线', response.context['change_note'])
        self.assertIn('行标识符（四列格式）', response.content.decode())

    def test_an_invalid_version_falls_back_to_the_default(self):
        html = self.client.get('/docs/catalog/pg_demo/?v=1999').content.decode()
        self.assertIn('相对 PostgreSQL 11：新增 1 个字段。', html)

    def test_unknown_relation_is_404(self):
        self.assertEqual(self.client.get('/docs/catalog/pg_nope/').status_code, 404)
        self.assertEqual(self.client.get('/docs/catalog/PG_DEMO/').status_code, 404)
        self.assertEqual(self.client.get('/docs/catalog/demo/').status_code, 404)

    def test_changes_root_redirects_to_the_default_version(self):
        response = self.client.get('/docs/catalog/changes/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/docs/catalog/changes/12/')

    def test_changes_page_renders(self):
        html = self.client.get('/docs/catalog/changes/12/').content.decode()
        self.assertIn('PostgreSQL 12 系统目录变更', html)
        self.assertIn('pg_gone', html)
        html = self.client.get('/docs/catalog/changes/20/').content.decode()
        self.assertIn('20 devel', html)
        self.assertIn('devel 手册', html)

    def test_changes_page_for_an_unknown_version_is_404(self):
        self.assertEqual(self.client.get('/docs/catalog/changes/99/').status_code, 404)

    def test_the_docs_navigation_marks_the_column_active(self):
        response = self.client.get('/docs/catalog/')
        active = [item for item in response.context['navmenu'] if item.get('active')]
        self.assertEqual([item['link'] for item in active], ['/docs/catalog/'])

    def test_the_column_is_local_only(self):
        from pgweb.util.contexts import LOCAL_ONLY_SECTIONS, _source_url
        self.assertIn('/docs/catalog/', LOCAL_ONLY_SECTIONS)
        self.assertEqual(_source_url('/docs/catalog/pg_demo/'), '')

    def test_sitemap_lists_the_index_every_relation_and_every_changes_page(self):
        from .struct import get_struct
        pages = [page for page, _ in get_struct()]
        self.assertIn('docs/catalog/', pages)
        self.assertIn('docs/catalog/pg_demo/', pages)
        self.assertIn('docs/catalog/pg_fresh/', pages)
        self.assertIn('docs/catalog/changes/10/', pages)
        self.assertIn('docs/catalog/changes/20/', pages)


class CatalogDocArtifactTests(TestCase):
    """手册与运行时对不上的字段，是手册的老账，不能算成开发版的变化。"""

    @classmethod
    def setUpTestData(cls):
        from pgweb.docs.models import DocPage
        load_manuals()
        # 12 的手册记着一个 12 运行时没有的 demoghost，又漏掉了运行时有的 demoextra；
        # devel 手册照抄了这两处，再加一个真的新字段 demoflags。
        documented = DEMO_SPEC + [GHOST]
        DocPage.objects.filter(version_id=12, file='catalog-pg-demo.html').update(
            content=single_column_page('pg_demo', documented, DEMO_LEAD))
        DocPage.objects.filter(version_id=0, file='catalog-pg-demo.html').update(
            content=single_column_page(
                'pg_demo', documented + [('demoflags', 'int4', '开发版新增的标志位', '')],
                DEMO_LEAD))
        cls.snapshot = export()
        cls.relation = {r['name']: r for r in cls.snapshot['relations']}['pg_demo']

    def test_a_column_the_manual_kept_but_the_release_dropped_is_not_an_addition(self):
        devel = self.relation['versions']['20']
        self.assertNotIn('demoghost', [column['name'] for column in devel['columns']])
        change = next(c for c in self.relation['changes'] if c['to'] == '20')
        self.assertEqual([c['name'] for c in change['added_columns']], ['demoflags'])

    def test_a_column_no_manual_documents_is_carried_not_removed(self):
        devel = self.relation['versions']['20']
        self.assertEqual([column['name'] for column in devel['columns']],
                         ['oid', 'demoname', 'demoowner', 'demoextra', 'demoflags'])
        change = next(c for c in self.relation['changes'] if c['to'] == '20')
        self.assertEqual(change['removed_columns'], [])
        carried = next(c for c in devel['columns'] if c['name'] == 'demoextra')
        self.assertEqual(carried['description'], 'Added in 12')

    def test_both_kinds_of_artifact_are_reported(self):
        artifacts = self.snapshot['harvest']['devel']['doc_artifacts']
        self.assertEqual(artifacts['pg_demo'], ['demoextra', 'demoghost'])

    def test_the_change_stays_structural_only_for_the_real_addition(self):
        change = next(c for c in self.relation['changes'] if c['to'] == '20')
        self.assertTrue(change['structural'])
        self.assertFalse(change['column_order_changed'])

    def test_an_untrustworthy_manual_order_is_not_reported_as_a_change(self):
        """上一版手册顺序本来就和运行时顺序不一致时，顺序差异说明不了目录变了。"""
        runtime = [{'name': 'a'}, {'name': 'b'}, {'name': 'c'}]
        self.assertFalse(catalog_importer.doc_order_is_trustworthy(['a', 'c', 'b'], runtime))
        self.assertTrue(catalog_importer.doc_order_is_trustworthy(['a', 'b', 'c'], runtime))
        self.assertTrue(catalog_importer.doc_order_is_trustworthy(['a', 'z', 'b', 'c'], runtime))


class CatalogReferenceTests(TestCase):
    """引用不能在推导开发版时丢掉。"""

    @classmethod
    def setUpTestData(cls):
        from pgweb.docs.models import DocPage
        load_manuals()
        # devel 手册把 demoowner 的引用写成自引用式的写法，解析不出来。
        DocPage.objects.filter(version_id=0, file='catalog-pg-demo.html').update(
            content=single_column_page(
                'pg_demo',
                [(f, t, d, '') for f, t, d, r in DEMO_DEVEL_SPEC],
                DEMO_LEAD))
        cls.relation = {r['name']: r for r in export()['relations']}['pg_demo']

    def test_a_reference_the_devel_manual_does_not_spell_out_is_carried(self):
        devel = self.relation['versions']['20']
        owner = next(c for c in devel['columns'] if c['name'] == 'demoowner')
        self.assertEqual(owner['references'], 'pg_authid.oid')
        # 上一版也没有引用的字段不会凭空长出一个。
        self.assertNotIn('references', next(c for c in devel['columns'] if c['name'] == 'demoname'))

    def test_the_carried_reference_is_not_reported_as_a_change(self):
        change = next(c for c in self.relation['changes'] if c['to'] == '20')
        self.assertEqual(change['reference_changes'], [])


class CatalogOverviewSourceTests(TestCase):
    """目录表的总览表 14 起搬了页，两处都要认。"""

    @classmethod
    def setUpTestData(cls):
        from pgweb.docs.models import DocPage
        load_manuals()
        # PG 10 – 14 的那张「系统目录」总览表在 catalogs.html 里。
        DocPage.objects.filter(version_id=12, file='catalogs-overview.html').update(
            file='catalogs.html')
        cls.relations = {r['name']: r for r in export()['relations']}

    def test_the_one_liner_is_read_from_catalogs_html_too(self):
        self.assertEqual(self.relations['pg_demo']['summary_zh'], '演示用的目录表')
        # 早于当前稳定版就移除的关系，一句话只能从它还在的那几版里取。
        self.assertEqual(self.relations['pg_gone']['summary_zh'], '已经移除的目录表')


class CatalogDevelDuplicateTests(TestCase):
    """devel 手册里有、上一版没有的关系不能被追加成第二条记录。"""

    @classmethod
    def setUpTestData(cls):
        from pgweb.docs.models import DocPage
        load_manuals()
        # pg_gone 在 12 已移除，但 devel 手册里仍有它的页面。
        DocPage.objects.create(file='catalog-pg-gone.html', version_id=0,
                               title='catalog-pg-gone.html', content=PAGE_GONE_SINGLE)
        cls.snapshot = export()

    def test_the_relation_appears_once(self):
        names = [r['name'] for r in self.snapshot['relations']]
        self.assertEqual(names.count('pg_gone'), 1)
        catalog_importer.validate(self.snapshot)

    def test_it_comes_back_as_a_relation_the_devel_manual_documents_again(self):
        relation = {r['name']: r for r in self.snapshot['relations']}['pg_gone']
        self.assertIn('20', relation['versions'])
        self.assertEqual(relation['present_in'], ['10', '11', '20'])


class CatalogChangesCacheTests(TestCase):
    """相邻比较缓存 5 分钟，非相邻比较现算。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()
        catalog_importer.import_snapshot(export())

    def setUp(self):
        cache.clear()

    def test_the_adjacent_case_is_cached_and_forget_clears_it(self):
        first = catalog.changes('12')
        self.assertEqual(first['summary']['removed_relations'], 1)
        CatalogRelation.objects.filter(name='pg_gone').delete()
        # 缓存还在，结果不变。
        self.assertEqual(catalog.changes('12')['summary']['removed_relations'], 1)
        catalog.forget()
        self.assertEqual(catalog.changes('12')['summary']['removed_relations'], 0)

    def test_an_arbitrary_comparison_is_never_cached(self):
        self.assertEqual(catalog.changes('12', from_major='10')['summary']['removed_relations'], 1)
        CatalogRelation.objects.filter(name='pg_gone').delete()
        self.assertEqual(catalog.changes('12', from_major='10')['summary']['removed_relations'], 0)

    def test_an_unknown_version_still_raises_through_the_cache(self):
        with self.assertRaises(CatalogVersion.DoesNotExist):
            catalog.changes('99')


class CatalogTrustedOrderTests(SimpleTestCase):
    """手册顺序不可信时，快照按上一版的顺序摆。"""

    def test_known_columns_follow_the_previous_release_order(self):
        previous = [{'name': 'a'}, {'name': 'b'}, {'name': 'c'}]
        # 手册把 b 和 c 调了个位置，又在末尾加了一个新字段。
        columns = [{'name': 'a'}, {'name': 'c'}, {'name': 'b'}, {'name': 'new'}]
        ordered = catalog_importer.trusted_order(columns, previous)
        self.assertEqual([c['name'] for c in ordered], ['a', 'b', 'c', 'new'])

    def test_a_new_column_keeps_the_place_the_manual_gave_it(self):
        previous = [{'name': 'a'}, {'name': 'b'}]
        columns = [{'name': 'new'}, {'name': 'b'}, {'name': 'a'}]
        ordered = catalog_importer.trusted_order(columns, previous)
        self.assertEqual([c['name'] for c in ordered], ['new', 'a', 'b'])


class CatalogDefaultVersionTests(TestCase):
    """默认版本只在建版本条缓存时算一次。"""

    @classmethod
    def setUpTestData(cls):
        load_manuals()
        catalog_importer.import_snapshot(export())

    def setUp(self):
        cache.clear()

    def test_the_default_comes_from_the_version_bar(self):
        catalog.versions()
        with self.assertNumQueries(0):
            self.assertEqual(catalog.default_major(), '12')
            self.assertEqual(catalog.pick_major('', ['10', '11', '12']), '12')
            self.assertEqual(catalog.pick_major('nope', ['10', '11', '12']), '12')
            self.assertEqual(catalog.pick_major('10', ['10', '11', '12']), '10')
            # 默认版本没有这个关系时取它最后存在的版本。
            self.assertEqual(catalog.pick_major('', ['10', '11']), '11')
            self.assertEqual(catalog.pick_major('', []), '')

    def test_the_scale_string_matches_what_the_pages_count(self):
        self.assertEqual(BY_SLUG['catalog']['scale'], '158 个关系 · 4 类')
