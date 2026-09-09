from collections import Counter
from urllib.parse import quote

from django.core.paginator import Paginator
from django.db import connection
from django.http import Http404, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.views.decorators.http import require_safe
from pgweb.util.decorators import queryparams

from .catalog import (CATEGORIES, DIMENSIONS, LEGACY_DIMENSIONS, PAGE_SIZE, PGEXT, QUERY_PARAMS, SORTS, VIEWS,
                      browse_url, catalog, category_blurb, category_color, category_label, detail_url, dimension_url,
                      facets, localized, present, safe_url, short_number, sql_readout, value_color, value_label, with_lang)
from .markdown import render_document


LABELS = {
    'catalog': ('扩展目录', 'Extension Catalog'), 'all': ('全部扩展', 'All extensions'),
    'indexes': ('索引', 'Indexes'), 'list_all': ('全部索引', 'All indexes'),
    'search': ('搜索', 'Search'), 'sidebar_search': ('搜索扩展…', 'Search extensions…'),
    'categories': ('功能分类', 'Categories'), 'license': ('许可证', 'License'),
    'language': ('编程语言', 'Language'), 'repo': ('仓库来源', 'Repository'),
    'any': ('不限', 'Any'), 'sort': ('排序', 'Sort'),
    'sort_stars': ('星标', 'Stars'), 'sort_name': ('名称', 'Name'), 'sort_recent': ('最近活跃', 'Recently active'),
    'view': ('视图', 'View'), 'view_table': ('表格', 'Table'), 'view_card': ('卡片', 'Cards'),
    'results': ('个匹配扩展', 'matching extensions'), 'active': ('当前筛选', 'Active filters'),
    'clear': ('清除筛选', 'Clear filters'), 'query': ('关键词', 'Query'),
    'empty': ('没有找到匹配的扩展', 'No matching extensions'),
    'empty_help': ('试试更短的关键词，或移除部分筛选条件。', 'Try a shorter query or remove a filter.'),
    'previous': ('上一页', 'Previous'), 'next': ('下一页', 'Next'), 'page': ('页', 'Page'),
    'col_name': ('名称', 'Name'), 'col_version': ('版本', 'Version'), 'col_desc': ('简介', 'Description'),
    'col_category': ('分类', 'Category'), 'col_license': ('许可证', 'License'), 'col_lang': ('语言', 'Language'),
    'col_pg': ('PG 版本', 'PG'), 'col_stars': ('星标', 'Stars'), 'col_count': ('扩展数', 'Extensions'),
    'col_share': ('占比', 'Share'), 'col_examples': ('代表扩展', 'Examples'), 'col_value': ('取值', 'Value'),
    'overview': ('概览', 'Overview'), 'documentation': ('使用文档', 'Documentation'),
    'related': ('相关扩展', 'Related extensions'), 'requires': ('依赖扩展', 'Requires'),
    'required_by': ('被依赖', 'Required by'), 'see_also': ('参见', 'See also'), 'family': ('同项目扩展', 'Same package'),
    'version': ('版本', 'Version'), 'package': ('扩展包', 'Package'), 'compatibility': ('PostgreSQL 版本', 'PostgreSQL versions'),
    'kind': ('扩展形态', 'Kind'), 'lifecycle': ('上游状态', 'Upstream status'), 'kernel': ('适用内核', 'Kernel'),
    'vendor': ('厂商', 'Vendor'), 'need_ddl': ('需要 CREATE EXTENSION', 'Needs CREATE EXTENSION'),
    'need_load': ('需要预加载', 'Needs preload'), 'trusted': ('可信扩展', 'Trusted'), 'relocatable': ('可迁移', 'Relocatable'),
    'libs': ('共享库', 'Libraries'), 'schemas': ('Schema', 'Schemas'), 'maintained': ('目录更新', 'Catalog updated'),
    'stars': ('星标', 'Stars'), 'last_commit': ('最近提交', 'Last commit'), 'last_release': ('最近发布', 'Last release'),
    'links': ('上游链接', 'Upstream links'), 'source': ('源码仓库', 'Source repository'), 'home': ('项目主页', 'Homepage'),
    'docs': ('官方文档', 'Documentation'), 'license_text': ('许可证原文', 'License text'),
    'control': ('Control 文件', 'Control file'), 'pgxn': ('PGXN', 'PGXN'), 'pgext_page': ('pgext.cloud', 'pgext.cloud'),
    'contents': ('本页目录', 'On this page'), 'yes': ('是', 'Yes'), 'no': ('否', 'No'),
    'document_empty': ('尚无使用文档', 'Documentation is not available yet'),
    'doc_fallback': ('当前语言的文档尚未收录，以下显示另一语言版本。',
                     'Documentation in this language is unavailable; the other language is shown below.'),
    'repo_note': ('来源标签由目录记录提供，不代表特定平台的安装包可用性。',
                  'Repository labels describe catalog provenance, not binary availability on a specific platform.'),
    'hero_eyebrow': ('pgext.cloud · PostgreSQL 的一切可能', 'pgext.cloud · everything PostgreSQL can become'),
    'hero_title': ('PostgreSQL 扩展目录', 'PostgreSQL Extension Catalog'),
    'field_note': ('一格一个扩展，颜色即分类；实心为已打包，浅色为仅源码。',
                   'One square per extension, coloured by category; solid squares are packaged, faded ones are source-only.'),
    'index_intro': ('从不同角度浏览扩展生态。点击任意一行，查看该条目下的全部扩展。',
                    'Browse the ecosystem from different angles. Pick a row to list its extensions.'),
    'source_note': ('数据来自 PGEXT 元数据库', 'Data from the PGEXT catalog'),
    'snapshot': ('目录快照', 'Snapshot'), 'bilingual': ('中英文文档', 'Bilingual docs'),
    'packaged': ('已打包', 'Packaged'), 'extensions': ('个扩展', 'extensions'),
    'copy_sql': ('点击复制这条查询', 'Click to copy this query'), 'copied': ('已复制', 'Copied'),
    'skip': ('跳到正文', 'Skip to content'), 'menu': ('目录与筛选', 'Catalog menu'),
}
PROPERTY_LABELS = {
    'kind': {'standard': ('标准扩展', 'Standard'), 'preload': ('预加载扩展', 'Preloaded'),
             'puresql': ('纯 SQL', 'Pure SQL'), 'headless': ('无 DDL 扩展', 'No extension DDL')},
    'lifecycle': {'active': ('活跃', 'Active'), 'abandoned': ('停止维护', 'Abandoned'), 'archived': ('已归档', 'Archived'),
                  'deprecated': ('已弃用', 'Deprecated'), 'preview': ('预览', 'Preview')},
}


