"""Offline conversion and native rendering contracts for accepted Chinese text."""
from copy import deepcopy
from django.test import SimpleTestCase
from bs4 import BeautifulSoup

from pgweb.wiki.center_text import localized_html, plain_text, prepare
from tools.wiki_center_sync.topics import localize_snapshot, revalidate_index_evidence


def text_row(kind='role'):
    return {'collection': kind, 'key': 'example', 'version': '20', 'text': {
        'locale': 'zh-Hans', 'version': '20', 'source_database': 'center',
        'summary': '中文摘要', 'body_html': '<p>不能绕过权限检查。</p><pre>SELECT 1;</pre>',
        'content_hash': 'a' * 64, 'source_revision': 'pinned',
        'payload': {'facts': [{'label': '权限', 'value': '只读'}]}}}


class CanonicalTopicTests(SimpleTestCase):
    def test_conversion_preserves_code_evidence_and_comparison(self):
        original = {'description': ['Read only'], 'signature': 'example(int)',
                    'facts': [{'label': 'Privilege', 'value': 'Read only'}],
                    'sections': [], 'related': [], 'sources': [{'url': 'https://www.postgresql.org/docs/20/'}],
                    'comparison_data': {'signature': 'example(int)'},
                    'release': {'revision': 'original-source'}, 'runtime_verified': False}
        chinese = {'facts': [{'label': '权限', 'value': '旧译文'}]}
        before = deepcopy(original)
        canonical = text_row()
        result = localize_snapshot('role', '20', original, chinese, canonical)
        self.assertEqual(original, before)
        for field in ('signature', 'sources', 'comparison_data', 'release', 'runtime_verified'):
            self.assertEqual(result[field], original[field])
        self.assertEqual(result['facts'], canonical['text']['payload']['facts'])
        self.assertEqual(result['center_zh']['body_html'], canonical['text']['body_html'])
        self.assertEqual(result['description'], ['中文摘要'])

    def test_rejects_fallback_or_cross_version_translation(self):
        for field, value in [('version', '19'), ('locale', 'en')]:
            row = text_row()
            row['text'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                localize_snapshot('role', '20', {}, {}, row)

    def test_lock_translation_does_not_replace_command_variant_or_pin(self):
        command = {'slug': 'vacuum', 'variant': 'original-id', 'label': 'VACUUM FULL',
                   'note': 'Blocks reads.', 'source_url': 'https://www.postgresql.org/docs/20/',
                   'source': {'path': 'doc/src/sgml/mvcc.sgml', 'revision': 'original'}}
        base = {'conflicts': ['access-share'], 'commands': [command]}
        chinese = deepcopy(base)
        chinese['commands'][0].update(label='VACUUM FULL', note='阻塞读取。', variant='translated-id')
        result = localize_snapshot('lock', '20', base, chinese, text_row('lock'))
        self.assertEqual(result['commands'][0]['variant'], 'original-id')
        self.assertEqual(result['commands'][0]['source'], command['source'])
        self.assertEqual(result['commands'][0]['note'], '阻塞读取。')
        chinese['commands'][0]['label'] = 'VACUUM'
        with self.assertRaises(ValueError):
            localize_snapshot('lock', '20', base, chinese, text_row('lock'))

    def test_runtime_link_adaptation_does_not_mutate_stored_body(self):
        body = ('<p>不得更改 <code>NULL</code>。'
                '<a href="/zh/docs/18/a.html#x">中文</a>'
                '<a href="https://pg.center/docs/18/a.html">英文证据</a>'
                '<a href="/zh/wiki/sql/wait-for/?v=19">等待</a></p>')
        snapshot = {'center_zh': {'body_html': body}}
        prepare(snapshot, '18')
        self.assertEqual(snapshot['center_zh']['body_html'], body)
        links = [a['href'] for a in BeautifulSoup(snapshot['center_zh_rendered'], 'html.parser').select('a')]
        self.assertEqual(links, ['/docs/18/a.html#x', 'https://pg.center/docs/18/a.html', '/wiki/sql/wait/?v=19'])
        self.assertEqual(plain_text(snapshot['center_zh_rendered']), plain_text(body))

    def test_html_uses_existing_sanitizer_and_explicit_offline_link_map(self):
        output = localized_html('<script>bad()</script><p onclick="bad()">正文</p>'
                                '<a href="javascript:bad()">坏链接</a>'
                                '<a href="/zh/docs/9.0/a.html#old">来源</a>',
                                link_map={'/docs/9.0/a.html#old': '/docs/9.0/a.html#new'})
        self.assertNotIn('bad()', output)
        self.assertNotIn('onclick', output)
        self.assertIn('/docs/9.0/a.html#new', output)

    def test_nested_evidence_revalidation_requires_same_quote_and_state(self):
        old = {'release': {'revision': 'new'}, 'sources': [{'sha256': 'new'}],
               'capabilities': [{'key': 'ordered', 'state': 'yes', 'evidence': [
                   {'quote': 'Exact same-version statement.', 'file': 'indexes.html',
                    'anchor': 'x', 'url': '/docs/19/indexes.html#x', 'sha256': 'old'}]}],
               'storage_options': []}
        replay = deepcopy(old)
        replay['capabilities'][0]['evidence'][0]['sha256'] = 'new'
        adapted = deepcopy(old)
        changes = revalidate_index_evidence(old, adapted, replay)
        self.assertEqual(len(changes), 1)
        evidence = adapted['capabilities'][0]['evidence'][0]
        self.assertEqual(evidence['sha256'], 'new')
        self.assertEqual(evidence['prior_evidence']['sha256'], 'old')
        self.assertFalse(evidence['revalidation']['runtime_rerun'])
        self.assertEqual(old['capabilities'][0]['evidence'][0]['sha256'], 'old')
        for field, value in [('state', 'no'), ('quote', 'A different claim.')]:
            invalid = deepcopy(replay)
            if field == 'state':
                invalid['capabilities'][0][field] = value
            else:
                invalid['capabilities'][0]['evidence'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                revalidate_index_evidence(old, deepcopy(old), invalid)
