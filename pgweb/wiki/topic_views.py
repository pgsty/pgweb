from django.http import Http404, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.views.decorators.http import require_safe
from urllib.parse import urlencode

from pgweb.util.decorators import queryparams

from . import topics
from .views import shell


@require_safe
@queryparams('v', 'q', 'category')
def index(request, kind):
    try:
        payload = topics.index(kind, request.GET.get('v', ''),
                               request.GET.get('q', '').strip()[:120], request.GET.get('category', ''))
    except ValueError:
        raise Http404()
    title = 'PostgreSQL ' + payload['topic']['name']
    return render(request, 'wiki/topic_index.html', shell(
        payload, title, payload['topic']['lead'], payload['root'], section=payload['root']))


@require_safe
@queryparams('v')
def detail(request, kind, slug):
    model = topics.TOPICS[kind]['model']
    try:
        payload = topics.detail(kind, slug.lower(), request.GET.get('v', ''))
    except (ValueError, model.DoesNotExist):
        raise Http404()
    canonical = topics.row_url(kind, payload['item'])
    if slug != slug.lower():
        query = urlencode({'v': request.GET['v']}) if request.GET.get('v') else ''
        return HttpResponsePermanentRedirect(canonical + ('?' + query if query else ''))
    title = '{} · {}'.format(payload['item']['name'], payload['topic']['name'])
    return render(request, 'wiki/topic_detail.html', shell(
        payload, title, payload['item']['summary'], canonical, section=payload['root']))
