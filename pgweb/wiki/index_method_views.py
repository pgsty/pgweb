"""HTTP views for Index AM using the shared Wiki shell."""
from urllib.parse import urlencode
from django.http import Http404, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.views.decorators.http import require_safe
from pgweb.util.decorators import queryparams
from . import index_methods, topics
from .encyclopedia import context


@require_safe
@queryparams('v', 'q', 'category', 'from')
def index(request):
    try:
        payload = index_methods.index(request.GET.get('v', ''), request.GET.get('q', '').strip()[:120],
                                      request.GET.get('category', ''), request.GET.get('from', ''))
    except ValueError:
        raise Http404()
    retained = {key: request.GET[key] for key in ('q', 'category', 'from') if request.GET.get(key)}
    for version in payload['versions']:
        version['url'] = payload['root'] + '?' + urlencode(dict(retained, v=version['major']))
    payload['compare_from'] = request.GET.get('from', '')
    return render(request, 'wiki/index_method_index.html', context(payload,
                  'PostgreSQL Index AM', payload['topic']['lead'], payload['root']))


@require_safe
@queryparams('v', 'from')
def detail(request, slug):
    try:
        payload = index_methods.detail(slug.lower(), request.GET.get('v', ''), request.GET.get('from', ''))
    except (ValueError, topics.TOPICS['indexam']['model'].DoesNotExist):
        raise Http404()
    canonical = topics.row_url('indexam', payload['item'])
    if slug != slug.lower():
        query = urlencode({key: request.GET[key] for key in ('v', 'from') if request.GET.get(key)})
        return HttpResponsePermanentRedirect(canonical + ('?' + query if query else ''))
    return render(request, 'wiki/index_method_detail.html', context(payload,
                  payload['item']['name'] + ' · Index AM', payload['item']['summary'], canonical))


@require_safe
@queryparams('from')
def changes(request, major=None):
    try:
        payload = index_methods.index(major or '', baseline=request.GET.get('from', ''))
    except ValueError:
        raise Http404()
    canonical = payload['root'] + 'changes/' + payload['major'] + '/'
    if major is None:
        from django.http import HttpResponseRedirect
        query = urlencode({'from': request.GET['from']}) if request.GET.get('from') else ''
        return HttpResponseRedirect(canonical + ('?' + query if query else ''))
    payload['changes_page'] = True
    for version in payload['versions']:
        suffix = '?' + urlencode({'from': request.GET['from']}) if request.GET.get('from') else ''
        version['url'] = payload['root'] + 'changes/' + version['major'] + '/' + suffix
    return render(request, 'wiki/index_method_changes.html', context(payload,
                  'Index AM 版本变化 · PostgreSQL ' + payload['version']['label'],
                  '比较所选 PostgreSQL 手册记录的能力与存储参数。', canonical))
