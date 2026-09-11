from django.utils.functional import SimpleLazyObject
from django.shortcuts import render
from django.conf import settings
from django.core.cache import cache

from pgweb.util.seo import page_metadata
from pgweb.wiki.columns import nav_items as wiki_nav_items


TOPBAR_CACHE_KEY = 'pgweb:topbar-news'
_CACHE_MISS = object()

THIRD_PARTY_DOCS = [
    {
        'title': 'Patroni',
        'link': 'https://pigsty.cc/docs/patroni',
        'description': 'PostgreSQL 高可用管理工具，支持集群管理、主从切换与故障恢复。',
    },
    {
        'title': 'PgBouncer',
        'link': 'https://pigsty.cc/docs/pgbouncer',
        'description': '轻量级 PostgreSQL 连接池，通过复用连接降低连接开销。',
    },
    {
        'title': 'pgBackRest',
        'link': 'https://pigsty.cc/docs/pgbackrest',
        'description': 'PostgreSQL 备份与恢复工具，提供备份管理、WAL 归档与恢复功能。',
    },
    {
        'title': 'pg_exporter',
        'link': 'https://pigsty.cc/docs/pg_exporter',
        'description': '采集 PostgreSQL 监控指标，供 Prometheus 抓取并用于监控与告警。',
    },
    {
        'title': 'Pigsty',
        'link': 'https://pigsty.cc/docs',
        'description': '开源 PostgreSQL 发行版，提供部署、监控、高可用、备份恢复与扩展管理。',
    },
    {
        'title': 'pig',
        'link': 'https://pigsty.cc/docs/pig',
        'description': 'PostgreSQL 命令行工具，用于安装和管理 PostgreSQL 内核与扩展。',
    },
    {
        'title': 'PostGIS',
        'link': 'https://postgis.net/docs/manual-dev/zh_Hans/',
        'description': '为 PostgreSQL 提供几何与地理类型、空间索引和空间分析能力。',
    },
    {
        'title': 'TimescaleDB',
        'link': 'https://docs.timescaledb.cn/',
        'description': '面向时序数据的 PostgreSQL 扩展，提供超表、连续聚合与数据压缩等功能。',
    },
    {
        'title': 'Citus',
        'link': 'https://learn.microsoft.com/zh-cn/postgresql/citus/?view=citus-14',
        'description': '将 PostgreSQL 扩展为分布式数据库，支持在多个节点间分发数据与查询。',
    },
]

