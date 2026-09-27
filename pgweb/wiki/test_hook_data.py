"""Parser, source inventory and version-specific hook interface regressions."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.wiki.build_hooks import parse_header, scan_tree


class HookSourceParserTests(unittest.TestCase):
    def test_multiline_and_pointer_return_typedefs(self):
        text = '''/* extern missing_hook_type fake_hook; */
typedef const char *(*explain_get_index_name_hook_type) (Oid indexId);
extern PGDLLIMPORT explain_get_index_name_hook_type explain_get_index_name_hook;
typedef List *(*row_security_policy_hook_type)
    (CmdType cmdtype, Relation relation);
extern row_security_policy_hook_type row_security_policy_hook_restrictive;
extern void unrelated_hook_function(int);
'''
        hooks = parse_header(text, 'src/include/example.h')
        self.assertEqual([h['name'] for h in hooks], [
            'explain_get_index_name_hook', 'row_security_policy_hook_restrictive'])
        self.assertEqual(hooks[0]['signature'],
            'typedef const char *(*explain_get_index_name_hook_type) (Oid indexId);')
        self.assertEqual(hooks[0]['type_line'], 2)
        self.assertEqual(hooks[0]['line'], 3)
        self.assertIn('CmdType cmdtype, Relation relation', hooks[1]['signature'])

    def test_missing_typedef_is_an_error(self):
        with self.assertRaisesRegex(ValueError, 'missing function-pointer typedef'):
            parse_header('extern missing_hook_type missing_hook;', 'example.h')

    def test_inventory_is_discovered_and_macro_calls_are_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            header = tree / 'src/include/new.h'
            source = tree / 'src/backend/new.c'
            header.parent.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            header.write_text('typedef bool (*novel_hook_type) (int value);\n'
                              'extern PGDLLIMPORT novel_hook_type novel_hook;\n'
                              '#define CALL_NOVEL(value) (*novel_hook)(value)\n')
            source.write_text('novel_hook_type novel_hook = default_novel;\n')
            hooks, count = scan_tree(tree)
            self.assertEqual(count, 1)
            self.assertEqual(set(hooks), {'novel_hook'})
            self.assertEqual(hooks['novel_hook']['initial_value'], 'default_novel')
            self.assertEqual(hooks['novel_hook']['calls'][0][:2], ('src/include/new.h', 3))


class HookSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / 'data/wiki/hooks.json'
        cls.data = json.loads(path.read_text())
        cls.items = {item['name']: item for item in cls.data['items']}

    def test_complete_inventory_and_fixed_provenance(self):
        self.assertEqual([r['major'] for r in self.data['releases']],
                         [str(n) for n in range(10, 21)])
        for release in self.data['releases']:
            major = release['major']
            inventory = self.data['inventory'][major]
            names = sorted(name for name, item in self.items.items() if major in item['versions'])
            self.assertEqual(names, inventory['names'])
            self.assertEqual(len(names), inventory['hook_count'])
            self.assertGreater(inventory['header_count'], 600)
            self.assertRegex(release['revision'], r'^[0-9a-f]{40}$')
            for name in names:
                row = self.items[name]['versions'][major]
                self.assertEqual(row['release'], release)
                self.assertTrue(row['description'][0])
                self.assertTrue(row['signature'].startswith('typedef '))
                self.assertGreaterEqual(len(row['sources']), 3)
                for source in row['sources']:
                    self.assertIn('/blob/' + release['revision'] + '/', source['url'])
                    self.assertRegex(source['sha256'], r'^[0-9a-f]{64}$')
                    self.assertRegex(source['url'], r'#L\d+$')
        self.assertEqual(self.data['inventory']['10']['hook_count'], 27)
        self.assertEqual(self.data['inventory']['13']['hook_count'], 28)

    def test_known_signature_changes_and_non_null_defaults(self):
        executor = self.items['ExecutorRun_hook']['versions']
        self.assertIn('bool execute_once', executor['17']['signature'])
        self.assertNotIn('execute_once', executor['18']['signature'])
        analyzer = self.items['post_parse_analyze_hook']['versions']
        self.assertNotIn('JumbleState', analyzer['13']['signature'])
        self.assertIn('JumbleState', analyzer['14']['signature'])
        perms = self.items['ExecutorCheckPerms_hook']['versions']
        self.assertNotIn('List *rtePermInfos', perms['15']['signature'])
        self.assertIn('List *rtePermInfos', perms['16']['signature'])
        tls = self.items['openssl_tls_init_hook']['versions']
        self.assertNotIn('12', tls)
        self.assertEqual({f['label']: f['value'] for f in tls['18']['facts']}['初始值'],
                         'default_openssl_tls_init')
        self.assertNotIn('14', self.items['shmem_request_hook']['versions'])
        self.assertIn('15', self.items['shmem_request_hook']['versions'])

    def test_names_and_chinese_editorial_fields(self):
        from pgweb.wiki.hook_data import HOOKS
        self.assertEqual(set(self.items), set(HOOKS))
        for item in self.items.values():
            self.assertEqual(item['slug'], item['name'].lower())
            for field in ('name_zh', 'category', 'summary'):
                self.assertRegex(item[field], '[\u4e00-\u9fff]')
            self.assertNotIn('引入', item['summary'])


if __name__ == '__main__':
    unittest.main()
