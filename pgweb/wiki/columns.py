"""百科栏目。

这里是栏目本身的唯一定义：名称、地址、规模、上线状态、上游来源。文档导航末尾的
入口和 sitemap 都从这份列表生成，栏目上线时只改这里的 `live`。

`origin` 是这批数据的上游双语站点，`repo` 是它的仓库；两者都由 Pigsty 维护，
本站的百科是它们的中文渲染。SQL 命令与函数百科直接来自本站手册，没有独立上游仓库。

条目数是当前固定快照的实体并集；已上线栏目的页面按数据库中的真实数量显示。
系统目录采样至 19 beta 4，开发版另外从本站同构建手册推导。
"""

COLUMNS = (
    {
        'slug': 'sql',
        'name': 'SQL 命令',
        'short': 'SQL 命令',
        'tone': 'sql',
        'lead': '每条 SQL 命令的语法、参数与逐版本的语法演化。',
        'scale': '186 条命令 · 17 组',
        'coverage': 'PostgreSQL 10 – 20 devel',
        'repo': '',
        'origin': '',
        'live': True,
    },
    {
        'slug': 'sqlstate',
        'name': 'SQL 状态码',
        'short': 'SQL 状态码',
        'tone': 'err',
        'lead': 'SQLSTATE 的含义、报文、诊断与处置。',
        'scale': '263 个 SQL 状态码 · 44 个类',
        'coverage': 'PostgreSQL 9.0 – 19beta3',
        'repo': 'pgsty/err.pg.center',
        'origin': 'https://err.pg.center',
        'live': True,
    },
    {
        'slug': 'catalog',
        'name': '系统目录',
        'short': '系统目录',
        'tone': 'cat',
        'lead': '系统目录与视图的字段构成，以及逐版本的结构变化。',
        'scale': '153 个关系 · 4 类',
        'coverage': 'PostgreSQL 9.0 – 20 devel',
        'repo': 'pgsty/cat.pg.center',
        'origin': 'https://cat.pg.center',
        'live': True,
    },
    {
        'slug': 'guc',
        'name': '配置参数',
        'short': '配置参数',
        'tone': 'guc',
        'lead': '全部配置参数的作用、默认值演变与调优取舍。',
        'scale': '449 个参数 · 16 类',
        'coverage': 'PostgreSQL 9.0 – 20 devel',
        'repo': 'pgsty/guc.pg.center',
        'origin': 'https://guc.pg.center',
        'live': True,
    },
    {
        'slug': 'waitevent',
        'name': '等待事件',
        'short': '等待事件',
        'tone': 'wait',
        'lead': '每个等待事件的触发机制、是否异常与排查手段。',
        'scale': '302 个等待事件 · 9 类',
        'coverage': 'PostgreSQL 9.6 – 20 devel',
        'repo': 'pgsty/wait.pg.center',
        'origin': 'https://wait.pg.center',
        'live': True,
    },
    {
        'slug': 'lock',
        'name': '锁百科',
        'short': '锁百科',
        'tone': 'wait',
        'lead': '表级锁与行级锁的冲突矩阵、对应命令与逐版本规则。',
        'scale': '12 种锁模式 · 2 个层级',
        'coverage': 'PostgreSQL 10 – 20 devel',
        'repo': '',
        'origin': '',
        'live': True,
    },
    {
        'slug': 'func',
        'name': '函数百科',
        'short': '函数百科',
        'tone': 'func',
        'lead': '每个内置函数的签名、说明、示例与逐版本的签名演化。',
        'scale': '707 个函数 · 27 组',
        'coverage': 'PostgreSQL 9.0 – 20 devel',
        # 数据不来自独立的上游仓库：本站手册第 9 章就是来源。
        'repo': '',
        'origin': '',
        'live': True,
    },
)

from .topic_specs import TOPIC_SPECS

COLUMNS += tuple({
    'slug': slug, 'name': spec['name'], 'short': spec['name'], 'tone': spec['tone'],
    'lead': spec['lead'], 'scale': spec['scale'], 'coverage': 'PostgreSQL 10 – 20 devel',
    'repo': '', 'origin': '', 'live': True,
} for slug, spec in TOPIC_SPECS.items())

BY_SLUG = {column['slug']: column for column in COLUMNS}

NAV_GROUPS = (
    ('query-language', '查询语言', ('sql', 'func', 'sqlstate')),
    ('indexes-storage', '索引与存储', ('catalog', 'relopts', 'oid')),
    ('operations', '运行与维护', ('guc', 'waitevent', 'lock', 'role')),
    ('client-tools', '客户端工具', ()),
    ('extensibility', '扩展机制', ('hook',)),
    ('releases', '版本发布', ()),
)
COLUMNS = tuple(dict(BY_SLUG[slug], section=title, section_id=anchor)
                for anchor, title, slugs in NAV_GROUPS for slug in slugs)
BY_SLUG = {column['slug']: column for column in COLUMNS}


def nav_sections():
    """Only available Wiki sections appear in the homepage and global footer."""
    return [{'id': anchor, 'title': title, 'link': '/wiki/#' + anchor}
            for anchor, title, slugs in NAV_GROUPS if slugs]


def home_cards():
    """Small current counts and sampled ranges, without loading full snapshots."""
    from django.db.models import F, Func, TextField
    from . import models
    from .sqlcmd_common import version_key

    sources = {
        'sql': ('SqlCommand', '条命令', None, None),
        'func': ('PgFunction', '个函数', 'FuncVersion', 'function_count'),
        'sqlstate': ('ErrorCode', '个状态码', 'ErrorCodeRelease', 'code_count'),
        'catalog': ('CatalogRelation', '个关系', 'CatalogVersion', 'relation_count'),
        'guc': ('GucParameter', '个参数', 'GucVersion', 'parameter_count'),
        'waitevent': ('WaitEvent', '个事件', 'WaitEventVersion', 'event_count'),
        'lock': ('LockMode', '种锁模式', None, None),
        'hook': ('ExtensionHook', '个钩子', None, None),
        'relopts': ('StorageParameter', '个参数条目', None, None),
        'role': ('PredefinedRole', '个角色', None, None),
        'oid': ('ObjectIdentifierType', '个类型', None, None),
    }
    cards = listing()
    for card in cards:
        model_name, unit, version_model, count_field = sources[card['slug']]
        model = getattr(models, model_name)
        if version_model:
            versions = getattr(models, version_model).objects.filter(**{count_field + '__gt': 0})
            majors = list(versions.values_list('major', flat=True))
        else:
            majors = list(model.objects.order_by().annotate(
                major=Func(F('versions'), function='jsonb_object_keys', output_field=TextField())
            ).values_list('major', flat=True).distinct())
        majors.sort(key=version_key)
        card.update(count=model.objects.count(), unit=unit,
                    first=majors[0] if majors else '', last=majors[-1] if majors else '')
    return cards


def url(column):
    """A live column links to its own index; one not yet rendered here links
    straight to its origin site, so every entry leads to real content."""
    return '/wiki/{}/'.format(column['slug']) if column['live'] else column.get('origin', '')


def present(column):
    return dict(column, url=url(column), tone_class='wiki-tone-' + column['tone'],
                repo_url='https://github.com/' + column['repo'] if column['repo'] else '')


def listing():
    return [present(column) for column in COLUMNS]


def live_columns():
    return [column for column in COLUMNS if column['live']]


def nav_items():
    """Collection links for the standalone Wiki navigation."""
    return [{'title': column['name'], 'link': url(column),
             'section': column['section'], 'section_id': column['section_id']}
            for column in COLUMNS if url(column)]
