from datetime import date

from bs4 import BeautifulSoup
from django.db import connection
from django.test import SimpleTestCase, TestCase

from pgweb.core.models import Version
from pgweb.docs.models import DocPage
from .extract import extract_page, reading_html
from .indexer import rebuild_extensions, rebuild_version
from .lexicon import query_text, index_text
from .models import IndexedPage, SearchEntry
from .service import highlight, parse_query, search, preview
from pgweb.ext.sync import import_snapshot
from pgweb.ext.tests import snapshot as extension_snapshot


PARAMETER = '''<div class="sect1" id="RESOURCE"><div class="titlepage"><h2>资源消耗</h2></div>
<p>前面的普通正文也必须可以检索。</p><dl>
<dt id="GUC-WORK-MEM"><code class="varname">work_mem</code> (<code class="type">integer</code>)</dt>
<dd><p>设置排序或哈希操作的工作内存限制，默认 4MB（25% 的 "内存"）。</p><p>每个操作都可以使用此内存。</p></dd>
<dt id="GUC-SHARED-BUFFERS"><code class="varname">shared_buffers</code></dt>
<dd><p>设置共享内存缓冲区的大小。</p></dd></dl>
<div class="sect2" id="NESTED"><h3>事务隔离</h3><p>可串行化隔离保证事务行为。</p></div>
<p>后面的普通正文不能因为嵌套小节被遗漏。</p></div>'''
FUNCTION = '''<div class="sect1" id="FUNCTIONS"><h2>JSON 函数和操作符</h2>
<p>普通正文中提及 <code class="function">imaginary_function</code>，不是定义。</p>
<table><thead><tr><th><p class="func_signature"><code class="function">header_not_function</code></p></th></tr></thead><tbody>
<tr><td class="func_table_entry"><p class="func_signature"><code class="function">jsonb_set</code>
(target jsonb, path text[], value jsonb) → jsonb</p><p>更新 JSON 中的值。</p>
<p>参见 <a href="datatype-json.html#JSON">JSON 类型</a>。</p></td></tr>
<tr><td class="func_table_entry"><p class="func_signature"><code class="function">jsonb_set</code>
(target jsonb, path text[], value jsonb, create boolean) → jsonb</p><p>另一条重载定义。</p></td></tr>
<tr><td class="func_table_entry"><p class="func_signature">jsonb <code class="literal">-&gt;&gt;</code> text → text</p><p>提取字符串值。</p></td></tr>
</tbody></table></div>'''
ERRORS = '''<div class="appendix" id="ERRORS"><h2>错误代码</h2><table><tbody>
<tr><td>23505</td><td><code class="symbol">unique_violation</code></td></tr>
<tr><td>00000</td><td><code class="symbol">successful_completion</code></td></tr>
</tbody></table></div>'''
PSQL = '''<div class="refentry"><h2>psql</h2><dl>
<dt id="D"><code>\\d[S+]</code></dt><dd><p>查看关系结构。</p></dd>
<dt id="DOMAINS"><code>\\dD[S+]</code></dt><dd><p>列出域。</p></dd>
<dt id="COMMENTS"><code>\\dd</code></dt><dd><p>显示注释。</p></dd>
</dl></div>'''


