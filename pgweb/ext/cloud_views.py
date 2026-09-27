"""Server-rendered cloud support pages with progressive GET filtering."""
import csv
from io import StringIO

from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from pgweb.util.contexts import get_nav_menu
from pgweb.util.decorators import queryparams
from . import cloud
from .catalog import CATEGORIES, catalog
from .views import seo

PARAMS = ('q', 'pg', 'category', 'scope', 'status', 'service', 'selection', 'page', 'format')
PAGE_SIZE = 50


def cloud_navigation(data, service=None):
    nav = get_nav_menu('download')
    for item in nav:
        if item['link'] == '/ext/':
            item['submenu'] = [
                {'title': '全部扩展', 'link': '/ext/'},
                {'title': '云厂商对比', 'link': '/ext/cloud/', 'active': not service},
            ]
            if service:
                current = data['by_service'][service]
                item['submenu'].append({'title': current['label'], 'link': current['url'], 'active': True})
    return nav


def _dropdown(param, label, choices, selected):
    return {'param': param, 'label': label, 'options': [
        {'value': key, 'label': name, 'current': key == selected} for key, name in choices]}


def _csv(data, rows, columns):
    output = StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['entry_key', 'extension', 'canonical', 'packaged', 'category', 'service', 'pg_major', 'raw_name',
                     'status', 'version', 'note', 'engine_status', 'data_status', 'list_scope',
                     'source_url', 'engine_url', 'checked_at', 'coverage_note'])
    for row in rows:
        for column in columns:
            cell = cloud.evidence(data, row, column['service'], column['pg'])
            meta = data['coverage'].get((column['service'], column['pg']), {})
            values = [row['key'], row['name'], not row['unresolved'], row['packaged'], row['category'],
                      column['service'], column['pg'], cell['raw_name'], cell['status'], cell['version'], cell['note'],
                      meta.get('engine_status', ''), meta.get('data_status', ''), meta.get('list_scope', ''),
                      cell['source_url'], cell['engine_url'], cell['checked_at'], cell['coverage_note']]
            # Avoid spreadsheet formula execution from provider-controlled text.
            writer.writerow(["'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r'))
                             else value for value in values])
    response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="pgext-cloud-matrix.csv"'
    return response


