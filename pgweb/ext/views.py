from collections import Counter
from urllib.parse import quote

from django.core.paginator import Paginator
from django.http import Http404, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.views.decorators.http import require_safe
from pgweb.util.decorators import queryparams
from pgweb.util.contexts import get_nav_menu

from .catalog import (CATEGORIES, DIMENSIONS, LEGACY_DIMENSIONS, PAGE_SIZE, PGEXT, QUERY_PARAMS,
                      browse_url, catalog, category_color, category_label, detail_url,
                      facets, present, safe_url, value_label)


LABELS = {
    'catalog': '扩展目录',
    'requires': '依赖扩展',
    'required_by': '被依赖',
    'see_also': '参见',
    'family': '同项目扩展',
    'version': '版本',
    'package': '扩展包',
    'compatibility': 'PostgreSQL 版本',
    'kind': '扩展形态',
    'lifecycle': '上游状态',
    'kernel': '适用内核',
    'vendor': '厂商',
    'need_ddl': '需要 CREATE EXTENSION',
    'need_load': '需要预加载',
    'trusted': '可信扩展',
    'relocatable': '可迁移',
    'libs': '共享库',
    'schemas': 'Schema',
    'maintained': '目录更新',
    'stars': '星标',
    'last_commit': '最近提交',
    'last_release': '最近发布',
    'source': '源码仓库',
    'home': '项目主页',
    'docs': '官方文档',
    'license_text': '许可证原文',
    'control': 'Control 文件',
    'pgxn': 'PGXN',
    'pgext_page': 'pgext.cloud',
    'yes': '是',
    'no': '否',
    'repo': '仓库来源',
}
PROPERTY_LABELS = {'kind': {'standard': '标准扩展', 'preload': '预加载扩展', 'puresql': '纯 SQL', 'headless': '无 DDL 扩展'}, 'lifecycle': {'active': '活跃', 'abandoned': '停止维护', 'archived': '已归档', 'deprecated': '已弃用', 'preview': '预览'}}


def context(rows, selected=None, query=''):
    selected = selected or {}
    categories = [{'code': code, 'label': category_label(code),
                   'url': browse_url(filters={**selected, 'category': code}, q=query),
                   'active': selected.get('category') == code} for code in CATEGORIES]
    all_url = browse_url(filters={**selected, 'category': ''}, q=query)
    navmenu = get_nav_menu('download')
    for item in navmenu:
        if item['link'] == '/ext/':
            item.update(link=all_url, active=not selected.get('category'),
                        submenu=[{'title': category['label'], 'link': category['url'],
                                  'active': category['active']} for category in categories])
    return {
        'total': len(rows),
        'source_url': PGEXT + '/', 'source_label': 'PGEXT.CLOUD',
        'sidebar_categories': categories, 'navmenu': navmenu,
        'selected': selected,
    }


def seo(ctx, title, description, canonical, noindex=False):
    ctx['title'] = title
    ctx['noindex'] = noindex
    ctx['seo'] = {'title': title if title.startswith('PostgreSQL ') else title + ' · PostgreSQL', 'description': description,
                  'canonical': canonical, 'lang': 'zh'}


