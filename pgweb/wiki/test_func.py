"""函数百科栏目：取数形状、三种页面与检索条目。

夹具在库里造一份 18 个版本、6 个函数的小数据集，形状与导入器写出来的一致
（`docs/func-column.md` §2）：一个 9.0 基线活到 20、一个 13 新增、一个 12 之后
移除、一个换过分组、一个大小写混合名、两个多签名。变化记录由 `func.compare`
按相邻两版的快照现算，与页面读的是同一套判定。

函数的版本区间按夹具需要简化过，不是真实的收录历史。
"""

import copy
from datetime import date

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings

from . import func
from .columns import BY_SLUG
from .models import FUNC_GROUP_LABEL, FuncVersion, PgFunction


MAJORS = ('9.0', '9.1', '9.2', '9.3', '9.4', '9.5', '9.6',
          '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20')
# 事实一律取自上游英文页；本站手册只有 10 起才有译文，9.x 只有英文。
NO_CHINESE = MAJORS[:7]
# 11 版本站没有手册，中文借用 10 的：快照记 'inherited'。
INHERITED = ('11',)
OLD_LAYOUT = MAJORS[:10]
# 本站手册只有这几棵树；9.x 没有手册，20 是 devel。
MANUAL_TREES = (10, 12, 18, 0)

LABEL = {'19': '19 beta 3', '20': '20 devel'}
STATUS = {'18': 'stable', '19': 'preview', '20': 'devel'}
SUPPORT = {'stable': 'supported', 'preview': 'preview', 'devel': 'devel'}

PAGE_TITLE = {
    'functions-string.html': '9.4. 字符串函数和操作符',
    'functions-formatting.html': '9.8. 数据类型格式化函数',
    'functions-uuid.html': '9.14. UUID 函数',
    'functions-conditional.html': '9.18. 条件表达式',
    'functions-array.html': '9.19. 数组函数和操作符',
    'functions-srf.html': '9.25. 集合返回函数',
    'functions-info.html': '9.26. 系统信息函数和操作符',
}


def zh_from_of(major):
    if major in NO_CHINESE:
        return ''
    return 'inherited' if major in INHERITED else 'doc'


def layout_of(major):
    return 'table-old' if major in OLD_LAYOUT else 'table-new'


def doc_slug(major):
    if major in NO_CHINESE:
        return ''
    return 'devel' if major == '20' else major


# ---------------------------------------------------------------- 夹具

def make_versions():
    FuncVersion.objects.bulk_create([
        FuncVersion(
            major=major, label=LABEL.get(major, major),
            status=STATUS.get(major, 'historical'),
            support_status=SUPPORT.get(STATUS.get(major, 'historical'), 'end-of-life'),
            doc_slug=doc_slug(major),
            # 事实恒为上游英文页；本站手册只提供中文。
            source='upstream', layout=layout_of(major),
            position=index)
        for index, major in enumerate(MAJORS)])


def sig(text, returns='', zh='', en='', examples=()):
    """一条签名，形状照 `docs/func-column.md` §2 的快照。"""
    return {
        'text': text,
        'html': '<code class="function">{}</code>'.format(text.split(' (')[0]),
        'returns': returns, 'description_zh': zh, 'description': en,
        # 两份 HTML 分语言：英文那份恒有，中文那份没有译文时为空。
        'description_html': '<p>{}</p>'.format(en), 'description_zh_html': '<p>{}</p>'.format(zh),
        'examples': [{'expr': expr, 'result': result} for expr, result in examples],
    }


def make_snapshot(major, group, page, anchor, signatures, pages=None, prose=False):
    """一版快照。本站手册没有该版译文时，中文整份留空，只剩上游英文描述。

    `prose=True` 是「上游这一版只在正文里提到这个函数、没有给出签名」：签名列表为空，
    描述照常，另带 `prose_only` 标记。
    """
    zh_from = zh_from_of(major)
    rows = []
    for item in copy.deepcopy(signatures):
        if not zh_from:
            item['description_zh'] = ''
            item['description_zh_html'] = ''
        # 逐条判定：整份快照标 'doc'，个别签名也可能没配上中文。
        item['zh_from'] = zh_from if item['description_zh'] else ''
        rows.append(item)
    first = rows[0] if rows else {}
    return {
        'group': group, 'group_label': FUNC_GROUP_LABEL[group],
        'pages': list(pages or (page,)),
        'doc': {'file': page, 'anchor': anchor, 'slug': doc_slug(major)},
        'layout': layout_of(major), 'zh_from': zh_from,
        'signatures': [] if prose else rows, 'prose_only': bool(prose),
        'description_zh': first.get('description_zh', ''),
        'description': first.get('description', ''),
    }


def make_changes(versions, majors):
    """相邻两版都存在才比，新的在后；增删记在后一版。"""
    changes = []
    first, last = majors[0], majors[-1]
    for index in range(1, len(MAJORS)):
        previous, current = MAJORS[index - 1], MAJORS[index]
        left, right = versions.get(previous), versions.get(current)
        if right and not left:
            if current == first and first != MAJORS[0]:
                changes.append(func.compare({}, right, previous, current))
            continue
        if left and not right:
            if previous == last:
                changes.append(func.compare(left, {}, previous, current))
            continue
        if not left:
            continue
        change = func.compare(left, right, previous, current)
        if change is not None:
            changes.append(change)
    return changes


def make_function(name, slug, group, page, anchor, snapshots, position, groups=None, prose=()):
    """`snapshots` 是 {major: [签名…]}，其余字段照导入器的算法推出来。

    `prose` 列出「上游只在正文里提到、没有给出签名」的版本。
    """
    majors = [major for major in MAJORS if major in snapshots]
    versions = {}
    for major in majors:
        item = snapshots[major]
        signatures, where = (item if isinstance(item, tuple) else (item, group))
        versions[major] = make_snapshot(major, where, page, anchor, signatures,
                                        prose=major in prose)
    changes = make_changes(versions, majors)
    latest = versions[majors[-1]]
    first_signature = (latest['signatures'] or [{}])[0]
    function = PgFunction(
        slug=slug, name=name, name_key=name.lower(),
        group=latest['group'], group_label=latest['group_label'],
        groups=groups or [latest['group']],
        summary=first_signature.get('description', ''),
        summary_zh=first_signature.get('description_zh', ''),
        signature=first_signature.get('text', ''),
        first_version=majors[0], last_version=majors[-1], present_in=majors,
        changed_in=[change['to'] for change in changes
                    if change['signatures']['added'] or change['signatures']['removed']],
        signature_count=len(latest['signatures']),
        versions=versions, changes=changes, position=position, source_rev='fixture')
    function.save()
    return function


