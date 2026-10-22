"""Contracts for transferring verified Chinese text without changing evidence."""
from copy import deepcopy
from django.test import SimpleTestCase

from tools.wiki_center_sync.core import (chinese_text, display_version_metadata, fresh_row, local_manual_url,
                                         sql_display)
from . import func, func_importer, sqlcmd, sqlcmd_importer


class CenterCoreContractTests(SimpleTestCase):
    def test_display_version_does_not_rewrite_sampled_source(self):
        original = {'major': '19', 'label': '19 beta 4', 'source_tag': 'REL_19_BETA4',
                    'revision': 'original-source-sha', 'measurement': '19beta4'}
        value = display_version_metadata(original)
        self.assertEqual(value['label'], '19 rc 1')
        for key in ('source_tag', 'revision', 'measurement'):
            self.assertEqual(value[key], original[key])
        self.assertEqual(original['label'], '19 beta 4')

    def test_selected_chinese_must_be_real_and_keeps_source_hash(self):
        record = {'collection': 'sql', 'key': 'wait', 'version': '19',
                  'text': {'locale': 'zh-Hans', 'body_html': '<p>等待 WAL</p>',
                           'content_hash': 'original', 'summary': '等待'}}
        original = deepcopy(record)
        value = chinese_text(record, 'dataset')
        self.assertEqual(value['content_hash'], 'original')
        self.assertEqual(value['definition_version'], '19')
        self.assertEqual(record, original)
        record['text']['locale'] = 'en'
        with self.assertRaises(ValueError):
            chinese_text(record, 'dataset')
        record['text'].update(locale='zh-Hans', body_html='')
        with self.assertRaises(ValueError):
            chinese_text(record, 'dataset')

    def test_django_hash_will_be_recomputed_but_evidence_is_not_rewritten(self):
        row = {'content_hash': 'old', 'imported_at': 'old', 'source_rev': 'old',
               'facts': {'known_present_by': '7.4'}, 'evidence': {'runtimes': ['18.6']}}
        original = deepcopy(row)
        value = fresh_row(row, 'new')
        self.assertNotIn('content_hash', value)
        self.assertEqual(value['facts'], row['facts'])
        self.assertEqual(value['evidence'], row['evidence'])
        self.assertEqual(row, original)

    def test_sql_wrapper_preserves_literal_whitespace_and_historical_section(self):
        body = "<pre>FETCH  FORWARD 2 IN c\nSELECT 'a  b'</pre><section><h2>用法</h2><p>读取两行。</p><pre>SELECT 1</pre></section>"
        value = sql_display(body)
        self.assertEqual(value['synopsis_text'], "FETCH  FORWARD 2 IN c\nSELECT 'a  b'")
        self.assertEqual(value['sections'][0]['key'], 'usage')
        self.assertIn('<pre>SELECT 1</pre>', value['sections'][0]['html'])
        with self.assertRaises(ValueError):
            sql_display('<section><h2>描述</h2><pre>nested only</pre></section>')

    def test_sql_presentation_does_not_mutate_source_syntax(self):
        snap = {'synopsis_html': 'WAIT <em>lsn</em>', 'synopsis_text': 'WAIT lsn',
                'sections': [{'key': 'description', 'title': 'Description', 'html': '<p>Wait.</p>'}],
                'center_zh': {'summary': '等待', 'body_html': 'sealed source bytes',
                    'display': sql_display('<pre>WAIT lsn</pre><section><h2>描述</h2><p>等待。<a href="/zh/wiki/sql/wait-for/?v=19">命令</a></p></section>')}}
        original = deepcopy(snap)
        view = sqlcmd.localized_snapshot(snap)
        self.assertEqual(snap, original)
        self.assertEqual(view['purpose_zh'], '等待')
        self.assertIn('/wiki/sql/wait/?v=19', view['sections'][0]['html'])
        self.assertEqual(view['center_zh']['body_html'], 'sealed source bytes')

    def test_historical_files_allowed_without_path_traversal(self):
        for name in ('sql-fetch.htm', 'sql-fetch.html'):
            self.assertIsNotNone(sqlcmd_importer.FILE_RE.fullmatch(name))
        for name in ('../sql-fetch.htm', 'sql-fetch.html/other', 'random.htm'):
            self.assertIsNone(sqlcmd_importer.FILE_RE.fullmatch(name))

    def test_reviewed_translation_is_not_labelled_manual_translation(self):
        origin = 'same-version-source-with-reviewed-chinese'
        self.assertIn(origin, func_importer.ZH_SOURCES)
        self.assertEqual(func.zh_label({'zh_from': origin}), '同版原文审阅译文')
        self.assertNotEqual(func.zh_label({'zh_from': origin}), func.zh_label({'zh_from': 'doc'}))

    def test_signature_localization_preserves_technical_values(self):
        signature = {'text': 'f(x integer)', 'html': '<code>f</code>(x integer)',
                     'returns': 'integer', 'description': 'Returns x.', 'description_zh': '返回 x。',
                     'description_zh_html': '<p>返回 <code>x</code>，参见<a href="/zh/docs/18/functions-math.html">手册</a>。</p>',
                     'zh_from': 'same-version-pgdoc', 'examples': [{'expr': 'f(1)', 'result': '1'}]}
        snap = {'signatures': [signature], 'center_zh': {}}
        original = deepcopy(snap)
        result = func.signatures_of(snap, None)[0]
        self.assertEqual(snap, original)
        for key in ('text', 'html', 'returns', 'examples'):
            self.assertEqual(result[key], signature[key])
        self.assertIn('/docs/18/functions-math.html', result['description_zh_html'])

    def test_local_manual_alias_is_same_version_and_exact(self):
        pages = {('7.0', 'sql-fetch.html'): {'anchors': ['SQL-FETCH']}}
        value, error = local_manual_url('/zh/docs/7.0/sql-fetch.htm#sql-fetch', pages)
        self.assertIsNone(error)
        self.assertEqual(value, '/docs/7.0/sql-fetch.html#SQL-FETCH')
        for url, reason in [('/docs/7.1/sql-fetch.htm#SQL-FETCH', 'missing-page'),
                            ('/docs/7.0/sql-fetch.htm#unknown', 'missing-anchor')]:
            value, error = local_manual_url(url, pages)
            self.assertEqual(value, url)
            self.assertEqual(error, reason)

    def test_reviewed_dossier_links_require_the_exact_target(self):
        old = '/docs/18/fdwhandler.html#FDW-CALLBACKS-SCAN'
        pages = {('18', 'fdw-callbacks.html'): {'anchors': ['FDW-CALLBACKS-SCAN']}}
        self.assertEqual(local_manual_url(old, pages),
                         ('/docs/18/fdw-callbacks.html#FDW-CALLBACKS-SCAN', None))
        self.assertEqual(local_manual_url(old, {}), (old, 'missing-page'))
        self.assertEqual(local_manual_url(old.replace('/18/', '/17/'), pages)[1], 'missing-page')
