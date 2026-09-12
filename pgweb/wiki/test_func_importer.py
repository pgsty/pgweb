"""用手工构造的四版上游原页与三版中文手册检验函数百科的采集、中文叠加、比较与写入。

夹具分两层，和真实分工一致：
- **事实**放在缓存目录里的英文原页（9.6 老式 DocBook 五列表、12 英文五列表、13 与 18 签名段），
  存在性、签名、示例、分组都只认它；
- **中文**放在 `DocPage` 里的本站手册译文，只补描述。手册里故意放了一个上游那一版
  还没有的函数，用来证明译文不会凭空造出版本覆盖。

测试全程不联网：`upstream_majors()` 被替换成夹具里的四个版本，`urlopen` 一律抛错。
"""

from copy import deepcopy
from datetime import date
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from pgweb.core.models import Version
from pgweb.docs.models import DocPage
from pgweb.wiki import func_importer as importer
from pgweb.wiki.models import (FUNC_GROUPS, FUNC_GROUP_LABEL, FUNC_GROUP_ORDER, FuncVersion,
                               PgFunction, func_group_of, func_slug)

MAJORS = ('9.6', '12', '13', '18')


# ------------------------------------------------------------------ 通用片段

def version_row(tree, current=False, testing=0, supported=False):
    return Version(tree=tree, current=current, testing=testing, latestminor=3,
                   supported=supported, reldate=date(2026, 8, 13),
                   firstreldate=date(2020, 1, 1), eoldate=date(2030, 1, 1))


def page(body):
    return '<div class="sect1" id="FUNCTIONS-DEMO">' + body + '</div>'


def prose(anchor, blocks):
    """散文页：每个 `pre.synopsis` 后面跟一段描述。"""
    return ('<div class="sect2" id="' + anchor + '">' +
            ''.join('<pre class="synopsis">\n' + synopsis + '\n</pre><p>' + description + '</p>'
                    for synopsis, description in blocks) + '</div>')


# ------------------------------------------------------------------ 上游：五列表

def old_row(call, returns, description, example='', result=''):
    return ('<tr><td><a class="indexterm" id="id-1.2.3"></a><code class="literal">'
            '<code class="function">{}</code></code></td><td><code class="type">{}</code></td>'
            '<td>{}</td><td><code class="literal">{}</code></td>'
            '<td><code class="literal">{}</code></td></tr>'.format(
                call, returns, description, example, result))


def old_row_split(name, args, returns, description, example='', result=''):
    """上游常见写法：函数名单独在 code.function 里，参数在同一格后面的兄弟节点上。"""
    return ('<tr><td><code class="literal"><code class="function">{}</code> ( {} )</code></td>'
            '<td><code class="type">{}</code></td><td>{}</td>'
            '<td><code class="literal">{}</code></td>'
            '<td><code class="literal">{}</code></td></tr>'.format(
                name, args, returns, description, example, result))


def example_result_table(anchor, rows):
    """有些页把结果列写成 Example Result，也要认出来。"""
    head = ('<thead><tr><th>Function</th><th>Description</th><th>Example</th>'
            '<th>Example Result</th></tr></thead>')
    body = ''.join('<tr><td><code class="literal"><code class="function">{}</code></code></td>'
                   '<td>{}</td><td><code class="literal">{}</code></td>'
                   '<td><code class="literal">{}</code></td></tr>'.format(*row) for row in rows)
    return ('<div class="table" id="' + anchor + '"><table class="table">' + head +
            '<tbody>' + body + '</tbody></table></div>')


def old_table(anchor, rows):
    head = ('<thead><tr><th>Function</th><th>Return Type</th><th>Description</th>'
            '<th>Example</th><th>Result</th></tr></thead>')
    return ('<div class="table" id="' + anchor + '"><table class="table">' + head +
            '<tbody>' + ''.join(rows) + '</tbody></table></div>')


def trig_one_column(anchor, rows):
    """9.6 以前的三角函数表：只有一列函数。"""
    head = '<thead><tr><th>Function</th><th>Description</th></tr></thead>'
    body = ''.join('<tr><td><code class="literal"><code class="function">{}</code></code></td>'
                   '<td>{}</td></tr>'.format(call, text) for call, text in rows)
    return ('<div class="table" id="' + anchor + '"><table class="table">' + head +
            '<tbody>' + body + '</tbody></table></div>')


def trig_two_columns(anchor, rows):
    """9.6 起的三角函数表：弧度与角度各占一列，两列都是函数列。"""
    head = ('<thead><tr><th>Function (radians)</th><th>Function (degrees)</th>'
            '<th>Description</th></tr></thead>')
    body = ''.join('<tr><td><code class="literal"><code class="function">{}</code></code></td>'
                   '<td><code class="literal"><code class="function">{}</code></code></td>'
                   '<td>{}</td></tr>'.format(radians, degrees, text)
                   for radians, degrees, text in rows)
    return ('<div class="table" id="' + anchor + '"><table class="table">' + head +
            '<tbody>' + body + '</tbody></table></div>')


# ------------------------------------------------------------------ 上游：签名段

def signature(body):
    return '<p class="func_signature">' + body + '</p>'


def entry(bodies, description, examples=()):
    return ('<td class="func_table_entry">' + ''.join(signature(body) for body in bodies) +
            '<p>' + description + '</p>' +
            ''.join('<p><code class="literal">{}</code> → <code class="returnvalue">{}</code></p>'
                    .format(expr, result) for expr, result in examples) + '</td>')


def new_table(anchor, entries):
    return ('<div class="table" id="' + anchor + '"><p class="title"><strong>Table</strong></p>'
            '<div class="table-contents"><table class="table"><tbody>' +
            ''.join('<tr>' + item + '</tr>' for item in entries) +
            '</tbody></table></div></div>')


