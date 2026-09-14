"""配置参数栏目：取数形状、三种页面与检索条目。

夹具在库里造一份 18 个版本、5 个参数的小数据集，形状与导入器写出来的一致
（`docs/guc-column.md` §2），造法只用 `guc_common` 里那份唯一的比较规则，
不依赖导入器：两边跑的是同一套判定。
"""

import copy
from datetime import date

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings

from . import guc
from .columns import BY_SLUG
from .guc_common import diff_fields, human_value, is_default_change, is_substantive
from .models import GUC_CATEGORY_ZH, GucParameter, GucVersion


MAJORS = ('9.0', '9.1', '9.2', '9.3', '9.4', '9.5', '9.6',
          '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20')
# 本站手册只有这几棵树；9.x 没有手册，20 是 devel。
MANUAL_TREES = (10, 12, 18, 0)

LABEL = {'19': '19 beta 3', '20': '20 devel'}
STATUS = {'18': 'stable', '19': 'preview', '20': 'devel'}
SUPPORT = {'stable': 'supported', 'preview': 'preview', 'devel': 'devel'}


def doc_slug(major):
    return 'devel' if major == '20' else major


# ---------------------------------------------------------------- 夹具

def make_versions():
    GucVersion.objects.bulk_create([
        GucVersion(
            major=major, label=LABEL.get(major, major),
            status=STATUS.get(major, 'historical'),
            support_status=SUPPORT.get(STATUS.get(major, 'historical'), 'end-of-life'),
            source_key='19beta3' if major == '19' else '' if major == '20' else major,
            server_version='' if major == '20' else major + '.1',
            doc_slug=doc_slug(major),
            schema_source='documentation' if major == '20' else 'runtime',
            position=index)
        for index, major in enumerate(MAJORS)])


def make_snapshot(major, fact, doc_file, anchor, html='', same_as='', carried=''):
    category = fact['category']
    unit = fact.get('unit') or ''
    return {
        'setting': fact.get('boot_val'), 'boot_val': fact.get('boot_val'), 'unit': unit,
        # 导入器对「手册推不出默认值」写空串，不写「未设置」。
        'human': fact['human'] if 'human' in fact else human_value(fact.get('boot_val'), unit),
        'category': category, 'category_zh': GUC_CATEGORY_ZH.get(category, category),
        'short_desc': fact.get('short_desc', ''), 'extra_desc': fact.get('extra_desc', ''),
        'context': fact.get('context', ''), 'vartype': fact.get('vartype', ''),
        'min_val': fact.get('min_val', ''), 'max_val': fact.get('max_val', ''),
        'enumvals': list(fact.get('enumvals') or ()),
        'doc': {'file': doc_file, 'anchor': anchor, 'slug': doc_slug(major),
                'url': 'https://www.postgresql.org/docs/{}/{}#{}'.format(
                    doc_slug(major), doc_file, anchor)},
        'doc_html': html, 'doc_same_as': same_as,
        'carried_from': carried,
        'carry_reason': '手册不含 pg_settings 事实，沿用 19' if carried else '',
    }


def make_changes(versions, majors, carried):
    changes = []
    first, last = majors[0], majors[-1]
    for index in range(1, len(MAJORS)):
        previous, current = MAJORS[index - 1], MAJORS[index]
        left, right = versions.get(previous), versions.get(current)
        if right and not left:
            if current == first and first != MAJORS[0]:
                changes.append({'from': previous, 'to': current, 'status': 'added', 'fields': {},
                                'substantive': True, 'default_changed': False, 'carried': False})
            continue
        if left and not right:
            if previous == last:
                changes.append({'from': previous, 'to': current, 'status': 'removed', 'fields': {},
                                'substantive': False, 'default_changed': False, 'carried': False})
            continue
        if not left:
            continue
        if current in carried:
            changes.append({'from': previous, 'to': current, 'status': 'changed', 'fields': {},
                            'substantive': False, 'default_changed': False, 'carried': True})
            continue
        fields = diff_fields(left, right)
        if fields:
            changes.append({'from': previous, 'to': current, 'status': 'changed', 'fields': fields,
                            'substantive': is_substantive(fields),
                            'default_changed': is_default_change(fields), 'carried': False})
    return changes


def make_default_history(versions, majors):
    history, previous = [], object()
    for major in majors:
        snapshot = versions[major]
        key = (snapshot['boot_val'], snapshot['unit'])
        if key == previous:
            history[-1]['to'] = major
            continue
        history.append({'from': major, 'to': major, 'boot_val': snapshot['boot_val'],
                        'unit': snapshot['unit'], 'human': snapshot['human']})
        previous = key
    return history


def make_parameter(name, group, group_slug, doc_file, anchor, facts, html=None, same_as=None,
                   carried=(), editorial=None, intro=None, history=True, position=0):
    html, same_as = html or {}, same_as or {}
    majors = [major for major in MAJORS if major in facts]
    versions = {major: make_snapshot(major, facts[major], doc_file, anchor,
                                     html.get(major, ''), same_as.get(major, ''),
                                     '19' if major in carried else '')
                for major in majors}
    changes = make_changes(versions, majors, set(carried))
    latest = versions[majors[-1]]
    parameter = GucParameter(
        name=name, key=name.lower(), group=group, group_slug=group_slug,
        category=latest['category'], category_zh=latest['category_zh'],
        vartype=latest['vartype'], context=latest['context'], unit=latest['unit'],
        boot_val=latest['boot_val'], boot_human=latest['human'],
        short_desc=latest['short_desc'],
        short_desc_zh=facts[majors[-1]].get('short_desc_zh', ''),
        enumvals=latest['enumvals'], min_val=latest['min_val'], max_val=latest['max_val'],
        first_version=majors[0], last_version=majors[-1], present_in=majors,
        changed_in=[c['to'] for c in changes
                    if c['status'] == 'changed' and c['substantive']],
        default_changed_in=[c['to'] for c in changes if c['default_changed']],
        baseline=majors[0] == MAJORS[0],
        versions=versions, changes=changes,
        default_history=make_default_history(versions, majors) if history else [],
        docs={major: {'status': 'verified', 'anchor': anchor,
                      'url': versions[major]['doc']['url']} for major in majors},
        editorial=editorial or {}, intro_commit=intro or {},
        position=position, source_rev='fixture')
    parameter.save()
    return parameter


