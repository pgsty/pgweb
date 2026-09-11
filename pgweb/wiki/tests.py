from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from . import errcode, importer, markup
from .columns import BY_SLUG, COLUMNS, listing, live_columns, nav_items, url
from .models import ErrorCode, ErrorCodeClass, ErrorCodeRelease, ErrorCodeText


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