# 12 及以前的五列表拼出来的签名，与 13 起的签名段写法不同：那一跳整体改写。
SUB_OLD = [sig('substring ( string from integer for integer ) → text', returns='text',
               en='Extract substring.', zh='提取子串。',
               examples=[("substring('Thomas' from 2 for 3)", 'hom')]),
           sig('substring ( string from pattern ) → text', returns='text',
               en='Extract substring matching POSIX regular expression.', zh='按正则提取子串。')]
SUB_NEW = [sig('substring ( string text [ FROM start integer ] [ FOR count integer ] ) → text',
               returns='text', zh='提取子串。', en='Extracts the substring.',
               examples=[("substring('Thomas' from 2 for 3)", 'hom')]),
           sig('substring ( string text FROM pattern text ) → text', returns='text',
               zh='按 POSIX 正则提取子串。', en='Extracts the first substring matching POSIX regex.')]
SUB_SIMILAR = sig('substring ( string text SIMILAR pattern text ESCAPE escape text ) → text',
                  returns='text', zh='按 SQL 正则提取子串。',
                  en='Extracts the first substring matching SQL regex.')

TO_CHAR_OLD = [sig('to_char ( timestamp, text ) → text', returns='text',
                   en='Convert time stamp to string.', zh='把时间戳转成字符串。'),
               sig('to_char ( numeric, text ) → text', returns='text',
                   en='Convert number to string.', zh='把数字转成字符串。')]
# 第二条没有中文：整份快照有译文，个别签名仍可能没配上，页面要退回英文。
TO_CHAR_NEW = [sig('to_char ( timestamp with time zone, text ) → text', returns='text',
                   zh='把时间戳转成字符串。', en='Converts time stamp to string.'),
               sig('to_char ( numeric_type, text ) → text', returns='text',
                   en='Converts number to string.')]

COALESCE_OLD = [sig('COALESCE ( value [, ...] )', en='Return first non-null value.',
                    zh='返回第一个非空值。')]
COALESCE_NEW = [sig('COALESCE ( value [, ...] ) → value', zh='返回第一个非空值。',
                    en='Returns the first of its arguments that is not null.')]

UNNEST_OLD = [sig('unnest ( anyarray ) → setof anyelement', returns='setof anyelement',
                  en='Expand an array to a set of rows.', zh='把数组展开成多行。')]
UNNEST_NEW = [sig('unnest ( anyarray ) → setof anyelement', returns='setof anyelement',
                  zh='把数组展开成多行。', en='Expands an array into a set of rows.')]

UUID_NEW = [sig('gen_random_uuid ( ) → uuid', returns='uuid', zh='生成版本 4 的随机 UUID。',
                en='Generates a version 4 random UUID.')]

XIP_OLD = [sig('txid_snapshot_xip ( txid_snapshot ) → setof bigint', returns='setof bigint',
               en='Get in-progress transaction IDs in snapshot.', zh='取快照中进行中的事务号。')]


def make_dataset():
    make_versions()
    # 1) 9.0 收录基线，一直活到 20；13 是手册重排那一跳，15 多一条签名。
    substring = {}
    for major in MAJORS:
        if major in OLD_LAYOUT:
            substring[major] = SUB_OLD
        elif major in ('13', '14'):
            substring[major] = SUB_NEW
        else:
            substring[major] = SUB_NEW + [SUB_SIMILAR]
    make_function('substring', 'substring', 'string', 'functions-string.html',
                  'FUNCTIONS-STRING-SQL', substring, position=3000)

    # 2) 名字里有下划线：规范地址是连字符形式。
    to_char = {major: (TO_CHAR_OLD if major in OLD_LAYOUT else TO_CHAR_NEW) for major in MAJORS}
    make_function('to_char', 'to-char', 'formatting', 'functions-formatting.html',
                  'FUNCTIONS-FORMATTING', to_char, position=7000)

    # 3) 13 新增。
    uuid = {major: UUID_NEW for major in MAJORS[MAJORS.index('13'):]}
    make_function('gen_random_uuid', 'gen-random-uuid', 'uuid', 'functions-uuid.html',
                  'FUNCTIONS-UUID', uuid, position=14000,
                  # 引入那一版上游只在正文里提到，没有给签名。
                  prose=('13',))

    # 4) 全大写的语法型函数：名字原样保留，地址走小写。
    coalesce = {major: (COALESCE_OLD if major in OLD_LAYOUT else COALESCE_NEW)
                for major in MAJORS}
    make_function('COALESCE', 'coalesce', 'conditional', 'functions-conditional.html',
                  'FUNCTIONS-COALESCE-NVL-IFNULL', coalesce, position=18000)

    # 5) 14 换了分组：签名没变，主分组从数组函数挪到集合返回函数。
    unnest = {}
    for major in MAJORS:
        signatures = UNNEST_OLD if major in OLD_LAYOUT else UNNEST_NEW
        unnest[major] = (signatures, 'array' if MAJORS.index(major) < MAJORS.index('14') else 'srf')
    make_function('unnest', 'unnest', 'srf', 'functions-array.html', 'FUNCTIONS-ARRAY',
                  unnest, position=26000, groups=['array', 'srf'])

    # 6) 12 之后移除。
    xip = {major: XIP_OLD for major in OLD_LAYOUT}
    make_function('txid_snapshot_xip', 'txid-snapshot-xip', 'info', 'functions-info.html',
                  'FUNCTIONS-TXID-SNAPSHOT', xip, position=27000,
                  # 上游 9.x 的原页只在正文里提到它，10 起才列进函数表。
                  prose=('9.0', '9.1', '9.2', '9.3', '9.4', '9.5', '9.6'))

    counts, signatures, zh = {}, {}, {}
    added, removed, changed = {}, {}, {}
    for function in PgFunction.objects.all():
        for major in function.present_in:
            counts[major] = counts.get(major, 0) + 1
            signatures[major] = signatures.get(major, 0) + len(
                function.versions[major]['signatures'])
            if function.versions[major]['zh_from']:
                zh[major] = zh.get(major, 0) + 1
        for change in function.changes:
            bucket = {'added': added, 'removed': removed}.get(change['status'], changed)
            bucket[change['to']] = bucket.get(change['to'], 0) + 1
    for version in FuncVersion.objects.all():
        version.function_count = counts.get(version.major, 0)
        version.signature_count = signatures.get(version.major, 0)
        version.zh_coverage = zh.get(version.major, 0)
        version.added_count = added.get(version.major, 0)
        version.removed_count = removed.get(version.major, 0)
        version.changed_count = changed.get(version.major, 0)
        version.save(update_fields=['function_count', 'signature_count', 'zh_coverage',
                                    'added_count', 'removed_count', 'changed_count'])