def call(name, args, returns):
    body = '<code class="function">{}</code> ( {} )'.format(name, args)
    return body + ' → <code class="returnvalue">{}</code>'.format(returns) if returns else body


SUB_PLAIN = call('substring', '<em class="parameter"><code>string</code></em> '
                              '<code class="type">text</code>', 'text')
SUB_FROM = call('substring', '<em class="parameter"><code>string</code></em> '
                             '<code class="type">text</code> <code class="literal">FROM</code> '
                             '<em class="parameter"><code>pattern</code></em>', 'text') + '.'
SUB_SIMILAR = call('substring', '<em class="parameter"><code>string</code></em> '
                                '<code class="type">text</code> '
                                '<code class="literal">SIMILAR</code> '
                                '<em class="parameter"><code>pattern</code></em>', 'text')
OPERATOR_ONLY = ('<code class="type">text</code> <code class="literal">||</code> '
                 '<code class="type">text</code> → <code class="returnvalue">text</code>')
LINKS = ('<a class="indexterm" id="id-4"></a><a href="other.html#X">other</a> '
         '<a href="#X">here</a> <a href="https://example.com/">outside</a> '
         '<a href="javascript:evil()">bad</a>')

XML_SYNOPSIS = call('xmlelement', '<code class="literal">NAME</code> '
                                  '<em class="replaceable"><code>name</code></em>', 'xml')
XML_PAIR = (call('table_to_xml', '<code class="type">regclass</code>', 'xml') + '\n' +
            call('query_to_xml', '<code class="type">text</code>', 'xml'))
# 手册把同一个函数的几种写法连着摆，中间夹着「或写成…：」这样的抬头。
XML_ALT = '<code class="function">xmlelement</code> ( <code class="literal">NAME</code> name, content )'
# 上游也有不给函数名加标记的 synopsis，同页别处标过就收。
JSON_TABLE_SYNOPSIS = ('JSON_TABLE (\n    <em class="replaceable"><code>context_item</code></em>,\n'
                       '    COLUMNS ( <em class="replaceable"><code>column</code></em> )\n)')
EXISTS_SYNOPSIS = 'EXISTS (<em class="replaceable"><code>subquery</code></em>)'

GCD_DESCRIPTION = 'Greatest common divisor.'


def upstream_pages(major):
    """一个大版本的上游英文原页。9.6 与 12 是五列表，13 与 18 是签名段。"""
    pages = {}
    if major in ('9.6', '12'):
        rows = [old_row('substring(string [from int])', 'text', 'Extract substring',
                        "substring('Thomas' from 2)", 'homas'),
                old_row('bit_length(string)', 'int', 'Number of bits in string',
                        "bit_length('jose')", '32'),
                old_row_split('to_char', '<code class="type">timestamp</code>, '
                              '<code class="type">text</code>', 'text',
                              'convert time stamp to string', "to_char(now(), 'HH')", '05')]
        pages['functions-string.html'] = page(
            old_table('FUNCTIONS-STRING-SQL', rows) +
            example_result_table('FUNCTIONS-STRING-OTHER', [
                ('to_hex(int)', 'convert number to hex', 'to_hex(2147483647)', '7fffffff')]))
        pages['functions-admin.html'] = page(old_table('FUNCTIONS-ADMIN-BACKUP', [
            old_row('pg_start_backup(label text)', 'pg_lsn', 'Prepare for on-line backup',
                    "pg_start_backup('x')", '0/0')]))
        trig = [('acos(x)', 'inverse cosine'), ('asin(x)', 'inverse sine')]
        pages['functions-enum.html'] = page(unmarked_table('FUNCTIONS-ENUM-SUPPORT', [
            (['enum_first(anyenum)'], 'Returns the first value of the input enum type.',
             "enum_first(null::rainbow)", 'red'),
            (['enum_range(anyenum)'], 'Returns all values of the input enum type.',
             'enum_range(null::rainbow)', '{red,orange}'),
        ]))
        pages['functions-json.html'] = page(unmarked_table('FUNCTIONS-JSON-CREATION', [
            (['to_json(anyelement)', 'to_jsonb(anyelement)'],
             'Returns the value as json or jsonb.', "to_json('Fred'::text)", '"Fred"'),
            (['string || string'], 'Not a function, must be skipped.', '', ''),
        ]))
        pages['functions-math.html'] = page(
            trig_one_column('FUNCTIONS-MATH-TRIG-TABLE', trig) if major == '9.6' else
            trig_two_columns('FUNCTIONS-MATH-TRIG-TABLE',
                             [('acos(x)', 'acosd(x)', 'inverse cosine'),
                              ('asin(x)', 'asind(x)', 'inverse sine')]))
    else:
        subs = [SUB_PLAIN, SUB_FROM] if major == '13' else [SUB_PLAIN, SUB_SIMILAR]
        pages['functions-string.html'] = page(new_table('FUNCTIONS-STRING-SQL', [
            entry([OPERATOR_ONLY], 'Concatenates the two strings.', [("'a' || 'b'", 'ab')]),
            entry(subs, 'Extracts the substring.' if major == '13' else
                  'Extracts the substring, reworded.',
                  [("substring('Thomas' from 2)", 'homas')]),
            entry([call('bit_length', '<em class="parameter"><code>string</code></em> '
                                      '<code class="type">text</code>', 'integer')],
                  'Number of bits in string. ' + LINKS, [("bit_length('jose')", '32')]),
            entry([call('gcd', '<code class="type">numeric_type</code>', 'numeric_type')],
                  GCD_DESCRIPTION),
            # 结果有多行时写在紧随其后的 <pre> 里，箭头后面是空的。
            entry([call('regexp_matches', '<code class="type">text</code>', 'setof text[]')],
                  'Returns captured substrings.') .replace(
                      '</td>', '<p><code class="literal">regexp_matches(\'ab\', \'.\', \'g\')</code>'
                               ' →</p><pre class="programlisting">\n {a}\n {b}\n</pre></td>'),
        ]))
        pages['functions-bitstring.html'] = page(new_table('FUNCTIONS-BITSTRING', [
            entry([call('bit_length', '<code class="type">bit</code>', 'integer')],
                  'Number of bits in bit string.')]))
        pages['functions-formatting.html'] = page(new_table('FUNCTIONS-FORMATTING-TABLE', [
            entry([call('to_char', '<code class="type">timestamp</code>, '
                                   '<code class="type">text</code>', 'text')],
                  'Converts time stamp to string.', [("to_char(now(), 'HH')", '05')])]))
        pages['functions-math.html'] = page(new_table('FUNCTIONS-MATH-TRIG-TABLE', [
            entry([call('acos', '<code class="type">double precision</code>',
                        'double precision')], 'Inverse cosine, result in radians.'),
            entry([call('acosd', '<code class="type">double precision</code>',
                        'double precision')], 'Inverse cosine, result in degrees.'),
            entry([call('asin', '<code class="type">double precision</code>',
                        'double precision')], 'Inverse sine, result in radians.'),
            entry([call('asind', '<code class="type">double precision</code>',
                        'double precision')], 'Inverse sine, result in degrees.'),
        ]))
        pages['functions-subquery.html'] = page(
            prose('FUNCTIONS-EXISTS', [(EXISTS_SYNOPSIS, 'Subquery existence test.')]))
        if major == '18':
            pages['functions-json.html'] = page(
                prose('FUNCTIONS-SQLJSON-TABLE',
                      [(JSON_TABLE_SYNOPSIS, 'JSON_TABLE turns JSON into a table.')]) +
                new_table('FUNCTIONS-JSON-TABLE', [
                    entry([call('json_agg', '<code class="type">anyelement</code>', 'json')],
                          'Aggregates into a JSON array, see '
                          '<code class="function">JSON_TABLE</code>.')]))
            pages['functions-aggregate.html'] = page(new_table('FUNCTIONS-AGGREGATE-TABLE', [
                entry([call('any_value', '<code class="type">anyelement</code>', 'anyelement')],
                      'Returns an arbitrary value from the non-null input values.')]))
    # 第一个 synopsis 后面还跟着整节正文，描述只该取第一段；
    # 再往后是「或写成…：」抬头加第二种写法，抬头不是描述。
    pages['functions-xml.html'] = page(prose('FUNCTIONS-PRODUCING-XML', [
        (XML_SYNOPSIS, 'Produces an XML element.'),
        (XML_PAIR, 'Maps a table or a query to XML.'),
    ]).replace('<p>Produces an XML element.</p>',
               '<p>Produces an XML element.</p><p>The name and attname items shown in the '
               'syntax are simple identifiers, not values.</p>'
               '<p><code class="literal">xmlelement(name foo)</code> → '
               '<code class="returnvalue">&lt;foo/&gt;</code></p>'
               '<p>or written with content:</p>'
               '<pre class="synopsis">\n' + XML_ALT + '\n</pre>'
               '<p>or as a plain call:</p>'))
    return pages