class ExtractionTests(SimpleTestCase):
    def test_only_definitions_become_functions_and_overloads_keep_distinct_anchors(self):
        entries = extract_page('functions-json.html', 'JSON 函数', FUNCTION, '18')
        functions = [e for e in entries if e['kind'] == 'function']
        self.assertEqual([e['name'] for e in functions], ['jsonb_set', 'jsonb_set'])
        self.assertEqual(len({e['anchor'] for e in functions}), 2)
        self.assertEqual(len({e['entity_key'] for e in functions}), 1)
        self.assertIn('/docs/18/datatype-json.html#JSON', functions[0]['preview'])

    def test_every_definition_anchor_exists_in_reader_and_is_repeatable(self):
        for filename, html in [('functions-json.html', FUNCTION), ('errcodes-appendix.html', ERRORS),
                               ('runtime-config-resource.html', PARAMETER), ('app-psql.html', PSQL)]:
            entries = extract_page(filename, filename, html, '18')
            rendered = reading_html(html)
            ids = [n['id'] for n in BeautifulSoup(rendered, 'html.parser').select('[id]')]
            self.assertEqual(len(ids), len(set(ids)))
            for entry in entries:
                if entry['anchor']:
                    self.assertIn(entry['anchor'], ids)
            self.assertEqual(rendered, reading_html(rendered))

    def test_plain_prose_around_nested_sections_is_searchable(self):
        entries = extract_page('test.html', '资源消耗', PARAMETER, '18')
        body = ' '.join(e['body'] for e in entries if e['kind'] == 'guide')
        for phrase in ['前面的普通正文', '后面的普通正文', '可串行化隔离']:
            self.assertIn(phrase, body)

    def test_long_mixed_blocks_preserve_prose_around_tables(self):
        html = '<div class="sect1"><h2>章节</h2><div><p>保留开头</p><table><tbody>'
        html += ''.join('<tr><td>结构化数据' + str(n) + '中文' * 80 + '</td></tr>' for n in range(50))
        html += '</tbody></table><p>保留结尾</p></div></div>'
        entries = extract_page('test.html', '章节', html, '18')
        body = ' '.join(e['body'] for e in entries)
        self.assertIn('保留开头', body)
        self.assertIn('保留结尾', body)
        self.assertIn('结构化数据49', body)

    def test_multiple_chunks_with_the_same_section_anchor_are_not_lost(self):
        html = '<div class="sect1" id="LONG"><h2>长章节</h2>'
        html += ''.join('<p>段落{} '.format(n) + '中文正文' * 250 + '</p>' for n in range(20))
        html += '</div>'
        entries = extract_page('test.html', '长章节', html, '18')
        body = ' '.join(e['body'] for e in entries)
        for n in range(20):
            self.assertIn('段落{} '.format(n), body)
        self.assertGreater(len(entries), 1)
        self.assertEqual(len({e['entity_key'] for e in entries}), 1)

    def test_old_module_titles_and_distinct_timezone_types(self):
        for title in ['F.23. pageinspect', 'F.23. pageinspect — 数据库页的底层检查']:
            entries = extract_page('pageinspect.html', title, '<div class="sect1"><h2>' + title + '</h2></div>', '15')
            self.assertIn(('extension', 'pageinspect'), [(e['kind'], e['name']) for e in entries])
        html = '<div><h2>类型</h2><table><tbody>'
        html += '<tr><td><code class="type">timestamp [ (p) ] [ without time zone ]</code></td><td></td></tr>'
        html += '<tr><td><code class="type">timestamp [ (p) ] with time zone</code></td><td><code class="type">timestamptz</code></td></tr>'
        html += '</tbody></table></div>'
        entries = [e for e in extract_page('datatype.html', '类型', html, '18') if e['kind'] == 'type']
        self.assertEqual(len({e['entity_key'] for e in entries}), 2)
        self.assertIn('timestamp', entries[0]['aliases'])
        self.assertIn('timestamptz', entries[1]['aliases'])

    def test_psql_preserves_case_and_documented_flag_variants(self):
        entries = extract_page('app-psql.html', 'psql', PSQL, '18')
        commands = {e['name']: e for e in entries if e['kind'] == 'psql'}
        self.assertIn('\\dS+', commands['\\d']['aliases'])
        self.assertIn('\\dD+', commands['\\dD']['aliases'])
        self.assertNotEqual(commands['\\dd']['entity_key'], commands['\\dD']['entity_key'])

    def test_preview_is_sanitized_and_snippet_cannot_inject_markup(self):
        hostile = PARAMETER.replace('默认 4MB。', '<script>alert(1)</script><img src="x" onerror="bad()"><a href="javascript:bad()">默认</a>')
        entries = extract_page('test.html', '资源消耗', hostile, '18')
        for entry in entries:
            self.assertNotIn('<script', entry['preview'])
            self.assertNotIn('onerror', entry['preview'])
            self.assertNotIn('javascript:', entry['preview'])
        rendered = highlight('<img onerror="bad()"> work_mem', 'work_mem')
        self.assertNotIn('<img', rendered)
        self.assertIn('<mark>work_mem</mark>', rendered)

    def test_chinese_words_are_indexed_inside_longer_phrases(self):
        self.assertIn('缓冲区', index_text('共享缓冲区设置'))
        self.assertEqual(query_text('如何设置共享缓冲区'), '设置 共享缓冲区')