def load_manuals():
    from pgweb.core.models import Version
    from pgweb.docs.models import DocPage
    Version.objects.bulk_create([
        Version(tree=tree, current=tree == 18, reldate=date(2025, 9, 1),
                firstreldate=date(2025, 9, 1), eoldate=date(2030, 1, 1))
        for tree in MANUAL_TREES])
    for tree in MANUAL_TREES:
        for filename, title in PAGE_TITLE.items():
            DocPage.objects.create(file=filename, version_id=tree, title=title,
                                   content='<html><body>{}</body></html>'.format(filename))


# 模板由前端分头在写：真模板在就用真模板，还没落地就退到这份只打印上下文的占位。
STUBS = {
    'wiki/func_index.html': '{{ title }}|{{ total }}|'
                            '{% for g in groups %}{{ g.anchor }} {% endfor %}',
    'wiki/func_detail.html': '{{ title }}|{{ name }}|{{ change_note }}|{{ version.major }}',
    'wiki/func_changes.html': '{{ title }}|{{ version.label }}|{{ summary.added }}',
}


def with_stub_templates(cls):
    templates = copy.deepcopy(settings.TEMPLATES)
    loaders = list(templates[0]['OPTIONS']['loaders'])
    loaders.append(('django.template.loaders.locmem.Loader', STUBS))
    templates[0]['OPTIONS']['loaders'] = loaders
    return override_settings(TEMPLATES=templates)(cls)


class FuncFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        load_manuals()
        make_dataset()

    def setUp(self):
        cache.clear()

    def rows(self):
        return {row['slug']: row for group in func.index()['groups'] for row in group['rows']}


# ---------------------------------------------------------------- 索引页

class FuncIndexTests(FuncFixture):
    """索引页的分组、版本变动与筛选。"""

    def test_versions_cover_the_whole_range_with_one_default(self):
        order = func.versions()
        self.assertEqual([v['major'] for v in order], list(MAJORS))
        self.assertEqual([v['major'] for v in order if v['is_default']], ['18'])
        self.assertEqual(func.default_major(), '18')
        last = order[-1]
        self.assertEqual((last['label'], last['status_label'], last['source']),
                         ('20 devel', '开发版', 'upstream'))
        self.assertTrue(last['devel'])
        self.assertTrue(order[-2]['preview'])
        self.assertEqual(last['url'], '/docs/func/changes/20/')
        self.assertEqual(order[0]['doc_slug'], '')
        # 事实一律取自上游英文页，版本条上不再有语言，改说中文覆盖了多少个函数。
        self.assertEqual((order[0]['source'], order[0]['layout']), ('upstream', 'table-old'))
        self.assertNotIn('lang', last)
        # 20 版在场的五个函数都有中文；9.x 本站没有手册，一个都没有。
        self.assertEqual((last['zh_coverage'], last['function_count']), (5, 5))
        self.assertEqual(order[0]['zh_coverage'], 0)
        self.assertEqual(order[0]['function_count'], 5)

    def test_the_version_bar_carries_the_shared_ruler_marks(self):
        order = func.versions()
        first, last = order[0], order[-1]
        self.assertEqual((first['tick_head'], first['tick_tail']), ('9', '0'))
        self.assertEqual((last['tick_head'], last['tick_tail']), ('20', ''))
        self.assertEqual(first['tone'], 'eol')
        self.assertEqual(last['tone'], 'dev')
        self.assertEqual(order[-2]['tone'], 'beta')
        self.assertEqual({v['major']: v['tone'] for v in order}['18'], 'live')
        self.assertEqual(last['tone_label'], '开发版')

    def test_groups_follow_the_manual_order(self):
        payload = func.index()
        self.assertEqual([group['slug'] for group in payload['groups']],
                         ['string', 'formatting', 'uuid', 'conditional', 'srf', 'info'])
        self.assertEqual(payload['total'], 6)
        self.assertEqual(payload['group_count'], 6)
        self.assertEqual((payload['earliest_major'], payload['latest_major']), ('9.0', '20'))
        string = payload['groups'][0]
        self.assertEqual((string['anchor'], string['label'], string['count']),
                         ('group-string', '字符串函数和操作符', 1))
        self.assertEqual(string['eyebrow'], 'STRING FUNCTIONS AND OPERATORS')
        # 换过分组的函数归到它最新那一版的分组。
        self.assertEqual([row['slug'] for row in payload['groups'][4]['rows']], ['unnest'])

    def test_every_strip_has_one_cell_per_version(self):
        for slug, row in self.rows().items():
            self.assertEqual([cell['major'] for cell in row['strip']], list(MAJORS), slug)

    def test_the_strip_marks_every_version_and_names_each_cell(self):
        rows = self.rows()
        states = lambda slug: [cell['state'] for cell in rows[slug]['strip']]
        # 13 是手册重排，不算签名变化；15 新增一条签名。
        self.assertEqual(states('substring'), ['present'] * 12 + ['changed'] + ['present'] * 5)
        self.assertEqual(rows['substring']['strip'][0]['label'], '9.0 · 存在')
        self.assertEqual(rows['substring']['strip'][12]['label'], '15 · 签名变更')
        self.assertEqual(states('gen-random-uuid'), ['absent'] * 10 + ['added'] + ['present'] * 7)
        self.assertEqual(states('txid-snapshot-xip'),
                         ['present'] * 10 + ['removed'] + ['absent'] * 7)
        self.assertEqual(rows['txid-snapshot-xip']['strip'][10]['label'], '13 · 移除')
        # 只换了分组、签名没变的那一版仍是「存在」。
        self.assertEqual(states('unnest'), ['present'] * 18)

    def test_rows_carry_the_facts_the_table_prints(self):
        rows = self.rows()
        substring = rows['substring']
        self.assertEqual(substring['url'], '/docs/func/substring/')
        self.assertEqual(substring['name'], 'substring')
        self.assertEqual(substring['group'], 'string')
        self.assertEqual(substring['group_label'], '字符串函数和操作符')
        self.assertEqual(substring['summary_zh'], '提取子串。')
        self.assertEqual(substring['signature_count'], 3)
        self.assertEqual((substring['first'], substring['last']), ('9.0', '20'))
        self.assertTrue(substring['baseline'])
        self.assertFalse(substring['removed'])
        self.assertEqual((substring['change_count'], substring['last_change']), (1, '15'))
        self.assertIn('提取子串。', substring['text'])
        self.assertIn('字符串函数和操作符', substring['text'])
        gone = rows['txid-snapshot-xip']
        self.assertTrue(gone['removed'])
        self.assertEqual(gone['removed_in'], '13')
        self.assertFalse(rows['gen-random-uuid']['baseline'])
        self.assertEqual(rows['coalesce']['name'], 'COALESCE')
        self.assertEqual(rows['coalesce']['url'], '/docs/func/coalesce/')

    def test_filters_count_groups_and_versions(self):
        filters = {item['param']: item for item in func.index()['filters']}
        self.assertEqual(list(filters), ['group', 'first', 'present'])
        groups = {option['value']: option['count'] for option in filters['group']['options']}
        self.assertEqual(groups, {'string': 1, 'formatting': 1, 'uuid': 1, 'conditional': 1,
                                  'srf': 1, 'info': 1})
        self.assertEqual(filters['group']['options'][0]['label'], '字符串函数和操作符')
        first = {option['value']: option['count'] for option in filters['first']['options']}
        self.assertEqual(first, {'9.0': 5, '13': 1})
        present = {option['value']: option['count'] for option in filters['present']['options']}
        self.assertEqual((present['9.0'], present['12'], present['13'], present['20']),
                         (5, 5, 5, 5))
        # 引入版本的下拉从新到旧。
        self.assertEqual([option['value'] for option in filters['first']['options']],
                         ['13', '9.0'])

    def test_stats_count_snapshots_signatures_and_changes(self):
        stats = func.index()['stats']
        self.assertEqual(stats['functions'], 6)
        self.assertEqual(stats['versions'], 18)
        self.assertEqual(stats['removed'], 1)
        self.assertEqual(stats['snapshots'],
                         sum(len(f.present_in) for f in PgFunction.objects.all()))
        self.assertEqual(stats['signatures'],
                         sum(f.signature_count for f in PgFunction.objects.all()))
        self.assertEqual(stats['changes'], 1)

    def test_the_index_reads_the_table_once(self):
        func.versions()
        with self.assertNumQueries(1):
            func.index_payload()

    def test_a_detail_page_does_not_scan_the_whole_column(self):
        func.index()
        func.doc_pages()
        with self.assertNumQueries(1):
            func.detail('substring', '18')
        with self.assertNumQueries(1):
            func.detail('substring', '9.0')

    def test_the_default_version_is_read_off_the_version_bar(self):
        func.versions()
        with self.assertNumQueries(0):
            self.assertEqual(func.default_major(), '18')
            self.assertEqual(func.pick_major('', ['9.0', '18', '20']), '18')
            self.assertEqual(func.pick_major('nope', ['9.0', '18', '20']), '18')
            self.assertEqual(func.pick_major('9.0', ['9.0', '18', '20']), '9.0')
            self.assertEqual(func.pick_major('', ['9.0', '12']), '12')
            self.assertEqual(func.pick_major('', []), '')


