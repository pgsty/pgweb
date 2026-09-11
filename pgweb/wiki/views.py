import re
from urllib.parse import quote

from django.http import Http404, HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_safe

from pgweb.util.contexts import get_nav_menu
from pgweb.util.decorators import queryparams

from . import catalog, errcode, guc
from .columns import BY_SLUG
from .models import CatalogRelation, CatalogVersion, ErrorCode, GucParameter, GucVersion


SQLSTATE = re.compile(r'^[0-9A-Za-z]{5}$')
RELATION = re.compile(r'^pg_[a-z0-9_]+$')
GUC_NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
CATALOG_ROOT = '/docs/catalog/'
GUC_ROOT = '/docs/guc/'


def shell(ctx, title, description, canonical, class_code='', section='/docs/sqlstate/'):
    """The shared page context: the 文档 side navigation and SEO fields."""
    menu = get_nav_menu('docs')
    for item in menu:
        if item.get('link') == section:
            item['active'] = True
    ctx['navmenu'] = menu
    ctx['title'] = title
    ctx['seo'] = {'title': title if title.startswith('PostgreSQL ') else title + ' · PostgreSQL',
                  'description': description, 'canonical': canonical, 'lang': 'zh'}
    return ctx


@require_safe
def errcode_index(request):
    column = BY_SLUG['sqlstate']
    payload = errcode.index()
    description = 'PostgreSQL 全部 {} 个 SQL 状态码（SQLSTATE）的中文索引，按 {} 个类别分组，' \
                  '每条给出条件名、宏名称、严重等级、起始版本与状态。'.format(
                      payload['total'], payload['class_count'])
    return render(request, 'wiki/errcode_index.html', shell(dict(
        payload, column=column,
    ), 'PostgreSQL 状态码', description, '/docs/sqlstate/'))


@require_safe
@queryparams('v')
def errcode_detail(request, sqlstate):
    if not SQLSTATE.match(sqlstate):
        raise Http404()
    # 站内规范形式是大写：PostgreSQL 报错里输出的就是大写。
    if sqlstate != sqlstate.upper():
        return HttpResponsePermanentRedirect('/docs/sqlstate/{}/'.format(sqlstate.upper()))
    try:
        payload = errcode.detail_payload(sqlstate, request.GET.get('v', ''))
    except ErrorCode.DoesNotExist:
        raise Http404()

    code = payload['code']
    name = payload['name']
    heading = '{} {}'.format(code.sqlstate, code.condition_name).strip()
    title = '{}{} · SQL 状态码'.format(heading, '（{}）'.format(name) if name else '')
    text = payload['text']
    description = (text.summary or text.description) if text else heading
    return render(request, 'wiki/errcode_detail.html', shell(dict(
        payload, column=BY_SLUG['sqlstate'], heading=heading,
    ), title, description, code.url, class_code=code.klass_id))


# ---------------------------------------------------------------- 系统目录

@require_safe
# 筛选在当前页即时过滤，参数写进 URL；中间件只放行这几个。
@queryparams('q', 'kind', 'present', 'first')
def catalog_index(request):
    column = BY_SLUG['catalog']
    payload = catalog.index()
    description = ('PostgreSQL 系统目录表、系统视图、统计视图与进度视图的中文字段百科，'
                   '共 {} 个关系，覆盖 {} 至 {}，逐字段给出类型、说明与跨大版本的结构变化。'.format(
                       payload['total'], payload['earliest_major'], payload['latest_major']))
    return render(request, 'wiki/catalog_index.html', shell(dict(
        payload, column=column,
    ), 'PostgreSQL 系统目录', description, CATALOG_ROOT, section=CATALOG_ROOT))


@require_safe
@queryparams('v')
def catalog_detail(request, name):
    if not RELATION.match(name):
        raise Http404()
    try:
        payload = catalog.detail(name, request.GET.get('v', ''))
    except CatalogRelation.DoesNotExist:
        raise Http404()

    relation = payload['relation']
    major = payload['version']['major'] if payload['version'] else ''
    title = '{} · {}'.format(relation.name, payload['kind_label'])
    description = '{} 是 PostgreSQL {}。{}'.format(
        relation.name, payload['kind_label'],
        payload['description_zh'] or relation.summary_zh or relation.summary or '')
    return render(request, 'wiki/catalog_detail.html', shell(dict(
        payload, column=BY_SLUG['catalog'], heading=relation.name, major=major,
    ), title, ' '.join(description.split())[:200], relation.url, section=CATALOG_ROOT))