class ScopeTests(SimpleTestCase):
    def parse(self, query, **kwargs):
        return parse_query(query, available=[14, 17, 18, 19], current=18, **kwargs)

    def test_numeric_scope_overrides_visible_default_and_kind_is_separate(self):
        state = self.parse('pg17:kind:guc work_mem')
        self.assertEqual((state['version'], state['kind'], state['term']), (17, 'guc', 'work_mem'))

    def test_missing_or_external_scopes_never_fall_back_to_current(self):
        for term in ['pg99: work_mem', 'pg15: work_mem', 'pt: ttl']:
            with self.assertRaises(ValueError):
                self.parse(term)
        state = self.parse('ex: vector')
        self.assertEqual((state['scope'], state['sources'], state['term']), ('ex', ('ext',), 'vector'))
        self.assertEqual(self.parse('kind:operator ->>')['kind'], 'function')
        self.assertEqual(self.parse('kind:psql \\d')['kind'], 'psql')
        self.assertEqual(self.parse('kind:cli pg_dump')['kind'], 'tool')

    def test_sql_cast_uri_and_host_port_survive_parsing(self):
        for term in ['::', 'pg::text', 'postgresql://localhost/db', 'localhost:5432']:
            state = self.parse(term)
            self.assertEqual(state['term'], term)
            self.assertEqual(state['version'], 18)

    def test_unknown_prefix_is_reported_and_limits_are_enforced(self):
        self.assertTrue(self.parse('oops: work_mem')['notice'])
        for term in ['x' * 256, 'x\0y']:
            with self.assertRaises(ValueError):
                self.parse(term)


class SearchDatabaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for major in [17, 18]:
            # Avoid Version.save's unrelated cache-purge side effects in these fixtures.
            Version.objects.bulk_create([Version(tree=major, current=major == 18, reldate=date(2025, 9, 1),
                                                 firstreldate=date(2025, 9, 1), eoldate=date(2030, 1, 1))])
            for filename, body in [('runtime-config-resource.html', PARAMETER), ('functions-json.html', FUNCTION),
                                   ('errcodes-appendix.html', ERRORS), ('app-psql.html', PSQL)]:
                DocPage.objects.create(file=filename, version_id=major, title=filename, content=body)
            rebuild_version(major)

    def test_exact_identifiers_aliases_errors_and_symbols_rank_first(self):
        for term, name, kind in [('work_mem', 'work_mem', 'guc'), ('workmem', 'work_mem', 'guc'),
                                 ('共享缓冲区', 'shared_buffers', 'guc'), ('23505', '23505', 'error'),
                                 ('00000', '00000', 'error'), ('unique_violation', '23505', 'error'),
                                 ('jsonb_set', 'jsonb_set', 'function'), ('->>', '->>', 'operator'),
                                 ('\\d+', '\\d', 'psql'), ('\\dD', '\\dD', 'psql'), ('\\dd', '\\dd', 'psql')]:
            with self.subTest(term=term):
                result = search(term)
                self.assertEqual((result['results'][0]['name'], result['results'][0]['kind']), (name, kind))

    def test_scope_and_kind_are_applied_before_ranking(self):
        result = search('pg17: kind:guc work_mem')
        self.assertTrue(result['results'])
        self.assertTrue(all(e['version'] == 17 and e['kind'] == 'guc' for e in result['results']))
        self.assertFalse(search('pg19: work_mem')['results'])

    def test_current_scope_does_not_silently_use_an_older_index(self):
        IndexedPage.objects.filter(page__version=18).delete()
        result = search('work_mem')
        self.assertTrue(result['error'])
        self.assertFalse(result['results'])
        self.assertTrue(search('pg17: work_mem')['results'])

    def test_source_rename_invalidates_old_extraction(self):
        page = DocPage.objects.get(version=18, file='functions-json.html')
        with connection.cursor() as cursor:
            cursor.execute('UPDATE docs SET file=%s WHERE id=%s', ['renamed.html', page.pk])
        self.assertFalse(IndexedPage.objects.filter(pk=page.pk).exists())

    def test_overloads_fold_but_preview_keeps_other_definitions_and_versions(self):
        result = search('jsonb_set')
        hits = [r for r in result['results'] if r['kind'] == 'function']
        self.assertEqual(len(hits), 1)
        detail = preview(SearchEntry.objects.select_related('document__page').get(pk=hits[0]['id']))
        self.assertEqual(len(detail['definitions']), 1)
        self.assertEqual([e['version'] for e in detail['other_versions']], [17])

    def test_reindex_is_incremental_and_removes_changed_definitions(self):
        before = list(SearchEntry.objects.values_list('id', flat=True))
        report = rebuild_version(18)
        self.assertEqual(report, {'unchanged': 4})
        self.assertEqual(before, list(SearchEntry.objects.values_list('id', flat=True)))
        page = DocPage.objects.get(version=18, file='runtime-config-resource.html')
        page.content = page.content.replace('work_mem', 'new_parameter')
        page.save()
        report = rebuild_version(18)
        self.assertEqual(report['pages'], 1)
        self.assertFalse(SearchEntry.objects.filter(version=18, kind='guc', name='work_mem').exists())
        self.assertTrue(SearchEntry.objects.filter(version=17, kind='guc', name='work_mem').exists())

    def test_dry_run_does_not_write_and_source_change_invalidates_for_raw_loader(self):
        page = DocPage.objects.get(version=18, file='errcodes-appendix.html')
        before = list(SearchEntry.objects.values_list('id', flat=True))
        rebuild_version(18, dry_run=True, force=True)
        self.assertEqual(before, list(SearchEntry.objects.values_list('id', flat=True)))
        with connection.cursor() as cursor:
            cursor.execute('UPDATE docs SET content=replace(content, %s, %s) WHERE id=%s', ['23505', '23506', page.pk])
        self.assertFalse(SearchEntry.objects.filter(version=18, name='23505').exists())
        rebuild_version(18)
        self.assertTrue(SearchEntry.objects.filter(version=18, name='23506').exists())
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM docs WHERE id=%s', [page.pk])
        self.assertFalse(IndexedPage.objects.filter(pk=page.pk).exists())
        self.assertFalse(SearchEntry.objects.filter(version=18, name='23506').exists())

    def test_literal_punctuation_does_not_match_everything(self):
        # The fixture body contains a percent sign and quotes; a lone symbol
        # must not turn into a scan of every chapter that contains it.
        for term in ['%', '"', '""', '\\', "x' OR 1=1 --"]:
            with self.subTest(term=term):
                self.assertEqual(search(term)['total'], 0)
        self.assertEqual(search('"工作内存"')['total'], 1)
        self.assertEqual(search('->>')['results'][0]['name'], '->>')

    def test_incomplete_kind_filter_is_not_a_search_term(self):
        result = search('kind:')
        self.assertEqual((result['kind'], result['term']), ('', ''))
        self.assertTrue(result['results'])
        self.assertEqual(search('kind: work_mem')['results'][0]['name'], 'work_mem')

    def test_http_api_legacy_scope_and_reading_anchor(self):
        result = self.client.get('/search/api/', {'q': '23505', 'u': '/docs/17/'}).json()
        first = result['results'][0]
        self.assertEqual(first['version'], 17)
        detail = self.client.get('/search/preview/{}/'.format(first['id']))
        self.assertEqual(detail.status_code, 200)
        rendered = self.client.get(first['url'].split('#')[0])
        self.assertContains(rendered, 'id="' + first['url'].split('#')[1] + '"')
        page = self.client.get('/search/', {'q': 'pg17: work_mem'})
        self.assertContains(page, '文档检索')
        self.assertContains(page, 'ds-initial')
        self.assertContains(page, 'noindex,follow')
        self.assertEqual(page['Cache-Control'], 'no-cache')
        self.assertIn("style-src 'self'", page['Content-Security-Policy'])
        self.assertEqual(self.client.post('/search/api/').status_code, 405)
        # The site-wide crawler search stays reachable behind site=1.
        site = self.client.get('/search/', {'q': 'work_mem', 'site': '1'})
        self.assertTemplateUsed(site, 'search/sitesearch.html')
        self.assertContains(site, '站内搜索')


class ExtensionSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Version.objects.bulk_create([Version(tree=18, current=True, reldate=date(2025, 9, 1),
                                             firstreldate=date(2025, 9, 1), eoldate=date(2030, 1, 1))])
        DocPage.objects.create(file='runtime-config-resource.html', version_id=18, title='资源消耗', content=PARAMETER)
        DocPage.objects.create(file='pgtrgm.html', version_id=18, title='F.30. pg_trgm — 三元组匹配',
                               content='<div class="sect1"><h2>F.30. pg_trgm — 三元组匹配</h2><p>手册中的模块说明。</p></div>')
        rebuild_version(18)
        rows = extension_snapshot()
        rows['tables']['universe'][1].update(name='pg_trgm', pkg='pg_trgm', lead_ext='pg_trgm', contrib=True,
                                             zh_desc='三元组相似度', en_desc='Trigram similarity')
        import_snapshot(rows)
        rebuild_extensions()

    def test_catalogue_entries_are_found_by_name_and_description(self):
        result = search('vector')
        first = result['results'][0]
        self.assertEqual((first['source'], first['group'], first['url']), ('ext', 'extension', '/e/vector/'))
        self.assertEqual(search('向量检索')['results'][0]['name'], 'vector')
        self.assertEqual([f['count'] for f in result['facets'] if f['key'] == 'extension'], [1])
        detail = preview(SearchEntry.objects.get(pk=first['id']))
        self.assertIn('向量检索', detail['html'])
        self.assertIn('CREATE EXTENSION vector;', detail['html'])
        self.assertEqual(detail['versions'], [])

    def test_extension_scope_and_manual_definition_win_over_catalogue_card(self):
        self.assertTrue(all(r['source'] == 'ext' for r in search('ex: ')['results']))
        self.assertEqual(search('ex: work_mem')['total'], 0)
        result = search('pg_trgm')
        hits = [r for r in result['results'] if r['group'] == 'extension']
        self.assertEqual(len(hits), 1)
        self.assertEqual((hits[0]['source'], hits[0]['version']), ('pg', 18))
        detail = preview(SearchEntry.objects.select_related('document__page').get(pk=hits[0]['id']))
        self.assertEqual(detail['catalog']['url'], '/e/pg_trgm/')
        self.assertEqual([v['version'] for v in detail['versions']], [18])
        rebuilt = rebuild_extensions()
        self.assertEqual(rebuilt, {'extensions': 2})
        self.assertEqual(SearchEntry.objects.filter(source='ext').count(), 2)


RELATION_PAGE = '''<div class="sect1" id="CATALOG-PG-DEMO">
<div class="titlepage"><div><div><h2 class="title">52.1.&nbsp;<code class="structname">pg_demo</code></h2></div></div></div>
<p>目录<code class="structname">pg_demo</code>记录演示对象。</p>
<div class="table" id="id-2"><p class="title"><strong>Table&nbsp;52.1.&nbsp;<code class="structname">pg_demo</code> 列</strong></p>
<div class="table-contents"><table class="table" summary="pg_demo 列" border="1"><colgroup><col /></colgroup>
<thead><tr><th class="catalog_table_entry"><p class="column_definition">列类型</p><p>描述</p></th></tr></thead>
<tbody>
<tr><td class="catalog_table_entry"><p class="column_definition"><code class="structfield">oid</code> <code class="type">oid</code></p>
<p>行标识符</p></td></tr>
<tr><td class="catalog_table_entry"><p class="column_definition"><code class="structfield">demoname</code> <code class="type">name</code></p>
<p>演示对象的名字</p></td></tr>
</tbody></table></div></div></div>'''


