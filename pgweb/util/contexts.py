from django.utils.functional import SimpleLazyObject
from django.shortcuts import render
from django.conf import settings

# This is the whole site navigation structure. Stick in a smarter file?
sitenav = {
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
        {'title': '新闻', 'link': '/about/press/'},
        {'title': '许可证', 'link': '/about/licence/'},
    ],
    'download': [
        {'title': '下载', 'link': '/download/', 'submenu': [
            {'title': '安装包', 'link': '/download/'},
            {'title': '源代码', 'link': 'https://www.postgresql.org/ftp/source/'}
        ]},
        {'title': '软件目录', 'link': '/download/product-categories/'},
        {'title': '扩展目录', 'link': 'https://pigsty.cc/ext'},
        {'title': '文件浏览器', 'link': 'https://www.postgresql.org/ftp/'},
    ],
    'docs': [
        {'title': '文档', 'link': '/docs/'},
        {'title': '手册', 'link': '/docs/', 'submenu': [
            {'title': '手册归档', 'link': '/docs/manuals/archive/'},
        ]},
        {'title': '发布说明', 'link': '/docs/release/'},
        {'title': '书籍', 'link': '/docs/books/'},
        {'title': '教程与其他资源', 'link': '/docs/online-resources/'},
        {'title': 'FAQ', 'link': '/docs/faq/'},
        {'title': 'Wiki', 'link': 'https://wiki.postgresql.org'},
        {'title': '三方文档', 'link': 'https://pigsty.cc' , 'submenu': [
            {'title': 'pigsty 文档', 'link': 'https://pigsty.cc/docs/'},
            {'title': 'pig cli 文档', 'link': 'https://pigsty.cc/docs/pig'},
            {'title': 'pg 扩展文档', 'link': 'https://pigsty.cc/ext/e/'},
            {'title': 'patroni 文档', 'link': 'https://pigsty.cc/docs/patroni/'},
            {'title': 'pgbouncer 文档', 'link': 'https://pigsty.cc/docs/pgbouncer/'},
            {'title': 'pgbackrest 文档', 'link': 'https://pigsty.cc/docs/pgbackrest/'},
            {'title': 'pg_exporter 文档', 'link': 'https://pigsty.cc/docs/pg_exporter/'},
        ]},
    ],
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
        {'title': '提交清单', 'link': 'https://commitfest.postgresql.org'},
        {'title': '测试', 'link': '/developer/testing/', 'submenu': [
            {'title': 'Beta 版信息', 'link': '/developer/beta/'},
        ]},
        {'title': '邮件列表', 'link': 'https://www.postgresql.org/list/'},
        {'title': '开发者 FAQ', 'link': 'https://wiki.postgresql.org/wiki/Developer_FAQ'},
        {'title': '相关项目', 'link': '/developer/related-projects/'},
    ],
    'support': [
        {'title': '支持', 'link': '/support/'},
        {'title': '版本策略', 'link': '/support/versioning/'},
        {'title': '安全', 'link': '/support/security/'},
        {'title': '专业服务', 'link': '/support/professional_support/'},
        {'title': '托管方案', 'link': '/support/professional_hosting/'},
        {'title': '报告 Bug', 'link': '/account/submitbug/'},
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
    if section in sitenav:
        return sitenav[section]
    else:
        return {}


def render_pgweb(request, section, template, context):
    context['navmenu'] = get_nav_menu(section)
    return render(request, template, context)


def _get_gitrev():
    # Return the current git revision, that is used for
    # cache-busting URLs.
    try:
        with open('.git/refs/heads/master') as f:
            return f.readline()[:8]
    except IOError:
        # A "git gc" will remove the ref and replace it with a packed-refs.
        try:
            with open('.git/packed-refs') as f:
                for l in f.readlines():
                    if l.endswith("refs/heads/master\n"):
                        return l[:8]
                # Not found in packed-refs. Meh, just make one up.
                return 'ffffffff'
        except IOError:
            # If packed-refs also can't be read, just give up
            return 'eeeeeeee'


# Template context processor to add information about the root link and
# the current git revision. git revision is returned as a lazy object so
# we don't spend effort trying to load it if we don't need it (though
# all general pages will need it since it's used to render the css urls)
def PGWebContextProcessor(request):
    gitrev = SimpleLazyObject(_get_gitrev)
    return {
        'link_root': settings.SITE_ROOT.rstrip('/'),
        'do_esi': settings.DO_ESI,
        'gitrev': gitrev,
    }