# ---------------------------------------------------------------- 详情页

class FuncDetailTests(FuncFixture):
    """详情页的事实、签名、版本条、矩阵、时间线与措辞。"""

    def test_detail_defaults_to_the_stable_version_and_honours_v(self):
        self.assertEqual(func.detail('substring')['version']['major'], '18')
        self.assertEqual(func.detail('substring', '9.3')['version']['major'], '9.3')
        self.assertEqual(func.detail('substring', 'nope')['version']['major'], '18')
        # 18 没有这个函数：落到它最后存在的 12。
        self.assertEqual(func.detail('txid-snapshot-xip')['version']['major'], '12')

    def test_lookup_takes_the_slug_the_name_or_its_spelling(self):
        self.assertEqual(func.detail('to-char')['slug'], 'to-char')
        self.assertEqual(func.detail('to_char')['slug'], 'to-char')
        self.assertEqual(func.detail('TO_CHAR')['name'], 'to_char')
        self.assertEqual(func.detail('COALESCE')['slug'], 'coalesce')
        self.assertEqual(func.detail('coalesce')['name'], 'COALESCE')
        with self.assertRaises(PgFunction.DoesNotExist):
            func.detail('nosuch')

    def test_facts_report_group_signatures_introduction_status_and_source(self):
        facts = {row['label']: row for row in func.detail('substring', '18')['facts']}
        self.assertEqual(facts['分组']['value'], '字符串函数和操作符')
        self.assertEqual(facts['分组']['url'], '/docs/func/#group-string')
        self.assertEqual(facts['签名数']['value'], '3 条')
        self.assertEqual(facts['引入版本']['value'], '9.0（基线）')
        self.assertEqual(facts['状态']['value'], '现存')
        self.assertEqual(facts['签名变更']['value'], '1 次')
        self.assertEqual(facts['本版来源']['value'], '本站译文')
        # 本站没有该版手册：说明按上游英文原文显示。
        english = {row['label']: row for row in func.detail('substring', '9.3')['facts']}
        self.assertEqual(english['本版来源']['value'], '英文原文')
        # 借用别版译文的那一版说清楚是沿用。
        borrowed = {row['label']: row for row in func.detail('substring', '11')['facts']}
        self.assertEqual(borrowed['本版来源']['value'], '本站译文（沿用）')
        gone = {row['label']: row for row in func.detail('txid-snapshot-xip')['facts']}
        self.assertEqual(gone['状态']['value'], '于 13 移除')
        fresh = {row['label']: row for row in func.detail('gen-random-uuid')['facts']}
        self.assertEqual(fresh['引入版本']['value'], '13')
        self.assertEqual(fresh['签名变更']['value'], '未变过')

    def test_signatures_carry_text_html_examples_and_the_added_mark(self):
        payload = func.detail('substring', '15')
        signatures = payload['signatures']
        self.assertEqual(len(signatures), 3)
        self.assertEqual([row['added'] for row in signatures], [False, False, True])
        first = signatures[0]
        self.assertTrue(first['text'].startswith('substring ( string text'))
        self.assertEqual(first['returns'], 'text')
        self.assertEqual(first['description_zh'], '提取子串。')
        self.assertEqual(first['examples'],
                         [{'expr': "substring('Thomas' from 2 for 3)", 'result': 'hom'}])
        self.assertIn('<code class="function">substring</code>', first['html'])
        # 两份描述 HTML 都传给模板，不在这里丢掉行内标记；英文那份是英文，别搞混。
        self.assertEqual(first['description_zh_html'], '<p>提取子串。</p>')
        self.assertEqual(first['description_html'], '<p>Extracts the substring.</p>')
        # 每条签名带上中文来源，模板据此加「沿用」标记或按英文显示。
        self.assertEqual((first['zh_from'], first['inherited'], first['zh_label']),
                         ('doc', False, '本站译文'))
        borrowed = func.detail('substring', '11')['signatures'][0]
        self.assertEqual((borrowed['zh_from'], borrowed['inherited'], borrowed['zh_label']),
                         ('inherited', True, '本站译文（沿用）'))
        # 整份快照有译文，个别签名没配上中文：那一条按英文显示，不跟着快照说成本站译文。
        mixed = func.detail('to-char', '18')
        self.assertEqual(mixed['snapshot']['zh_from'], 'doc')
        self.assertEqual([(row['zh_from'], row['zh_label']) for row in mixed['signatures']],
                         [('doc', '本站译文'), ('', '英文原文')])
        self.assertEqual(mixed['signatures'][1]['description'], 'Converts number to string.')
        english = func.detail('substring', '9.3')['signatures'][0]
        self.assertEqual((english['zh_from'], english['inherited']), ('', False))
        self.assertEqual(english['description_zh'], '')
        self.assertEqual(english['description_zh_html'], '')
        self.assertEqual(english['description'], 'Extract substring.')
        # 没有译文时英文那份仍在，模板拿它渲染并标 lang="en"。
        self.assertEqual(english['description_html'], '<p>Extract substring.</p>')
        # 没有变化的那一版一条都不标「新」。
        self.assertEqual([row['added'] for row in func.detail('substring', '18')['signatures']],
                         [False, False, False])

    def test_a_version_with_only_prose_says_so_instead_of_faking_signatures(self):
        """上游某版只在正文里提到这个函数：如实说，不借别版的签名充数。"""
        payload = func.detail('txid-snapshot-xip', '9.0')
        self.assertTrue(payload['prose_only'])
        self.assertEqual(payload['signatures'], [])
        self.assertEqual(payload['signature_note'],
                         'PostgreSQL 9.0 的手册只在正文里提到此函数，未给出签名。')
        facts = {row['label']: row['value'] for row in payload['facts']}
        self.assertEqual(facts['本版形态'], '仅正文提及')
        self.assertNotIn('签名数', facts)
        # 本站手册与官方文档的链接照给，读者有去处。
        self.assertTrue(payload['doc']['official_url'])
        # 给出签名的版本照旧。
        later = func.detail('txid-snapshot-xip', '12')
        self.assertFalse(later['prose_only'])
        self.assertEqual(later['signature_note'], '')
        self.assertEqual(len(later['signatures']), 1)
        self.assertEqual({row['label']: row['value'] for row in later['facts']}['签名数'], '1 条')

    def test_the_matrix_lists_only_versions_that_give_signatures(self):
        """只有正文的版本没有签名可画，列进矩阵整列都是「不存在」，会被读成没有这个函数。"""
        matrix = func.detail('txid-snapshot-xip', '12')['matrix']
        self.assertEqual([v['major'] for v in matrix['versions']], ['10', '11', '12'])
        self.assertEqual([row['text'] for row in matrix['rows']], [XIP_OLD[0]['text']])
        self.assertTrue(all(cell['state'] == 'exists'
                            for row in matrix['rows'] for cell in row['cells']))
        # 版本条与版本方格仍然列全 18 版，读者不会漏掉这个函数在 9.x 也存在。
        self.assertEqual(len(func.detail('txid-snapshot-xip', '12')['ribbon']), len(MAJORS))
        rows = {row['slug']: row for group in func.index()['groups'] for row in group['rows']}
        self.assertEqual(len(rows['txid-snapshot-xip']['strip']), len(MAJORS))
        self.assertEqual(rows['txid-snapshot-xip']['strip'][0]['state'], 'present')

    def test_a_version_without_signatures_never_reports_signature_changes(self):
        """9.6 只有正文、10 给出签名，这不是「新增了一条签名」。"""
        function = PgFunction.objects.get(slug='txid-snapshot-xip')
        self.assertEqual(function.changed_in, [])
        self.assertEqual([c['to'] for c in function.changes], ['13'])
        bare = {'layout': 'table-old', 'group': 'info', 'prose_only': True,
                'texts': [], 'description': 'A.'}
        full = {'layout': 'table-old', 'group': 'info', 'texts': ['f ( ) → int'],
                'description': 'A.'}
        self.assertIsNone(func.compare(bare, full, '9.6', '10'))
        self.assertIsNone(func.compare(full, bare, '10', '11'))
        # 两边都有签名时照常比。
        self.assertEqual(func.compare(full, dict(full, texts=['f ( int ) → int']), '10',
                                      '11')['signatures'],
                         {'added': ['f ( int ) → int'], 'removed': ['f ( ) → int']})

    def test_removed_signatures_come_from_the_previous_version(self):
        # 夹具里 15 只增不减。
        self.assertEqual(func.detail('substring', '15')['removed_signatures'], [])
        self.assertEqual(func.detail('substring', '18')['removed_signatures'], [])

    def test_ribbon_is_one_cell_per_version_with_the_current_one_marked(self):
        ribbon = func.detail('substring', '12')['ribbon']
        self.assertEqual(len(ribbon), len(MAJORS))
        cells = {cell['major']: cell for cell in ribbon}
        self.assertTrue(cells['12']['current'])
        self.assertFalse(cells['18']['current'])
        self.assertEqual(cells['15']['state'], 'changed')
        self.assertEqual(cells['9.0']['state'], 'present')
        self.assertEqual(cells['18']['url'], '/docs/func/substring/?v=18')
        self.assertEqual(cells['12']['doc_url'],
                         '/docs/12/functions-string.html#FUNCTIONS-STRING-SQL')
        # 本站没有 11 的手册，就不给链接。
        self.assertEqual(cells['11']['doc_url'], '')
        self.assertEqual(cells['20']['doc_url'],
                         '/docs/devel/functions-string.html#FUNCTIONS-STRING-SQL')
        self.assertTrue(cells['20']['devel'])
        self.assertEqual(cells['19']['label'], '19 beta 3')
        gone = {cell['major']: cell for cell in func.detail('txid-snapshot-xip')['ribbon']}
        self.assertEqual(gone['13']['state'], 'removed')
        self.assertEqual(gone['13']['url'], '')
        self.assertEqual(gone['14']['state'], 'absent')

    def test_change_note_has_one_wording_per_situation(self):
        self.assertEqual(func.detail('substring', '9.0')['change_note'],
                         '9.0 是本数据集的收录基线，不代表该函数首次于 9.0 引入。'
                         '本站手册未收录该版的这条译文，说明按英文原文显示。')
        # 引入那一版上游只给了正文，没有签名：如实说，不说「共 0 条签名」。
        self.assertEqual(func.detail('gen-random-uuid', '13')['change_note'],
                         'PostgreSQL 13 的手册只在正文里提到此函数，未给出签名。')
        self.assertEqual(func.detail('substring', '15')['change_note'],
                         '相对 PostgreSQL 14：新增 1 条签名。')
        self.assertEqual(func.detail('substring', '15')['change_note'],
                         '相对 PostgreSQL 14：新增 1 条签名。')
        self.assertEqual(func.detail('substring', '13')['change_note'],
                         'PostgreSQL 13 重排了函数表的写法，签名文本整体改变，此处不逐条比较。')
        self.assertEqual(func.detail('substring', '18')['change_note'],
                         '相对 PostgreSQL 17 无变化。')
        self.assertEqual(func.detail('substring', '9.3')['change_note'],
                         '相对 PostgreSQL 9.2 无变化。'
                         '本站手册未收录该版的这条译文，说明按英文原文显示。')
        # 有译文的版本不追加这句。
        self.assertNotIn('英文原文', func.detail('substring', '18')['change_note'])
        # 换分组也说清楚。
        self.assertEqual(func.detail('unnest', '14')['change_note'],
                         '相对 PostgreSQL 13：分组由数组函数和操作符改为集合返回函数。')

    def test_preview_and_devel_versions_carry_a_notice(self):
        self.assertIn('预发行', func.detail('substring', '19')['notice'])
        self.assertIn('开发版', func.detail('substring', '20')['notice'])
        self.assertEqual(func.detail('substring', '18')['notice'], '')

    def test_timeline_is_newest_first_and_lists_the_signature_chips(self):
        timeline = func.detail('substring', '18')['timeline']
        self.assertEqual([item['to'] for item in timeline], ['15'])
        item = timeline[0]
        self.assertEqual((item['from'], item['status']), ('14', 'changed'))
        self.assertEqual(item['added'], [SUB_SIMILAR['text']])
        self.assertEqual(item['removed'], [])
        self.assertEqual(item['url'], '/docs/func/substring/?v=15')
        self.assertFalse(item['doc_overhaul'])
        # 新增与移除也在时间线上。
        self.assertEqual([i['status'] for i in func.detail('gen-random-uuid')['timeline']],
                         ['added'])
        gone = func.detail('txid-snapshot-xip')['timeline'][0]
        self.assertEqual((gone['status'], gone['to'], gone['url']), ('removed', '13', ''))
        moved = func.detail('unnest', '18')['timeline'][0]
        self.assertEqual(moved['group_changed'], {'from': 'array', 'to': 'srf'})

    def test_matrix_is_signatures_by_version(self):
        matrix = func.detail('substring', '18')['matrix']
        self.assertEqual([version['major'] for version in matrix['versions']], list(MAJORS))
        self.assertEqual([row['text'] for row in matrix['rows']],
                         [SUB_OLD[0]['text'], SUB_OLD[1]['text'],
                          SUB_NEW[0]['text'], SUB_NEW[1]['text'], SUB_SIMILAR['text']])
        states = {row['text']: [cell['state'] for cell in row['cells']] for row in matrix['rows']}
        self.assertEqual(states[SUB_OLD[0]['text']], ['exists'] * 10 + ['absent'] * 8)
        self.assertEqual(states[SUB_NEW[0]['text']], ['absent'] * 10 + ['exists'] * 8)
        self.assertEqual(states[SUB_SIMILAR['text']], ['absent'] * 12 + ['exists'] * 6)
        cells = {cell['major']: cell for cell in matrix['rows'][2]['cells']}
        self.assertEqual(cells['18']['url'], '/docs/func/substring/?v=18')
        self.assertEqual(cells['9.0']['url'], '')
        self.assertTrue(cells['18']['current'])

    def test_doc_links_the_manual_and_borrows_the_nearest_one_for_nine_x(self):
        payload = func.detail('substring', '18')
        self.assertEqual(payload['doc']['local_url'],
                         '/docs/18/functions-string.html#FUNCTIONS-STRING-SQL')
        self.assertFalse(payload['doc']['borrowed'])
        self.assertEqual(payload['doc']['label'], 'PostgreSQL 18 手册 · 9.4 字符串函数和操作符')
        self.assertEqual(payload['doc']['official_url'],
                         'https://www.postgresql.org/docs/18/functions-string.html'
                         '#FUNCTIONS-STRING-SQL')
        self.assertEqual(payload['doc']['file'], 'functions-string.html')
        borrowed = func.detail('substring', '9.3')['doc']
        self.assertTrue(borrowed['borrowed'])
        self.assertEqual(borrowed['major'], '10')
        self.assertEqual(borrowed['local_url'],
                         '/docs/10/functions-string.html#FUNCTIONS-STRING-SQL')
        self.assertEqual(borrowed['official_url'],
                         'https://www.postgresql.org/docs/9.3/functions-string.html'
                         '#FUNCTIONS-STRING-SQL')
        devel = func.detail('substring', '20')['doc']
        self.assertEqual(devel['local_url'],
                         '/docs/devel/functions-string.html#FUNCTIONS-STRING-SQL')
        self.assertEqual(devel['official_url'],
                         'https://www.postgresql.org/docs/devel/functions-string.html'
                         '#FUNCTIONS-STRING-SQL')

    def test_doc_versions_only_list_manuals_the_site_has(self):
        payload = func.detail('substring', '18')
        self.assertEqual([item['major'] for item in payload['doc_versions']],
                         ['10', '12', '18', '20'])

    def test_related_are_the_neighbours_of_the_same_group(self):
        # 夹具里每组只有一个函数，相邻为空；同组多一个就出现。
        self.assertEqual(func.detail('substring', '18')['related'], [])
        make_function('substr', 'substr', 'string', 'functions-string.html',
                      'FUNCTIONS-STRING-OTHER',
                      {major: [sig('substr ( string text, start integer ) → text', zh='取子串。')]
                       for major in MAJORS}, position=3001)
        cache.clear()
        related = func.detail('substring', '18')['related']
        self.assertEqual([item['slug'] for item in related], ['substr'])
        self.assertEqual(related[0]['url'], '/docs/func/substr/')
        self.assertEqual(related[0]['summary_zh'], '取子串。')

    def test_siblings_are_the_index_table_of_the_same_group(self):
        payload = func.detail('substring', '18')
        self.assertEqual([group['slug'] for group in payload['siblings']], ['string'])
        group = payload['siblings'][0]
        self.assertEqual(group['current'], 'substring')
        self.assertEqual([row['slug'] for row in group['rows']], ['substring'])
        self.assertEqual(payload['previous_major'], '17')
        self.assertEqual(func.detail('substring', '9.0')['previous_major'], '')
        self.assertEqual(payload['eyebrow'], 'FUNCTION')
        self.assertEqual(payload['group_label'], '字符串函数和操作符')