@require_safe
def catalog_changes_root(request):
    # 默认落在当前稳定版，不落在预发行或开发版。
    return HttpResponseRedirect('/docs/catalog/changes/{}/'.format(catalog.default_major()))


@require_safe
@queryparams('from')
def catalog_changes(request, major):
    try:
        payload = catalog.changes(major, request.GET.get('from', ''))
    except CatalogVersion.DoesNotExist:
        raise Http404()
    label = payload['version']['label']
    title = 'PostgreSQL {} 系统目录变更'.format(label)
    summary = payload['summary']
    description = ('PostgreSQL {} 相对 {} 的系统目录变更：新增 {} 个关系，移除 {} 个，'
                   '{} 个关系的结构有变化。'.format(
                       label, payload['previous']['label'] if payload['previous'] else '首个收录版本',
                       summary['added_relations'], summary['removed_relations'],
                       summary['structurally_changed']))
    return render(request, 'wiki/catalog_changes.html', shell(dict(
        payload, column=BY_SLUG['catalog'],
    ), title, description, '/docs/catalog/changes/{}/'.format(major), section=CATALOG_ROOT))


# ---------------------------------------------------------------- 配置参数

@require_safe
# 筛选在当前页即时过滤，参数写进 URL；中间件只放行这几个。
@queryparams('q', 'group', 'context', 'first', 'present')
def guc_index(request):
    column = BY_SLUG['guc']
    payload = guc.index()
    description = ('PostgreSQL 配置参数（GUC）的中文百科，共 {} 个参数，按 {} 个一级分类分组，'
                   '覆盖 {} 至 {}，逐版本给出默认值、上下文、取值范围与变化。'.format(
                       payload['total'], payload['group_count'],
                       payload['earliest_major'], payload['latest_major']))
    return render(request, 'wiki/guc_index.html', shell(dict(
        payload, column=column,
    ), 'PostgreSQL 配置参数', description, GUC_ROOT, section=GUC_ROOT))


@require_safe
@queryparams('v')
def guc_detail(request, name):
    if not GUC_NAME.match(name):
        raise Http404()
    try:
        payload = guc.detail(name, request.GET.get('v', ''))
    except GucParameter.DoesNotExist:
        raise Http404()
    if payload['name'] != name:
        # 站内规范形式是 pg_settings 里的大小写：datestyle → DateStyle。
        wanted = request.GET.get('v', '')
        return HttpResponsePermanentRedirect('/docs/guc/{}/{}'.format(
            payload['name'], '?v=' + quote(wanted) if wanted else ''))

    parameter = payload['parameter']
    major = payload['version']['major'] if payload['version'] else ''
    title = '{} · PostgreSQL 配置参数'.format(parameter.name)
    description = '{} 是 PostgreSQL {}配置参数。{}'.format(
        parameter.name, payload['group_label'],
        parameter.short_desc_zh or parameter.short_desc or '')
    return render(request, 'wiki/guc_detail.html', shell(dict(
        payload, column=BY_SLUG['guc'], heading=parameter.name, major=major,
    ), title, ' '.join(description.split())[:200], parameter.url, section=GUC_ROOT))


@require_safe
def guc_changes_root(request):
    # 默认落在当前稳定版，不落在预发行或开发版。
    return HttpResponseRedirect('/docs/guc/changes/{}/'.format(guc.default_major()))


@require_safe
@queryparams('from')
def guc_changes(request, major):
    try:
        payload = guc.changes(major, request.GET.get('from', ''))
    except GucVersion.DoesNotExist:
        raise Http404()
    label = payload['version']['label']
    summary = payload['summary']
    title = 'PostgreSQL {} 配置参数变更'.format(label)
    description = ('PostgreSQL {} 相对 {} 的配置参数变更：新增 {} 个，移除 {} 个，'
                   '{} 个参数的默认值有变化。'.format(
                       label, payload['previous']['label'] if payload['previous'] else '首个收录版本',
                       summary['added'], summary['removed'], summary['default_changed']))
    return render(request, 'wiki/guc_changes.html', shell(dict(
        payload, column=BY_SLUG['guc'],
    ), title, description, '/docs/guc/changes/{}/'.format(major), section=GUC_ROOT))