def docbook(html):
    """把现代写法降级成 9.x 的老式 DocBook：class 全大写、行内标记用 <tt>。"""
    for tag in ('code', 'span', 'em'):
        html = html.replace('<{} class="'.format(tag), '<tt class="')
        html = html.replace('</{}>'.format(tag), '</tt>')
    for name in ('literal', 'function', 'type', 'parameter', 'replaceable', 'returnvalue',
                 'optional', 'table', 'sect1', 'sect2', 'indexterm', 'synopsis'):
        html = html.replace('class="{}"'.format(name), 'class="{}"'.format(name.upper()))
    return html


def write_upstream_cache(root, majors=MAJORS):
    for major in majors:
        directory = Path(root) / major
        directory.mkdir(parents=True, exist_ok=True)
        pages = upstream_pages(major)
        index = ''.join('<a href="{}">{}</a>'.format(name, name) for name in pages)
        index += '<a href="notfunctions.html">other</a>'
        (directory / 'functions.html').write_text('<html><body>' + index + '</body></html>',
                                                  encoding='utf-8')
        for name, content in pages.items():
            body = docbook(content) if major.startswith('9.') else content
            (directory / name).write_text(body, encoding='utf-8')
    return root


# ------------------------------------------------------------------ 本站手册（只出中文）

def zh_row(call, returns, description, example='', result=''):
    return ('<tr><td><code class="literal"><code class="function">{}</code></code></td>'
            '<td><code class="type">{}</code></td><td>{}</td>'
            '<td><code class="literal">{}</code></td>'
            '<td><code class="literal">{}</code></td></tr>'.format(
                call, returns, description, example, result))


def zh_old_table(anchor, rows):
    head = ('<thead><tr><th>函数</th><th>返回类型</th><th>描述</th>'
            '<th>示例</th><th>结果</th></tr></thead>')
    return ('<div class="table" id="' + anchor + '"><table class="table">' + head +
            '<tbody>' + ''.join(rows) + '</tbody></table></div>')


def unmarked_table(anchor, rows):
    """上游 ≤12 的枚举与 JSON 函数表：调用只包在 code.literal 里，整页没有 code.function。"""
    head = ('<thead><tr><th>Function</th><th>Description</th><th>Example</th>'
            '<th>Example Result</th></tr></thead>')
    body = ''.join(
        '<tr><td><a class="indexterm" id="id-9"></a>' +
        ''.join('<p><code class="literal">{}</code></p>'.format(call) for call in calls) +
        '</td><td>{}</td><td><code class="literal">{}</code></td>'
        '<td><code class="literal">{}</code></td></tr>'.format(text, example, result)
        for calls, text, example, result in rows)
    return ('<div class="table" id="' + anchor + '"><table class="table">' + head +
            '<tbody>' + body + '</tbody></table></div>')