# ---------------------------------------------------------------- 变更页

class FuncChangesTests(FuncFixture):
    """版本变更页的四项汇总与四类明细。"""

    def test_a_release_reports_added_removed_and_signature_changes(self):
        payload = func.changes('13')
        self.assertEqual(payload['previous']['major'], '12')
        self.assertFalse(payload['arbitrary'])
        self.assertEqual(payload['summary'],
                         {'added': 1, 'removed': 1, 'changed': 0, 'moved': 0})
        self.assertEqual([card['slug'] for card in payload['added']], ['gen-random-uuid'])
        self.assertEqual([card['slug'] for card in payload['removed']], ['txid-snapshot-xip'])
        card = payload['added'][0]
        self.assertEqual(card['name'], 'gen_random_uuid')
        self.assertEqual(card['url'], '/docs/func/gen-random-uuid/')
        self.assertEqual(card['group_label'], 'UUID 函数')
        self.assertEqual(card['summary_zh'], '生成版本 4 的随机 UUID。')
        # 引入那一版上游只在正文里提到：卡片如实写 0，不拿最新版的签名充数。
        self.assertTrue(card['prose_only'])
        self.assertEqual((card['signature'], card['signature_count']), ('', 0))
        # 下一版给出签名之后照常显示。
        later = func.changes('14')
        self.assertEqual(later['summary'], {'added': 0, 'removed': 0, 'changed': 0, 'moved': 1})
        # 手册重排那一跳只记增删，不把几百个函数全标成变化。
        self.assertTrue(payload['doc_overhaul'])
        self.assertIn('重排', payload['overhaul_note'])

    def test_a_release_that_only_changes_signatures(self):
        payload = func.changes('15')
        self.assertEqual(payload['summary'],
                         {'added': 0, 'removed': 0, 'changed': 1, 'moved': 0})
        entry = payload['changed'][0]
        self.assertEqual(entry['slug'], 'substring')
        self.assertEqual((entry['added'], entry['removed']), (1, 0))
        self.assertEqual(entry['sample'], SUB_SIMILAR['text'])
        self.assertFalse(payload['doc_overhaul'])

    def test_a_release_that_moves_a_function_between_groups(self):
        payload = func.changes('14')
        self.assertEqual(payload['summary'],
                         {'added': 0, 'removed': 0, 'changed': 0, 'moved': 1})
        entry = payload['moved'][0]
        self.assertEqual(entry['slug'], 'unnest')
        self.assertEqual((entry['from_group'], entry['to_group']), ('array', 'srf'))
        self.assertEqual(entry['from_group_label'], '数组函数和操作符')
        self.assertEqual(entry['to_group_label'], '集合返回函数')

    def test_a_quiet_release_reports_nothing(self):
        payload = func.changes('18')
        self.assertEqual(payload['summary'],
                         {'added': 0, 'removed': 0, 'changed': 0, 'moved': 0})
        self.assertEqual(payload['previous']['major'], '17')
        self.assertEqual(payload['notice'], '')

    def test_the_first_version_lists_the_baseline(self):
        payload = func.changes('9.0')
        self.assertTrue(payload['baseline'])
        self.assertIsNone(payload['previous'])
        self.assertIn('收录基线', payload['baseline_note'])
        slugs = [row['slug'] for group in payload['baseline_groups'] for row in group['rows']]
        self.assertEqual(sorted(slugs),
                         ['coalesce', 'substring', 'to-char', 'txid-snapshot-xip', 'unnest'])
        self.assertEqual(payload['summary'],
                         {'added': 0, 'removed': 0, 'changed': 0, 'moved': 0})

    def test_the_devel_release_carries_a_notice(self):
        payload = func.changes('20')
        self.assertIn('开发版', payload['notice'])
        self.assertEqual(payload['version']['label'], '20 devel')

    def test_a_non_adjacent_comparison_is_computed_on_the_spot(self):
        payload = func.changes('18', from_major='12')
        self.assertTrue(payload['arbitrary'])
        self.assertEqual(payload['from_major'], '12')
        self.assertEqual([card['slug'] for card in payload['added']], ['gen-random-uuid'])
        self.assertEqual([card['slug'] for card in payload['removed']], ['txid-snapshot-xip'])
        # 12 与 18 版面不同：只记增删，不逐条比签名。
        self.assertTrue(payload['doc_overhaul'])
        self.assertEqual(payload['summary']['changed'], 0)
        payload = func.changes('18', from_major='13')
        self.assertFalse(payload['doc_overhaul'])
        self.assertEqual([entry['slug'] for entry in payload['changed']], ['substring'])
        self.assertEqual([entry['slug'] for entry in payload['moved']], ['unnest'])

    def test_an_unknown_from_falls_back_to_the_adjacent_comparison(self):
        payload = func.changes('18', from_major='nope')
        self.assertFalse(payload['arbitrary'])
        self.assertEqual(payload['from_major'], '')
        self.assertEqual(payload['previous']['major'], '17')

    def test_compare_reports_only_real_differences(self):
        left = {'layout': 'table-new', 'zh_from': 'doc', 'group': 'string',
                'texts': ['a ( ) → text'], 'description_zh': '甲。', 'description': 'A.'}
        right = dict(left, texts=['a ( ) → text', 'a ( text ) → text'])
        change = func.compare(left, right, '17', '18')
        self.assertEqual(change['signatures'], {'added': ['a ( text ) → text'], 'removed': []})
        self.assertEqual(change['status'], 'changed')
        self.assertFalse(change['doc_overhaul'])
        self.assertIsNone(func.compare(left, dict(left)))
        self.assertEqual(func.compare({}, right)['status'], 'added')
        self.assertEqual(func.compare(left, {})['status'], 'removed')
        self.assertIsNone(func.compare({}, {}))
        # 版面不同就不逐条比，语言不同就不比描述。
        overhaul = func.compare(dict(left, layout='table-old'), right, '12', '13')
        self.assertIsNone(overhaul)
        # 只比英文原文那一层：译文覆盖面不同、中文措辞改了，都不算说明变了。
        english = dict(left, zh_from='', description_zh='')
        self.assertIsNone(func.compare(english, left, '9.6', '10'))
        self.assertIsNone(func.compare(left, dict(left, description_zh='乙。'), '17', '18'))
        # 英文原文变了才算。
        other = dict(english, description='B.')
        self.assertTrue(func.compare(english, other, '9.5', '9.6')['descriptions_changed'])
        # 折叠空白之后一致就不算变。
        self.assertIsNone(func.compare(left, dict(left, description='A.  '), '17', '18'))

    def test_changes_for_an_unknown_version_raises(self):
        with self.assertRaises(FuncVersion.DoesNotExist):
            func.changes('99')


