import re

from django.http import Http404, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.views.decorators.http import require_safe

from pgweb.util.contexts import get_nav_menu

from . import errcode
from .columns import BY_SLUG, listing
from .models import ErrorCode


TITLE = 'PostgreSQL 百科'
DESCRIPTION = '逐条查得到、每条有出处的 PostgreSQL 参考资料：错误码、配置参数、等待事件与系统目录。'

SQLSTATE = re.compile(r'^[0-9A-Za-z]{5}$')


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


@require_safe
def errcode_index(request):
    column = BY_SLUG['errcode']
    payload = errcode.index()
    description = 'PostgreSQL 全部 {} 个 SQLSTATE 错误码的中文索引，按 {} 个类别分组，' \
                  '每条给出条件名、宏名称、严重等级与启用、弃用版本。'.format(
                      payload['total'], payload['class_count'])
    return render(request, 'wiki/errcode_index.html', shell(dict(
        payload, column=column,
    ), 'PostgreSQL 错误码大全', description, '/wiki/errcode/'))


@require_safe
def errcode_detail(request, sqlstate):
    if not SQLSTATE.match(sqlstate):
        raise Http404()
    # 站内规范形式是大写：PostgreSQL 报错里输出的就是大写。
    if sqlstate != sqlstate.upper():
        return HttpResponsePermanentRedirect('/wiki/errcode/{}/'.format(sqlstate.upper()))
    try:
        payload = errcode.detail_payload(sqlstate, request.GET.get('v', ''))
    except ErrorCode.DoesNotExist:
        raise Http404()

    code = payload['code']
    name = payload['name']
    heading = '{} {}'.format(code.sqlstate, code.condition_name).strip()
    title = '{}{} · 错误码'.format(heading, '（{}）'.format(name) if name else '')
    text = payload['text']
    description = (text.summary or text.description) if text else heading
    return render(request, 'wiki/errcode_detail.html', shell(dict(
        payload, column=BY_SLUG['errcode'], heading=heading,
    ), title, description, code.url))
