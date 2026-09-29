"""Native Chinese readers for PostgreSQL release branches."""
import re
from urllib.parse import urlencode

from django.http import Http404, HttpResponsePermanentRedirect, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from pgweb.docs.compare import CATEGORY_LABELS
from pgweb.docs.compare_store import ComparisonDataUnavailable
from pgweb.docs.versions import DEVEL_MAJOR_VERSION
from pgweb.util.decorators import queryparams
from .encyclopedia import base_context
from . import version_data as data

DESCRIPTION = 'PostgreSQL 大版本的生命周期、本站手册、功能变化、升级注意事项、小版本发布与安全证据。'


def _context(title='版本发布', canonical=data.ROOT):
    context = base_context('versions', title, DESCRIPTION, canonical)
    context['collection'] = {'title': '版本发布', 'tone': 'catalog', 'label': '大版本分支'}
    return context


def _error(request, message, status):
    if request.GET.get('format') == 'json':
        return JsonResponse({'error': message}, status=status)
    return render(request, 'wiki/version_index.html', dict(_context(), error=message), status=status)


@queryparams('q', 'state', 'format')
@require_safe
def index(request):
    query, state = request.GET.get('q', '').strip()[:200], request.GET.get('state', '')
    if state and state not in data.STATE_LABELS:
        return _error(request, '请选择有效的生命周期状态。', 400)
    try:
        catalog = data.load_catalog()
    except ComparisonDataUnavailable:
        return _error(request, '发布数据暂不可用，请稍后重试。', 503)
    rows = data.filter_branches(catalog, query, state)
    payload = {'rows': rows, 'total': len(catalog['rows']), 'filtered': len(rows),
               'query': query, 'selected_state': state, 'policy_url': data.POLICY_URL,
               'release_as_of': catalog['release_as_of'], 'security_as_of': catalog['security_as_of'],
               'states': [{'key': key, 'label': label, 'count': sum(row['state'] == key for row in catalog['rows'])}
                          for key, label in data.STATE_LABELS.items()]}
    if request.GET.get('format') == 'json':
        return JsonResponse(dict(format=1, **payload))
    export_query = urlencode({key: value for key, value in
                              (('q', query), ('state', state), ('format', 'json')) if value})
    return render(request, 'wiki/version_index.html', dict(_context(), export_query=export_query, **payload))


@queryparams('q', 'kind', 'format')
@require_safe
def detail(request, branch):
    if branch == 'devel':
        suffix = '?' + request.GET.urlencode() if request.GET else ''
        return HttpResponsePermanentRedirect(data.ROOT + str(DEVEL_MAJOR_VERSION) + '/' + suffix)
    if not re.fullmatch(r'[1-9]\d*(?:\.\d+)?', branch):
        raise Http404('未知的 PostgreSQL 大版本分支')
    kind, query = request.GET.get('kind', ''), request.GET.get('q', '').strip()[:200]
    if kind and kind not in CATEGORY_LABELS:
        return _error(request, '请选择有效的变更类别。', 400)
    try:
        catalog = data.load_catalog()
    except ComparisonDataUnavailable:
        return _error(request, '发布数据暂不可用，请稍后重试。', 503)
    if not any(row['branch'] == branch for row in catalog['rows']):
        raise Http404('未知的 PostgreSQL 大版本分支')
    payload = data.detail_payload(catalog, branch, query, kind)
    row = payload['version']
    payload.update(pdfs=data.manual_resources(row), query=query, selected_kind=kind,
                   branches=catalog['rows'])
    if request.GET.get('format') == 'json':
        return JsonResponse(dict(format=1, **payload))
    export_query = urlencode({key: value for key, value in
                              (('q', query), ('kind', kind), ('format', 'json')) if value})
    return render(request, 'wiki/version_detail.html',
                  dict(_context('PostgreSQL ' + branch + ' · 版本发布', row['url']),
                       export_query=export_query, **payload))
