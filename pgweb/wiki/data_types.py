"""Data-type readers over fixed, versioned PostgreSQL source inventories."""

import json
import re
from collections import defaultdict
from urllib.parse import urlencode, urlsplit

from django.http import Http404, HttpResponsePermanentRedirect, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from pgweb.util.decorators import queryparams
from . import topics
from .encyclopedia import localized_preview_html, version_note
from .models import DataType, PgOperator
from .encyclopedia import context

RELATION_FIELDS = {
    'casts': [('castsource', '源类型'), ('casttarget', '目标类型'), ('castcontext', '转换上下文'),
              ('castmethod', '转换方式'), ('castfunc', '函数')],
    'operators': [('oprname', '运算符'), ('oprleft', '左操作数'), ('oprright', '右操作数'),
                  ('oprresult', '返回类型'), ('descr', '含义'), ('oprcode', '实现函数')],
    'operator_classes': [('opcname', '操作符类'), ('opcmethod', '索引方法'), ('opcintype', '输入类型'),
                         ('opcfamily', '操作符族'), ('opcdefault', '默认'), ('opckeytype', '存储类型')],
    'ranges': [('rngtypid', '范围类型'), ('rngmultitypid', '多范围类型'), ('rngsubtype', '子类型'),
               ('rngsubopc', '排序操作符类'), ('rngcanonical', '规范化函数'),
               ('rngsubdiff', '差值函数'), ('rngcollation', '排序规则')],
}
RELATION_VALUES = {
    'castcontext': {'i': '隐式', 'a': '赋值', 'e': '显式'},
    'castmethod': {'f': '函数', 'b': '二进制兼容', 'i': '输入／输出'},
    'opcdefault': {'t': '是', 'f': '否'},
    'opckeytype': {'0': '与输入类型相同'},
    'oprleft': {'0': '无（一元）', '-': '无（一元）'},
    'oprright': {'0': '无（一元）', '-': '无（一元）'},
}


def _json(data):
    return JsonResponse(data, json_dumps_params={'ensure_ascii': False})


def comparison(left, right):
    """Compare attributes, separately from editorial/manual prose and build hashes."""
    if not left or not right:
        return {'available': False, 'changes': [], 'prose_changed': False}
    changes = []
    left_facts, right_facts = defaultdict(list), defaultdict(list)
    for snapshot, facts in ((left, left_facts), (right, right_facts)):
        for fact in snapshot.get('facts', []):
            if fact['label'] in ('Manual description', '手册说明'):
                continue
            facts[fact['label']].append(fact['value'])
    for label in sorted(left_facts.keys() | right_facts.keys()):
        if left_facts.get(label) != right_facts.get(label):
            changes.append({'label': label, 'before': '; '.join(left_facts.get(label, ['未记录'])),
                            'after': '; '.join(right_facts.get(label, ['未记录']))})
    normalized_left = left.get('comparison_data', left)
    normalized_right = right.get('comparison_data', right)
    for field, label in (('aliases', 'SQL 名称与别名'), ('catalog', '系统目录属性'),
                         ('casts', '类型转换'), ('operators', '运算符重载'),
                         ('operator_classes', '操作符类'), ('ranges', '范围类型属性')):
        a, b = normalized_left.get(field), normalized_right.get(field)
        if a != b:
            changes.append({'label': label, 'before': json.dumps(a, ensure_ascii=False, sort_keys=True),
                            'after': json.dumps(b, ensure_ascii=False, sort_keys=True)})
    return {'available': True, 'changes': changes,
            'prose_changed': left.get('description') != right.get('description') or
            left.get('manual_html') != right.get('manual_html')}


def _type_links(rows, major):
    links = {}
    for row in rows:
        snapshot = row['versions'].get(major)
        if not snapshot:
            continue
        names = [row['name'], row['slug'], *snapshot.get('aliases', [])]
        catalog = snapshot.get('catalog') or {}
        if catalog.get('typname'):
            names.append(catalog['typname'])
        for name in names:
            links[name] = topics.row_url('type', row) + '?v=' + major
    return links


def _operator_slug(entry):
    from .operator_data import operator_slug

    def operand(name):
        return 'none' if name in ('0', '-', '') else name

    return operator_slug(entry['oprname'], operand(entry.get('oprleft', '')),
                         operand(entry.get('oprright', '')))


def _operator_descriptions(entries, major):
    """Read only same-version Chinese prose, in one query for all overloads."""
    slugs = {_operator_slug(entry) for entry in entries}
    if not slugs:
        return {}
    descriptions = {}
    rows = PgOperator.objects.filter(slug__in=slugs).values_list(
        'slug', 'versions__' + major + '__description')
    for slug, paragraphs in rows:
        if isinstance(paragraphs, list):
            translated = next((text for text in paragraphs if isinstance(text, str) and
                               re.search(r'[\u3400-\u9fff]', text)), '')
            if translated:
                descriptions[slug] = translated
    return descriptions