# This is the whole site navigation structure. Stick in a smarter file?
sitenav = {
    # 静态兜底；模板拿到的是 _get_sitenav() 里带最近七天日期的版本。
    'info': [
        {'title': '新闻博览', 'link': '/info/', 'keep': True},
        {'title': 'PG 日报', 'link': '/info/daily/', 'submenu': [{'title': '日报归档', 'link': '/info/archive/'}]},
        {'title': '社区新闻', 'link': '/about/newsarchive/'},
        {'title': '近期活动', 'link': '/about/events/'},
    ],
    'about': [
        {'title': '关于', 'link': '/about/'},
        {'title': '项目治理', 'link': '/about/governance/'},
        {'title': '政策', 'link': '/about/policies/'},
        {'title': '特性矩阵', 'link': '/about/featurematrix/'},
        {'title': '捐赠', 'link': '/about/donate/'},
        {'title': '历史', 'link': '/docs/current/history.html'},
        {'title': '赞助者', 'link': '/about/sponsors/', 'submenu': [
            {'title': '贡献赞助', 'link': '/about/contributing/'},
            {'title': '财务赞助', 'link': '/about/financial/'},
            {'title': '服务器赞助', 'link': '/about/servers/'},
        ]},
        {'title': '最新动态', 'link': '/about/newsarchive/'},
        {'title': '近期活动', 'link': '/about/events/', 'submenu': [
            {'title': '往期活动', 'link': '/about/eventarchive/'},
        ]},
        {'title': '媒体资料', 'link': '/about/press/'},
        {'title': '许可证', 'link': '/about/licence/'},
        {'title': '关于 pgsql.cc', 'link': '/about/pgsql/'},
    ],
    'download': [
        {'title': '下载', 'link': '/download/', 'submenu': [
            {'title': '安装包', 'link': '/download/'},
            {'title': '源代码', 'link': 'https://www.postgresql.org/ftp/source/'}
        ]},
        {'title': '软件目录', 'link': '/download/product-categories/'},
        {'title': '扩展目录', 'link': '/ext/'},
        {'title': '浏览文件', 'link': 'https://www.postgresql.org/ftp/'},
    ],
    'docs': [
        {'title': '文档', 'link': '/docs/'},
        {'title': '手册', 'link': '/docs/', 'submenu': [
            {'title': '归档', 'link': '/docs/manuals/archive/'},
        ]},
        {'title': '发行说明', 'link': '/docs/release/'},
        {'title': '书籍', 'link': '/docs/books/'},
        {'title': '其他', 'link': '/docs/online-resources/'},
        {'title': 'FAQ', 'link': '/docs/faq/'},
        {'title': 'PostgreSQL Wiki', 'link': 'https://wiki.postgresql.org'},
        {'title': '三方文档', 'link': '/docs/third-party/', 'id': 'ecosystem-docs'},
    ] + wiki_nav_items(),
    'community': [
        {'title': '社区', 'link': '/community/'},
        {'title': '贡献者', 'link': '/community/contributors/'},
        {'title': '邮件列表', 'link': 'https://www.postgresql.org/list/'},
        {'title': 'IRC', 'link': '/community/irc/'},
        # {'title': 'Slack', 'link': 'https://join.slack.com/t/postgresteam/shared_invite/zt-1qj14i9sj-E9WqIFlvcOiHsEk2yFEMjA'},
        {'title': '本地用户组', 'link': '/community/user-groups/'},
        {'title': '认可的非营利组织', 'link': '/community/recognised-npos/'},
        {'title': '活动', 'link': '/about/events/'},
        {'title': '国际化站点', 'link': '/community/international/'},
    ],
    'developer': [
        {'title': '开发者', 'link': '/developer/'},
        {'title': '核心团队', 'link': '/developer/core/'},
        {'title': '提交者', 'link': '/developer/committers/'},
        {'title': '路线图', 'link': '/developer/roadmap/'},
        {'title': '编码', 'link': '/developer/coding/'},
        {'title': 'CommitFest', 'link': 'https://commitfest.postgresql.org'},
        {'title': '测试', 'link': '/developer/testing/', 'submenu': [
            {'title': 'Beta 版信息', 'link': '/developer/beta/'},
        ]},
        {'title': '邮件列表', 'link': 'https://www.postgresql.org/list/'},
        {'title': '开发者 FAQ', 'link': 'https://wiki.postgresql.org/wiki/Developer_FAQ'},
        {'title': '相关项目', 'link': '/developer/related-projects/'},
        {'title': '消息翻译', 'link': '/nls/'},
    ],
    'support': [
        {'title': '支持', 'link': '/support/'},
        {'title': '版本策略', 'link': '/support/versioning/'},
        {'title': '安全信息', 'link': '/support/security/'},
        {'title': '专业服务', 'link': '/support/professional_support/'},
        {'title': '托管方案', 'link': '/support/professional_hosting/'},
        {'title': '报告 Bug', 'link': 'https://www.postgresql.org/account/submitbug/'},
    ],
    'account': [
        {'title': '您的账户', 'link': '/account/'},
        {'title': '个人档案', 'link': '/account/profile/'},
        {'title': '邮件列表订阅', 'link': 'https://lists.postgresql.org/manage/'},
        {'title': '已提交的数据', 'link': '/account/', 'submenu': [
            {'title': '新闻文章', 'link': '/account/edit/news/'},
            {'title': '活动', 'link': '/account/edit/events/'},
            {'title': '产品', 'link': '/account/edit/products/'},
            {'title': '专业服务', 'link': '/account/edit/services/'},
            {'title': '组织', 'link': '/account/edit/organisations/'},
        ]},
        {'title': '修改密码', 'link': '/account/changepwd/'},
        {'title': '退出登录', 'link': '/account/logout/'},
    ],
}


def get_nav_menu(section):
    # Views replace submenu entries without changing the global navigation.
    return [item.copy() for item in sitenav.get(section, ())]


def render_pgweb(request, section, template, context):
    context['navmenu'] = get_nav_menu(section)
    return render(request, template, context)


