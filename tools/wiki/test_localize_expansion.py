"""No-database regression checks for fixed snapshot localization."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.wiki.localize_expansion import (
    Translator, align_page, localize, sha, technical,
)


class LocalizationTests(unittest.TestCase):
    def test_stable_definition_body_ignores_added_anchor_controls(self):
        en = '<dl><dt id="AUTH">AuthenticationOk</dt><dd><dl><dt>Int32(0)</dt><dd><p>Authentication succeeded.</p></dd></dl></dd></dl>'
        zh = '<dl><dt id="AUTH">AuthenticationOk<a class="id_link">#</a></dt><dd><dl><dt id="ZH-AUTO">Int32(0)<a class="id_link">#</a></dt><dd><p>认证成功。</p></dd></dl></dd></dl>'
        rows = align_page(en, zh)
        self.assertEqual(rows['Authentication succeeded.']['text'], '认证成功。')
        self.assertTrue(rows['Authentication succeeded.']['locator'].startswith('#AUTH/dd'))

    def test_changed_technical_or_numeric_facts_are_not_substituted(self):
        for zh in ('<p id="x">需要 <code>wal_level</code> 为 1。</p>',
                   '<p id="x">需要 <code>work_mem</code> 为 2。</p>'):
            self.assertNotIn('Needs work_mem at 1.', align_page(
                '<p id="x">Needs <code>work_mem</code> at 1.</p>', zh))

    def test_original_source_and_comparison_are_preserved(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'labels.tsv').write_text('Example\t示例\nInput\t输入\n')
            bundle = {'pages': {'18/a.html': {'en': '<p>Original text.</p>', 'zh': '<p>原文。</p>'}}}
            alignment = {'18/a.html': {'Original text.': {'text': '原文。', 'html': '原文。', 'locator': '#a'}}}
            translator = Translator(bundle, alignment, path)
            source = {'kind': 'plan', 'items': [{'slug': 'result', 'name': 'Result', 'summary': 'Example', 'category': 'Example', 'versions': {'18': {'facts': [{'label': 'Input', 'value': 'Original text.'}], 'comparison_data': {'description': ['Original text.']}, 'sources': [{'url': '/docs/18/a.html', 'sha256': 'english-hash'}]}}}]}
            saved = deepcopy(source)
            result, counts = localize(source, translator, 'fixed-commit')
            snapshot = result['items'][0]['versions']['18']
            self.assertEqual(source, saved)
            self.assertEqual(snapshot['comparison_data'], saved['items'][0]['versions']['18']['comparison_data'])
            self.assertEqual(snapshot['sources'][0]['sha256'], 'english-hash')
            self.assertEqual(snapshot['sources'][0]['url'], 'https://pg.center/docs/18/a.html')
            self.assertEqual(snapshot['localization']['sources'][0]['sha256'], sha(bundle['pages']['18/a.html']['zh']))
            self.assertEqual(snapshot['facts'][0]['value'], '原文。')
            self.assertEqual(counts['snapshots'], 1)

    def test_extension_translation_requires_matching_identity_and_original(self):
        with TemporaryDirectory() as directory:
            bundle = {'pages': {}, 'extensions': {'one': {'en': 'Same English.', 'zh': '第一项。'}, 'two': {'en': 'Same English.', 'zh': '第二项。'}, 'three': {'en': 'Same English.', 'zh': None}}}
            translator = Translator(bundle, {}, Path(directory))
            source = {'kind': 'fdw', 'items': [{'slug': 'core', 'name': 'core', 'summary': 'core', 'category': 'core', 'versions': {'20': {'collection_tables': [{'key': 'directory', 'columns': [{'key': 'extension', 'label': 'extension'}, {'key': 'description', 'label': 'description'}], 'rows': [{'extension': {'text': name, 'url': '/e/' + name + '/'}, 'description': 'Same English.'} for name in ('one', 'two', 'three')]}]}}}]}
            result, _ = localize(source, translator, 'fixed')
            snapshot = result['items'][0]['versions']['20']
            self.assertEqual([r['description'] for r in snapshot['collection_tables'][0]['rows']], ['第一项。', '第二项。', 'Same English.'])
            self.assertEqual([r['extension'] for r in snapshot['localization']['extension_sources']], ['one', 'two'])

    def test_technical_tokens_are_not_mistaken_for_untranslated_prose(self):
        for token in ('Byte1(\'R\')', 'Int32 (Oid)', '2026-09-29 · 75629c2e1e81 · README.md',
                      "'08:00:2b:01:02:03'", 'Index Only Scan', 'ISO 8859-1, ECMA 94'):
            self.assertTrue(technical(token), token)
        self.assertFalse(technical('A scan can spill to disk.'))


if __name__ == '__main__':
    unittest.main()