class CatalogSearchTests(TestCase):
    """系统目录词条与手册里抽出的关系条目共用同一个实体，结果里只出现一条。"""

    @classmethod
    def setUpTestData(cls):
        from pgweb.wiki import tests as wiki_tests
        from pgweb.wiki.catalog_importer import import_snapshot as import_catalog
        from pgweb.search.indexer import rebuild_catalog
        # 10 – 12 的手册供中文采集，18 的手册供检索抽取。
        wiki_tests.load_manuals(devel=False)
        Version.objects.bulk_create([Version(tree=18, current=True, reldate=date(2025, 9, 1),
                                             firstreldate=date(2025, 9, 1), eoldate=date(2030, 1, 1))])
        DocPage.objects.create(file='catalog-pg-demo.html', version_id=18,
                               title='52.1. pg_demo', content=RELATION_PAGE)
        rebuild_version(18)
        import_catalog(wiki_tests.export())
        cls.report = rebuild_catalog()

    def test_every_relation_becomes_one_entry(self):
        self.assertEqual(self.report, {'catalog': SearchEntry.objects.filter(source='catalog').count()})
        entry = SearchEntry.objects.get(source='catalog', name='pg_demo')
        self.assertEqual((entry.kind, entry.subtype, entry.url),
                         ('relation', 'catalog', '/docs/catalog/pg_demo/'))
        self.assertIn('pgdemo', entry.aliases)
        # 去掉 pg_ 之后还是复合名才留别名：stat_demo 指得明确，demo 不指任何东西。
        self.assertNotIn('demo', entry.aliases)
        stat = SearchEntry.objects.get(source='catalog', name='pg_stat_demo')
        self.assertIn('stat_demo', stat.aliases)
        self.assertIn('statdemo', stat.aliases)

    def test_the_entity_key_matches_the_manual_relation_entry(self):
        manual = SearchEntry.objects.get(source='pg', kind='relation', name='pg_demo')
        entry = SearchEntry.objects.get(source='catalog', name='pg_demo')
        self.assertEqual(entry.entity_key, manual.entity_key)
        self.assertEqual(entry.entity_key, 'relation:pg_demo')

    def test_the_column_entry_wins_over_the_manual_row(self):
        result = search('pg_demo')
        first = result['results'][0]
        self.assertEqual((first['source'], first['source_label'], first['url']),
                         ('catalog', '本站词条', '/docs/catalog/pg_demo/'))
        self.assertEqual(first['group'], 'relation')
        # 同一实体的手册条目折进同一条结果里。
        self.assertGreater(first['variants'], 1)

    def test_a_column_name_finds_the_relation(self):
        self.assertEqual(search('demoname')['results'][0]['name'], 'pg_demo')

    def test_a_generic_word_does_not_resolve_to_a_relation(self):
        """pg_class 不能靠 class 这个词把手册条目挤下去。"""
        entry = SearchEntry.objects.get(source='catalog', name='pg_demo')
        self.assertNotIn('demo', entry.aliases)

    def test_the_preview_keeps_the_manual_version_line(self):
        entry = SearchEntry.objects.get(source='catalog', name='pg_demo')
        detail = preview(entry)
        self.assertIn('演示用的目录表', detail['html'])
        self.assertIn('demoname', detail['html'])
        self.assertEqual(detail['source_label'], '本站词条')
        # 词条自己没有版本，但同一实体的手册页仍然列在版本行里。
        self.assertEqual([item['version'] for item in detail['versions']], [18])
        self.assertFalse(any(item['current'] for item in detail['versions']))

    def test_rebuilding_replaces_the_previous_entries(self):
        from pgweb.search.indexer import rebuild_catalog
        before = SearchEntry.objects.filter(source='catalog').count()
        self.assertEqual(rebuild_catalog(), {'catalog': before})
        self.assertEqual(SearchEntry.objects.filter(source='catalog').count(), before)
        self.assertEqual(rebuild_catalog(dry_run=True), {'catalog': before})

    def test_the_scope_includes_the_column(self):
        self.assertIn('catalog', parse_query('pg_demo', 'pg', '', [18], 18)['sources'])
        self.assertIn('catalog', parse_query('pg_demo', 'pg18', '', [18], 18)['sources'])
