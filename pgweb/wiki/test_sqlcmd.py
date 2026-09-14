"""十八个版本、五条命令的页面、查询、导航与检索验收。"""

from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from pgweb.core.models import Version
from pgweb.docs.models import DocPage
from pgweb.search import indexer, service
from pgweb.search.models import SearchEntry
from pgweb.wiki import sqlcmd
from pgweb.wiki.models import SqlCommand, sqlcmd_group_of, sqlcmd_slug, sqlcmd_split
from pgweb.wiki.sqlcmd_common import compare, sections_at
from pgweb.wiki.test_sqlcmd_importer import PARAMETERS, reference, toc, version


MAJORS = ['9.' + str(n) for n in range(7)] + [str(n) for n in range(10, 21)]


def make_dataset():
    trees = {m: Decimal(m) if m != '20' else Decimal(0) for m in MAJORS}
    Version.objects.bulk_create([version(t, m == '18', 2 if m in ('19', '20') else 0)
                                 for m, t in trees.items()])
    records = []
    for name, present in [('CREATE TABLE', MAJORS), ('SELECT', MAJORS),
                           ('MERGE', MAJORS[12:]), ('WAIT FOR', ['19', '20']),
                           ('CREATE PROPERTY GRAPH', ['19'])]:
        slug = sqlcmd_slug(name)
        snapshots = {}
        for major in present:
            file = 'sql-' + name.lower().replace(' ', '') + '.html'
            if name == 'WAIT FOR' and major == '19':
                file = 'sql-wait-for.html'
            syntax = name + ' <em class="replaceable"><code>name</code></em>\n  (id int)'
            if name == 'CREATE TABLE' and MAJORS.index(major) >= MAJORS.index('18'):
                syntax += '\n  [ NEW OPTION ]'
            body = '新正文' if name == 'SELECT' and major in ('18', '19', '20') else '共享正文'
            content = reference(name, syntax, body, PARAMETERS)
            from pgweb.wiki.sqlcmd_importer import parse_page
            snap = parse_page(content, file, {'major': major, 'doc_slug': 'devel' if major == '20' else major})
            if name == 'CREATE TABLE':
                snap['related'] = ['select']
            snapshots[major] = snap
            DocPage.objects.create(version_id=trees[major], file=file, title=name, content=content)
        changes = []
        for left, right in zip(MAJORS, MAJORS[1:]):
            change = compare(snapshots.get(left), snapshots.get(right), left, right)
            if change:
                changes.append(change)
        # 手工放一个多跳指针，页面必须完整解析；不依赖导入器的去重来验证自己。
        if name == 'SELECT':
            snapshots['9.1'].update(sections=[], sections_same_as='9.0')
            snapshots['9.2'].update(sections=[], sections_same_as='9.1')
        verb, object_name = sqlcmd_split(name)
        records.append(SqlCommand(slug=slug, name=name,
            aliases=list(dict.fromkeys(s['file'][4:-5] for s in snapshots.values())),
            verb=verb, object=object_name, group=sqlcmd_group_of(name), purpose_zh='示例用途',
            first_version=present[0], last_version=present[-1], present_in=present,
            changed_in=[c['to'] for c in changes if c['synopsis']],
            synopsis=snapshots[present[-1]]['synopsis_text'], related=snapshots[present[-1]]['related'],
            versions=snapshots, changes=changes, position=len(records)))
    SqlCommand.objects.bulk_create(records)
    for major, tree in trees.items():
        pages = DocPage.objects.filter(version=tree).values_list('file', 'title')
        DocPage.objects.create(version_id=tree, file='sql-commands.html', content=toc(pages))


class SqlcmdTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_dataset()

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_version_rows_and_counts(self):
        order = sqlcmd.versions()
        self.assertEqual([v['major'] for v in order], MAJORS)
        self.assertEqual(sqlcmd.default_major(), '18')
        self.assertEqual([v['major'] for v in order if v['is_default']], ['18'])
        self.assertEqual([v['status'] for v in order[-3:]], ['stable', 'preview', 'devel'])
        self.assertEqual(order[-1]['doc_slug'], 'devel')
        self.assertEqual(order[0]['command_count'], 2)
        self.assertEqual(order[12]['added_count'], 1)
        self.assertEqual(order[-1]['removed_count'], 1)

    def test_index_has_full_contract_and_one_cell_per_version(self):
        payload = sqlcmd.index()
        self.assertEqual((payload['total'], payload['group_count']), (5, 17))
        rows = {r['slug']: r for g in payload['groups'] for r in g['rows']}
        for row in rows.values():
            self.assertEqual(len(row['strip']), 18)
            self.assertIn('name', row['text'])
        self.assertTrue(rows['create-table']['baseline'])
        self.assertEqual(rows['create-table']['strip'][0]['state'], 'present')
        self.assertEqual(rows['merge']['first'], '15')
        self.assertEqual(rows['create-property-graph']['removed_in'], '20')
        self.assertEqual(rows['select']['change_count'], 0)
        self.assertEqual([f['param'] for f in payload['filters']], ['group', 'verb', 'first', 'present'])
        self.assertEqual(payload['stats']['snapshots'], 45)

    def test_index_uses_one_lean_query_after_version_cache(self):
        sqlcmd.versions()
        with CaptureQueriesContext(connection) as queries:
            sqlcmd.index()
        self.assertEqual(len(queries), 1)
        for column in ('"versions"', '"changes"', '"editorial"'):
            self.assertNotIn(column, queries[0]['sql'])
        with self.assertNumQueries(0):
            sqlcmd.index()

    def test_detail_facts_synopsis_related_and_siblings(self):
        payload = sqlcmd.detail('create-table')
        self.assertEqual(payload['version']['major'], '18')
        self.assertEqual(payload['previous_major'], '17')
        self.assertEqual(len(payload['facts']), 7)
        self.assertEqual(payload['synopsis']['lines'][-1]['state'], 'added')
        self.assertIn('PostgreSQL 18 新增', payload['synopsis']['html'])
        self.assertIn('<em class="replaceable"><code>name</code></em>', payload['synopsis']['html'])
        self.assertIn('语法概要新增 1 行，移除 0 行', payload['change_note'])
        self.assertEqual(payload['related'][0]['url'], '/docs/sql/select/?v=18')
        self.assertEqual(payload['siblings'][0]['slug'], 'table')
        self.assertEqual(payload['current'], 'create-table')
        self.assertEqual(payload['doc']['local_url'], '/docs/18/sql-createtable.html#SQL-DEMO')
        self.assertFalse(payload['doc']['borrowed'])
        self.assertEqual(len(payload['ribbon']), 18)
        self.assertEqual([c['major'] for c in payload['ribbon'] if c['current']], ['18'])

    def test_multi_hop_sections_and_unique_anchors(self):
        payload = sqlcmd.detail('select', '9.2')
        self.assertIn('共享正文', payload['sections'][0]['html'])
        self.assertEqual(payload['sections'][0]['anchor'], 'description')
        command = SqlCommand.objects.get(slug='select')
        command.versions['18']['sections'] += [{'key': 'other', 'title': '甲', 'html': '<p>A</p>'},
                                               {'key': 'other', 'title': '乙', 'html': '<p>B</p>'}]
        command.save()
        anchors = [s['anchor'] for s in sqlcmd.detail('select')['sections']]
        self.assertEqual(anchors[-2:], ['other', 'other-2'])

    def test_change_notes_baseline_added_body_unchanged_and_renamed(self):
        self.assertIn('不代表该命令首次于 9.0 引入', sqlcmd.detail('select', '9.0')['change_note'])
        self.assertEqual(sqlcmd.detail('merge', '15')['change_note'], 'PostgreSQL 15 新增此命令。')
        self.assertEqual(sqlcmd.detail('select', '18')['change_note'], '相对 PostgreSQL 17 语法未变，正文有更新。')
        self.assertEqual(sqlcmd.detail('select', '17')['change_note'], '相对 PostgreSQL 16 无变化。')
        self.assertIn('手册文件由 sql-wait-for.html 改为 sql-waitfor.html',
                      sqlcmd.detail('wait-for')['change_note'])

    def test_version_fallback_notices_and_missing_docs(self):
        self.assertEqual(sqlcmd.detail('merge', '9.0')['version']['major'], '18')
        self.assertEqual(sqlcmd.detail('wait-for')['version']['major'], '20')
        self.assertEqual(sqlcmd.detail('create-property-graph')['version']['major'], '19')
        self.assertIn('尚未正式发布', sqlcmd.detail('wait-for')['notice'])
        self.assertIn('历史版本', sqlcmd.detail('select', '10')['notice'])
        self.assertEqual(sqlcmd.detail('select', '18')['notice'], '')
        DocPage.objects.filter(version=18, file='sql-select.html').delete()
        sqlcmd.forget()
        payload = sqlcmd.detail('select', '18')
        self.assertEqual(payload['links']['doc'], '')
        self.assertIn('/docs/18/sql-select.html', payload['links']['official'])

    def test_timeline_is_newest_first(self):
        timeline = sqlcmd.detail('wait-for')['timeline']
        self.assertEqual([c['to'] for c in timeline], ['20', '19'])
        self.assertTrue(timeline[0]['renamed'])
        self.assertEqual(timeline[1]['status'], 'added')

    def test_changes_summary_baseline_and_arbitrary(self):
        payload = sqlcmd.changes('18')
        self.assertEqual(payload['summary'], {'added': 0, 'removed': 0, 'renamed': 0,
                                              'synopsis_changed': 1, 'sections_changed': 1})
        self.assertEqual(payload['synopsis_changed'][0]['sample'], '[ NEW OPTION ]')
        self.assertEqual(sqlcmd.changes('15')['added'][0]['name'], 'MERGE')
        self.assertEqual(sqlcmd.changes('20')['summary']['removed'], 1)
        self.assertEqual(sqlcmd.changes('20')['summary']['renamed'], 1)
        baseline = sqlcmd.changes('9.0')
        self.assertTrue(baseline['baseline'])
        self.assertEqual(sum(g['count'] for g in baseline['baseline_groups']), 2)
        arbitrary = sqlcmd.changes('18', '12')
        self.assertTrue(arbitrary['arbitrary'])
        self.assertEqual(arbitrary['summary']['added'], 1)
        self.assertEqual(arbitrary['summary']['synopsis_changed'], 1)
        self.assertEqual(sqlcmd.changes('18', 'bogus')['summary'], payload['summary'])

    def test_missing_commands_and_versions_raise(self):
        with self.assertRaises(SqlCommand.DoesNotExist):
            sqlcmd.detail('not-here')
        with self.assertRaises(SqlCommand.DoesNotExist):
            sqlcmd.changes('99')

    def test_route_status_codes_aliases_and_queryparams(self):
        for path in ['/docs/sql/', '/docs/sql/create-table/', '/docs/sql/create-table/?v=10',
                     '/docs/sql/merge/?v=15', '/docs/sql/wait-for/', '/docs/sql/changes/15/',
                     '/docs/sql/changes/9.0/', '/docs/sql/changes/20/', '/docs/sql/changes/18/?from=12',
                     '/docs/sql/?q=create&group=table&verb=CREATE&first=9.0&present=18']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        for alias in ['createtable', 'CREATETABLE', 'CREATE-TABLE']:
            response = self.client.get('/docs/sql/' + alias + '/?v=10')
            self.assertEqual(response.status_code, 301)
            self.assertEqual(response['Location'], '/docs/sql/create-table/?v=10')
        root = self.client.get('/docs/sql/changes/')
        self.assertEqual((root.status_code, root['Location']), (302, '/docs/sql/changes/18/'))
        for path in ['/docs/sql/nosuch/', '/docs/sql/changes/99/', '/docs/sql/1bad/']:
            self.assertEqual(self.client.get(path).status_code, 404)
        response = self.client.get('/docs/sql/create-table/?v=10&nope=1')
        self.assertEqual(response.context['version']['major'], '10')
        self.assertNotIn('nope', response.wsgi_request.GET)

    def test_pages_have_safe_html_and_active_navigation(self):
        for path in ['/docs/sql/', '/docs/sql/create-table/', '/docs/sql/changes/18/']:
            response = self.client.get(path)
            soup = BeautifulSoup(response.content, 'html.parser')
            self.assertFalse(soup.select('.cmd [style], .cmd [onclick], .cmd script:not([src])'))
            ids = [x['id'] for x in soup.select('.cmd [id]')]
            self.assertEqual(len(ids), len(set(ids)))
            active = [i['link'] for i in response.context['navmenu'] if i.get('active')]
            self.assertEqual(active, ['/docs/sql/'])

    def test_sitemap_and_column_empty_origin(self):
        from pgweb.wiki import columns
        from pgweb.wiki.struct import get_struct
        from pgweb.util.contexts import _source_url
        paths = [p for p, _ in get_struct()]
        self.assertIn('docs/sql/', paths)
        self.assertIn('docs/sql/create-table/', paths)
        self.assertIn('docs/sql/changes/20/', paths)
        self.assertEqual(_source_url('/docs/sql/create-table/'), '')
        pending = dict(columns.BY_SLUG['sql'], live=False)
        self.assertEqual(columns.url(pending), '')
        with patch.object(columns, 'COLUMNS', [pending]):
            self.assertEqual(columns.nav_items(), [])
        self.assertEqual(columns.present(columns.BY_SLUG['sql'])['repo_url'], '')

    def test_search_entry_shape_rebuild_and_real_deduplication(self):
        entry = indexer.sqlcmd_entry(SqlCommand.objects.get(slug='create-table'))
        self.assertEqual((entry['entity_key'], entry['kind'], entry['subtype']), ('sql:create table', 'sql', 'table'))
        self.assertIn('createtable', entry['aliases'])
        self.assertIn('create-table', entry['aliases'])
        self.assertIn('分组', entry['preview'])
        self.assertIn('[ NEW OPTION ]', entry['body'])
        self.assertEqual(entry['heading'], 'SQL 命令 · 表与视图')
        self.assertEqual(indexer.rebuild_sqlcmd(dry_run=True), {'sqlcmd': 5})
        self.assertFalse(SearchEntry.objects.exists())
        self.assertEqual(indexer.rebuild_sqlcmd(), {'sqlcmd': 5})
        self.assertEqual(indexer.rebuild_sqlcmd(), {'sqlcmd': 5})
        self.assertEqual(SearchEntry.objects.filter(source='sqlcmd').count(), 5)
        indexer.rebuild_version(18)
        result = service.search('CREATE TABLE')
        # 手册导读是独立实体；这里只折叠同名的 SQL 定义。
        self.assertTrue(SearchEntry.objects.filter(source='pg', entity_key='sql:create table').exists())
        exact = [r for r in result['results'] if r['name'] == 'CREATE TABLE' and r['kind'] == 'sql']
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0]['source'], 'sqlcmd')
        row = SearchEntry.objects.get(source='sqlcmd', name='CREATE TABLE')
        preview = service.preview(row)
        self.assertTrue(preview['versions'])
        self.assertIn('sqlcmd', service.parse_query('pg18:CREATE TABLE', available=[18], current=18)['sources'])

    def test_index_command_switch(self):
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('index_docs', sqlcmd=True, stdout=out)
        self.assertIn('"sqlcmd": 5', out.getvalue())
        self.assertEqual(SearchEntry.objects.filter(source='pg').count(), 0)

    def test_forget_invalidates_cached_pages(self):
        sqlcmd.index()
        sqlcmd.changes('18')
        SqlCommand.objects.filter(slug='merge').delete()
        sqlcmd.forget()
        self.assertEqual(sqlcmd.index()['total'], 4)
        self.assertEqual(sqlcmd.changes('15')['summary']['added'], 0)