# ---------------------------------------------------------------- 页面

@with_stub_templates
class FuncPageTests(FuncFixture):
    """四条路由都要能走通。"""

    def test_index_renders(self):
        response = self.client.get('/docs/func/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], 6)
        self.assertEqual(response.context['column']['slug'], 'func')
        self.assertIn('group-string', response.content.decode())

    def test_detail_renders_and_honours_the_version_parameter(self):
        response = self.client.get('/docs/func/substring/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['version']['major'], '18')
        response = self.client.get('/docs/func/substring/?v=9.3')
        self.assertEqual(response.context['version']['major'], '9.3')
        self.assertTrue(response.context['doc']['borrowed'])
        self.assertEqual(self.client.get('/docs/func/substring/?v=20')
                         .context['version']['major'], '20')

    def test_an_invalid_version_falls_back_to_the_default(self):
        response = self.client.get('/docs/func/substring/?v=1999')
        self.assertEqual(response.context['version']['major'], '18')

    def test_query_parameters_outside_the_whitelist_are_dropped(self):
        response = self.client.get('/docs/func/substring/?v=12&nope=1')
        self.assertEqual(response.context['version']['major'], '12')
        self.assertEqual(self.client.get('/docs/func/?q=sub&group=string'
                                         '&first=9.0&present=18').status_code, 200)

    def test_a_non_canonical_spelling_redirects_to_the_canonical_one(self):
        response = self.client.get('/docs/func/to_char/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/docs/func/to-char/')
        response = self.client.get('/docs/func/TO_CHAR/?v=12')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/docs/func/to-char/?v=12')
        response = self.client.get('/docs/func/COALESCE/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/docs/func/coalesce/')
        self.assertEqual(self.client.get('/docs/func/to-char/').status_code, 200)

    def test_an_unknown_function_is_404(self):
        self.assertEqual(self.client.get('/docs/func/nosuch/').status_code, 404)
        self.assertEqual(self.client.get('/docs/func/9bad/').status_code, 404)
        self.assertEqual(self.client.get('/docs/func/bad.name/').status_code, 404)

    def test_changes_root_redirects_to_the_default_version(self):
        response = self.client.get('/docs/func/changes/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/docs/func/changes/18/')

    def test_changes_pages_render_and_honour_from(self):
        self.assertEqual(self.client.get('/docs/func/changes/9.0/').status_code, 200)
        response = self.client.get('/docs/func/changes/13/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['version']['label'], '13')
        self.assertTrue(self.client.get('/docs/func/changes/18/?from=12')
                        .context['arbitrary'])
        self.assertEqual(self.client.get('/docs/func/changes/20/').status_code, 200)
        self.assertEqual(self.client.get('/docs/func/changes/99/').status_code, 404)

    def test_the_docs_navigation_marks_the_column_active(self):
        response = self.client.get('/docs/func/')
        active = [item for item in response.context['navmenu'] if item.get('active')]
        self.assertEqual([item['link'] for item in active], ['/docs/func/'])

    def test_the_column_is_local_only(self):
        from pgweb.util.contexts import LOCAL_ONLY_SECTIONS, _source_url
        self.assertIn('/docs/func/', LOCAL_ONLY_SECTIONS)
        self.assertEqual(_source_url('/docs/func/substring/'), '')

    def test_the_column_is_live_and_listed(self):
        self.assertTrue(BY_SLUG['func']['live'])
        self.assertEqual(BY_SLUG['func']['name'], '函数百科')
        self.assertEqual(BY_SLUG['func']['coverage'], 'PostgreSQL 9.0 – 20 devel')

    def test_sitemap_lists_the_index_every_function_and_every_changes_page(self):
        from .struct import get_struct
        pages = [page for page, _ in get_struct()]
        self.assertIn('docs/func/', pages)
        self.assertIn('docs/func/substring/', pages)
        self.assertIn('docs/func/to-char/', pages)
        self.assertIn('docs/func/changes/9.0/', pages)
        self.assertIn('docs/func/changes/20/', pages)


# ---------------------------------------------------------------- 检索

class FuncSearchEntryTests(FuncFixture):
    """检索条目的形状与重建计数。"""

    def entry(self, slug):
        from pgweb.search.indexer import func_entry
        return func_entry(PgFunction.objects.get(slug=slug))

    def test_entry_shares_the_entity_of_the_manual_definition(self):
        entry = self.entry('substring')
        self.assertEqual(entry['entity_key'], 'function:substring')
        self.assertEqual((entry['kind'], entry['subtype']), ('function', 'string'))
        self.assertEqual(entry['name'], 'substring')
        self.assertEqual(entry['url'], '/docs/func/substring/')
        self.assertEqual(entry['weight'], 0.5)
        self.assertEqual(entry['heading'], '函数 · 字符串函数和操作符')
        self.assertEqual(entry['signature'], SUB_NEW[0]['text'])
        self.assertIn('提取子串。', entry['body'])
        self.assertIn(SUB_SIMILAR['text'], entry['body'])
        self.assertIn('字符串函数和操作符', entry['body'])

    def test_aliases_include_the_underscoreless_spelling(self):
        entry = self.entry('gen-random-uuid')
        self.assertEqual(entry['aliases'], ['gen_random_uuid', 'genrandomuuid'])
        self.assertEqual(self.entry('substring')['aliases'], ['substring'])

    def test_preview_carries_the_facts_and_the_signatures(self):
        preview = self.entry('substring')['preview']
        self.assertIn('提取子串。', preview)
        self.assertIn('<dt>分组</dt><dd>字符串函数和操作符</dd>', preview)
        self.assertIn('<dt>签名数</dt><dd>3</dd>', preview)
        self.assertIn('<dt>最早收录</dt><dd>9.0</dd>', preview)
        self.assertIn('<dt>版本覆盖</dt><dd>9.0 – 20</dd>', preview)
        self.assertIn('签名（最新收录版本）', preview)

    def test_an_uppercase_name_keeps_its_spelling_and_folds_its_key(self):
        entry = self.entry('coalesce')
        self.assertEqual(entry['name'], 'COALESCE')
        self.assertEqual(entry['name_key'], 'coalesce')
        self.assertEqual(entry['entity_key'], 'function:coalesce')
        self.assertEqual(entry['url'], '/docs/func/coalesce/')

    def test_rebuild_counts_and_replaces_the_source(self):
        from pgweb.search.indexer import rebuild_func
        from pgweb.search.models import SearchEntry
        self.assertEqual(rebuild_func(dry_run=True), {'func': 6})
        self.assertEqual(SearchEntry.objects.filter(source='func').count(), 0)
        self.assertEqual(rebuild_func(), {'func': 6})
        self.assertEqual(SearchEntry.objects.filter(source='func').count(), 6)
        # 再跑一次是整体替换，不会翻倍。
        self.assertEqual(rebuild_func(), {'func': 6})
        self.assertEqual(SearchEntry.objects.filter(source='func').count(), 6)
        row = SearchEntry.objects.get(source='func', name='substring')
        self.assertEqual(row.entity_key, 'function:substring')
        self.assertIsNone(row.document_id)
        self.assertIsNone(row.version)
        self.assertEqual(row.url, '/docs/func/substring/')

    def test_the_search_service_includes_the_column(self):
        from pgweb.search import service
        state = service.parse_query('substring', available=[18], current=18)
        self.assertIn('func', state['sources'])
        self.assertIn('func', service.parse_query('pg18:substring', available=[18],
                                                  current=18)['sources'])