WAL_FACTS = dict(category='Write-Ahead Log / Settings', vartype='enum', context='postmaster',
                 enumvals=['minimal', 'archive', 'hot_standby', 'logical'],
                 short_desc='Sets the level of information written to the WAL.',
                 short_desc_zh='设置写入 WAL 的信息量。')
WAL_EDITORIAL = {
    'summary_zh': 'wal_level 决定写入预写式日志的信息量。', 'summary': 'How much goes into the WAL.',
    'mechanism_zh': ['minimal 只写崩溃恢复所需的记录。', 'replica 额外写归档与备库所需的记录。'],
    'mechanism': ['minimal writes only what crash recovery needs.'],
    'advice_zh': {'oltp': 'OLTP 用 replica。', 'olap': 'OLAP 也用 replica。', 'small': '小规格用 replica。'},
    'advice': {'oltp': 'Use replica.', 'olap': 'Use replica.', 'small': 'Use replica.'},
    'pitfalls_zh': ['改这个参数要重启。'], 'pitfalls': ['Requires a restart.'],
    'related': ['wal_skip_threshold', 'nosuch_param'],
    'references_zh': [{'title': '预写式日志', 'url': 'https://www.postgresql.org/docs/18/wal.html'}],
    'references': [{'title': 'WAL', 'url': 'https://www.postgresql.org/docs/18/wal.html'}],
}


def make_dataset():
    make_versions()
    # 1) 9.0 收录基线，一直活到 20；10 改默认值与枚举值，17 只改了简述，20 沿用 19。
    facts = {}
    for major in MAJORS:
        fact = dict(WAL_FACTS)
        if major in ('9.0', '9.1', '9.2', '9.3', '9.4', '9.5', '9.6'):
            fact['boot_val'] = 'minimal'
        else:
            fact['boot_val'] = 'replica'
            fact['enumvals'] = ['minimal', 'replica', 'logical']
        if major in ('17', '18', '19', '20'):
            fact['short_desc'] = 'Sets the level of information written to the WAL log.'
        facts[major] = fact
    make_parameter(
        'wal_level', 'Write-Ahead Log', 'wal', 'runtime-config-wal.html', 'GUC-WAL-LEVEL', facts,
        html={'10': '<p>决定写入 WAL 的信息量。</p>',
              '12': '<p>决定写入 WAL 的信息量（12 版措辞）。</p>',
              '20': '<p>决定写入 WAL 的信息量（devel 措辞）。</p>'},
        # 11 与 18 的译文与更早某版逐字相同，导入时去重成指针；18 本站有手册，11 没有。
        same_as={'11': '10', '18': '12'}, carried=('20',), editorial=WAL_EDITORIAL,
        intro={'status': 'predates_history_boundary'}, position=30000)

    # 2) 13 新增，带一条已核实的引入提交。
    skip = {major: dict(category='Write-Ahead Log / Settings', vartype='integer', context='user',
                        boot_val='2048', unit='kB', min_val='0', max_val='2147483647',
                        short_desc='Size of new file to fsync instead of writing WAL.',
                        short_desc_zh='改用 fsync 而非写 WAL 的新文件大小阈值。')
            for major in ('13', '14', '15', '16', '17', '18', '19', '20')}
    make_parameter(
        'wal_skip_threshold', 'Write-Ahead Log', 'wal', 'runtime-config-wal.html',
        'GUC-WAL-SKIP-THRESHOLD', skip, html={'18': '<p>小于此值的新文件直接 fsync。</p>'},
        carried=('20',),
        intro={'status': 'verified', 'hash': '8be0fb9c8a86d0b60fcd68d6d2deba7d2e3bbabd',
               'authored_at': '2020-03-29T10:00:00+09:00', 'subject': 'Skip WAL for new relations.',
               'url': 'https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=8be0fb9c',
               'discussion': ['https://postgr.es/m/example']},
        position=30001)

    # 3) 9.5 引入，16 之后移除；15 改过默认值。
    old = {}
    for major in ('9.5', '9.6', '10', '11', '12', '13', '14', '15', '16'):
        old[major] = dict(category='Resource Usage / Memory', vartype='integer',
                          context='postmaster' if major in ('9.5', '9.6', '10', '11') else 'sighup',
                          unit='min', boot_val='-1' if major in ('9.5', '9.6', '10', '11', '12',
                                                                 '13', '14') else '0',
                          min_val='-1', max_val='86400',
                          short_desc='Time before a snapshot is too old to read pages changed after.',
                          short_desc_zh='快照过旧的时间阈值。')
    make_parameter('old_snapshot_threshold', 'Resource Usage', 'resource',
                   'runtime-config-resource.html', 'GUC-OLD-SNAPSHOT-THRESHOLD', old,
                   html={'12': '<p>快照过旧的时间阈值。</p>'}, position=20000)

    # 4) 只有 20 手册里有的新参数：没有 pg_settings 事实，也没有默认值变迁。
    fresh = {'20': dict(category='Query Tuning / Planner Method Configuration', vartype='',
                        context='', boot_val=None, human='', short_desc='',
                        short_desc_zh='启用或禁用分组聚合计划。')}
    make_parameter('enable_groupagg', 'Query Tuning', 'query',
                   'runtime-config-query.html', 'GUC-ENABLE-GROUPAGG', fresh,
                   html={'20': '<p>启用或禁用分组聚合计划。</p>'}, history=False, position=50000)

    # 5) 大小写混合的规范名；19 改了默认值，20 沿用。
    style = {}
    for major in MAJORS:
        style[major] = dict(category='Client Connection Defaults / Locale and Formatting',
                            vartype='string', context='user',
                            boot_val='ISO, DMY' if major in ('19', '20') else 'ISO, MDY',
                            short_desc='Sets the display format for date and time values.',
                            short_desc_zh='设置日期与时间值的显示格式。')
    make_parameter('DateStyle', 'Client Connection Defaults', 'client',
                   'runtime-config-client.html', 'GUC-DATESTYLE', style,
                   html={'18': '<p>设置日期与时间值的显示格式。</p>'}, carried=('20',),
                   position=90000)

    counts = {}
    for parameter in GucParameter.objects.all():
        for major in parameter.present_in:
            counts[major] = counts.get(major, 0) + 1
    for version in GucVersion.objects.all():
        version.parameter_count = counts.get(version.major, 0)
        version.save(update_fields=['parameter_count'])


