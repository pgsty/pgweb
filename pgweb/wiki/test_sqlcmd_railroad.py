"""Grammar behavior, per-major preview contracts and SVG geometry regressions."""

from copy import deepcopy
from itertools import product
from xml.etree import ElementTree as ET

from django.test import SimpleTestCase, TestCase
from django.core.cache import cache
import railroad as rr

from pgweb.search import indexer, service
from pgweb.search.models import SearchEntry
from pgweb.wiki.sqlcmd_railroad import choice, context, productions, walk
from pgweb.wiki.test_sqlcmd import make_dataset


def var(name):
    return '<em class="replaceable"><code>' + name + '</code></em>'


def language(node):
    """Small finite expansion to test paths, allowing up to two repetitions."""
    if node.kind in ('var', 'text'):
        return {(node.text,)}
    if node.kind == 'optional':
        return {()} | language(node.children[0])
    if node.kind == 'choice':
        return set().union(*(language(c) for c in node.children))
    if node.kind == 'group':
        return language(node.children[0])
    if node.kind in ('paren', 'quoted'):
        left, right = ('(', ')') if node.kind == 'paren' else ("'", "'")
        return {(left,) + v + (right,) for v in language(node.children[0])}
    if node.kind == 'repeat':
        values = language(node.children[0])
        separator = (node.text,) if node.text else ()
        return values | {a + separator + b for a, b in product(values, repeat=2)}
    return {sum(path, ()) for path in product(*(language(c) for c in node.children))}


