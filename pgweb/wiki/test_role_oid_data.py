"""Complete inventories, changing manual layouts, and source-faithful versions."""
import json
from pathlib import Path

from django.test import SimpleTestCase

from tools.wiki.build_role_oid import assemble, ordered_sections, parse_oid, parse_roles
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]


def document(body, label='PostgreSQL 18.6 手册'):
    return f'<a accesskey="h" title="{label}"></a><div class="sect1" id="DATATYPE-OID">{body}</div>'


class ManualShapeTests(SimpleTestCase):
    def test_grouped_roles_keep_member_description_separate(self):
        html = document('''<dl class="variablelist">
          <dt id="PREDEFINED-ROLE-PG-MONITOR"><code class="varname">pg_monitor</code>
            <code class="varname">pg_read_all_settings</code></dt>
          <dd><p>这些角色便于监控。</p>
            <p><code>pg_monitor</code>是<code>pg_read_all_settings</code>的成员。</p>
            <p><code>pg_read_all_settings</code>读取全部配置。</p></dd></dl>''')
        release, items = parse_roles(html, '18', 'stable')
        self.assertEqual(set(items), {'pg_monitor', 'pg_read_all_settings'})
        self.assertEqual(items['pg_read_all_settings']['description'], ['pg_read_all_settings 读取全部配置。'])
        self.assertNotIn('成员', ' '.join(items['pg_read_all_settings']['description']))
        self.assertIn('pg_read_all_settings', items['pg_monitor']['description'][0])
        self.assertEqual(items['pg_read_all_settings']['sources'][0]['url'],
                         '/docs/18/predefined-roles.html#PREDEFINED-ROLE-PG-MONITOR')
        self.assertEqual(release['ref'], 'PostgreSQL 18.6 手册')
        self.assertEqual(len(release['revision']), 64)

    def test_old_table_adds_permission_limit_from_surrounding_prose(self):
        html = document('''<div class="table" id="DEFAULT-ROLES-TABLE"><table><tbody><tr>
          <td>pg_signal_backend</td><td>允许向后端发送信号。</td>
          </tr></tbody></table></div><p><code>pg_signal_backend</code>不能向超级用户的后端发送信号。</p>''',
                        'PostgreSQL 10.23 手册')
        _, items = parse_roles(html, '10', 'historical')
        self.assertIn('不能', items['pg_signal_backend']['sections'][0]['paragraphs'][0])
        self.assertIn('/10/default-roles.html#DEFAULT-ROLES-TABLE',
                      items['pg_signal_backend']['sources'][0]['url'])

    def test_oid_membership_is_table_plus_explicit_prose_types(self):
        html = document('''<p><code class="type">regcollation</code>只是提到，未列在表中。</p>
          <div id="DATATYPE-OID-TABLE"><table><tbody><tr>
          <td>oid</td><td>任意</td><td>数字形式的对象标识符</td><td>564182</td>
          </tr></tbody></table></div>
          <p><code class="type">xid</code>用于 xmin 与 xmax。</p>''')
        _, items = parse_oid(html, '12', 'historical')
        self.assertEqual(set(items), {'oid', 'xid'})
        self.assertNotIn('xid8', items)
        self.assertNotIn('regcollation', items)
        self.assertEqual(items['xid']['sections'], [])

    def test_oid_notes_and_their_examples_are_not_discarded(self):
        html = document('''<div id="DATATYPE-OID-TABLE"><table><tbody><tr>
          <td>oid</td><td>任意</td><td>数字形式的对象标识符</td><td>564182</td>
          </tr></tbody></table></div><div class="note">
          <p>使用 text 强制后绑定。</p><pre>nextval('foo'::text)</pre>
          <p>这些规则不能忽略。</p></div><p><code class="type">xid</code>是事务 ID。</p>''')
        _, items = parse_oid(html, '18', 'stable')
        section = items['oid']['sections'][0]
        self.assertEqual(section['title'], '早绑定与后绑定')
        self.assertIn('后绑定', section['blocks'][0]['paragraphs'][0])
        self.assertEqual(section['blocks'][0]['code'], "nextval('foo'::text)")
        self.assertEqual(section['blocks'][-1]['paragraphs'], ['这些规则不能忽略。'])

    def test_oid_thematic_blocks_preserve_warning_after_incorrect_example(self):
        body = BeautifulSoup('''<p>通过 information_schema 和 pg_relation_size 查找 OID。</p>
          <pre>正确示例</pre><p>看似简单的写法：</p><pre>错误示例</pre>
          <p>这种写法并不推荐。</p><p>存储表达式会建立依赖关系。</p>''', 'html.parser')
        sections = ordered_sections(body.find_all(['p', 'pre']))
        self.assertEqual([s['title'] for s in sections], ['从信息模式查找 OID', '依赖关系'])
        self.assertEqual(sections[0]['blocks'], [
            {'paragraphs': ['通过 information_schema 和 pg_relation_size 查找 OID。'], 'code': '正确示例'},
            {'paragraphs': ['看似简单的写法：'], 'code': '错误示例'},
            {'paragraphs': ['这种写法并不推荐。']},
        ])

    def test_malformed_rows_and_unlabelled_roles_fail(self):
        for row in ('<td>pg_signal_backend</td>',
                    '<td>pg_new_role</td><td>新权限。</td>'):
            with self.subTest(row=row), self.assertRaises(ValueError):
                parse_roles(document('<div class="table" id="T"><table><tbody><tr>' +
                                     row + '</tr></tbody></table></div>'), '17', 'stable')
        with self.assertRaises(ValueError):
            parse_oid(document('<div id="DATATYPE-OID-TABLE"><table><tbody><tr>'
                               '<td>oid</td><td>任意</td><td>少了一列</td>'
                               '</tr></tbody></table></div>'), '18', 'stable')

    def test_absence_in_later_page_does_not_copy_previous_version(self):
        def source(names):
            rows = ''.join(f'<tr><td>{name}</td><td>本版说明。</td></tr>' for name in names)
            return document('<div class="table" id="T"><table><tbody>' + rows + '</tbody></table></div>')
        snapshot = assemble('role', [('10', source(['pg_monitor', 'pg_signal_backend']), 'historical'),
                                     ('11', source(['pg_monitor']), 'historical')])
        signal = next(x for x in snapshot['items'] if x['name'] == 'pg_signal_backend')
        self.assertEqual(set(signal['versions']), {'10'})


class CommittedRoleOidDataTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.roles = json.loads((ROOT / 'data/wiki/roles.json').read_text())
        cls.oids = json.loads((ROOT / 'data/wiki/oid_types.json').read_text())

    def test_complete_version_sets_and_source_identity(self):
        counts = {'role': [5, 8, 8, 8, 11, 12, 14, 15, 16, 16, 16],
                  'oid': [14, 14, 14, 16, 16, 16, 16, 16, 16, 18, 18]}
        for data in (self.roles, self.oids):
            self.assertEqual([r['major'] for r in data['releases']], [str(v) for v in range(10, 21)])
            self.assertEqual(len(data['items']), {'role': 16, 'oid': 18}[data['kind']])
            self.assertEqual([sum(r['major'] in item['versions'] for item in data['items'])
                              for r in data['releases']], counts[data['kind']])
            releases = {r['major']: r for r in data['releases']}
            self.assertEqual(releases['19']['channel'], 'preview')
            self.assertEqual(releases['19']['ref'], 'PostgreSQL 19beta4 手册')
            self.assertEqual(releases['20']['channel'], 'devel')
            for item in data['items']:
                self.assertRegex(item['name_zh'], r'[\u4e00-\u9fff]')
                for major, version in item['versions'].items():
                    self.assertEqual(version['release'], releases[major])
                    self.assertEqual(version['sources'][0]['sha256'], releases[major]['revision'])
                    self.assertTrue(version['description'])
                    self.assertRegex(releases[major]['revision'], r'^[0-9a-f]{64}$')
                    for description in version['description']:
                        self.assertNotRegex(description, r'<(?:p|a|code|div|span)[ >]')

    def test_new_members_are_not_backfilled_into_older_versions(self):
        roles = {item['name']: item for item in self.roles['items']}
        oid = {item['name']: item for item in self.oids['items']}
        for name, first in [('pg_read_server_files', 11), ('pg_database_owner', 14),
                            ('pg_checkpoint', 15), ('pg_create_subscription', 16),
                            ('pg_maintain', 17), ('pg_signal_autovacuum_worker', 18)]:
            self.assertEqual(list(roles[name]['versions']), [str(v) for v in range(first, 21)])
        for name, first in [('regcollation', 13), ('xid8', 13), ('regdatabase', 19), ('oid8', 19)]:
            self.assertEqual(list(oid[name]['versions']), [str(v) for v in range(first, 21)])
        self.assertEqual(set(oid), {'oid', 'oid8', 'regclass', 'regcollation', 'regconfig',
                                   'regdatabase', 'regdictionary', 'regnamespace', 'regoper',
                                   'regoperator', 'regproc', 'regprocedure', 'regrole', 'regtype',
                                   'xid', 'xid8', 'cid', 'tid'})

    def test_oid_navigation_has_unique_subjects_and_ordered_blocks(self):
        oid = {item['name']: item for item in self.oids['items']}
        expected = ['存储与取值范围', '名称解析与搜索路径', '早绑定与后绑定',
                    '从信息模式查找 OID', '依赖关系']
        for major in map(str, range(14, 21)):
            sections = oid['regclass']['versions'][major]['sections']
            self.assertEqual([s['title'] for s in sections], expected)
            self.assertEqual([len(s['blocks']) for s in sections], [1, 3, 2, 3, 1])
        for major in map(str, range(10, 14)):
            sections = oid['regclass']['versions'][major]['sections']
            self.assertEqual([s['title'] for s in sections],
                             ['存储与取值范围', '名称解析与搜索路径', '依赖关系', '事务隔离与规划限制'])
        for item in self.oids['items']:
            for version in item['versions'].values():
                titles = [s['title'] for s in version['sections']]
                self.assertEqual(len(titles), len(set(titles)))
                self.assertFalse(any('（续）' in title for title in titles))
                for section in version['sections']:
                    self.assertEqual(section['paragraphs'], [])
                    self.assertTrue(section['blocks'])

    def test_role_permission_boundaries_and_oid_examples_survive(self):
        roles = {item['name']: item for item in self.roles['items']}
        for major in map(str, range(14, 21)):
            owner = json.dumps(roles['pg_database_owner']['versions'][major], ensure_ascii=False)
            self.assertIn('隐式', owner)
            self.assertIn('不能', owner)
        for major in map(str, range(10, 21)):
            signal = json.dumps(roles['pg_signal_backend']['versions'][major], ensure_ascii=False)
            self.assertIn('超级用户', signal)
        for name in ('pg_read_all_data', 'pg_write_all_data'):
            for version in roles[name]['versions'].values():
                self.assertIn('BYPASSRLS', json.dumps(version, ensure_ascii=False))
        oid = {item['name']: item for item in self.oids['items']}
        for version in oid['regprocedure']['versions'].values():
            facts = {f['label']: f['value'] for f in version['facts']}
            self.assertEqual(facts['引用目录'], 'pg_proc')
            self.assertEqual(facts['输入值示例'], 'sum(int4)')
        for major in map(str, range(10, 14)):
            self.assertIn('事务隔离', json.dumps(oid['regclass']['versions'][major], ensure_ascii=False))
        self.assertIn('后绑定', json.dumps(oid['regclass']['versions']['18'], ensure_ascii=False))
        for major, version in oid['xid']['versions'].items():
            self.assertFalse(version['sections'])
            self.assertFalse(any('引用目录' == f['label'] for f in version['facts']))