def _media_stamp():
    # Development only: HEAD does not move while files are being edited, so
    # the newest mtime under media/css and media/js is appended to the
    # cache-busting revision. Costs one directory walk per request.
    import os
    latest = 0
    for folder in ('media/css', 'media/js'):
        for root, _dirs, files in os.walk(folder):
            for name in files:
                try:
                    latest = max(latest, int(os.stat(os.path.join(root, name)).st_mtime))
                except OSError:
                    pass
    return str(latest)


def _get_gitrev():
    # Return the current git revision, that is used for
    # cache-busting URLs. Resolve HEAD's branch (main on pgsql.cc,
    # master upstream) so a deploy always busts the CSS/JS caches.
    rev = _git_head()
    return rev + '-' + _media_stamp() if settings.DEBUG else rev


def _git_head():
    def _read(path):
        with open(path) as f:
            return f.readline().strip()

    try:
        head = _read('.git/HEAD')
        ref = head[5:] if head.startswith('ref: ') else None
        if ref is None:
            # Detached HEAD: the line is the sha itself
            return head[:8]
        try:
            return _read('.git/' + ref)[:8]
        except IOError:
            # A "git gc" will remove the ref and replace it with a packed-refs.
            with open('.git/packed-refs') as f:
                for l in f.readlines():
                    if l.endswith(" %s\n" % ref):
                        return l[:8]
            # Not found in packed-refs. Meh, just make one up.
            return 'ffffffff'
    except IOError:
        # If git metadata can't be read, just give up
        return 'eeeeeeee'


# Template context processor to add information about the root link and
# the current git revision. git revision is returned as a lazy object so
# we don't spend effort trying to load it if we don't need it (though
# all general pages will need it since it's used to render the css urls)
#
def _get_topbar_news():
    from pgweb.news.models import PinnedNewsArticle

    cached = cache.get(TOPBAR_CACHE_KEY, _CACHE_MISS)
    if cached is not _CACHE_MISS:
        return cached or None

    pinned = (
        PinnedNewsArticle.objects.select_related('pinnedarticle')
        .only('pinnedarticle__id', 'pinnedarticle__date', 'pinnedarticle__title')
        .first()
    )
    article = pinned.pinnedarticle if pinned else None
    result = None
    if article:
        result = {
            'date': article.date,
            'title': article.title,
            'permanenturl': article.permanenturl,
        }
    cache.set(TOPBAR_CACHE_KEY, result or False, settings.TOPBAR_CACHE_SECONDS)
    return result


# Topbar news is lazy so requests that do not render the global header avoid
# the query. pgsql.cc does not use ESI, so keep a short application cache as
# well instead of querying PinnedNewsArticle for every page.
DOC_MAJORS_CACHE_KEY = 'pgweb:doc-majors'


def _get_doc_majors():
    # Supported major versions, newest first, for the "文档" menu.
    majors = cache.get(DOC_MAJORS_CACHE_KEY)
    if majors is None:
        from pgweb.core.models import Version
        majors = [int(v.tree) for v in Version.objects.filter(supported=True, tree__gt=0).order_by('-tree')]
        cache.set(DOC_MAJORS_CACHE_KEY, majors, 600)
    return majors


# 本站独有的栏目，上游没有对应页面。给它们拼一个 postgresql.org 地址只会得到 404。
LOCAL_ONLY_SECTIONS = ('/docs/sqlstate/', '/docs/catalog/', '/info/', '/ext/', '/e/', '/nls/')


def _source_url(path):
    if path.startswith(LOCAL_ONLY_SECTIONS):
        return ''
    return 'https://www.postgresql.org' + path


def _get_sitenav():
    """The navigation with the 博览 entry's recent days filled in (cached briefly)."""
    from pgweb.info.highlights import info_nav
    return dict(sitenav, info=info_nav())


def PGWebContextProcessor(request):
    gitrev = SimpleLazyObject(_get_gitrev)
    return {
        'link_root': settings.SITE_ROOT.rstrip('/'),
        'do_esi': settings.DO_ESI,
        'gitrev': gitrev,
        'topbarnews': SimpleLazyObject(_get_topbar_news),
        'sitenav': SimpleLazyObject(_get_sitenav),
        'doc_majors': SimpleLazyObject(_get_doc_majors),
        'site_search': bool(getattr(settings, 'SEARCH_DSN', '')),
        'seo': page_metadata(request.path),
        'source_url': _source_url(request.path),
        'source_label': '前往 postgresql.org 对应页面',
    }