def manual_pages(major):
    """本站手册译文。故意和上游对不齐，用来检验译文不参与存在性判断。"""
    pages = {}
    if major == '12':
        pages['functions-string.html'] = page(zh_old_table('FUNCTIONS-STRING-SQL', [
            zh_row('substring(string [from int])', 'text', '提取子字符串。',
                   "substring('Thomas' from 2)", 'homas'),
            zh_row('bit_length(string)', 'int', '字符串中的位数。', "bit_length('jose')", '32'),
        ]))
        return pages
    subs = [SUB_PLAIN, SUB_FROM] if major == '13' else [SUB_PLAIN, SUB_SIMILAR]
    entries = [entry([call('bit_length', '<em class="parameter"><code>string</code></em> '
                                         '<code class="type">text</code>', 'integer')],
                     '字符串中的位数。')]
    if major == '18':
        # substring 与 gcd 的译文只有 18 有：一个英文换了措辞不许借，一个一字不差可以借。
        entries.insert(0, entry(subs, '提取子串，说法改了。',
                                [("substring('Thomas' from 2)", 'homas')]))
        entries.append(entry([call('gcd', '<code class="type">numeric_type</code>',
                                   'numeric_type')], '最大公约数。'))
    pages['functions-string.html'] = page(new_table('FUNCTIONS-STRING-SQL', entries))
    pages['functions-xml.html'] = page(prose('FUNCTIONS-PRODUCING-XML', [
        (XML_SYNOPSIS, '产生一个 XML 元素。')]))
    if major == '13':
        # 译文仓库按新版回填的典型症状：13 的译文里混进了上游 18 才有的函数。
        pages['functions-json.html'] = page(
            prose('FUNCTIONS-SQLJSON-TABLE',
                  [(JSON_TABLE_SYNOPSIS, 'JSON_TABLE 把 JSON 展成表。')]) +
            new_table('FUNCTIONS-JSON-TABLE', [
                entry([call('json_agg', '<code class="type">anyelement</code>', 'json')],
                      '聚合成 JSON 数组，见 <code class="function">JSON_TABLE</code>。')]))
    return pages


def load_manuals():
    Version.objects.bulk_create([
        version_row(9.6), version_row(12), version_row(13),
        version_row(18, current=True, supported=True),
    ])
    for major, tree in (('12', 12), ('13', 13), ('18', 18)):
        DocPage.objects.create(version_id=tree, file='functions.html', content='<p>Chapter 9</p>')
        DocPage.objects.create(version_id=tree, file='func-other.html', content='<p>不相干</p>')
        for filename, content in manual_pages(major).items():
            DocPage.objects.create(version_id=tree, file=filename, title=filename, content=content)


def export(root, majors=MAJORS, offline=False):
    """夹具版导出：版本清单固定成夹具里的几版，urlopen 一律抛错保证不联网。"""
    with patch.object(importer, 'upstream_majors', lambda: list(majors)), \
         patch('urllib.request.urlopen', side_effect=AssertionError('不该联网')):
        return importer.export_snapshot(offline=offline, cache_dir=root)


def by_slug(snapshot):
    return {item['slug']: item for item in snapshot['functions']}


def change_between(item, from_major, to_major):
    return next((change for change in item['changes']
                 if change['from'] == from_major and change['to'] == to_major), None)


# ------------------------------------------------------------------ 纯函数

class FuncPureTests(SimpleTestCase):
    def test_groups_table(self):
        self.assertEqual(len(FUNC_GROUPS), 32)
        self.assertEqual(len({slug for _, slug, _, _ in FUNC_GROUPS}), 32)
        self.assertEqual(FUNC_GROUP_ORDER['logical'], 0)
        self.assertLess(FUNC_GROUP_ORDER['string'], FUNC_GROUP_ORDER['bitstring'])
        self.assertEqual(FUNC_GROUP_LABEL['info'], '系统信息函数和操作符')
        self.assertEqual(func_group_of('functions-string.html'), 'string')
        self.assertEqual(func_group_of('functions-event-triggers.html'), 'event-triggers')

    def test_slug(self):
        self.assertEqual(func_slug('to_char'), 'to-char')
        self.assertEqual(func_slug('COALESCE'), 'coalesce')
        self.assertEqual(func_slug('_pg_expandarray'), 'fn-pg-expandarray')
        self.assertEqual(func_slug(''), '')

    def test_normalize_signature(self):
        self.assertEqual(importer.normalize_text('substring (  a  )   →  text.'),
                         'substring ( a ) → text')
        self.assertEqual(importer.normalize_text('COALESCE(value [, ...])'),
                         'COALESCE(value [, ...])')

    def test_split_call(self):
        self.assertEqual(importer.split_call('rank(args) WITHIN GROUP (ORDER BY x)'),
                         ('rank', 'args', 'WITHIN GROUP (ORDER BY x)'))
        self.assertEqual(importer.split_call('current_catalog'), ('current_catalog', '', ''))

    def test_header_role(self):
        self.assertEqual(importer.header_role('Function'), 'name')
        self.assertEqual(importer.header_role('函数'), 'name')
        # 9.6 起三角函数表拆成弧度与角度两列，两列都要当函数列采。
        self.assertEqual(importer.header_role('Function (radians)'), 'name')
        self.assertEqual(importer.header_role('Function (degrees)'), 'name')
        self.assertEqual(importer.header_role('函数（角度）'), 'name')
        self.assertEqual(importer.header_role('Return Type'), 'returns')
        self.assertEqual(importer.header_role('Operator'), '')
        self.assertEqual(importer.header_role('转换名称'), '')

    def test_upstream_slug_and_layout(self):
        self.assertEqual(importer.upstream_slug('18'), '18')
        self.assertEqual(importer.upstream_slug(importer.DEVEL_MAJOR), 'devel')
        self.assertEqual(importer.layout_of('9.6'), 'table-old')
        self.assertEqual(importer.layout_of('12'), 'table-old')
        self.assertEqual(importer.layout_of('13'), 'table-new')
        self.assertLess(importer.version_key('9.6'), importer.version_key('10'))
        self.assertEqual(importer.major_of(9.0), '9.0')

    def test_compare_snapshots(self):
        left = {'group': 'string', 'lang': 'en', 'layout': 'table-new',
                'signatures': [{'text': 'f ( a ) → int'}], 'description': 'Does a thing.'}
        self.assertIsNone(importer.compare_snapshots(deepcopy(left), deepcopy(left), '13', '14'))
        right = deepcopy(left)
        right['signatures'].append({'text': 'f ( a, b ) → int'})
        change = importer.compare_snapshots(left, right, '13', '14')
        self.assertEqual(change['signatures'], {'added': ['f ( a, b ) → int'], 'removed': []})
        self.assertIsNone(importer.compare_snapshots(None, None, '13', '14'))
        self.assertEqual(importer.compare_snapshots(None, left, '13', '14')['status'], 'added')
        self.assertEqual(importer.compare_snapshots(left, None, '13', '14')['status'], 'removed')


