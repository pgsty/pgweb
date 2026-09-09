from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from pgweb.util.decorators import queryparams
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
    try:
        offset = max(0, min(10000, int(request.GET.get('offset', 0))))
    except ValueError:
        offset = 0
    return {'raw': raw, 'scope': scope, 'kind': request.GET.get('kind', ''), 'offset': offset}


@queryparams('q', 'scope', 'kind', 'u', 'offset')
@require_GET
def search_page(request):
    payload = service.search(**arguments(request))
    response = render(request, 'search/docsearch.html', {'search': payload, 'seo': {'title': '文档检索 · PostgreSQL 中文社区'}})
    response['Cache-Control'] = 'no-cache'
    return response


@queryparams('q', 'scope', 'kind', 'u', 'offset')
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