def load_manuals():
    from pgweb.core.models import Version
    from pgweb.docs.models import DocPage
    Version.objects.bulk_create([
        Version(tree=tree, current=tree == 18, reldate=date(2025, 9, 1),
                firstreldate=date(2025, 9, 1), eoldate=date(2030, 1, 1))
        for tree in MANUAL_TREES])
    files = ('runtime-config-wal.html', 'runtime-config-resource.html',
             'runtime-config-client.html', 'runtime-config-query.html')
    for tree in MANUAL_TREES:
        for filename in files:
            DocPage.objects.create(file=filename, version_id=tree,
                                   title='19.5.1. 设置' if 'wal' in filename else filename,
                                   content='<html><body>{}</body></html>'.format(filename))


# 模板由前端分头在写：真模板在就用真模板，还没落地就退到这份只打印上下文的占位。
STUBS = {
    'wiki/guc_index.html': '{{ title }}|{{ total }}|'
                           '{% for g in groups %}{{ g.anchor }} {% endfor %}',
    'wiki/guc_detail.html': '{{ title }}|{{ name }}|{{ change_note }}|{{ version.major }}',
    'wiki/guc_changes.html': '{{ title }}|{{ version.label }}|{{ summary.added }}',
}


def with_stub_templates(cls):
    templates = copy.deepcopy(settings.TEMPLATES)
    loaders = list(templates[0]['OPTIONS']['loaders'])
    loaders.append(('django.template.loaders.locmem.Loader', STUBS))
    templates[0]['OPTIONS']['loaders'] = loaders
    return override_settings(TEMPLATES=templates)(cls)


class GucFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        load_manuals()
        make_dataset()

    def setUp(self):
        cache.clear()


# ---------------------------------------------------------------- 索引页

class GucIndexTests(GucFixture):
    """索引页的分组、版本变动与筛选。"""

    def test_versions_cover_the_whole_range_with_one_default(self):
        order = guc.versions()
        self.assertEqual([v['major'] for v in order], list(MAJORS))
        self.assertEqual([v['major'] for v in order if v['is_default']], ['18'])
        self.assertEqual(guc.default_major(), '18')
        last = order[-1]
        self.assertEqual((last['label'], last['status_label'], last['schema_source']),
                         ('20 devel', '开发版', 'documentation'))
        self.assertTrue(order[-1]['devel'])
        self.assertTrue(order[-2]['preview'])
        self.assertEqual(order[-1]['url'], '/docs/guc/changes/20/')

    def test_groups_follow_the_manual_order_and_carry_subgroups(self):
        payload = guc.index()
        self.assertEqual([group['slug'] for group in payload['groups']],
                         ['resource', 'wal', 'query', 'client'])
        self.assertEqual(payload['total'], 5)
        self.assertEqual(payload['group_count'], 4)
        self.assertEqual((payload['earliest_major'], payload['latest_major']), ('9.0', '20'))
        wal = next(g for g in payload['groups'] if g['slug'] == 'wal')
        self.assertEqual(wal['anchor'], 'group-wal')
        self.assertEqual(wal['label'], '预写式日志')
        self.assertEqual(len(wal['subgroups']), 1)
        subgroup = wal['subgroups'][0]
        self.assertEqual(subgroup['anchor'], 'cat-wal-settings')
        self.assertEqual(subgroup['label'], '设置')
        self.assertEqual(subgroup['count'], 2)
        self.assertEqual([row['name'] for row in subgroup['rows']],
                         ['wal_level', 'wal_skip_threshold'])

    def test_a_category_that_is_its_own_group_has_no_subgroup_label(self):
        self.assertEqual(guc.category_label('锁管理', '锁管理'), '')
        self.assertEqual(guc.category_anchor('locks', 'Lock Management'), 'cat-locks')

    def test_every_strip_has_one_cell_per_version(self):
        rows = {row['name']: row for group in guc.index()['groups']
                for sub in group['subgroups'] for row in sub['rows']}
        for name, row in rows.items():
            self.assertEqual([cell['major'] for cell in row['strip']], list(MAJORS), name)

    def test_the_strip_marks_every_version_and_names_each_cell(self):
        rows = {row['name']: row for group in guc.index()['groups']
                for sub in group['subgroups'] for row in sub['rows']}
        states = lambda name: [cell['state'] for cell in rows[name]['strip']]
        self.assertEqual(states('wal_level'), ['present'] * 7 + ['changed'] + ['present'] * 10)
        wal = rows['wal_level']['strip']
        self.assertEqual(wal[0]['label'], '9.0 · 存在')
        self.assertEqual(wal[7]['label'], '10 · 默认值变更')
        self.assertEqual(states('wal_skip_threshold'), ['absent'] * 10 + ['added'] + ['present'] * 7)
        self.assertEqual(states('old_snapshot_threshold'),
                         ['absent'] * 5 + ['added'] + ['present'] * 3 + ['changed']
                         + ['present'] * 2 + ['changed'] + ['present'] + ['removed'] + ['absent'] * 3)
        self.assertTrue(rows['old_snapshot_threshold']['removed'])
        self.assertEqual(rows['old_snapshot_threshold']['removed_in'], '17')
        self.assertEqual(states('enable_groupagg'), ['absent'] * 17 + ['added'])

    def test_the_baseline_version_is_never_marked_added(self):
        rows = {row['name']: row for group in guc.index()['groups']
                for sub in group['subgroups'] for row in sub['rows']}
        self.assertEqual(rows['wal_level']['strip'][0]['state'], 'present')
        self.assertTrue(rows['wal_level']['baseline'])
        self.assertFalse(rows['wal_skip_threshold']['baseline'])

    def test_rows_show_the_default_version_snapshot(self):
        rows = {row['name']: row for group in guc.index()['groups']
                for sub in group['subgroups'] for row in sub['rows']}
        # 19 改了默认值、20 沿用；行上要显示 18 的取值，不是最新那一版的。
        self.assertEqual(rows['DateStyle']['boot_human'], 'ISO, MDY')
        self.assertEqual(GucParameter.objects.get(key='datestyle').boot_human, 'ISO, DMY')
        # 默认版本没有这个参数时退到它最后存在的版本。
        self.assertEqual(rows['old_snapshot_threshold']['boot_human'], '0 min')
        self.assertEqual(rows['wal_level']['vartype_label'], '枚举')
        self.assertEqual(rows['wal_level']['context_label'], '重启生效')
        self.assertIn('重启', rows['wal_level']['context_note'])
        self.assertEqual(rows['wal_level']['last_change'], '10')
        self.assertEqual(rows['wal_level']['change_count'], 1)
        self.assertEqual(rows['wal_level']['default_change_count'], 1)
        self.assertIn('设置写入 WAL 的信息量。', rows['wal_level']['text'])

    def test_filters_count_groups_contexts_and_versions(self):
        filters = {item['param']: item for item in guc.index()['filters']}
        self.assertEqual(list(filters), ['group', 'context', 'first', 'present'])
        groups = {o['value']: o['count'] for o in filters['group']['options']}
        self.assertEqual(groups, {'resource': 1, 'wal': 2, 'query': 1, 'client': 1})
        contexts = {o['value']: o['count'] for o in filters['context']['options']}
        self.assertEqual(contexts, {'postmaster': 1, 'sighup': 1, 'user': 2})
        first = {o['value']: o['count'] for o in filters['first']['options']}
        self.assertEqual(first, {'9.0': 2, '9.5': 1, '13': 1, '20': 1})
        present = {o['value']: o['count'] for o in filters['present']['options']}
        self.assertEqual((present['9.0'], present['18'], present['20']), (2, 3, 4))
        self.assertEqual(filters['context']['options'][0]['label'], '重启生效')

    def test_stats_count_snapshots_and_changes(self):
        stats = guc.index()['stats']
        self.assertEqual(stats['parameters'], 5)
        self.assertEqual(stats['versions'], 18)
        self.assertEqual(stats['removed'], 1)
        self.assertEqual(stats['snapshots'],
                         sum(len(p.present_in) for p in GucParameter.objects.all()))
        self.assertEqual(stats['default_changes'], 3)

    def test_the_index_reads_the_table_once(self):
        guc.versions()
        # 一次取行（JSON 大列留在库里），一次汇总计数。
        with self.assertNumQueries(2):
            guc.index_payload()

    def test_a_detail_page_does_not_scan_the_whole_column(self):
        guc.index()
        with self.assertNumQueries(3):
            guc.detail('wal_level', '18')
        # 缓存热起来之后只剩那一行参数。
        with self.assertNumQueries(2):
            guc.detail('wal_level', '9.0')

    def test_the_default_version_is_read_off_the_version_bar(self):
        guc.versions()
        with self.assertNumQueries(0):
            self.assertEqual(guc.default_major(), '18')
            self.assertEqual(guc.pick_major('', ['9.0', '18', '20']), '18')
            self.assertEqual(guc.pick_major('nope', ['9.0', '18', '20']), '18')
            self.assertEqual(guc.pick_major('9.0', ['9.0', '18', '20']), '9.0')
            # 默认版本没有这个参数时取它最后存在的版本。
            self.assertEqual(guc.pick_major('', ['9.5', '16']), '16')
            self.assertEqual(guc.pick_major('', []), '')