def ui_language(request):
    return 'en' if request.GET.get('lang') == 'en' else 'zh'


def intcomma(value):
    return '{:,}'.format(value or 0)


def context(request, rows, language, selected=None, dimension=None):
    """Sidebar, language switch and labels shared by every catalogue page."""
    selected = selected or {}
    all_facets = facets(rows, language)
    params = {key: value for key, value in request.GET.items() if key in QUERY_PARAMS and key != 'lang'}
    labels = {key: localized(value, language) for key, value in LABELS.items()}
    return {
        'language': language, 't': labels, 'facets': all_facets,
        'home_url': browse_url(language), 'list_url': with_lang('/ext/list/', language),
        'total': len(rows), 'total_text': intcomma(len(rows)),
        'packaged': sum(1 for row in rows if row.get('packaged')),
        'bilingual': sum(1 for row in rows if row['has_zh'] and row['has_en']),
        'snapshot': max((row['mtime'] for row in rows if row.get('mtime')), default=None),
        'sidebar_categories': [{**item, 'active': selected.get('category') == item['value']} for item in all_facets['category']],
        'index_links': [{'key': key, 'label': localized(spec['label'], language), 'count': len(all_facets[key]),
                         'url': dimension_url(key, language), 'active': dimension == key} for key, spec in DIMENSIONS.items()],
        'language_zh_url': with_lang(request.path, 'zh', **params),
        'language_en_url': with_lang(request.path, 'en', **params),
        'ext_source_url': PGEXT + '/',
    }