def universe(rows):
    columns, pitch = 120, 8
    ordered = sorted(rows, key=lambda row: (list(CATEGORIES).index(row['category']) if row['category'] in CATEGORIES else 99,
                                           -(row['stars'] or 0), row['name']))
    cells = [{'x': (index % columns) * pitch, 'y': (index // columns) * pitch,
              'name': row['name'], 'color': category_color(row['category']),
              'packaged': row.get('packaged'), 'url': detail_url(row['name']),
              'category': category_label(row['category']),
              'description': row.get('zh_desc') or '暂无中文简介',
              'metadata': ' · '.join(filter(None, (row.get('version'), category_label(row['category']),
                                                  row.get('license'), row.get('lang'),
                                                  '已打包' if row.get('packaged') else '未打包')))}
             for index, row in enumerate(ordered)]
    return {'cells': cells, 'width': columns * pitch, 'height': max(pitch, ((len(cells) + columns - 1) // columns) * pitch)}


def selection(request):
    selected = {key: request.GET.get(spec['param'], '').strip()[:100] for key, spec in DIMENSIONS.items()}
    selected['category'] = selected['category'].upper()
    if not selected['repo']:
        selected['repo'] = request.GET.get('repository', '').strip()[:100]
    return selected


@require_safe
@queryparams(*QUERY_PARAMS)
def browse(request):
    rows = catalog()
    selected = selection(request)
    query = request.GET.get('q', '').strip()[:255]
    if any(key in request.GET for key in ('lang', 'sort', 'view', 'repository')):
        return HttpResponsePermanentRedirect(browse_url(filters=selected, q=query, page=request.GET.get('page')))
    words = query.casefold().split()
    ctx = context(rows, selected, query)

    def matches(row, skip=None):
        return (all(not value or key == skip or row[DIMENSIONS[key]['field']] == value for key, value in selected.items())
                and all(word in row['search_text'] for word in words))

    results = sorted((row for row in rows if matches(row)), key=lambda row: (-(row['stars'] or 0), row['name']))
    if words:
        needle = query.casefold()
        results.sort(key=lambda row: (row['name'].casefold() != needle, not row['name'].casefold().startswith(needle)))
    pager = Paginator(results, PAGE_SIZE)
    page = pager.get_page(request.GET.get('page'))
    dropdowns = []
    options_by_dimension = facets(rows)
    for key, spec in DIMENSIONS.items():
        counts = Counter(row[spec['field']] for row in rows if matches(row, skip=key))
        options = [{**item, 'count': counts[item['value']], 'current': selected[key] == item['value']}
                   for item in options_by_dimension[key]]
        if selected[key] and all(item['value'] != selected[key] for item in options):
            options.append({'value': selected[key], 'label': value_label(key, selected[key]), 'count': 0, 'current': True})
        dropdowns.append({'key': key, 'param': spec['param'], 'label': spec['label'], 'options': options, 'value': selected[key]})
    ctx.update({
        'query': query, 'rows': [present(row) for row in page], 'page': page, 'dropdowns': dropdowns,
        'universe': universe(results), 'result_count': pager.count, 'filtered': bool(query or any(selected.values())),
        'pagination': [{'label': number, 'current': number == page.number,
                        'url': browse_url(filters=selected, q=query, page=number) if isinstance(number, int) else ''}
                       for number in pager.get_elided_page_range(page.number, on_each_side=1, on_ends=1)],
        'previous_url': browse_url(filters=selected, q=query, page=page.previous_page_number()) if page.has_previous() else '',
        'next_url': browse_url(filters=selected, q=query, page=page.next_page_number()) if page.has_next() else '',
    })
    description = '以下数据来自 pgext.cloud，这是一个由 Pigsty 维护的 PG 扩展目录，收纳了 {} 个扩展插件。'.format(len(rows))
    seo(ctx, 'PostgreSQL 扩展目录', description, browse_url(filters=selected, q=query, page=page.number), noindex=bool(query or any(selected.values())))
    return render(request, 'ext/browse.html', ctx)


@require_safe
@queryparams(*QUERY_PARAMS)
def index(request):
    return HttpResponsePermanentRedirect(browse_url(filters=selection(request), q=request.GET.get('q', '')))


@require_safe
@queryparams(*QUERY_PARAMS)
def section(request, segment):
    key = LEGACY_DIMENSIONS.get(segment, segment)
    if key in DIMENSIONS:
        return index(request)
    code = segment.upper()
    if code in CATEGORIES:
        return HttpResponsePermanentRedirect(browse_url(filters={**selection(request), 'category': code}, q=request.GET.get('q', '')))
    if any(row['name'] == segment for row in catalog()):
        return HttpResponsePermanentRedirect(detail_url(segment))
    raise Http404('Unknown catalogue section')


@require_safe
@queryparams(*QUERY_PARAMS)
def value(request, dimension, value):
    key = LEGACY_DIMENSIONS.get(dimension, dimension)
    if key not in DIMENSIONS:
        raise Http404('Unknown extension filter')
    known = list(CATEGORIES) if key == 'category' else {row[DIMENSIONS[key]['field']] for row in catalog()}
    match = next((item for item in known if item.casefold() == value.casefold()), None)
    if match is None:
        raise Http404('Unknown value')
    return HttpResponsePermanentRedirect(browse_url(filters={**selection(request), key: match}, q=request.GET.get('q', '')))


@require_safe
@queryparams(*QUERY_PARAMS)
def legacy_index(request, dimension):
    if LEGACY_DIMENSIONS.get(dimension, dimension) not in DIMENSIONS:
        raise Http404('Unknown extension index')
    return index(request)


@require_safe
@queryparams('lang')
def detail(request, name):
    rows = catalog()
    by_name = {row['name']: row for row in rows}
    if name not in by_name:
        raise Http404('Extension not found')
    if 'lang' in request.GET:
        return HttpResponsePermanentRedirect(detail_url(name))
    ctx = context(rows, {'category': by_name[name]['category']})
    row = by_name[name]
    extension = present(row)
    labels = LABELS
    pgext_url = PGEXT + '/e/' + quote(name, safe='')
    links = [{'label': labels['pgext_page'], 'url': pgext_url}]
    for field, label in (('repo_url', labels['source']), ('home_url', labels['home']), ('doc_url', labels['docs']),
                         ('license_url', labels['license_text']), ('control_url', labels['control']), ('pgxn_url', labels['pgxn'])):
        target = safe_url(row.get(field))
        if target and target not in [link['url'] for link in links]:
            links.append({'label': label, 'url': target})
    if len(links) == 1 and extension['upstream'] and extension['upstream'] != pgext_url:
        links.append({'label': labels['source'], 'url': extension['upstream']})

    def yes_no(flag):
        return labels['yes'] if flag else labels['no']
    overview = [(labels['package'], row['pkg'], browse_url(q=row['pkg']) if row['pkg'] != name else '')]
    overview.append((labels['version'], row.get('version') or '—', ''))
    if row.get('pg_ver'):
        overview.append((labels['compatibility'], ' · '.join(str(v) for v in row['pg_ver']), ''))
    overview.append((labels['repo'], extension['repository_label'], extension['repository_href']))
    for field in ('kind', 'lifecycle'):
        if row.get(field):
            overview.append((labels[field], PROPERTY_LABELS[field].get(row[field], row[field]), ''))
    for field in ('kernel', 'vendor'):
        if row.get(field):
            overview.append((labels[field], row[field], ''))
    for field in ('need_ddl', 'need_load', 'trusted', 'relocatable'):
        if row.get(field) is not None:
            overview.append((labels[field], yes_no(row[field]), ''))
    for field in ('libs', 'schemas'):
        if row.get(field):
            overview.append((labels[field], ', '.join(row[field]), ''))
    if row.get('stars') is not None:
        overview.append((labels['stars'], format(row['stars'], ','), extension['upstream']))
    for field in ('last_commit', 'last_release'):
        if row.get(field):
            overview.append((labels[field], row[field].strftime('%Y-%m-%d'), ''))
    if row.get('mtime'):
        overview.append((labels['maintained'], row['mtime'].strftime('%Y-%m-%d'), ''))

    relationships = []
    for field in ('requires', 'required_by', 'see_also'):
        members = [present(by_name[n]) for n in row.get(field) or [] if n in by_name and n != name]
        if members:
            relationships.append({'key': field, 'label': labels[field], 'members': members})
    family = [present(member) for member in rows if member['pkg'] == row['pkg'] and member['name'] != name]
    if family:
        relationships.append({'key': 'family', 'label': labels['family'], 'members': family})

    ctx.update({
        'extension': extension,
        'links': links, 'overview': [{'label': l, 'value': v, 'url': u} for l, v, u in overview],
        'relationships': relationships,
        'source_url': pgext_url, 'breadcrumb_category': browse_url({'category': row['category']}),
    })
    seo(ctx, '{} · {}'.format(name, labels['catalog']), extension['description'], canonical=detail_url(name))
    return render(request, 'ext/detail.html', ctx)


@require_safe
def detail_root(request):
    return HttpResponsePermanentRedirect('/ext/')


@require_safe
def sitemap(request):
    paths = ['/ext/'] + [detail_url(row['name']) for row in catalog()]
    return render(request, 'ext/sitemap.xml', {'paths': paths}, content_type='application/xml')