# ---------------------------------------------------------------- 详情页

class GucDetailTests(GucFixture):
    """详情页的事实、版本条、矩阵、时间线与手册说明。"""

    def test_detail_defaults_to_the_stable_version_and_honours_v(self):
        self.assertEqual(guc.detail('wal_level')['version']['major'], '18')
        self.assertEqual(guc.detail('wal_level', '9.3')['version']['major'], '9.3')
        self.assertEqual(guc.detail('wal_level', 'nope')['version']['major'], '18')
        # 18 没有这个参数：落到它最后存在的 16。
        self.assertEqual(guc.detail('old_snapshot_threshold')['version']['major'], '16')
        self.assertEqual(guc.detail('enable_groupagg')['version']['major'], '20')

    def test_lookup_is_case_insensitive_and_reports_the_canonical_name(self):
        self.assertEqual(guc.detail('datestyle')['name'], 'DateStyle')
        self.assertEqual(guc.detail('DATESTYLE')['name'], 'DateStyle')
        with self.assertRaises(GucParameter.DoesNotExist):
            guc.detail('nosuch')

    def test_facts_report_type_context_default_category_and_status(self):
        facts = {row['label']: row for row in guc.detail('wal_level', '18')['facts']}
        self.assertEqual(facts['类型']['value'], '枚举')
        self.assertEqual(facts['类型']['note'], 'enum')
        self.assertEqual(facts['上下文']['value'], '重启生效')
        self.assertIn('重启', facts['上下文']['note'])
        self.assertEqual(facts['默认值']['value'], 'replica')
        self.assertTrue(facts['默认值']['mono'])
        self.assertEqual(facts['枚举值']['value'], 'minimal, replica, logical')
        self.assertEqual(facts['分类']['value'], '预写式日志 / 设置')
        self.assertEqual(facts['分类']['url'], '/docs/guc/#cat-wal-settings')
        self.assertEqual(facts['引入版本']['value'], '9.0（基线）')
        self.assertEqual(facts['状态']['value'], '现存')
        self.assertNotIn('取值范围', facts)

    def test_facts_of_a_removed_parameter_name_the_version_that_dropped_it(self):
        facts = {row['label']: row for row in guc.detail('old_snapshot_threshold')['facts']}
        self.assertEqual(facts['状态']['value'], '于 17 移除')
        self.assertEqual(facts['取值范围']['value'], '-1 – 86400')
        self.assertEqual(facts['默认值']['value'], '0 min')
        self.assertEqual(facts['引入版本']['value'], '9.5')

    def test_the_introduction_commit_links_the_introduced_version_fact(self):
        payload = guc.detail('wal_skip_threshold', '18')
        commit = payload['intro_commit']
        self.assertEqual(commit['short'], '8be0fb9c8a')
        self.assertEqual(commit['date'], '2020-03-29')
        self.assertEqual(commit['subject'], 'Skip WAL for new relations.')
        facts = {row['label']: row for row in payload['facts']}
        self.assertEqual(facts['引入版本']['url'], commit['url'])
        self.assertEqual(payload['links']['commit'], commit['url'])
        # 只有状态没有 hash 的当成没有提交。
        self.assertIsNone(guc.detail('wal_level', '18')['intro_commit'])

    def test_ribbon_is_one_cell_per_version_with_the_current_one_marked(self):
        ribbon = guc.detail('wal_level', '12')['ribbon']
        self.assertEqual(len(ribbon), len(MAJORS))
        cells = {cell['major']: cell for cell in ribbon}
        self.assertTrue(cells['12']['current'])
        self.assertFalse(cells['18']['current'])
        self.assertEqual(cells['10']['state'], 'changed')
        self.assertEqual(cells['9.0']['state'], 'present')
        self.assertEqual(cells['18']['url'], '/docs/guc/wal_level/?v=18')
        self.assertEqual(cells['12']['doc_url'], '/docs/12/runtime-config-wal.html#GUC-WAL-LEVEL')
        # 本站没有 11 的手册，就不给链接。
        self.assertEqual(cells['11']['doc_url'], '')
        self.assertEqual(cells['20']['doc_url'],
                         '/docs/devel/runtime-config-wal.html#GUC-WAL-LEVEL')
        self.assertTrue(cells['20']['devel'])
        gone = {cell['major']: cell for cell in guc.detail('old_snapshot_threshold')['ribbon']}
        self.assertEqual(gone['17']['state'], 'removed')
        self.assertEqual(gone['17']['url'], '')
        self.assertEqual(gone['18']['state'], 'absent')

    def test_default_track_segments_span_the_versions_they_cover(self):
        track = guc.detail('wal_level', '18')['default_track']
        self.assertEqual([(item['from'], item['to'], item['span'], item['human']) for item in track],
                         [('9.0', '9.6', 7, 'minimal'), ('10', '20', 11, 'replica')])
        self.assertEqual([item['current'] for item in track], [False, True])
        # 一段也要画出来：说明自收录起没变过。
        single = guc.detail('wal_skip_threshold', '18')['default_track']
        self.assertEqual(len(single), 1)
        self.assertEqual(single[0]['human'], '2 MiB')
        self.assertEqual(single[0]['span'], 8)
        # 20 才出现、没有 pg_settings 事实的参数没有变迁条。
        self.assertEqual(guc.detail('enable_groupagg')['default_track'], [])

    def test_an_uncollected_default_is_not_shown_as_unset(self):
        """20 的新参数只有手册：默认值没采集到，不能说成「未设置」。"""
        payload = guc.detail('enable_groupagg')
        labels = [row['label'] for row in payload['facts']]
        self.assertNotIn('默认值', labels)
        self.assertNotIn('上下文', labels)
        self.assertEqual(labels, ['分类', '引入版本', '状态'])
        cells = {cell['field']: cell for cell in payload['matrix']['rows'][0]['cells']}
        self.assertEqual(cells['boot_val']['value'], '')
        # 真的没有默认值的参数仍然照说。
        self.assertEqual(guc.human_of({'boot_val': None, 'unit': ''}), '未设置')
        self.assertEqual(guc.human_of({'boot_val': None, 'unit': '', 'human': ''}), '')

    def test_matrix_rows_are_versions_and_mark_changed_cells(self):
        matrix = guc.detail('wal_level', '18')['matrix']
        self.assertEqual([field['field'] for field in matrix['fields']],
                         ['boot_val', 'unit', 'context', 'vartype', 'min_val', 'max_val',
                          'enumvals'])
        self.assertEqual([field['label'] for field in matrix['fields']][:2], ['默认值', '单位'])
        self.assertEqual([row['major'] for row in matrix['rows']], list(MAJORS))
        rows = {row['major']: row for row in matrix['rows']}
        self.assertTrue(rows['18']['current'])
        self.assertTrue(rows['20']['carried'])
        cells = {cell['field']: cell for cell in rows['10']['cells']}
        self.assertEqual(cells['boot_val']['value'], 'replica')
        self.assertTrue(cells['boot_val']['changed'])
        self.assertTrue(cells['enumvals']['changed'])
        self.assertFalse(cells['context']['changed'])
        self.assertEqual(cells['context']['value'], '重启生效')
        # 9.0 是第一行，没有可比的上一版。
        self.assertFalse(any(cell['changed'] for cell in rows['9.0']['cells']))
        self.assertFalse(any(cell['changed'] for cell in rows['11']['cells']))

    def test_timeline_is_newest_first_and_spells_out_every_field(self):
        timeline = guc.detail('wal_level', '18')['timeline']
        self.assertEqual([item['to'] for item in timeline], ['20', '17', '10'])
        self.assertTrue(timeline[0]['carried'])
        self.assertEqual(timeline[0]['fields'], [])
        wording = timeline[1]
        self.assertFalse(wording['substantive'])
        self.assertEqual([field['field'] for field in wording['fields']], ['short_desc'])
        landmark = timeline[2]
        self.assertEqual((landmark['from'], landmark['status']), ('9.6', 'changed'))
        self.assertTrue(landmark['substantive'])
        self.assertTrue(landmark['default_changed'])
        fields = {field['field']: field for field in landmark['fields']}
        self.assertEqual((fields['boot_val']['from'], fields['boot_val']['to']),
                         ('minimal', 'replica'))
        self.assertEqual(fields['boot_val']['to_human'], 'replica')
        # 枚举值保持列表，由模板拼；默认值另带人类可读形式。
        self.assertEqual(fields['enumvals']['to'], ['minimal', 'replica', 'logical'])
        self.assertEqual(landmark['url'], '/docs/guc/wal_level/?v=10')
        # 新增与移除也在时间线上。
        self.assertEqual([item['status'] for item in
                          guc.detail('wal_skip_threshold', '18')['timeline']][-1], 'added')
        self.assertEqual(guc.detail('old_snapshot_threshold')['timeline'][0]['status'], 'removed')

    def test_change_note_has_one_wording_per_situation(self):
        self.assertEqual(guc.detail('wal_level', '9.0')['change_note'],
                         '9.0 是本数据集的收录基线，不代表该参数首次于 9.0 引入。')
        self.assertEqual(guc.detail('wal_skip_threshold', '13')['change_note'],
                         'PostgreSQL 13 新增此参数。')
        self.assertEqual(
            guc.detail('wal_level', '10')['change_note'],
            '相对 PostgreSQL 9.6：默认值由 minimal 改为 replica，'
            '枚举值由 minimal, archive, hot_standby, logical 改为 minimal, replica, logical。')
        self.assertEqual(guc.detail('wal_level', '17')['change_note'],
                         '相对 PostgreSQL 16 仅简述或分类有更新。')
        self.assertEqual(guc.detail('wal_level', '18')['change_note'],
                         '相对 PostgreSQL 17 无变化。')
        self.assertEqual(guc.detail('wal_level', '20')['change_note'],
                         'PostgreSQL 20 开发版沿用 19 的 pg_settings 事实，说明取自 devel 手册。')

    def test_preview_and_devel_versions_carry_a_notice(self):
        self.assertIn('预发行', guc.detail('wal_level', '19')['notice'])
        self.assertIn('开发版', guc.detail('wal_level', '20')['notice'])
        self.assertEqual(guc.detail('wal_level', '18')['notice'], '')

    def test_doc_follows_the_same_as_pointer(self):
        payload = guc.detail('wal_level', '11')
        self.assertEqual(payload['doc']['major'], '10')
        self.assertFalse(payload['doc']['borrowed'])
        self.assertEqual(payload['doc']['html'], '<p>决定写入 WAL 的信息量。</p>')

    def test_a_deduplicated_translation_still_links_the_version_being_read(self):
        """doc_same_as 是存储去重，不是「译文住在那一版」：链接仍指正在读的这一版。"""
        payload = guc.detail('wal_level', '18')
        self.assertEqual(payload['doc']['major'], '12')
        self.assertFalse(payload['doc']['borrowed'])
        self.assertEqual(payload['doc']['html'], '<p>决定写入 WAL 的信息量（12 版措辞）。</p>')
        self.assertEqual(payload['doc']['local_url'],
                         '/docs/18/runtime-config-wal.html#GUC-WAL-LEVEL')
        self.assertEqual(payload['doc']['label'], 'PostgreSQL 18 手册 · 19.5.1 设置')
        self.assertEqual(payload['links']['doc'], payload['doc']['local_url'])

    def test_nine_x_borrows_the_nearest_translation_and_keeps_its_own_official_link(self):
        payload = guc.detail('wal_level', '9.3')
        self.assertTrue(payload['doc']['borrowed'])
        self.assertEqual(payload['doc']['major'], '10')
        self.assertEqual(payload['doc']['local_url'],
                         '/docs/10/runtime-config-wal.html#GUC-WAL-LEVEL')
        self.assertEqual(payload['doc']['official_url'],
                         'https://www.postgresql.org/docs/9.3/runtime-config-wal.html#GUC-WAL-LEVEL')
        self.assertEqual(payload['links']['doc'], '')
        self.assertEqual(payload['doc']['label'], 'PostgreSQL 10 手册 · 19.5.1 设置')

    def test_doc_versions_only_list_manuals_the_site_has(self):
        payload = guc.detail('wal_level', '18')
        self.assertEqual([item['major'] for item in payload['doc_versions']],
                         ['10', '12', '18', '20'])
        self.assertEqual(payload['links']['doc'],
                         '/docs/18/runtime-config-wal.html#GUC-WAL-LEVEL')
        self.assertEqual(payload['links']['doc_label'], 'PostgreSQL 18 手册')

    def test_editorial_keeps_chinese_and_resolves_related_parameters(self):
        editorial = guc.detail('wal_level', '18')['editorial']
        self.assertEqual(len(editorial['mechanism']), 2)
        self.assertEqual(editorial['advice']['oltp'], 'OLTP 用 replica。')
        self.assertEqual(editorial['pitfalls'], ['改这个参数要重启。'])
        related = {item['name']: item for item in editorial['related']}
        self.assertTrue(related['wal_skip_threshold']['exists'])
        self.assertEqual(related['wal_skip_threshold']['url'], '/docs/guc/wal_skip_threshold/')
        self.assertEqual(related['wal_skip_threshold']['short_desc_zh'],
                         '改用 fsync 而非写 WAL 的新文件大小阈值。')
        self.assertFalse(related['nosuch_param']['exists'])
        self.assertEqual(related['nosuch_param']['url'], '')
        self.assertEqual(editorial['references'][0]['title'], '预写式日志')
        # 没有编辑分析的参数给的是空壳，不是 None。
        empty = guc.detail('enable_groupagg')['editorial']
        self.assertEqual((empty['mechanism'], empty['pitfalls'], empty['related']), ([], [], []))

    def test_siblings_are_the_index_table_of_the_same_subcategory(self):
        payload = guc.detail('wal_level', '18')
        self.assertEqual([group['slug'] for group in payload['siblings']], ['wal'])
        group = payload['siblings'][0]
        self.assertEqual(group['current'], 'wal_level')
        self.assertEqual([sub['category'] for sub in group['subgroups']],
                         ['Write-Ahead Log / Settings'])
        self.assertEqual([row['name'] for row in group['subgroups'][0]['rows']],
                         ['wal_level', 'wal_skip_threshold'])
        self.assertEqual(payload['previous_major'], '17')
        self.assertEqual(guc.detail('wal_level', '9.0')['previous_major'], '')


