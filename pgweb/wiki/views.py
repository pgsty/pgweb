from django.shortcuts import render
from django.views.decorators.http import require_safe

from pgweb.util.contexts import get_nav_menu

from .columns import listing


TITLE = 'PostgreSQL 百科'
DESCRIPTION = '逐条查得到、每条有出处的 PostgreSQL 参考资料：错误码、配置参数、等待事件与系统目录。'


def shell(ctx, title, description, canonical):
    """The shared 百科 page context: side navigation and SEO fields."""
    ctx['navmenu'] = get_nav_menu('wiki')
    ctx['title'] = title
    ctx['seo'] = {'title': title if title.startswith('PostgreSQL ') else title + ' · PostgreSQL',
                  'description': description, 'canonical': canonical, 'lang': 'zh'}
    return ctx


@require_safe
def home(request):
    return render(request, 'wiki/home.html', shell({
        'columns': listing(),
    }, TITLE, DESCRIPTION, '/wiki/'))