class RailroadGrammarTests(SimpleTestCase):
    def test_optional_choice_and_literal_parentheses_have_different_paths(self):
        node = productions('FETCH [ NEXT | PRIOR ] ( ' + var('count') + ' )', 'FETCH')[0]['node']
        self.assertEqual(language(node), {('FETCH', '(', 'count', ')'),
                                         ('FETCH', 'NEXT', '(', 'count', ')'),
                                         ('FETCH', 'PRIOR', '(', 'count', ')')})

    def test_list_repeats_item_and_sort_modifiers_but_not_clause_keyword(self):
        html = 'SELECT [ ORDER BY ' + var('expression') + ' [ ASC | DESC ] [ NULLS FIRST ] [, ...] ]'
        node = productions(html, 'SELECT')[0]['node']
        repeat = next(n for n in walk(node) if n.kind == 'repeat')
        leaves = [n.text for n in walk(repeat) if n.kind in ('var', 'text')]
        self.assertEqual(leaves, ['expression', 'ASC', 'DESC', 'NULLS', 'FIRST'])
        self.assertIn(('SELECT', 'ORDER', 'BY', 'expression', 'ASC', ',', 'expression', 'DESC', 'NULLS', 'FIRST'), language(node))

    def test_explicit_group_repeats_without_swallowing_function_header(self):
        node = productions('CREATE FUNCTION ' + var('name') + ' { LANGUAGE ' + var('lang') + ' | WINDOW } ...', 'CREATE FUNCTION')[0]['node']
        self.assertIn(('CREATE', 'FUNCTION', 'name', 'WINDOW', 'LANGUAGE', 'lang'), language(node))
        self.assertNotIn(('CREATE', 'FUNCTION', 'name', 'WINDOW', 'name', 'WINDOW'), language(node))

    def test_named_list_does_not_repeat_the_object_name(self):
        html = 'ALTER TYPE ' + var('name') + ' ' + var('action') + ' [, ...]\n'
        html += '<span class="phrase">其中 ' + var('action') + ' 为以下之一：</span>\n  ADD X\n  DROP X'
        rules = productions(html, 'ALTER TYPE')
        self.assertIn(('ALTER', 'TYPE', 'name', 'action', ',', 'action'), language(rules[0]['node']))
        self.assertEqual(language(rules[1]['node']), {('ADD', 'X'), ('DROP', 'X')})

    def test_cte_belongs_to_select_and_table_is_a_separate_main_form(self):
        html = '[ WITH ' + var('query') + ' ]\nSELECT ' + var('value')
        html += '\n<span class="phrase">其中 ' + var('query') + ' 为：</span>\n  X AS ( SELECT Y )\n\nTABLE ' + var('name')
        rules = productions(html, 'SELECT')
        self.assertEqual([r['key'] for r in rules], ['', 'query', ''])
        self.assertIn(('WITH', 'query', 'SELECT', 'value'), language(rules[0]['node']))
        self.assertEqual(language(rules[2]['node']), {('TABLE', 'name')})

    def test_reset_is_an_alternative_to_set(self):
        rules = productions('SET ROLE ' + var('name') + '\nSET ROLE NONE\nRESET ROLE', 'SET ROLE')
        self.assertEqual(len(rules), 3)
        self.assertEqual(language(rules[2]['node']), {('RESET', 'ROLE')})

    def test_quoted_values_repeat_with_both_quotes(self):
        node = productions("CREATE TYPE AS ENUM ( '" + var('label') + "' [, ...] )", 'CREATE TYPE')[0]['node']
        self.assertIn(('CREATE', 'TYPE', 'AS', 'ENUM', '(', "'", 'label', "'", ',', "'", 'label', "'", ')'), language(node))

    def test_list_introducer_with_does_not_repeat(self):
        node = productions('ALTER MAPPING FOR ' + var('token') + ' [, ...] WITH ' + var('dictionary') + ' [, ...]', 'ALTER')[0]['node']
        repeats = [n for n in walk(node) if n.kind == 'repeat']
        self.assertEqual([[x.text for x in walk(n) if x.kind in ('text', 'var')] for n in repeats], [['token'], ['dictionary']])

    def test_empty_call_list_does_not_admit_a_leading_comma(self):
        node = productions('CALL ' + var('name') + ' ( [ ' + var('argument') + ' ] [, ...] )', 'CALL')[0]['node']
        self.assertEqual(language(node), {('CALL', 'name', '(', ')'), ('CALL', 'name', '(', 'argument', ')'),
                                         ('CALL', 'name', '(', 'argument', ',', 'argument', ')')})

    def test_multiline_alternatives_retain_their_continuations(self):
        html = 'SELECT ' + var('from_item') + '\n<span class="phrase">' + var('from_item') + ' 可以是下列之一：</span>\n'
        html += '    TABLE X\n        [ TABLESAMPLE Y ]\n    ( SELECT Z )\n'
        choices = productions(html, 'SELECT')[1]['node']
        self.assertEqual(language(choices), {('TABLE', 'X'), ('TABLE', 'X', 'TABLESAMPLE', 'Y'), ('(', 'SELECT', 'Z', ')')})

    def test_stacked_choice_bounds_include_the_last_branch_height(self):
        child = rr.Stack('first', 'second', 'third')
        diagram = choice([rr.Skip(), child])
        self.assertGreaterEqual(diagram.down, child.height + child.down + rr.VS)
        nested = choice([diagram, rr.Stack('fourth', 'fifth')])
        self.assertGreater(nested.down, diagram.down)

    def test_inline_and_nested_bars_do_not_join_separate_alternatives(self):
        html = 'INSERT ' + var('action') + '<span class="phrase">' + var('action') + ' 为以下之一：</span>\n'
        html += '    DO NOTHING\n    DO UPDATE { A |\n                B }\n              [ WHERE X ]\n'
        html += '    DO SELECT | DO READ\n'
        node = productions(html, 'INSERT')[1]['node']
        self.assertEqual(language(node), {('DO', 'NOTHING'), ('DO', 'UPDATE', 'A'), ('DO', 'UPDATE', 'B'),
                                         ('DO', 'UPDATE', 'A', 'WHERE', 'X'), ('DO', 'UPDATE', 'B', 'WHERE', 'X'),
                                         ('DO', 'SELECT'), ('DO', 'READ')})

    def test_svg_escapes_text_has_no_inline_styles_and_is_namespaced(self):
        snapshot = {'name': 'CHECK', 'synopsis_html': 'CHECK ' + var('x&lt;script&gt;') + ' ' + var('rule') +
                    '<span class="phrase">其中 ' + var('rule') + ' 为：</span> A | B'}
        before = deepcopy(snapshot)
        first, second = context(snapshot, 'detail'), context(snapshot, 'preview')
        self.assertEqual(snapshot, before)
        self.assertEqual(first['digest'], second['digest'])
        svg = first['rules'][0]['svg']
        ET.fromstring(svg)
        self.assertNotIn('<script>', svg)
        self.assertNotIn('<style', svg)
        self.assertIn('href="#detail-rule"', svg)
        self.assertIn('href="#preview-rule"', second['rules'][0]['svg'])
        self.assertEqual(svg.count('>rule</text>'), 1)


class RailroadPreviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_dataset()
        indexer.rebuild_sqlcmd()

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_version_changes_summary_diagram_current_marker_and_links(self):
        entry = SearchEntry.objects.get(source='sqlcmd', name='CREATE TABLE')
        url = '/search/preview/{}/'.format(entry.pk)
        a = self.client.get(url, {'v': '17'}).json()
        b = self.client.get(url, {'v': '18'}).json()
        self.assertEqual((a['version'], b['version']), (17, 18))
        self.assertNotEqual(a['syntax_digest'], b['syntax_digest'])
        self.assertNotIn('NEW OPTION', a['html'])
        self.assertIn('NEW OPTION', b['html'])
        self.assertIn('railroad-diagram', a['html'])
        self.assertTrue(a['url'].endswith('?v=17'))
        self.assertIn('/docs/17/', a['manual_url'])
        self.assertEqual([v['version'] for v in a['versions'] if v['current']], [17])
        # All majors, including those outside the manual search index.
        self.assertEqual(len(a['versions']), 18)

    def test_summary_comes_from_selected_snapshot_not_latest_index(self):
        entry = SearchEntry.objects.get(source='sqlcmd', name='SELECT')
        a, b = service.preview(entry, '17'), service.preview(entry, '18')
        self.assertIn('共享正文', a['html'])
        self.assertIn('新正文', b['html'])
        self.assertNotIn('新正文', a['html'])
        # Identical syntax can legitimately share a diagram across majors.
        self.assertEqual(a['syntax_digest'], b['syntax_digest'])

    def test_missing_version_is_explained_and_not_listed_as_available(self):
        entry = SearchEntry.objects.get(source='sqlcmd', name='CREATE PROPERTY GRAPH')
        data = service.preview(entry, '20')
        self.assertEqual(data['version'], 19)
        self.assertEqual([v['version'] for v in data['versions']], [19])
        self.assertIn('未收录 PostgreSQL 20', data['html'])
        self.assertIn('尚未正式发布', data['html'])

    def test_devel_manual_rename_and_new_command_default(self):
        entry = SearchEntry.objects.get(source='sqlcmd', name='WAIT FOR')
        older, newer = service.preview(entry, '19'), service.preview(entry, '20')
        self.assertIn('/docs/19/sql-wait-for.html', older['manual_url'])
        self.assertIn('/docs/devel/sql-waitfor.html', newer['manual_url'])
        self.assertEqual(service.preview(entry)['version'], 20)

    def test_detail_uses_the_same_version_diagram_as_preview(self):
        entry = SearchEntry.objects.get(source='sqlcmd', name='CREATE TABLE')
        data = service.preview(entry, '17')
        response = self.client.get('/docs/sql/create-table/?v=17')
        self.assertEqual(response.context['railroad']['digest'], data['syntax_digest'])
        self.assertContains(response, '语法铁道图')
