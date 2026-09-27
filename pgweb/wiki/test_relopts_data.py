"""Regression tests for relation-option scope and version extraction.

These tests need no database. The committed data is checked for the changes
most likely to be damaged by a generic definition-list parser.
"""
import json
from pathlib import Path
import unittest

from bs4 import BeautifulSoup
from tools.wiki.build_relopts import list_entries, paragraphs, term_names

ROOT = Path(__file__).resolve().parents[2]


class ReloptsDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads((ROOT / 'data/wiki/relopts.json').read_text())
        cls.items = {item['slug']: item for item in cls.payload['items']}

    def test_complete_documented_inventory(self):
        self.assertEqual(len(self.items), 60)
        counts = {major: sum(major in item['versions'] for item in self.items.values())
                  for major in map(str, range(10, 21))}
        self.assertEqual(counts, {'10': 41, '11': 43, '12': 47, '13': 51,
            '14': 51, '15': 52, '16': 52, '17': 52, '18': 56, '19': 58, '20': 59})
        self.assertEqual(sum(counts.values()), 562)
        self.assertEqual(self.payload['kind'], 'relopts')

    def test_separate_fillfactor_scopes(self):
        scopes = ['table', 'btree', 'hash', 'gist', 'spgist']
        for scope in scopes:
            self.assertIn(scope + '-fillfactor', self.items)
        table_facts = self.items['table-fillfactor']['versions']['18']['facts']
        btree_facts = self.items['btree-fillfactor']['versions']['18']['facts']
        self.assertIn({'label': '默认值', 'value': '100'}, table_facts)
        self.assertIn({'label': '默认值', 'value': '90'}, btree_facts)
        for scope in ['hash', 'gist', 'spgist']:
            facts = self.items[scope + '-fillfactor']['versions']['18']['facts']
            self.assertFalse(any(f['label'] in {'默认值', '取值范围'} for f in facts))
        self.assertNotIn('gin-fillfactor', self.items)
        self.assertNotIn('toast-fillfactor', self.items)

    def test_toast_only_expands_explicit_options(self):
        for absent in ['toast-autovacuum-analyze-threshold', 'toast-autovacuum-analyze-scale-factor',
                       'toast-autovacuum-parallel-workers', 'toast-user-catalog-table',
                       'toast-toast-tuple-target']:
            self.assertNotIn(absent, self.items)
        source = self.items['toast-autovacuum-vacuum-threshold']['versions']['18']
        self.assertIn('TOAST 参数的继承', [s['title'] for s in source['sections']])
        guc = next(s for s in source['sections'] if s['title'].startswith('对应全局参数'))
        self.assertIn('属于 GUC', guc['paragraphs'][0])
        self.assertTrue(any('触发' in p for p in guc['paragraphs'][1:]))

    def test_real_version_transitions(self):
        vacuum = self.items['table-vacuum-index-cleanup']['versions']
        self.assertIn({'label': '取值类型', 'value': '布尔值'}, vacuum['12']['facts'])
        self.assertIn({'label': '取值类型', 'value': '枚举值'}, vacuum['14']['facts'])
        self.assertIn('true', ' '.join(vacuum['12']['description']))
        self.assertIn('AUTO', ' '.join(vacuum['14']['description']))
        self.assertEqual(set(self.items['btree-vacuum-cleanup-index-scale-factor']['versions']), {'11', '12'})
        self.assertNotIn('12', self.items['btree-deduplicate-items']['versions'])
        self.assertNotIn('12', self.items['toast-autovacuum-vacuum-insert-threshold']['versions'])
        self.assertNotIn('17', self.items['table-autovacuum-vacuum-max-threshold']['versions'])
        self.assertNotIn('18', self.items['table-autovacuum-parallel-workers']['versions'])
        self.assertNotIn('18', self.items['table-log-autoanalyze-min-duration']['versions'])

    def test_toast_value_type_only_applies_when_creating_a_toast_relation(self):
        option = self.items['table-toast-value-type']
        self.assertEqual(set(option['versions']), {'20'})
        snapshot = option['versions']['20']
        self.assertIn({'label': '取值类型', 'value': '枚举值'}, snapshot['facts'])
        description = ' '.join(snapshot['description'])
        self.assertIn('chunk_id', description)
        self.assertIn('没有影响', description)
        self.assertIn('转储和恢复', description)
        self.assertNotIn('toast-toast-value-type', self.items)

    def test_views_are_not_physical_storage_options(self):
        invoker = self.items['view-security-invoker']
        self.assertEqual(invoker['category'], '视图选项')
        self.assertEqual(set(invoker['versions']), set(map(str, range(15, 21))))
        for snapshot in invoker['versions'].values():
            self.assertIn('普通视图不存储查询结果', snapshot['sections'][0]['paragraphs'][0])
            security = next(s for s in snapshot['sections'] if s['title'] == '安全语义')
            self.assertTrue(any('SECURITY DEFINER' in p for p in security['paragraphs']))
        check = self.items['view-check-option']['versions']['18']
        details = next(s for s in check['sections'] if s['title'] == '写入检查的语义')
        self.assertTrue(any('LOCAL' == p for p in details['paragraphs']))
        self.assertTrue(any('CASCADED' == p for p in details['paragraphs']))
        self.assertTrue(any('INSTEAD' in p for p in details['paragraphs']))

    def test_oids_compatibility_semantics(self):
        option = self.items['table-oids']
        self.assertEqual(option['category'], '表兼容选项')
        self.assertEqual(option['versions']['11']['signature'], 'WITH (OIDS = TRUE | FALSE)')
        self.assertEqual(option['versions']['12']['signature'], 'WITH (OIDS = FALSE)')
        self.assertTrue(any('不再受支持' in p for p in option['versions']['18']['description']))

    def test_source_provenance_and_development_urls(self):
        releases = {r['major']: r for r in self.payload['releases']}
        self.assertEqual(releases['19']['channel'], 'preview')
        self.assertEqual(releases['20']['channel'], 'devel')
        for item in self.items.values():
            for major, snapshot in item['versions'].items():
                self.assertEqual(snapshot['release'], releases[major])
                self.assertTrue(snapshot['description'])
                self.assertTrue(snapshot['sources'])
                for source in snapshot['sources']:
                    self.assertRegex(source['sha256'], r'^[a-f0-9]{64}$')
                    version = 'devel' if major == '20' else major
                    self.assertTrue(source['url'].startswith('/docs/' + version + '/'))
                text = json.dumps(snapshot, ensure_ascii=False)
                self.assertNotRegex(text, r'<(?:p|a|div|span|code)\b')
                self.assertNotIn('pgpedia', text)

    def test_old_and_new_definition_terms(self):
        old = BeautifulSoup('<dl><dt><span class="term"><code class="literal">autovacuum_enabled</code>, '
            '<code class="literal">toast.autovacuum_enabled</code> (<code class="type">boolean</code>)</span></dt>'
            '<dd><p>正文。</p><div class="note"><p>限制。</p></div></dd></dl>', 'html.parser')
        new = BeautifulSoup('<dl><dt id="RELOPTION-FILLFACTOR"><span class="term">'
            '<code class="varname">fillfactor</code> (<code class="type">integer</code>)</span>'
            '<a class="id_link" href="#RELOPTION-FILLFACTOR">#</a></dt><dd><p>正文。</p></dd></dl>', 'html.parser')
        names, _, dd = list_entries(old)[0]
        self.assertEqual(names, ['autovacuum_enabled', 'toast.autovacuum_enabled'])
        self.assertEqual(paragraphs(dd), ['正文。', '限制。'])
        self.assertEqual(term_names(new.dt), ['fillfactor'])

    def test_unrecognized_or_incomplete_definition_fails(self):
        for markup in ['<dl><dt>new parameter</dt><dd><p>text</p></dd></dl>',
                       '<dl><dt><code>fillfactor</code></dt></dl>']:
            with self.assertRaises(ValueError):
                list_entries(BeautifulSoup(markup, 'html.parser'))


if __name__ == '__main__':
    unittest.main()