@queryparams(*PARAMS)
@require_safe
def matrix(request, service_id=None):
    data = cloud.snapshot()
    if service_id and service_id not in data['by_service']:
        raise Http404('Unknown cloud service')
    selected = cloud.selection(request, data, service_id)
    columns = cloud.columns(data, selected, service_id)
    entries = cloud.filtered_entries(data, selected, columns, service_id)
    if request.GET.get('format') == 'csv':
        return _csv(data, entries, columns)
    pager = Paginator(entries, PAGE_SIZE)
    page = pager.get_page(request.GET.get('page'))
    rows = []
    for original in page:
        row = dict(original)
        row['cells'] = [{**cloud.cell(data, row, c['service'], c['pg']), 'column_label': c['label']}
                        for c in columns]
        rows.append(row)
    service = data['by_service'].get(service_id)
    choices = [('supported', '本服务已列明'), ('packaged', 'Pigsty 打包'), ('all', '全部收录'), ('raw', '待归一条目')] if service else [
        ('compare', '打包 + 云端补充'), ('packaged', '仅 Pigsty 打包'), ('cloud', '仅云端补充'), ('raw', '待归一条目')]
    dates = sorted({cloud.date_text(m['checked_at']) for (sid, _), m in data['coverage'].items() if sid != cloud.ANCHOR})
    anchors = sorted({cloud.date_text(m['checked_at']) for (sid, _), m in data['coverage'].items() if sid == cloud.ANCHOR})
    label = dates[0] if len(dates) == 1 else '{} 至 {}'.format(dates[0], dates[-1]) if dates else '暂无资料'
    if anchors:
        label += '；Pigsty 包快照 ' + anchors[-1]
    title = '{} · 扩展支持'.format(service['label']) if service else 'PostgreSQL 云厂商扩展支持'
    ctx = {
        'mode': 'service' if service else 'compare', 'service': service,
        'title': title,
        'intro': ('比较同一云服务在 PostgreSQL 14–18 的扩展版本与支持边界。' if service else
                  '以 Pigsty 打包扩展为基线，补入云服务列明的扩展，比较同一 PostgreSQL 大版本的版本与可用性。'),
        'snapshot_label': label, 'total_services': sum(not s['anchor'] for s in data['services']),
        'form_action': cloud.matrix_url(service_id), 'query': selected['q'], 'selected_pg': selected['pg'],
        'pg_options': [{'value': pg, 'label': 'PG {}'.format(pg), 'current': pg == selected['pg']} for pg in cloud.MAJORS],
        'dropdowns': [_dropdown('scope', '扩展范围', choices, selected['scope']),
                      _dropdown('category', '功能分类', [('', '全部分类'), *CATEGORIES.items(), ('RAW', '待归一')], selected['category']),
                      _dropdown('status', '支持状态', [('', '全部状态'), ('supported', '已支持 / 条件支持'),
                                                     ('different', '仅看差异'), ('unknown', '含未知状态')], selected['status'])],
        'services': [{**s, 'current': s['id'] == service_id if service_id else s['id'] in selected['service']}
                     for s in data['services'] if not s['anchor']],
        'columns': columns, 'rows': rows, 'result_count': pager.count,
        'empty_evidence': bool(service and selected['scope'] == 'supported' and not entries
                               and not any(selected[key] for key in ('q', 'category', 'status'))),
        'packaged_url': cloud.matrix_url(service_id, selected={'scope': 'packaged'}),
        'total_entries': len(catalog()), 'page': page,
        'previous_url': cloud.matrix_url(service_id, selected=selected, page=page.previous_page_number()) if page.has_previous() else '',
        'next_url': cloud.matrix_url(service_id, selected=selected, page=page.next_page_number()) if page.has_next() else '',
        'pagination': [{'label': number, 'current': number == page.number,
                        'url': cloud.matrix_url(service_id, selected=selected, page=number) if isinstance(number, int) else ''}
                       for number in pager.get_elided_page_range(page.number, on_each_side=1, on_ends=1)],
        'reset_url': cloud.matrix_url(service_id), 'export_url': cloud.matrix_url(service_id, selected=selected, format='csv'),
        'legend': [{'status': state, 'label': label} for state, label in cloud.STATUS_LABELS.items()],
        'navmenu': cloud_navigation(data, service_id), 'ext_cloud_active': True,
    }
    canonical = cloud.matrix_url(service_id, selected=selected, page=page.number)
    seo(ctx, title, ctx['intro'], canonical, noindex=bool(request.GET))
    return render(request, 'ext/cloud.html', ctx)


@queryparams('service', 'pg', 'entry')
@require_safe
def evidence(request):
    data = cloud.snapshot()
    service = request.GET.get('service', '')
    try:
        pg = int(request.GET.get('pg', 18))
    except (TypeError, ValueError):
        raise Http404('Unknown PG version')
    if service not in data['by_service'] or pg not in cloud.MAJORS:
        raise Http404('Unknown service or PG version')
    entry = next((row for row in cloud.entry_rows(data) if row['key'] == request.GET.get('entry')), None)
    if not entry:
        raise Http404('Unknown extension')
    svc = data['by_service'][service]
    title = '{} · {} · PG {}'.format(entry['name'], svc['label'], pg)
    ctx = {'title': title, 'row': entry, 'column': {'label': svc['label'], 'pg': pg},
           'cell': cloud.evidence(data, entry, service, pg), 'service': svc,
           'back_url': cloud.matrix_url(service, selected={'q': entry['name']}),
           'navmenu': cloud_navigation(data, service), 'ext_cloud_active': True}
    seo(ctx, title, '扩展支持状态、版本与来源依据', request.path, noindex=True)
    return render(request, 'ext/cloud_evidence.html', ctx)