# ---------------------------------------------------------------- 变更页

class GucChangesTests(GucFixture):
    """版本变更页的五项汇总与三类明细。"""

    def test_a_release_reports_added_removed_and_default_changes(self):
        payload = guc.changes('10')
        self.assertEqual(payload['previous']['major'], '9.6')
        self.assertFalse(payload['arbitrary'])
        self.assertEqual(payload['summary'],
                         {'added': 0, 'removed': 0, 'default_changed': 1, 'changed': 0,
                          'reworded': 0})
        entry = payload['default_changed'][0]
        self.assertEqual(entry['name'], 'wal_level')
        self.assertEqual(entry['url'], '/docs/guc/wal_level/')
        self.assertEqual((entry['from']['human'], entry['to']['human']), ('minimal', 'replica'))
        self.assertEqual(entry['category_zh'], '预写式日志 / 设置')

    def test_a_property_change_lists_the_fields_that_moved(self):
        payload = guc.changes('12')
        self.assertEqual(payload['summary'],
                         {'added': 0, 'removed': 0, 'default_changed': 0, 'changed': 1,
                          'reworded': 0})
        entry = payload['changed'][0]
        self.assertEqual(entry['name'], 'old_snapshot_threshold')
        self.assertEqual(entry['fields'],
                         [{'field': 'context', 'label': '上下文',
                           'from': '重启生效', 'to': '重载生效'}])

    def test_a_release_that_only_adds_a_parameter(self):
        payload = guc.changes('13')
        self.assertEqual(payload['summary']['added'], 1)
        card = payload['added'][0]
        self.assertEqual(card['name'], 'wal_skip_threshold')
        self.assertEqual(card['vartype_label'], '整数')
        self.assertEqual(card['context_label'], '会话')
        self.assertEqual(card['boot_human'], '2 MiB')
        self.assertEqual(card['category_zh'], '预写式日志 / 设置')

    def test_a_removal_is_reported_by_the_release_that_dropped_it(self):
        payload = guc.changes('17')
        self.assertEqual(payload['summary']['removed'], 1)
        self.assertEqual([card['name'] for card in payload['removed']],
                         ['old_snapshot_threshold'])
        self.assertEqual(payload['summary']['reworded'], 1)
        self.assertEqual([card['name'] for card in payload['reworded']], ['wal_level'])

    def test_the_devel_release_carries_everything_and_adds_the_new_parameters(self):
        payload = guc.changes('20')
        self.assertEqual(payload['summary']['added'], 1)
        self.assertEqual([card['name'] for card in payload['added']], ['enable_groupagg'])
        self.assertEqual(payload['summary']['changed'], 0)
        self.assertEqual(payload['summary']['default_changed'], 0)
        self.assertIn('开发版', payload['notice'])

    def test_the_first_version_lists_the_baseline(self):
        payload = guc.changes('9.0')
        self.assertTrue(payload['baseline'])
        self.assertIsNone(payload['previous'])
        self.assertIn('收录基线', payload['baseline_note'])
        names = [row['name'] for group in payload['baseline_groups']
                 for sub in group['subgroups'] for row in sub['rows']]
        self.assertEqual(sorted(names), ['DateStyle', 'wal_level'])
        self.assertEqual(payload['summary'],
                         {'added': 0, 'removed': 0, 'default_changed': 0, 'changed': 0,
                          'reworded': 0})
        # 基线名单上的事实取 9.0 那一版。
        rows = {row['name']: row for group in payload['baseline_groups']
                for sub in group['subgroups'] for row in sub['rows']}
        self.assertEqual(rows['wal_level']['boot_human'], 'minimal')

    def test_a_non_adjacent_comparison_is_computed_on_the_spot(self):
        payload = guc.changes('18', from_major='9.6')
        self.assertTrue(payload['arbitrary'])
        self.assertEqual(payload['from_major'], '9.6')
        self.assertEqual(payload['summary']['added'], 1)
        self.assertEqual([card['name'] for card in payload['added']], ['wal_skip_threshold'])
        self.assertEqual([card['name'] for card in payload['removed']],
                         ['old_snapshot_threshold'])
        self.assertEqual([entry['name'] for entry in payload['default_changed']], ['wal_level'])

    def test_an_unknown_from_falls_back_to_the_adjacent_comparison(self):
        payload = guc.changes('18', from_major='nope')
        self.assertFalse(payload['arbitrary'])
        self.assertEqual(payload['from_major'], '')
        self.assertEqual(payload['previous']['major'], '17')

    def test_compare_reports_only_real_differences(self):
        left = {'boot_val': 'on', 'unit': '', 'context': 'user'}
        right = {'boot_val': 'off', 'unit': None, 'context': 'user'}
        change = guc.compare(left, right, '17', '18')
        self.assertEqual(change['fields'], {'boot_val': {'from': 'on', 'to': 'off'}})
        self.assertTrue(change['default_changed'])
        # '' 与 None 是同一个空。
        self.assertIsNone(guc.compare(left, dict(left, unit=None)))
        self.assertEqual(guc.compare({}, right)['status'], 'added')
        self.assertEqual(guc.compare(left, {})['status'], 'removed')
        self.assertIsNone(guc.compare({}, {}))

    def test_changes_for_an_unknown_version_raises(self):
        with self.assertRaises(GucVersion.DoesNotExist):
            guc.changes('99')