def detail_payload(slug, wanted='', compare_from=''):
    payload = topics.detail('type', slug, wanted)
    snapshot = payload['snapshot']
    major = payload['major']
    choices = [v for v in payload['versions'] if v['present'] and v['major'] != major]
    prior = [v for v in choices if v['position'] < payload['version']['position']]
    baseline = next((v for v in choices if v['major'] == compare_from), None) if compare_from else (prior[-1] if prior else None)
    if compare_from and baseline is None:
        raise ValueError('不支持的比较版本')
    payload.update(compare_versions=choices, baseline=baseline, notice=version_note(payload['version']),
                   delta=comparison(payload['item']['versions'].get(baseline['major']) if baseline else None, snapshot))
    if snapshot:
        path = snapshot.get('manual_path', '')
        if path and not path.startswith('/') and not urlsplit(path).scheme:
            path = '/docs/{}/{}'.format(payload['version']['doc_slug'], path)
        # Use the manual reader's existing allowlist and URL resolution.
        payload['manual_html'] = localized_preview_html([snapshot.get('manual_html', '')], path) if path else ''
        payload['manual_url'] = path
        payload['manual_language'] = snapshot.get('manual_language') or ('en' if urlsplit(path).netloc == 'pg.center' else 'zh')
        payload['catalog_rows'] = [{'name': key, 'value': value} for key, value in (snapshot.get('catalog') or {}).items()]
        payload['type_links'] = _type_links(topics.records('type'), major)
        payload['aliases'] = snapshot.get('aliases', [])
        operator_descriptions = _operator_descriptions(snapshot.get('operators', []), major)
        payload['relation_tables'] = []
        for field, title in (('casts', '类型转换'), ('operators', '运算符重载'),
                             ('operator_classes', '操作符类'), ('ranges', '范围类型属性')):
            entries = snapshot.get(field, [])
            if entries:
                columns = [(key, label) for key, label in RELATION_FIELDS[field] if any(key in entry for entry in entries)]
                table = {'title': title, 'key': field, 'headings': [label for _, label in columns], 'rows': []}
                for entry in entries:
                    cells = []
                    for key, _ in columns:
                        value = entry.get(key, '')
                        if isinstance(value, (list, dict)):
                            value = json.dumps(value, ensure_ascii=False)
                        value = str(value)
                        url = payload['type_links'].get(value, '')
                        if field == 'operators' and key == 'oprname':
                            url = '/wiki/operator/{}/?v={}'.format(_operator_slug(entry), major)
                        if field == 'operator_classes' and key == 'opcname':
                            from .operator_data import catalog_slug
                            slug = catalog_slug('class', entry['opcmethod'], value)
                            url = '/wiki/opclass/{}/?v={}'.format(slug, major)
                        if field == 'operator_classes' and value in ('btree', 'hash', 'gist', 'spgist', 'gin', 'brin'):
                            url = '/wiki/indexam/{}/?v={}'.format(value, major)
                        cell = {'value': RELATION_VALUES.get(key, {}).get(value, value), 'url': url}
                        if field == 'operators' and key == 'descr':
                            cell['display_descr'] = operator_descriptions.get(_operator_slug(entry), '')
                        cells.append(cell)
                    table['rows'].append(cells)
                payload['relation_tables'].append(table)
    return payload


@require_safe
@queryparams('v', 'q', 'category', 'format')
def index(request):
    try:
        payload = topics.index('type', request.GET.get('v', ''), request.GET.get('q', '').strip()[:120], request.GET.get('category', ''))
    except ValueError:
        raise Http404('未知版本')
    if request.GET.get('format') == 'json':
        return _json({'kind': 'type', 'major': payload['major'], 'total': payload['total'],
                      'rows': [{'slug': r['slug'], 'name': r['name'], 'category': r['category'],
                                'summary': r['summary'], 'aliases': r['aliases'], 'url': r['url'],
                                'present_in': list(r['versions'])} for r in payload['rows']]})
    payload['page_query'] = urlencode({key: value for key, value in
                                       (('v', payload['major']), ('q', payload['query']), ('category', payload['category']))
                                       if value})
    # Retain the collection filters when changing versions.
    for version in payload['versions']:
        version['url'] = payload['root'] + '?' + urlencode({k: v for k, v in
                                                            (('v', version['major']), ('q', payload['query']), ('category', payload['category'])) if v})
    return render(request, 'wiki/data_type_index.html', context(payload, 'PostgreSQL 数据类型', payload['topic']['lead'], payload['root']))


@require_safe
@queryparams('v', 'from', 'format')
def detail(request, slug):
    rows = topics.records('type')
    row = next((r for r in rows if r['slug'] == slug.lower()), None)
    if row is None:
        matches = [r for r in rows if slug.casefold() in {a.casefold() for a in [r['name'], *r['aliases']]}]
        row = matches[0] if len(matches) == 1 else None
    if row is None:
        raise Http404('未知数据类型')
    if slug != row['slug']:
        query = urlencode({k: request.GET[k] for k in ('v', 'from', 'format') if k in request.GET})
        return HttpResponsePermanentRedirect(topics.row_url('type', row) + ('?' + query if query else ''))
    try:
        payload = detail_payload(slug, request.GET.get('v', ''), request.GET.get('from', ''))
    except (DataType.DoesNotExist, ValueError):
        raise Http404('未知版本或比较版本')
    if request.GET.get('format') == 'json':
        return _json({'kind': 'type', 'slug': slug, 'name': row['name'], 'major': payload['major'],
                      'snapshot': payload['snapshot'], 'from': payload['baseline']['major'] if payload['baseline'] else None,
                      'comparison': payload['delta']})
    return render(request, 'wiki/data_type_detail.html', context(payload, row['name'] + ' · 数据类型', payload['item']['summary'], topics.row_url('type', row)))