# ------------------------------------------------------------------ 采集与导出

class FuncExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        load_manuals()

    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        write_upstream_cache(self.root.name)
        self.snapshot = export(self.root.name)
        self.items = by_slug(self.snapshot)

    def test_versions(self):
        self.assertEqual([v['major'] for v in self.snapshot['versions']], list(MAJORS))
        rows = {v['major']: v for v in self.snapshot['versions']}
        self.assertTrue(all(v['source'] == 'upstream' for v in self.snapshot['versions']))
        self.assertNotIn('lang', rows['18'])
        self.assertEqual(rows['12']['layout'], 'table-old')
        self.assertEqual(rows['13']['layout'], 'table-new')
        self.assertEqual(rows['18']['status'], 'stable')
        self.assertEqual(rows['18']['support_status'], 'supported')
        self.assertEqual(rows['18']['doc_slug'], '18')
        # 9.6 本站没有手册，地址段留空。
        self.assertEqual(rows['9.6']['doc_slug'], '')
        self.assertEqual(self.snapshot['default_major'], '18')
        for version in self.snapshot['versions']:
            actual = sum(version['major'] in item['versions']
                         for item in self.snapshot['functions'])
            self.assertEqual(version['function_count'], actual)

    def test_signature_table_shape(self):
        snapshot = self.items['substring']['versions']['18']
        self.assertEqual(snapshot['layout'], 'table-new')
        self.assertEqual(snapshot['lang'], 'en')
        self.assertEqual(snapshot['doc'], {'file': 'functions-string.html',
                                           'anchor': 'FUNCTIONS-STRING-SQL', 'slug': '18'})
        self.assertEqual([item['text'] for item in snapshot['signatures']],
                         ['substring ( string text ) → text',
                          'substring ( string text SIMILAR pattern ) → text'])
        head = snapshot['signatures'][0]
        self.assertEqual(head['returns'], 'text')
        self.assertEqual(head['description'], 'Extracts the substring, reworded.')
        self.assertEqual(head['examples'], [{'expr': "substring('Thomas' from 2)",
                                             'result': 'homas'}])
        self.assertIn('<code class="function">substring</code>', head['html'])
        self.assertNotIn('id=', head['html'])

    def test_old_table_shape(self):
        snapshot = self.items['substring']['versions']['12']
        self.assertEqual(snapshot['layout'], 'table-old')
        head = snapshot['signatures'][0]
        self.assertEqual(head['text'], 'substring ( string [from int] ) → text')
        self.assertEqual(head['description'], 'Extract substring')
        self.assertEqual(head['examples'], [{'expr': "substring('Thomas' from 2)",
                                             'result': 'homas'}])

    def test_docbook_shape(self):
        """9.x 是老式 DocBook，class 转小写后复用同一套五列表解析。"""
        snapshot = self.items['substring']['versions']['9.6']
        self.assertEqual(snapshot['signatures'][0]['text'],
                         'substring ( string [from int] ) → text')
        self.assertEqual(snapshot['description'], 'Extract substring')

    def test_arguments_outside_code_function(self):
        """上游把参数放在 code.function 外面时，签名不能退化成 `to_char → text`。"""
        head = self.items['to-char']['versions']['12']['signatures'][0]
        self.assertEqual(head['text'], 'to_char ( timestamp, text ) → text')
        self.assertEqual(head['returns'], 'text')
        self.assertEqual(head['examples'], [{'expr': "to_char(now(), 'HH')", 'result': '05'}])
        for item in self.snapshot['functions']:
            for snapshot in item['versions'].values():
                for signature in snapshot['signatures']:
                    if signature['text'].startswith('to_char'):
                        self.assertIn('(', signature['text'])

    def test_example_result_column(self):
        """表头写成 Example Result 的表，结果列也要认出来。"""
        head = self.items['to-hex']['versions']['12']['signatures'][0]
        self.assertEqual(head['examples'],
                         [{'expr': 'to_hex(2147483647)', 'result': '7fffffff'}])

    def test_prose_description_is_first_paragraph_only(self):
        """散文页后面往往还有整节正文，描述只取第一段，示例照收。"""
        snapshot = self.items['xmlelement']['versions']['18']
        self.assertEqual(snapshot['description'], 'Produces an XML element.')
        self.assertNotIn('simple identifiers', snapshot['description'])
        self.assertEqual(self.items['xmlelement']['summary'], 'Produces an XML element.')
        self.assertEqual(snapshot['signatures'][0]['examples'],
                         [{'expr': 'xmlelement(name foo)', 'result': '<foo/>'}])

    def test_lead_in_is_not_a_description(self):
        """「或写成…：」这类抬头是下一条写法的引子，不能当描述；找不到就往前取正文。"""
        snapshot = self.items['xmlelement']['versions']['18']
        texts = [item['text'] for item in snapshot['signatures']]
        self.assertEqual(len(texts), 2)
        for item in snapshot['signatures']:
            self.assertNotIn('or written with content', item['description'])
            self.assertNotIn('or as a plain call', item['description'])
        # 第二种写法自己后面只有抬头，往前取到了最近一段实打实的正文（既不是抬头也不是示例）。
        self.assertEqual(snapshot['signatures'][1]['description'],
                         'The name and attname items shown in the syntax are simple '
                         'identifiers, not values.')
        self.assertEqual(snapshot['signatures'][0]['description'], 'Produces an XML element.')

    def test_multiline_example_result(self):
        """`expr →` 后面跟一段 <pre> 的写法，结果在那一段里。"""
        head = self.items['regexp-matches']['versions']['18']['signatures'][0]
        self.assertEqual(head['examples'],
                         [{'expr': "regexp_matches('ab', '.', 'g')", 'result': '{a}\n{b}'}])

    def test_bare_synopsis_name_is_marked(self):
        """兜底认出来的函数名要补上 code.function，签名卡里才和表格形态一致。"""
        head = self.items['json-table']['versions']['18']['signatures'][0]
        self.assertTrue(head['html'].startswith('<code class="function">JSON_TABLE</code>'))
        marked = self.items['xmlelement']['versions']['18']['signatures'][0]
        self.assertIn('<code class="function">xmlelement</code>', marked['html'])

    def test_synopsis_shape(self):
        snapshot = self.items['xmlelement']['versions']['18']
        self.assertEqual(snapshot['group'], 'xml')
        self.assertEqual(snapshot['doc']['anchor'], 'FUNCTIONS-PRODUCING-XML')
        self.assertEqual(snapshot['signatures'][0]['text'], 'xmlelement ( NAME name ) → xml')
        self.assertEqual(snapshot['description'], 'Produces an XML element.')
        self.assertEqual(self.items['table-to-xml']['versions']['18']['signatures'][0]['text'],
                         'table_to_xml ( regclass ) → xml')
        self.assertEqual(self.items['query-to-xml']['versions']['18']['signatures'][0]['text'],
                         'query_to_xml ( text ) → xml')

    def test_unmarked_synopsis_names(self):
        item = self.items['json-table']
        self.assertEqual(item['name'], 'JSON_TABLE')
        self.assertIn('JSON_TABLE ( context_item, COLUMNS ( column ) )',
                      item['versions']['18']['signatures'][0]['text'])
        self.assertNotIn('exists', self.items)

    def test_operator_rows_are_not_entries(self):
        self.assertTrue(all('||' not in item['signature'] for item in self.snapshot['functions']))

    def test_two_column_function_table(self):
        """9.6 起弧度/角度两列表：acos 不能因为换了表头就「消失」，acosd 同时入库。"""
        self.assertEqual(self.items['acos']['present_in'], ['9.6', '12', '13', '18'])
        self.assertEqual(self.items['asin']['present_in'], ['9.6', '12', '13', '18'])
        self.assertEqual(self.items['acosd']['present_in'], ['12', '13', '18'])
        self.assertIsNone(change_between(self.items['acos'], '9.6', '12'))
        self.assertEqual(self.items['acos']['versions']['12']['signatures'][0]['text'],
                         'acos ( x )')

    def test_unmarked_old_tables(self):
        """≤12 的枚举与 JSON 表整页没有 code.function，不兜底就会被误判成 13 才引入。"""
        self.assertEqual(self.items['enum-first']['first_version'], '9.6')
        self.assertEqual(self.items['enum-range']['first_version'], '9.6')
        self.assertEqual(self.items['enum-first']['versions']['12']['signatures'][0]['text'],
                         'enum_first ( anyenum )')
        # 一格里并列摆两条，各自成条。
        self.assertEqual(self.items['to-json']['first_version'], '9.6')
        self.assertEqual(self.items['to-jsonb']['first_version'], '9.6')
        self.assertEqual(self.items['to-json']['versions']['12']['signatures'][0]['examples'],
                         [{'expr': "to_json('Fred'::text)", 'result': '"Fred"'}])
        # 操作符行不匹配「标识符 (」，不会误收。
        self.assertNotIn('string', self.items)

    def test_manual_does_not_invent_versions(self):
        """13 的译文里混进了上游 18 才有的函数，存在性必须只认上游。"""
        self.assertEqual(self.items['json-table']['present_in'], ['18'])
        self.assertEqual(self.items['json-table']['first_version'], '18')
        self.assertEqual(self.items['json-agg']['present_in'], ['18'])

    def test_multi_page_grouping(self):
        item = self.items['bit-length']
        self.assertEqual(item['group'], 'string')
        self.assertEqual(item['groups'], ['string', 'bitstring'])
        self.assertEqual(item['versions']['18']['pages'],
                         ['functions-string.html', 'functions-bitstring.html'])
        self.assertIn(['bit-length', ['string', 'bitstring']],
                      self.snapshot['harvest']['multi_group'])

    def test_link_rewriting_and_sanitising(self):
        html = self.items['bit-length']['versions']['18']['description_html']
        self.assertIn('href="/docs/18/other.html#X"', html)
        self.assertIn('href="/docs/18/functions-string.html#X"', html)
        self.assertNotIn('javascript:', html)
        # 9.6 本站没有手册，同一条链接只能指上游。
        old = self.items['substring']['versions']['9.6']
        self.assertEqual(importer.link_target('other.html', {'major': '9.6', 'doc_slug': ''},
                                              'functions-string.html'),
                         'https://www.postgresql.org/docs/9.6/other.html')
        self.assertEqual(old['doc']['slug'], '')

    def test_added_and_removed(self):
        added = self.items['gcd']
        self.assertEqual(added['first_version'], '13')
        self.assertEqual(change_between(added, '12', '13')['status'], 'added')
        gone = self.items['pg-start-backup']
        self.assertEqual(gone['last_version'], '12')
        self.assertEqual(change_between(gone, '12', '13')['status'], 'removed')

    def test_doc_overhaul(self):
        change = change_between(self.items['substring'], '12', '13')
        self.assertTrue(change['doc_overhaul'])
        self.assertEqual(change['signatures'], {'added': [], 'removed': []})
        self.assertFalse(change['descriptions_changed'])
        self.assertEqual(self.snapshot['harvest']['doc_overhaul_at'], ['13'])
        self.assertNotIn('13', self.items['substring']['changed_in'])

    def test_signature_diff_and_wording(self):
        change = change_between(self.items['substring'], '13', '18')
        self.assertEqual(change['signatures']['added'],
                         ['substring ( string text SIMILAR pattern ) → text'])
        self.assertEqual(change['signatures']['removed'],
                         ['substring ( string text FROM pattern ) → text'])
        self.assertTrue(change['descriptions_changed'])
        self.assertEqual(self.items['substring']['changed_in'], ['18'])

    def test_group_changed(self):
        change = change_between(self.items['to-char'], '12', '13')
        self.assertEqual(change['group_changed'], {'from': 'string', 'to': 'formatting'})

    def test_transition(self):
        rows = {v['major']: v for v in self.snapshot['versions']}
        self.assertEqual(rows['9.6']['transition'], {})
        transition = rows['13']['transition']
        self.assertEqual(transition['from'], '12')
        self.assertIn('gcd', transition['added'])
        self.assertIn('pg-start-backup', transition['removed'])
        self.assertTrue(transition['doc_overhaul'])
        self.assertEqual(transition['changed'], [])
        self.assertIn({'slug': 'to-char', 'from': 'string', 'to': 'formatting'},
                      transition['moved'])
        later = rows['18']['transition']
        self.assertIn({'slug': 'substring', 'added': 1, 'removed': 1}, later['changed'])
        self.assertEqual(rows['18']['changed_count'], len(later['changed']))

    # -------------------------------------------------------------- 中文叠加层

    def test_chinese_from_same_version(self):
        snapshot = self.items['bit-length']['versions']['18']
        self.assertEqual(snapshot['zh_from'], 'doc')
        self.assertEqual(snapshot['description_zh'], '字符串中的位数。')
        self.assertEqual(snapshot['signatures'][0]['description_zh'], '字符串中的位数。')
        self.assertEqual(snapshot['signatures'][0]['zh_from'], 'doc')
        self.assertEqual(self.items['bit-length']['summary_zh'], '字符串中的位数。')
        # 英文事实原样保留，中文只是叠加。
        self.assertTrue(snapshot['description'].startswith('Number of bits in string.'))

    def test_chinese_inherited_only_when_english_identical(self):
        """gcd 两版英文一字不差，13 可以借 18 的译文；substring 换了措辞，不许借。"""
        gcd = self.items['gcd']
        self.assertEqual(gcd['versions']['18']['zh_from'], 'doc')
        self.assertEqual(gcd['versions']['13']['zh_from'], 'inherited')
        self.assertEqual(gcd['versions']['13']['description_zh'], '最大公约数。')
        self.assertEqual(gcd['versions']['13']['signatures'][0]['zh_from'], 'inherited')
        substring = self.items['substring']
        self.assertEqual(substring['versions']['18']['zh_from'], 'doc')
        self.assertEqual(substring['versions']['13']['zh_from'], '')
        self.assertEqual(substring['versions']['13']['description_zh'], '')

    def test_chinese_absent_leaves_english(self):
        item = self.items['any-value']
        self.assertEqual(item['versions']['18']['zh_from'], '')
        self.assertEqual(item['versions']['18']['signatures'][0]['zh_from'], '')
        self.assertEqual(item['summary_zh'], '')
        self.assertEqual(item['summary'],
                         'Returns an arbitrary value from the non-null input values.')

    def test_chinese_never_reaches_versions_without_upstream(self):
        self.assertEqual(set(self.items['json-table']['versions']), {'18'})
        self.assertEqual(self.items['json-table']['versions']['18']['zh_from'], '')

    def test_zh_coverage_and_report(self):
        rows = {v['major']: v for v in self.snapshot['versions']}
        harvest = self.snapshot['harvest']
        for major, version in rows.items():
            actual = sum(major in item['versions'] and
                         bool(item['versions'][major]['description_zh'])
                         for item in self.snapshot['functions'])
            self.assertEqual(version['zh_coverage'], actual)
            self.assertEqual(harvest['versions'][major]['zh'], actual)
        # 9.6 本站没有手册：拿得到中文只可能是借来的，而且英文必须一字不差。
        self.assertGreater(rows['18']['zh_coverage'], 0)
        for item in self.snapshot['functions']:
            snapshot = item['versions'].get('9.6')
            if snapshot:
                self.assertIn(snapshot['zh_from'], ('inherited', ''))
        self.assertEqual(set(harvest['zh']) - {'signatures'}, {'doc', 'inherited', 'none'})
        self.assertEqual(sum(harvest['zh'][key] for key in ('doc', 'inherited', 'none')),
                         self.snapshot['stats']['snapshots'])

    def test_harvest_report(self):
        harvest = self.snapshot['harvest']
        self.assertEqual(harvest['versions']['18']['layout'], 'table-new')
        self.assertNotIn('lang', harvest['versions']['18'])
        self.assertEqual(harvest['upstream']['majors'], list(MAJORS))
        self.assertEqual(harvest['upstream']['failures'], [])
        self.assertNotIn('fetched', harvest['upstream'])
        self.assertIn(['18', 'functions-subquery.html'], harvest['pages_without_functions'])

    # -------------------------------------------------------------- 校验

    def test_validate_rejects_bad_snapshots(self):
        for mutate in (
            lambda snap: snap['functions'][0].pop('present_in'),
            lambda snap: snap['functions'][0].update(changed_in=['12', '13', '18']),
            lambda snap: snap['functions'][0].update(group='不存在的分组'),
            lambda snap: snap.update(default_major='99'),
            lambda snap: snap['functions'][0]['versions']['18'].update(zh_from='maybe'),
            lambda snap: snap['functions'][0]['versions']['18']['signatures'][0].pop('zh_from'),
            lambda snap: snap['versions'][0].pop('zh_coverage'),
        ):
            broken = deepcopy(self.snapshot)
            mutate(broken)
            with self.assertRaises(ValueError):
                importer.validate(broken)

    def test_digest_is_stable(self):
        self.assertEqual(importer.digest(self.snapshot),
                         importer.digest(deepcopy(self.snapshot)))


