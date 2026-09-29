from urllib.parse import urlencode
import difflib
import json
from django.core.paginator import Paginator
from django.http import Http404, HttpResponsePermanentRedirect, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe
from pgweb.util.decorators import queryparams
from . import topics
from .views import shell



def base_context(kind='', title='', description='', canonical=''):
    from .columns import COLUMNS
    spec = topics.TOPICS.get(kind, {})
    navigation = [dict(slug=c['slug'], title=c['name'], url='/wiki/' + c['slug'] + '/',
                       active=c['slug'] == kind, tone=c['tone'], section=c.get('section', '')) for c in COLUMNS]
    ctx = dict(kind=kind, title=title, description=description, canonical=canonical,
               reference_nav=navigation, collection=spec)
    return shell(ctx, title, description, canonical, section='/wiki/' + kind + '/' if kind else '/wiki/')


def collection_state(version):
    if version.get('status') == 'devel':
        return 'devel'
    if version.get('status') == 'preview':
        return 'beta'
    if version.get('status') == 'stable':
        return 'current'
    return 'supported' if version.get('support_status') == 'supported' else 'eol'


def version_note(version):
    if version.get('status') == 'devel':
        return '开发快照：定义可能在正式发布前继续变化。'
    if version.get('status') == 'preview':
        return '预发布版本：定义可能在最终发布前继续变化。'
    if version.get('support_status') == 'end-of-life':
        return '历史版本：对应 PostgreSQL 版本已结束支持。'
    return ''


def exported(payload):
    """Explicit export boundary: never serialize models or template context."""
    return {key: payload[key] for key in ('kind', 'major', 'item', 'snapshot', 'comparison') if key in payload}


def display_tables(tables):
    return [dict(table, cells=[[record[column['key']] for column in table['columns']]
                               for record in table['rows']]) for table in tables]


def localized_preview_html(nodes, url):
    """Retain explicit source languages through the unchanged preview sanitizer."""
    from bs4 import BeautifulSoup
    from pgweb.search.extract import preview_html

    markers = {'wiki-source-lang-en': 'en', 'wiki-source-lang-zh': 'zh'}
    soup = BeautifulSoup(''.join(str(node) for node in nodes), 'html.parser')
    for node in soup.find_all(True):
        classes = [value for value in node.get('class', []) if value not in markers]
        language = node.get('lang')
        if language in ('en', 'zh'):
            classes.append('wiki-source-lang-' + language)
        if classes:
            node['class'] = classes
        else:
            node.attrs.pop('class', None)
    clean = BeautifulSoup(preview_html([str(soup)], url), 'html.parser')
    for node in clean.find_all(True):
        classes = node.get('class', [])
        for marker in classes:
            if marker in markers:
                node['lang'] = markers[marker]
        classes = [value for value in classes if value not in markers]
        if classes:
            node['class'] = classes
        else:
            node.attrs.pop('class', None)
    return str(clean)


def compare(payload, left, right):
    sampled = {v['major'] for v in payload['versions']}
    if left not in sampled or right not in sampled:
        raise Http404('Unsupported comparison version')
    snapshots = payload['item']['versions']
    a, b = snapshots.get(left), snapshots.get(right)

    def lines(snap):
        if snap is None:
            return ['该版未收录']
        value = snap.get('comparison_data', {key: snap.get(key) for key in ('signature', 'facts', 'tables')})
        return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).splitlines()
    status = 'unchanged' if a == b or (a and b and topics.signature_of(a) == topics.signature_of(b)) else 'added' if not a else 'removed' if not b else 'changed'
    return dict(left=left, right=right, status=status,
                diff='\n'.join(difflib.unified_diff(lines(a), lines(b), fromfile='PostgreSQL ' + left,
                                                    tofile='PostgreSQL ' + right, lineterm='')) if status != 'unchanged' else '')


def prepare_reader(payload):
    snapshot = payload['snapshot']
    if snapshot:
        path = snapshot.get('manual_path', '/docs/')
        if not path.startswith(('/', 'https://')):
            path = '/docs/{}/{}'.format('devel' if payload['major'] == '20' else payload['major'], path)
        snapshot['manual_language'] = snapshot.get('manual_language') or ('en' if path.startswith('https://pg.center/') else 'zh')
        snapshot['rendered_html'] = localized_preview_html([snapshot.get('manual_html', '')], path)
        payload['tables'] = display_tables(snapshot.get('tables', []))
    return payload


