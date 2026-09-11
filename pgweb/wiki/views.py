import re

from django.http import Http404, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.views.decorators.http import require_safe

from pgweb.util.contexts import get_nav_menu

from . import errcode
from .columns import BY_SLUG
from .models import ErrorCode


SQLSTATE = re.compile(r'^[0-9A-Za-z]{5}$')


def shell(ctx, title, description, canonical, class_code=''):
    """The shared page context: the 文档 side navigation and SEO fields."""
    menu = get_nav_menu('docs')
    for item in menu:
        if item.get('link') == '/docs/errcode/':
            item['active'] = True
    ctx['navmenu'] = menu
    ctx['title'] = title
    ctx['seo'] = {'title': title if title.startswith('PostgreSQL ') else title + ' · PostgreSQL',
                  'description': description, 'canonical': canonical, 'lang': 'zh'}
    return ctx


@require_safe
def errcode_index(request):
    column = BY_SLUG['errcode']
    payload = errcode.index()
    description = 'PostgreSQL 全部 {} 个 SQLSTATE 错误代码的中文索引，按 {} 个类别分组，' \
                  '每条给出条件名、宏名称、严重等级、起始版本与状态。'.format(
                      payload['total'], payload['class_count'])
    return render(request, 'wiki/errcode_index.html', shell(dict(
        payload, column=column,
    ), 'PostgreSQL 错误代码', description, '/docs/errcode/'))


@require_safe
def errcode_detail(request, sqlstate):
    if not SQLSTATE.match(sqlstate):
        raise Http404()
    # 站内规范形式是大写：PostgreSQL 报错里输出的就是大写。
    if sqlstate != sqlstate.upper():
        return HttpResponsePermanentRedirect('/docs/errcode/{}/'.format(sqlstate.upper()))
    try:
        payload = errcode.detail_payload(sqlstate, request.GET.get('v', ''))
    except ErrorCode.DoesNotExist:
        raise Http404()

    code = payload['code']
    name = payload['name']
    heading = '{} {}'.format(code.sqlstate, code.condition_name).strip()
    title = '{}{} · 错误代码'.format(heading, '（{}）'.format(name) if name else '')
    text = payload['text']
    description = (text.summary or text.description) if text else heading
    return render(request, 'wiki/errcode_detail.html', shell(dict(
        payload, column=BY_SLUG['errcode'], heading=heading,
    ), title, description, code.url, class_code=code.klass_id))
