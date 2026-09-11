"""百科的四个栏目。

这里是栏目本身的唯一定义：名称、地址、规模、上线状态、上游来源。文档导航末尾的
四个入口和 sitemap 都从这份列表生成，栏目上线时只改这里的 `live`。

`origin` 是这批数据的上游双语站点，`repo` 是它的仓库；两者都由 Pigsty 维护，
本站的百科是它们的中文渲染。

条目数是各数据仓库当前的实际规模，不是站点已导入的行数；已上线栏目的页面
自己按库里的真实数量显示。系统目录是个例外：cat 收到 19 beta 3 的 157 个关系，
本站在此之上从 devel 手册推出 PostgreSQL 20 一层，多出 pg_stat_kind_info 一个。
"""

COLUMNS = (
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
        'slug': 'guc',
        'name': '配置参数',
        'short': '配置参数',
        'tone': 'guc',
        'lead': '全部配置参数的作用、默认值演变与调优取舍。',
        'scale': '447 个参数',
        'coverage': 'PostgreSQL 9.0 – 19beta3',
        'repo': 'pgsty/guc.pg.center',
        'origin': 'https://guc.pg.center',
        'live': False,
    },
    {
        'slug': 'waitevent',
        'name': '等待事件',
        'short': '等待事件',
        'tone': 'wait',
        'lead': '每个等待事件的触发机制、是否异常与排查手段。',
        'scale': '281 个等待事件',
        'coverage': 'PostgreSQL 13 – 18',
        'repo': 'pgsty/wait.pg.center',
        'origin': 'https://wait.pg.center',
        'live': False,
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
)

BY_SLUG = {column['slug']: column for column in COLUMNS}


def url(column):
    """A live column links to its own index; one not yet rendered here links
    straight to its origin site, so every entry leads to real content."""
    return '/docs/{}/'.format(column['slug']) if column['live'] else column['origin']


def present(column):
    return dict(column, url=url(column), tone_class='wiki-tone-' + column['tone'],
                repo_url='https://github.com/' + column['repo'])


def listing():
    return [present(column) for column in COLUMNS]


def live_columns():
    return [column for column in COLUMNS if column['live']]


def nav_items():
    """The four columns as entries at the end of the 文档 navigation."""
    return [{'title': column['name'], 'link': url(column)} for column in COLUMNS]