def context(payload, title, description, canonical):
    result = base_context(payload['kind'], title, description, canonical)
    result.update(payload)
    result['collection'] = {'tone': payload['topic']['tone']}
    result['picker'] = [dict(version, current=version['is_current'], state=collection_state(version))
                        for version in payload['versions']]
    return result


@require_safe
@queryparams('v', 'q', 'category', 'page', 'format')
def index(request, kind):
    try:
        payload = topics.index(kind, request.GET.get('v', ''), request.GET.get('q', '').strip()[:120], request.GET.get('category', ''))
    except (ValueError, KeyError):
        raise Http404()
    collection_tables = []
    if kind in ('fdw', 'tableam', 'decode') and payload['versions']:
        latest = payload['versions'][-1]['major']
        path = 'versions__' + latest + '__collection_tables'
        for tables in topics.TOPICS[kind]['model'].objects.values_list(path, flat=True):
            collection_tables.extend(tables or [])
        if payload['query']:
            needle = payload['query'].casefold()
            collection_tables = [dict(table, rows=[row for row in table['rows'] if needle in
                                                   ' '.join(value['text'] if isinstance(value, dict) else value for value in row.values()).casefold()])
                                 for table in collection_tables]
    if request.GET.get('format') == 'json':
        return JsonResponse(dict({key: payload[key] for key in ('kind', 'major', 'rows', 'total', 'present')}, collection_tables=collection_tables))
    payload['collection_tables'] = display_tables(collection_tables)
    pager = Paginator(payload['rows'], 100).get_page(request.GET.get('page'))
    payload['rows'], payload['page'] = pager.object_list, pager
    retained = {key: request.GET[key] for key in ('q', 'category') if request.GET.get(key)}
    for version in payload['versions']:
        version['url'] = payload['root'] + '?' + urlencode(dict(retained, v=version['major']))
    payload['page_query'] = urlencode(dict(retained, v=payload['major']))
    return render(request, 'wiki/encyclopedia_index.html', context(payload, 'PostgreSQL ' + payload['topic']['name'], payload['topic']['lead'], payload['root']))


@require_safe
@queryparams('v', 'from', 'to', 'format')
def detail(request, kind, slug):
    model = topics.TOPICS[kind]['model']
    try:
        payload = topics.detail(kind, slug.lower(), request.GET.get('v', ''))
    except (ValueError, model.DoesNotExist):
        raise Http404()
    canonical = topics.row_url(kind, payload['item'])
    if slug != slug.lower():
        query = request.GET.urlencode()
        return HttpResponsePermanentRedirect(canonical + ('?' + query if query else ''))
    title = '{} · {}'.format(payload['item']['name'], payload['topic']['name'])
    majors = [v['major'] for v in payload['versions']]
    right = request.GET.get('to', payload['major'])
    i = majors.index(right) if right in majors else -1
    left = request.GET.get('from', majors[max(0, i - 1)])
    payload['comparison'] = compare(payload, left, right)
    if request.GET.get('format') == 'json':
        return JsonResponse(exported(payload))
    prepare_reader(payload)
    return render(request, 'wiki/encyclopedia_detail.html', context(payload, title, payload['item']['summary'], canonical))


@require_safe
@queryparams('from', 'format')
def changes(request, kind, major=''):
    try:
        payload = topics.index(kind, major)
    except (ValueError, KeyError):
        raise Http404()
    majors = [v['major'] for v in payload['versions']]
    if not majors:
        raise Http404()
    right = payload['major']
    left = request.GET.get('from', majors[max(0, majors.index(right) - 1)])
    if left not in majors:
        raise Http404()
    changes = []
    for row in topics.records(kind):
        a, b = row['versions'].get(left), row['versions'].get(right)
        if (a is None and b is None) or (a and b and topics.signature_of(a) == topics.signature_of(b)):
            continue
        status = 'added' if a is None else 'removed' if b is None else 'changed'
        changes.append(dict(name=row['name'], status=status,
                            url=topics.row_url(kind, row) + '?' + urlencode({'v': right, 'from': left, 'to': right})))
    payload.update(changes=changes, left=left, right=right)
    if request.GET.get('format') == 'json':
        return JsonResponse(dict(kind=kind, left=left, right=right, changes=changes))
    return render(request, 'wiki/encyclopedia_changes.html', context(payload, payload['topic']['name'] + '版本变化',
                                                              '所采样 PostgreSQL 构建之间的差异。', payload['root'] + 'changes/' + right + '/'))