# ------------------------------------------------------------------ 抓取与降级

class FuncFetchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        load_manuals()

    def test_offline_skips_missing_versions(self):
        with tempfile.TemporaryDirectory() as root:
            write_upstream_cache(root, majors=('13', '18'))
            snapshot = export(root, offline=True)
        upstream = snapshot['harvest']['upstream']
        self.assertEqual(upstream['majors'], ['13', '18'])
        self.assertEqual([failure['major'] for failure in upstream['failures']], ['9.6', '12'])
        self.assertEqual([v['major'] for v in snapshot['versions']], ['13', '18'])
        self.assertEqual(by_slug(snapshot)['substring']['first_version'], '13')

    def test_offline_with_empty_cache_fails(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                export(root, offline=True)

    def test_cache_hit_never_downloads(self):
        with tempfile.TemporaryDirectory() as root:
            write_upstream_cache(root)
            report = {'majors': [], 'failures': []}
            with patch('urllib.request.urlopen', side_effect=AssertionError('不该联网')):
                pages = importer.upstream_pages(list(MAJORS), root, False, report)
        self.assertEqual(sorted(pages), sorted(MAJORS))
        self.assertNotIn('downloads', report)


# ------------------------------------------------------------------ 写库

class FuncImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        load_manuals()

    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        write_upstream_cache(self.root.name)
        self.snapshot = export(self.root.name)

    def test_preview_then_import_then_idempotent(self):
        preview = importer.preview(self.snapshot)
        self.assertEqual(preview['added'], len(self.snapshot['functions']))
        self.assertEqual(PgFunction.objects.count(), 0)

        report = importer.import_snapshot(self.snapshot)
        self.assertEqual(report['added'], len(self.snapshot['functions']))
        self.assertEqual(PgFunction.objects.count(), len(self.snapshot['functions']))
        self.assertEqual(FuncVersion.objects.count(), len(MAJORS))

        again = importer.import_snapshot(self.snapshot)
        self.assertEqual(again['added'], 0)
        self.assertEqual(again['updated'], 0)
        self.assertEqual(again['unchanged'], len(self.snapshot['functions']))

    def test_stored_row_shape(self):
        importer.import_snapshot(self.snapshot)
        row = PgFunction.objects.get(slug='substring')
        self.assertEqual(row.name, 'substring')
        self.assertEqual(row.group, 'string')
        self.assertEqual(row.group_label, FUNC_GROUP_LABEL['string'])
        self.assertEqual(row.present_in, list(MAJORS))
        self.assertEqual(row.changed_in, ['18'])
        self.assertEqual(row.url, '/docs/func/substring/')
        self.assertEqual(row.eyebrow, 'FUNCTION')
        version = FuncVersion.objects.get(major='18')
        self.assertEqual(version.status_label, '当前稳定版')
        self.assertEqual(version.changes_url, '/docs/func/changes/18/')
        self.assertEqual(version.source_label, '上游英文原页')
        self.assertGreater(version.zh_coverage, 0)
        self.assertLessEqual(version.zh_coverage, version.function_count)

    def test_update_only_touches_changed_rows(self):
        importer.import_snapshot(self.snapshot)
        changed = deepcopy(self.snapshot)
        target = next(item for item in changed['functions'] if item['slug'] == 'gcd')
        target['summary_zh'] = '改过的一句话。'
        report = importer.import_snapshot(changed)
        self.assertEqual(report['updated'], 1)
        self.assertEqual(report['unchanged'], len(changed['functions']) - 1)
        self.assertEqual(PgFunction.objects.get(slug='gcd').summary_zh, '改过的一句话。')

    def test_prune(self):
        importer.import_snapshot(self.snapshot)
        PgFunction.objects.create(slug='stale-one', name='stale_one', name_key='stale_one',
                                  group='string', first_version='12', last_version='12')
        FuncVersion.objects.create(major='11', position=-1)
        kept = importer.import_snapshot(self.snapshot)
        self.assertEqual(kept['missing'], {'functions': ['stale-one'], 'versions': ['11']})
        self.assertIn('未加 --prune', kept['note'])

        pruned = importer.import_snapshot(self.snapshot, prune=True)
        self.assertEqual(pruned['removed'], {'functions': 1, 'versions': ['11']})
        self.assertFalse(PgFunction.objects.filter(slug='stale-one').exists())
        self.assertFalse(FuncVersion.objects.filter(major='11').exists())
