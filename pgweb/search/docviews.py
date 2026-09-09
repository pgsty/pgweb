from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from pgweb.util.decorators import queryparams
from pgweb.docs.versions import DEVEL_MAJOR_VERSION
from .models import SearchEntry
from . import service


def arguments(request):
    raw = request.GET.get('q', '')
    scope = request.GET.get('scope', 'pg')
    # Existing document search forms/bookmarks used the u=/docs/17/ parameter.
    legacy = request.GET.get('u', '').strip('/').split('/')
    if 'scope' not in request.GET and len(legacy) >= 2 and legacy[0] == 'docs':
        if legacy[1].isdigit():
            scope = 'pg' + legacy[1]
        elif legacy[1] == 'devel':
            scope = 'pg' + str(DEVEL_MAJOR_VERSION)
    try:
        offset = max(0, min(10000, int(request.GET.get('offset', 0))))
    except ValueError:
        offset = 0
    try:
        limit = max(1, min(service.PAGE_SIZE, int(request.GET.get('limit', service.PAGE_SIZE))))
    except ValueError:
        limit = service.PAGE_SIZE
    return {'raw': raw, 'scope': scope, 'kind': request.GET.get('kind', ''), 'offset': offset, 'limit': limit}


@queryparams('q', 'scope', 'kind', 'u', 'offset', 'limit')
@require_GET
def search_page(request):
    payload = service.search(**arguments(request))
    response = render(request, 'search/docsearch.html', {'search': payload, 'site_search': bool(getattr(settings, 'SEARCH_DSN', '')),
                                                          'seo': {'title': '文档检索 · PostgreSQL 中文社区'}})
    response['Cache-Control'] = 'no-cache'
    return response


@queryparams('q', 'scope', 'kind', 'u', 'offset', 'limit')
@require_GET
def search_api(request):
    response = JsonResponse(service.search(**arguments(request)), json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'no-cache'
    return response


@queryparams()
@require_GET
def preview_api(request, entry_id):
    entry = get_object_or_404(SearchEntry.objects.select_related('document__page').defer('vector', 'document__page__content'), pk=entry_id)
    response = JsonResponse(service.preview(entry), json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'no-cache'
    return response
