"""百科的五个栏目。

这里是栏目本身的唯一定义：名称、地址、规模、上线状态、上游来源。文档导航末尾的
五个入口和 sitemap 都从这份列表生成，栏目上线时只改这里的 `live`。

`origin` 是这批数据的上游双语站点，`repo` 是它的仓库；两者都由 Pigsty 维护，
本站的百科是它们的中文渲染。SQL 命令直接来自本站手册，没有独立上游仓库。

条目数是各数据仓库当前的实际规模，不是站点已导入的行数；已上线栏目的页面
自己按库里的真实数量显示。系统目录是个例外：cat 收到 19 beta 3 的 157 个关系，
本站在此之上从 devel 手册推出 PostgreSQL 20 一层，多出 pg_stat_kind_info 一个。
"""

COLUMNS = (
    {
        'slug': 'sql',
        'name': 'SQL 命令',
        'short': 'SQL 命令',
        'tone': 'sql',
        'lead': '每条 SQL 命令的语法、参数与逐版本的语法演化。',
        'scale': '183 条命令 · 17 组',
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
        'lead': '全部 263 个 SQLSTATE 的含义、报文、诊断与处置。',
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
        'scale': '158 个关系 · 4 类',
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
)

BY_SLUG = {column['slug']: column for column in COLUMNS}


def url(column):
    """A live column links to its own index; one not yet rendered here links
    straight to its origin site, so every entry leads to real content."""
    return '/docs/{}/'.format(column['slug']) if column['live'] else column.get('origin', '')


def present(column):
    return dict(column, url=url(column), tone_class='wiki-tone-' + column['tone'],
                repo_url='https://github.com/' + column['repo'] if column['repo'] else '')


def listing():
    return [present(column) for column in COLUMNS]


def live_columns():
    return [column for column in COLUMNS if column['live']]


def nav_items():
    """The five columns as entries at the end of the 文档 navigation."""
    return [{'title': column['name'], 'link': url(column)} for column in COLUMNS if url(column)]