def seo(request, ctx, title, description, canonical=None, noindex=False):
    ctx['title'] = title
    ctx['description'] = description
    ctx['noindex'] = noindex
    ctx['seo'] = {'title': title + ' · PostgreSQL', 'description': description,
                  'canonical': canonical or with_lang(request.path, ctx['language']), 'lang': ctx['language'],
                  'alternates': {'zh': ctx['language_zh_url'], 'en': ctx['language_en_url']}}


def universe(rows, language):
    """One square per extension in a fixed 120-column field, grouped by
    category in canonical order with a one-cell gap between groups."""
    columns, pitch, size = 120, 8, 6
    ordered = sorted(rows, key=lambda row: (list(CATEGORIES).index(row['category']) if row['category'] in CATEGORIES else 99,
                                           -(row['stars'] or 0), row['name']))
    groups, cell, previous = [], 0, None
    for row in ordered:
        if previous is not None and row['category'] != previous:
            groups[-1]['names'] = ' '.join(groups[-1]['names'])
            cell += 1
        if previous != row['category']:
            groups.append({'code': row['category'], 'label': category_label(row['category'], language),
                           'color': category_color(row['category']), 'url': browse_url(language, {'category': row['category']}),
                           'count': 0, 'cells': [], 'names': []})
        groups[-1]['cells'].append({'x': (cell % columns) * pitch, 'y': (cell // columns) * pitch, 'packaged': row.get('packaged')})
        groups[-1]['names'].append(row['name'])
        groups[-1]['count'] += 1
        previous = row['category']
        cell += 1
    if groups and isinstance(groups[-1]['names'], list):
        groups[-1]['names'] = ' '.join(groups[-1]['names'])
    height = ((cell + columns - 1) // columns) * pitch
    return {'groups': groups, 'width': columns * pitch, 'height': max(height, pitch), 'size': size}


def selection(request, fixed):
    selected = {}
    for key, spec in DIMENSIONS.items():
        value = fixed.get(key) or request.GET.get(spec['param'], '')
        if key == 'repo' and not value:
            value = request.GET.get('repository', '')
        selected[key] = value.strip()[:100]
    if selected['category']:
        selected['category'] = selected['category'].upper()
    return selected


@require_safe
@queryparams(*QUERY_PARAMS)
def browse(request, fixed=None):
    rows = catalog()
    language = ui_language(request)
    fixed = fixed or {}
    selected = selection(request, fixed)
    query = request.GET.get('q', '').strip()[:255]
    words = query.casefold().split()
    sort = request.GET.get('sort', 'stars')
    sort = sort if sort in SORTS else 'stars'
    view = request.GET.get('view', 'table')
    view = view if view in VIEWS else 'table'
    ctx = context(request, rows, language, selected)

    def matches(row, skip=None):
        return (all(not value or key == skip or row[DIMENSIONS[key]['field']] == value for key, value in selected.items())
                and all(word in row['search_text'] for word in words))

    results = [row for row in rows if matches(row)]
    if sort == 'name':
        results.sort(key=lambda row: row['name'].casefold())
    elif sort == 'recent':
        results.sort(key=lambda row: (-(row['last_active'] or row['mtime']).toordinal(), row['name']))
    else:
        results.sort(key=lambda row: (-(row['stars'] or 0), row['name']))
    if words:
        needle = query.casefold()
        results.sort(key=lambda row: (row['name'].casefold() != needle, not row['name'].casefold().startswith(needle)))
    pager = Paginator(results, PAGE_SIZE)
    page = pager.get_page(request.GET.get('page'))
    keep = {'q': query, 'sort': sort, 'view': view}

    dropdowns = []
    for key, spec in DIMENSIONS.items():
        counts = Counter(row[spec['field']] for row in rows if matches(row, skip=key))
        options = []
        for item in ctx['facets'][key]:
            count = counts.get(item['value'], 0)
            if not count and selected[key] != item['value']:
                continue
            options.append({**item, 'count': count, 'current': selected[key] == item['value'],
                            'url': browse_url(language, {**selected, key: item['value']}, **keep)})
        dropdowns.append({
            'key': key, 'param': spec['param'], 'label': localized(spec['label'], language), 'options': options,
            'value': selected[key], 'value_label': value_label(key, selected[key], language) if selected[key] else '',
            'color': value_color(key, selected[key]) if selected[key] else '',
            'any_url': browse_url(language, {**selected, key: ''}, **keep), 'index_url': dimension_url(key, language),
        })
    active = [{'dimension': localized(DIMENSIONS[key]['label'], language), 'value': value,
               'label': value_label(key, value, language), 'color': value_color(key, value),
               'remove_url': browse_url(language, {**selected, key: ''}, **keep)}
              for key, value in selected.items() if value]
    sql, sql_html = sql_readout(query, selected, sort)
    ctx.update({
        'query': query, 'selected': selected, 'sort': sort, 'view': view, 'page': page,
        'rows': [present(row, language) for row in page], 'dropdowns': dropdowns, 'active_filters': active,
        'clear_url': browse_url(language, {}, sort=sort, view=view),
        'query_remove_url': browse_url(language, selected, sort=sort, view=view),
        'sorts': [{'value': value, 'label': ctx['t']['sort_' + value], 'current': value == sort,
                   'url': browse_url(language, selected, **{**keep, 'sort': value})} for value in SORTS],
        'views': [{'value': value, 'label': ctx['t']['view_' + value], 'current': value == view,
                   'url': browse_url(language, selected, **{**keep, 'view': value, 'page': page.number})} for value in VIEWS],
        'pagination': [{'label': number, 'current': number == page.number,
                        'url': browse_url(language, selected, **keep, page=number) if isinstance(number, int) else ''}
                       for number in pager.get_elided_page_range(page.number, on_each_side=1, on_ends=1)],
        'previous_url': browse_url(language, selected, **keep, page=page.previous_page_number()) if page.has_previous() else '',
        'next_url': browse_url(language, selected, **keep, page=page.next_page_number()) if page.has_next() else '',
        'sql': sql, 'sql_html': sql_html, 'result_count': intcomma(pager.count),
        'is_home': not query and not any(selected.values()),
        'form_action': '/ext/', 'search_placeholder': localized(
            ('搜索 {} 个扩展：名称、功能、关键词…', 'Search {} extensions by name, feature or keyword…'), language).format(ctx['total_text']),
    })
    fixed_key = next(iter(fixed), None)
    if fixed_key == 'category':
        code = selected['category']
        ctx['category'] = {'code': code, 'label': category_label(code, language), 'color': category_color(code),
                           'blurb': category_blurb(code, language), 'count': sum(1 for row in rows if row['category'] == code)}
        ctx['ext_source_url'] = PGEXT + '/cate/' + quote(code, safe='')
        title = '{} {} · {}'.format(code, ctx['category']['label'], ctx['t']['catalog'])
        description = ctx['category']['blurb']
    elif fixed_key:
        label = value_label(fixed_key, selected[fixed_key], language)
        ctx['value_page'] = {'dimension': localized(DIMENSIONS[fixed_key]['label'], language), 'label': label,
                             'color': value_color(fixed_key, selected[fixed_key]), 'count': pager.count,
                             'index_url': dimension_url(fixed_key, language)}
        ctx['ext_source_url'] = PGEXT + '/{}/{}'.format(DIMENSIONS[fixed_key]['pgext'], quote(selected[fixed_key], safe=''))
        title = '{} · {} · {}'.format(label, ctx['value_page']['dimension'], ctx['t']['catalog'])
        description = localized(('{}：{} 个 PostgreSQL 扩展。', '{}: {} PostgreSQL extensions.'), language).format(label, pager.count)
    else:
        title = ctx['t']['hero_title']
        description = localized(('检索 PostgreSQL 扩展，按功能、许可证、编程语言和仓库来源浏览，阅读中英文使用文档。',
                                 'Find PostgreSQL extensions by category, license, language and repository, with English and Chinese documentation.'), language)
        if ctx['is_home']:
            ctx['universe'] = universe(rows, language)
    if query:
        title = localized(('搜索 “{}” · {}', 'Search “{}” · {}'), language).format(query, ctx['t']['catalog'])
    seo(request, ctx, title, description, canonical=browse_url(language, selected, **keep, page=page.number), noindex=bool(query))
    return render(request, 'ext/browse.html', ctx)


@require_safe
@queryparams(*QUERY_PARAMS)
def index(request, dimension=None):
    rows = catalog()
    language = ui_language(request)
    ctx = context(request, rows, language, dimension=dimension)
    by_stars = sorted(rows, key=lambda row: (-(row['stars'] or 0), row['name']))
    sections = []
    for key in ([dimension] if dimension else DIMENSIONS):
        spec = DIMENSIONS[key]
        values = []
        for item in ctx['facets'][key]:
            examples = [present(row, language) for row in by_stars if row[spec['field']] == item['value']][:3]
            values.append({**item, 'percent': max(1, round(item['count'] / max(len(rows), 1) * 100)), 'examples': examples,
                           'blurb': category_blurb(item['value'], language) if key == 'category' else ''})
        sections.append({'key': key, 'label': localized(spec['label'], language), 'values': values,
                         'url': dimension_url(key, language), 'note': ctx['t']['repo_note'] if key == 'repo' else ''})
    ctx.update({'dimension': dimension, 'sections': sections})
    if dimension:
        ctx['ext_source_url'] = PGEXT + '/list/' + DIMENSIONS[dimension]['pgext']
        title = '{} · {}'.format(sections[0]['label'], ctx['t']['catalog'])
    else:
        ctx['ext_source_url'] = PGEXT + '/list'
        title = '{} · {}'.format(ctx['t']['list_all'], ctx['t']['catalog'])
    seo(request, ctx, title, ctx['t']['index_intro'])
    return render(request, 'ext/index.html', ctx)


@require_safe
@queryparams(*QUERY_PARAMS)
def section(request, segment):
    """/ext/<segment>/: a dimension index, a category, or an old detail URL."""
    key = LEGACY_DIMENSIONS.get(segment, segment)
    if key in DIMENSIONS:
        return index(request, key)
    code = segment.upper()
    if code in CATEGORIES:
        if segment != code.lower():
            return HttpResponsePermanentRedirect(browse_url(ui_language(request), {'category': code}))
        return browse(request, {'category': code})
    if any(row['name'] == segment for row in catalog()):
        return HttpResponsePermanentRedirect(detail_url(segment, ui_language(request)))
    raise Http404('Unknown catalogue section')


@require_safe
@queryparams(*QUERY_PARAMS)
def value(request, dimension, value):
    """/ext/<dimension>/<value>/: one licence, language or repository."""
    key = LEGACY_DIMENSIONS.get(dimension, dimension)
    language = ui_language(request)
    value = value.rstrip('/')
    if key == 'category':
        if value.upper() not in CATEGORIES:
            raise Http404('Unknown category')
        return HttpResponsePermanentRedirect(browse_url(language, {'category': value.upper()}))
    if key not in DIMENSIONS or key == 'category':
        raise Http404('Unknown catalogue index')
    known = {row[DIMENSIONS[key]['field']] for row in catalog()}
    if value not in known:
        match = next((item for item in known if item.casefold() == value.casefold()), None)
        if match is None:
            raise Http404('Unknown value')
        return HttpResponsePermanentRedirect(browse_url(language, {key: match}))
    return browse(request, {key: value})


@require_safe
@queryparams(*QUERY_PARAMS)
def legacy_index(request, dimension):
    key = LEGACY_DIMENSIONS.get(dimension, dimension)
    if key not in DIMENSIONS:
        raise Http404('Unknown extension index')
    return HttpResponsePermanentRedirect(dimension_url(key, ui_language(request)))


@require_safe
@queryparams('lang')
def detail(request, name):
    rows = catalog()
    by_name = {row['name']: row for row in rows}
    if name not in by_name:
        raise Http404('Extension not found')
    language = ui_language(request)
    ctx = context(request, rows, language, {'category': by_name[name]['category']})
    row = by_name[name]
    extension = present(row, language)
    labels = ctx['t']
    with connection.cursor() as cursor:
        cursor.execute('SELECT en_doc, zh_doc FROM pgext.doc WHERE id = %s AND ext = %s', [row['id'], name])
        pair = cursor.fetchone() or ('', '')
    primary = pair[1 if language == 'zh' else 0]
    fallback = pair[0 if language == 'zh' else 1]
    content, toc = render_document(primary or fallback or '', by_name, language, row.get('doc_url') or extension['upstream'])

    links = []
    for field, label in (('repo_url', labels['source']), ('home_url', labels['home']), ('doc_url', labels['docs']),
                         ('license_url', labels['license_text']), ('control_url', labels['control']), ('pgxn_url', labels['pgxn'])):
        target = safe_url(row.get(field))
        if target and target not in [link['url'] for link in links]:
            links.append({'label': label, 'url': target})
    if not links and extension['upstream']:
        links.append({'label': labels['source'], 'url': extension['upstream']})
    pgext_url = PGEXT + '/ext/' + quote(name, safe='')
    links.append({'label': labels['pgext_page'], 'url': pgext_url})

    def yes_no(flag):
        return labels['yes'] if flag else labels['no']
    overview = [(labels['package'], row['pkg'], browse_url(language, {}, q=row['pkg']) if row['pkg'] != name else '')]
    overview.append((labels['version'], row.get('version') or '—', ''))
    if row.get('pg_ver'):
        overview.append((labels['compatibility'], ' · '.join(str(v) for v in row['pg_ver']), ''))
    overview.append((labels['repo'], extension['repository_label'], extension['repository_href']))
    for field in ('kind', 'lifecycle'):
        if row.get(field):
            overview.append((labels[field], localized(PROPERTY_LABELS[field].get(row[field], (row[field], row[field])), language), ''))
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
        overview.append((labels['stars'], intcomma(row['stars']), extension['upstream']))
    for field in ('last_commit', 'last_release'):
        if row.get(field):
            overview.append((labels[field], row[field].strftime('%Y-%m-%d'), ''))
    if row.get('mtime'):
        overview.append((labels['maintained'], row['mtime'].strftime('%Y-%m-%d'), ''))

    relationships = []
    for field in ('requires', 'required_by', 'see_also'):
        members = [present(by_name[n], language) for n in row.get(field) or [] if n in by_name and n != name]
        if members:
            relationships.append({'key': field, 'label': labels[field], 'members': members})
    family = [present(member, language) for member in rows if member['pkg'] == row['pkg'] and member['name'] != name]
    if family:
        relationships.append({'key': 'family', 'label': labels['family'], 'members': family})

    outline = [{'id': 'overview', 'name': labels['overview'], 'level': 2}, {'id': 'documentation', 'name': labels['documentation'], 'level': 2}]
    outline += [{**item, 'level': 3 if item['level'] >= 3 else 2} for item in toc if item['level'] >= 2]
    if relationships:
        outline.append({'id': 'related', 'name': labels['related'], 'level': 2})

    lifecycle = row.get('lifecycle')
    ctx.update({
        'extension': extension, 'document': content, 'doc_fallback': not primary and bool(fallback),
        'doc_language': (language if primary else ('en' if language == 'zh' else 'zh')) if (primary or fallback) else '',
        'links': links, 'overview': [{'label': l, 'value': v, 'url': u} for l, v, u in overview],
        'relationships': relationships, 'outline': outline,
        'lifecycle': localized(PROPERTY_LABELS['lifecycle'].get(lifecycle, (lifecycle, lifecycle)), language) if lifecycle and lifecycle != 'active' else '',
        'create_sql': 'CREATE EXTENSION "{}";'.format(name.replace('"', '""')) if row['need_ddl'] else '',
        'ext_source_url': pgext_url, 'breadcrumb_category': browse_url(language, {'category': row['category']}),
    })
    seo(request, ctx, '{} · {}'.format(name, labels['catalog']), extension['description'], canonical=detail_url(name, language))
    return render(request, 'ext/detail.html', ctx)


@require_safe
def detail_root(request):
    return HttpResponsePermanentRedirect('/ext/')


@require_safe
def sitemap(request):
    rows = catalog()
    paths = ['/ext/', '/ext/list/'] + ['/ext/{}/'.format(key) for key in DIMENSIONS]
    paths += ['/ext/{}/'.format(code.lower()) for code in CATEGORIES if any(row['category'] == code for row in rows)]
    for key in ('license', 'language', 'repo'):
        paths += sorted({browse_url('zh', {key: row[DIMENSIONS[key]['field']]}) for row in rows})
    paths += [detail_url(row['name']) for row in rows]
    return render(request, 'ext/sitemap.xml', {'paths': paths}, content_type='application/xml')