# ---------------------------------------------------------------- 页面

@with_stub_templates
class GucPageTests(GucFixture):
    """四条路由都要能走通。"""

    def test_index_renders(self):
        response = self.client.get('/docs/guc/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], 5)
        self.assertEqual(response.context['column']['slug'], 'guc')
        self.assertIn('group-wal', response.content.decode())

    def test_detail_renders_and_honours_the_version_parameter(self):
        response = self.client.get('/docs/guc/wal_level/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['version']['major'], '18')
        response = self.client.get('/docs/guc/wal_level/?v=9.3')
        self.assertEqual(response.context['version']['major'], '9.3')
        self.assertTrue(response.context['doc']['borrowed'])
        response = self.client.get('/docs/guc/wal_level/?v=20')
        self.assertEqual(response.context['version']['major'], '20')

    def test_an_invalid_version_falls_back_to_the_default(self):
        response = self.client.get('/docs/guc/wal_level/?v=1999')
        self.assertEqual(response.context['version']['major'], '18')

    def test_query_parameters_outside_the_whitelist_are_dropped(self):
        response = self.client.get('/docs/guc/wal_level/?v=10&nope=1')
        self.assertEqual(response.context['version']['major'], '10')
        self.assertEqual(self.client.get('/docs/guc/?q=wal&group=wal&context=user'
                                         '&first=9.0&present=18').status_code, 200)

    def test_a_non_canonical_spelling_redirects_to_the_canonical_one(self):
        response = self.client.get('/docs/guc/datestyle/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/docs/guc/DateStyle/')
        response = self.client.get('/docs/guc/DATESTYLE/?v=10')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/docs/guc/DateStyle/?v=10')
        self.assertEqual(self.client.get('/docs/guc/DateStyle/').status_code, 200)

    def test_an_unknown_parameter_is_404(self):
        self.assertEqual(self.client.get('/docs/guc/nosuch/').status_code, 404)
        self.assertEqual(self.client.get('/docs/guc/9bad/').status_code, 404)
        self.assertEqual(self.client.get('/docs/guc/bad-name/').status_code, 404)

    def test_changes_root_redirects_to_the_default_version(self):
        response = self.client.get('/docs/guc/changes/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/docs/guc/changes/18/')

    def test_changes_pages_render_and_honour_from(self):
        self.assertEqual(self.client.get('/docs/guc/changes/9.0/').status_code, 200)
        response = self.client.get('/docs/guc/changes/18/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['version']['label'], '18')
        response = self.client.get('/docs/guc/changes/18/?from=9.6')
        self.assertTrue(response.context['arbitrary'])
        self.assertEqual(self.client.get('/docs/guc/changes/20/').status_code, 200)
        self.assertEqual(self.client.get('/docs/guc/changes/99/').status_code, 404)

    def test_the_docs_navigation_marks_the_column_active(self):
        response = self.client.get('/docs/guc/')
        active = [item for item in response.context['navmenu'] if item.get('active')]
        self.assertEqual([item['link'] for item in active], ['/docs/guc/'])

    def test_the_column_is_local_only(self):
        from pgweb.util.contexts import LOCAL_ONLY_SECTIONS, _source_url
        self.assertIn('/docs/guc/', LOCAL_ONLY_SECTIONS)
        self.assertEqual(_source_url('/docs/guc/wal_level/'), '')

    def test_the_column_is_live_and_listed(self):
        self.assertTrue(BY_SLUG['guc']['live'])
        self.assertEqual(BY_SLUG['guc']['coverage'], 'PostgreSQL 9.0 – 20 devel')

    def test_sitemap_lists_the_index_every_parameter_and_every_changes_page(self):
        from .struct import get_struct
        pages = [page for page, _ in get_struct()]
        self.assertIn('docs/guc/', pages)
        self.assertIn('docs/guc/wal_level/', pages)
        self.assertIn('docs/guc/DateStyle/', pages)
        self.assertIn('docs/guc/changes/9.0/', pages)
        self.assertIn('docs/guc/changes/20/', pages)


# ---------------------------------------------------------------- 检索

class GucSearchEntryTests(GucFixture):
    """检索条目的形状与重建计数。"""

    def entry(self, name):
        from pgweb.search.indexer import guc_entry
        return guc_entry(GucParameter.objects.get(key=name.lower()))

    def test_entry_shares_the_entity_of_the_manual_definition(self):
        entry = self.entry('wal_level')
        self.assertEqual(entry['entity_key'], 'guc:wal_level')
        self.assertEqual((entry['kind'], entry['subtype']), ('guc', 'wal'))
        self.assertEqual(entry['name'], 'wal_level')
        self.assertEqual(entry['url'], '/docs/guc/wal_level/')
        self.assertEqual(entry['weight'], 0.5)
        self.assertEqual(entry['aliases'], ['wal_level', 'wallevel'])
        self.assertEqual(entry['heading'], '配置参数 · 预写式日志 / 设置')
        self.assertEqual(entry['signature'], '枚举 · 重启生效 · 默认 replica')
        self.assertIn('设置写入 WAL 的信息量。', entry['body'])
        self.assertIn('minimal 只写崩溃恢复所需的记录。', entry['body'])
        self.assertIn('预写式日志 / 设置', entry['body'])

    def test_preview_carries_the_facts_and_the_default_history(self):
        preview = self.entry('wal_level')['preview']
        self.assertIn('设置写入 WAL 的信息量。', preview)
        self.assertIn('<dt>默认值</dt><dd>replica</dd>', preview)
        self.assertIn('<dt>上下文</dt><dd>重启生效</dd>', preview)
        self.assertIn('<dt>引入版本</dt><dd>9.0（基线）</dd>', preview)
        self.assertIn('默认值变迁', preview)
        self.assertIn('9.0 – 9.6', preview)
        # 默认值从未变过就不画变迁。
        self.assertNotIn('默认值变迁', self.entry('wal_skip_threshold')['preview'])

    def test_a_mixed_case_name_keeps_its_spelling_and_folds_its_key(self):
        entry = self.entry('DateStyle')
        self.assertEqual(entry['name'], 'DateStyle')
        self.assertEqual(entry['name_key'], 'datestyle')
        self.assertEqual(entry['entity_key'], 'guc:datestyle')
        self.assertEqual(entry['url'], '/docs/guc/DateStyle/')

    def test_rebuild_counts_and_replaces_the_source(self):
        from pgweb.search.indexer import rebuild_guc
        from pgweb.search.models import SearchEntry
        self.assertEqual(rebuild_guc(dry_run=True), {'guc': 5})
        self.assertEqual(SearchEntry.objects.filter(source='guc').count(), 0)
        self.assertEqual(rebuild_guc(), {'guc': 5})
        self.assertEqual(SearchEntry.objects.filter(source='guc').count(), 5)
        # 再跑一次是整体替换，不会翻倍。
        self.assertEqual(rebuild_guc(), {'guc': 5})
        self.assertEqual(SearchEntry.objects.filter(source='guc').count(), 5)
        row = SearchEntry.objects.get(source='guc', name='wal_level')
        self.assertEqual(row.entity_key, 'guc:wal_level')
        self.assertIsNone(row.document_id)
        self.assertIsNone(row.version)

    def test_the_search_service_includes_the_column(self):
        from pgweb.search import service
        state = service.parse_query('wal_level', available=[18], current=18)
        self.assertIn('guc', state['sources'])
        self.assertIn('guc', service.parse_query('pg18:wal_level', available=[18],
                                                 current=18)['sources'])
