"""SQL 命令栏目的取数与页面上下文，契约见 docs/sqlcmd-column.md。"""

from collections import Counter
from copy import deepcopy
from html import escape

from bs4 import BeautifulSoup, NavigableString, Tag
from django.core.cache import cache
from django.db.models import BooleanField, Q
from django.db.models.expressions import RawSQL

from pgweb.docs.models import DocPage

from .models import SQLCMD_GROUPS, SQLCMD_GROUP_LABEL, SqlCommand
from .ruler import mark_ticks
from .sqlcmd_common import (STATUS_LABEL, compare, line_changes, major_of, sections_at,
                            version_rows)
from .sqlcmd_railroad import context as railroad_context

ROOT = '/docs/sql/'
CACHE_KEY = 'pgweb:wiki:sqlcmd-index'
VERSION_CACHE_KEY = 'pgweb:wiki:sqlcmd-versions2'
DOC_CACHE_KEY = 'pgweb:wiki:sqlcmd-docpages'
CHANGES_CACHE_KEY = 'pgweb:wiki:sqlcmd-changes:{}'
CACHE_SECONDS = 300
DEFER = ('versions', 'changes', 'editorial')
STATE_LABEL = {'absent': '不存在', 'present': '存在', 'added': '新增',
               'changed': '语法变化', 'removed': '移除'}


def versions():
    rows = cache.get(VERSION_CACHE_KEY)
    if rows is None:
        facts = list(SqlCommand.objects.values_list('present_in', 'changed_in'))
        majors = {major for present, _ in facts for major in present}
        majors.update(major_of(tree) for tree in DocPage.objects.filter(
            Q(version__gte=10) | Q(version=0), file='sql-commands.html')
            .values_list('version', flat=True))
        rows = version_rows(majors)
        previous = ''
        for version in rows:
            major = version['major']
            version.update(
                command_count=sum(major in present for present, _ in facts),
                added_count=sum(major in present and previous not in present
                                for present, _ in facts) if previous else 0,
                removed_count=sum(previous in present and major not in present
                                  for present, _ in facts) if previous else 0,
                changed_count=sum(major in changed for _, changed in facts),
                status_label=STATUS_LABEL[version['status']],
                url=ROOT + 'changes/{}/'.format(major),
                preview=version['status'] == 'preview', devel=version['status'] == 'devel',
                is_default=version['status'] == 'stable')
            previous = major
        if rows and not any(v['is_default'] for v in rows):
            rows[-1]['is_default'] = True
        mark_ticks(rows)
        cache.set(VERSION_CACHE_KEY, rows, CACHE_SECONDS)
    return rows


def default_major():
    return next((v['major'] for v in versions() if v['is_default']), '')


def pick_major(wanted, present, order=None):
    if wanted in present:
        return wanted
    order = versions() if order is None else order
    default = next((v['major'] for v in order if v['is_default']), '')
    return default if default in present else present[-1] if present else ''


def doc_pages():
    pages = cache.get(DOC_CACHE_KEY)
    if pages is None:
        pages = {('devel' if tree == 0 else major_of(tree), filename): title or ''
                 for tree, filename, title in DocPage.objects.filter(file__startswith='sql-')
                 .values_list('version', 'file', 'title')}
        cache.set(DOC_CACHE_KEY, pages, CACHE_SECONDS)
    return pages


def doc_url(snapshot, pages=None):
    if not snapshot:
        return ''
    pages = doc_pages() if pages is None else pages
    slug, filename = snapshot['slug'], snapshot['file']
    if (slug, filename) not in pages:
        return ''
    return '/docs/{}/{}{}'.format(slug, filename,
                                 '#' + snapshot['anchor'] if snapshot['anchor'] else '')


def forget():
    cached_versions = cache.get(VERSION_CACHE_KEY) or []
    cache.delete_many([CACHE_KEY, VERSION_CACHE_KEY, DOC_CACHE_KEY] +
                      [CHANGES_CACHE_KEY.format(v['major']) for v in cached_versions])


def baseline_note(order=None):
    order = versions() if order is None else order
    major = order[0]['major'] if order else ''
    return '{0} 是本数据集的收录基线，不代表该命令首次于 {0} 引入。'.format(major) if major else ''


def notice_of(version):
    if version['preview'] or version['devel']:
        return 'PostgreSQL {} 尚未正式发布；本页来自对应手册快照，内容仍可能变化。'.format(version['label'])
    if version['support_status'] == 'end-of-life':
        return 'PostgreSQL {} 为历史版本，已结束维护。'.format(version['label'])
    return ''


def removed_after(command, order):
    majors = [v['major'] for v in order]
    index = majors.index(command.last_version) if command.last_version in majors else len(majors)
    return majors[index + 1] if index + 1 < len(majors) else ''


def states_of(command, order):
    removed = removed_after(command, order)
    baseline = order[0]['major'] if order else ''
    return [(v['major'], 'removed' if v['major'] == removed else
             'absent' if v['major'] not in command.present_in else
             'added' if v['major'] == command.first_version and v['major'] != baseline else
             'changed' if v['major'] in command.changed_in else 'present') for v in order]


def strip_of(command, order):
    """版本变动：一排方格，每格一个版本，与表头刻度一一对应。"""
    return [{'major': major, 'state': state,
             'label': '{} · {}'.format(major, STATE_LABEL[state])}
            for major, state in states_of(command, order)]


def row_of(command, order):
    removed = removed_after(command, order)
    # 关键词去重，避免 CREATE TABLE 一条 100 多行的概要重复撑大 HTML 属性。
    keywords = ' '.join(dict.fromkeys(command.synopsis.split()))
    return {'slug': command.slug, 'name': command.name, 'url': command.url,
            'verb': command.verb, 'object': command.object, 'group': command.group,
            'verb_filter': command.verb if command.verb in ('CREATE', 'ALTER', 'DROP') else 'other',
            'purpose_zh': command.purpose_zh, 'purpose': command.purpose,
            'first': command.first_version, 'last': command.last_version,
            'baseline': bool(order and command.first_version == order[0]['major']),
            'removed': bool(removed), 'removed_in': removed,
            'change_count': len(command.changed_in),
            'last_change': command.changed_in[-1] if command.changed_in else '',
            'synopsis_lines': len(command.synopsis.splitlines()),
            'strip': strip_of(command, order), 'present_tokens': ' '.join(command.present_in),
            'text': ' '.join([command.name, command.purpose_zh, command.purpose,
                              *command.aliases, keywords])}


def groups_of(rows):
    return [{'slug': slug, 'label': label, 'eyebrow': eyebrow, 'anchor': 'group-' + slug,
             'count': sum(row['group'] == slug for row in rows),
             'rows': [row for row in rows if row['group'] == slug]}
            for slug, label, eyebrow in SQLCMD_GROUPS]


def filters_of(rows, order):
    groups = Counter(row['group'] for row in rows)
    verbs = Counter(row['verb_filter'] for row in rows)
    first = Counter(row['first'] for row in rows)
    present = Counter(v for row in rows for v in row['present_tokens'].split())
    return [
        {'param': 'group', 'label': '分组', 'options': [
            {'value': slug, 'label': label, 'count': groups[slug]} for slug, label, _ in SQLCMD_GROUPS]},
        {'param': 'verb', 'label': '动词', 'options': [
            {'value': v, 'label': label, 'count': verbs[v]}
            for v, label in [('CREATE', 'CREATE'), ('ALTER', 'ALTER'), ('DROP', 'DROP'), ('other', '其它')]]},
        {'param': 'first', 'label': '引入版本', 'options': [
            {'value': v['major'], 'label': v['label'], 'count': first[v['major']]}
            for v in reversed(order) if first[v['major']]]},
        {'param': 'present', 'label': '存在于版本', 'options': [
            {'value': v['major'], 'label': v['label'], 'count': present[v['major']]}
            for v in reversed(order)]},
    ]


def index():
    payload = cache.get(CACHE_KEY)
    if payload is None:
        order = versions()
        rows = [row_of(command, order) for command in SqlCommand.objects.defer(*DEFER)]
        payload = {
            'total': len(rows), 'group_count': len(SQLCMD_GROUPS), 'default_major': default_major(),
            'earliest_major': order[0]['major'] if order else '',
            'latest_major': order[-1]['major'] if order else '',
            'versions': order, 'groups': groups_of(rows), 'filters': filters_of(rows, order),
            'stats': {'commands': len(rows), 'versions': len(order),
                      'snapshots': sum(len(row['present_tokens'].split()) for row in rows),
                      'synopsis_changes': sum(row['change_count'] for row in rows),
                      'removed': sum(row['removed'] for row in rows)},
        }
        cache.set(CACHE_KEY, payload, CACHE_SECONDS)
    return payload


def find_command(slug):
    try:
        return SqlCommand.objects.get(slug=slug.lower())
    except SqlCommand.DoesNotExist:
        command = (SqlCommand.objects.annotate(alias_match=RawSQL(
            'EXISTS (SELECT 1 FROM unnest(aliases) AS alias WHERE lower(alias) = lower(%s))',
            (slug,), output_field=BooleanField())).filter(alias_match=True).first())
        if command is None:
            raise SqlCommand.DoesNotExist(slug)
        return command


def previous_major(command, major):
    position = command.present_in.index(major) if major in command.present_in else 0
    return command.present_in[position - 1] if position else ''


def html_lines(html):
    """在换行处闭合并重开行内标签；跨行 em/code 也不会破坏生成的 HTML。"""
    soup = BeautifulSoup(html, 'html.parser')
    lines, stack = [''], []

    def visit(node):
        if isinstance(node, NavigableString):
            parts = str(node).split('\n')
            for index, part in enumerate(parts):
                if index:
                    lines[-1] += ''.join('</{}>'.format(name) for name, _ in reversed(stack))
                    lines.append(''.join(start for _, start in stack))
                lines[-1] += escape(part, quote=False)
        elif isinstance(node, Tag):
            attrs = ''.join(' {}="{}"'.format(key, escape(' '.join(value) if isinstance(value, list)
                                                          else str(value), quote=True))
                            for key, value in node.attrs.items())
            start = '<{}{}>'.format(node.name, attrs)
            lines[-1] += start
            if node.name == 'br':
                return
            stack.append((node.name, start))
            for child in node.children:
                visit(child)
            stack.pop()
            lines[-1] += '</{}>'.format(node.name)
    for node in soup.children:
        visit(node)
    return lines


def synopsis_of(snapshot, previous, major):
    raw = snapshot['synopsis_html'].strip('\n')
    lines = html_lines(raw)
    text = BeautifulSoup(raw, 'html.parser').get_text()
    plain = text.splitlines()
    _, added = line_changes(previous['synopsis_text'], snapshot['synopsis_text']) if previous else (None, set())
    rendered = []
    for index, line in enumerate(lines):
        cls = 'cmd-synopsis__line' + (' is-added' if index in added else '')
        title = ' title="PostgreSQL {} 新增"'.format(escape(major)) if index in added else ''
        rendered.append('<span class="{}"{}>{}</span>'.format(cls, title, line))
    return {'html': '\n'.join(rendered), 'text': snapshot['synopsis_text'],
            'lines': [{'text': line, 'state': 'added' if i in added else 'same'}
                      for i, line in enumerate(plain)]}


def change_note(command, major, order, change):
    previous = previous_major(command, major)
    if order and major == order[0]['major']:
        return baseline_note(order)
    if change and change['status'] == 'added':
        note = 'PostgreSQL {} 新增此命令。'.format(major)
    elif change and change['synopsis']:
        note = '相对 PostgreSQL {}：语法概要新增 {} 行，移除 {} 行。'.format(
            change['from'], len(change['synopsis']['added']), len(change['synopsis']['removed']))
    elif change and (any(change['sections'].values()) or change['purpose_changed']):
        note = '相对 PostgreSQL {} 语法未变，正文有更新。'.format(change['from'])
    else:
        note = '相对 PostgreSQL {} 无变化。'.format(previous) if previous else ''
    if change and change['renamed']:
        note += '手册文件由 {} 改为 {}。'.format(change['renamed']['from_file'], change['renamed']['to_file'])
    return note


def detail(slug, wanted_major=''):
    command = find_command(slug)
    order = versions()
    major = pick_major(wanted_major, command.present_in, order)
    by_major = {v['major']: v for v in order}
    if not major or major not in by_major:
        raise SqlCommand.DoesNotExist(slug)
    version = by_major[major]
    snapshot = command.versions[major]
    previous = previous_major(command, major)
    change = next((c for c in command.changes if c['to'] == major and c['status'] != 'removed'), None)
    sections = deepcopy(sections_at(command.versions, major))
    counts = Counter()
    for section in sections:
        counts[section['key']] += 1
        section['anchor'] = section['key'] + ('-' + str(counts[section['key']])
                                             if counts[section['key']] > 1 else '')
    pages = doc_pages()
    local = doc_url(snapshot, pages)
    official = 'https://www.postgresql.org/docs/{}/{}{}'.format(
        snapshot['slug'], snapshot['file'], '#' + snapshot['anchor'] if snapshot['anchor'] else '')
    document = {'major': major, 'borrowed': False, 'local_url': local, 'official_url': official,
                'label': 'PostgreSQL {} 手册'.format(version['label'])}
    related_names = snapshot['related']
    related_rows = {c.slug: c for c in SqlCommand.objects.filter(slug__in=related_names)
                    .only('slug', 'name', 'purpose_zh', 'present_in')}
    related = [{'slug': name, 'name': related_rows[name].name if name in related_rows else name,
                'url': '{}{}{}?v={}'.format(ROOT, name, '/', major) if name in related_rows else '',
                'purpose_zh': related_rows[name].purpose_zh if name in related_rows else '',
                'exists': name in related_rows} for name in related_names]
    removed = removed_after(command, order)
    facts = [
        {'label': label, 'value': value, 'mono': mono, 'url': url} for label, value, mono, url in (
            ('动词', command.verb, True, ''), ('对象', command.object or '—', True, ''),
            ('分组', command.group_label, False, ROOT + '#group-' + command.group),
            ('引入版本', command.first_version + ('（基线）' if command.first_version == order[0]['major'] else ''), False, ''),
            ('状态', '于 {} 移除'.format(removed) if removed else '现存', False, ''),
            ('语法变更次数', str(len(command.changed_in)), False, ''),
            ('手册小节数', str(len(sections)), False, ''),
        )]
    return {
        'command': command, 'name': snapshot['name'], 'slug': command.slug,
        'group': command.group, 'group_label': command.group_label, 'eyebrow': command.eyebrow,
        'verb': command.verb, 'object': command.object, 'version': version,
        'previous_major': previous, 'snapshot': snapshot, 'facts': facts,
        'railroad': railroad_context(snapshot, 'rr-command-' + command.slug + '-' + major),
        'synopsis': synopsis_of(snapshot, command.versions.get(previous), major),
        'synopsis_diff': change['synopsis'] if change else None, 'sections': sections,
        'ribbon': [dict(by_major[m], state=state, current=m == major,
                        url=command.url + '?v=' + m if m in command.present_in else '',
                        doc_url=doc_url(command.versions.get(m), pages))
                   for m, state in states_of(command, order)],
        'change': change, 'change_note': change_note(command, major, order, change),
        'notice': notice_of(version), 'doc': document,
        'timeline': [dict(c, url=command.url + '?v=' + c['to'] if c['to'] in command.present_in else '')
                     for c in reversed(command.changes)],
        'related': related, 'editorial': command.editorial,
        'links': {'doc': local, 'doc_label': document['label'], 'official': official},
        'doc_versions': [dict(v, url=doc_url(command.versions[v['major']], pages)) for v in order
                         if v['major'] in command.versions and doc_url(command.versions[v['major']], pages)],
        'siblings': [dict(g, current=command.slug) for g in index()['groups'] if g['slug'] == command.group],
        'current': command.slug, 'versions': order,
    }


def card_of(command, major, purpose=None):
    return {'slug': command.slug, 'name': command.name, 'url': command.url + '?v=' + major,
            'group': command.group, 'group_label': command.group_label,
            'purpose_zh': command.purpose_zh if purpose is None else purpose,
            'verb': command.verb, 'object': command.object}


def changes(major, from_major=''):
    if from_major:
        return changes_payload(major, from_major)
    key = CHANGES_CACHE_KEY.format(major)
    payload = cache.get(key)
    if payload is None:
        payload = changes_payload(major)
        cache.set(key, payload, CACHE_SECONDS)
    return payload


def changes_payload(major, from_major=''):
    order = versions()
    by_major = {v['major']: v for v in order}
    if major not in by_major:
        raise SqlCommand.DoesNotExist(major)
    majors = list(by_major)
    position = majors.index(major)
    natural = majors[position - 1] if position else ''
    from_major = from_major if from_major in by_major and from_major != major else ''
    base = from_major or natural
    arbitrary = bool(from_major and from_major != natural)
    buckets = {key: [] for key in ('added', 'removed', 'renamed', 'synopsis_changed', 'sections_changed')}
    if base:
        queryset = SqlCommand.objects.filter(Q(present_in__contains=[base]) | Q(present_in__contains=[major]))
        if arbitrary:
            # 按命令加载快照，解析比较两版所引用的小节；不取编辑分析与预存变化。
            queryset = queryset.defer('editorial', 'changes')
        else:
            queryset = queryset.defer('versions', 'editorial').annotate(
                right_purpose=RawSQL('versions -> %s ->> %s', (major, 'purpose_zh')),
                left_purpose=RawSQL('versions -> %s ->> %s', (base, 'purpose_zh')))
        for command in queryset:
            if arbitrary:
                left, right = command.versions.get(base), command.versions.get(major)
                left = dict(left, sections=sections_at(command.versions, base)) if left else None
                right = dict(right, sections=sections_at(command.versions, major)) if right else None
                change = compare(left, right, base, major)
                purpose = (right or left or {}).get('purpose_zh', '')
            else:
                change = next((c for c in command.changes if c['from'] == base and c['to'] == major), None)
                purpose = command.right_purpose if major in command.present_in else command.left_purpose
            if not change:
                continue
            card = card_of(command, base if change['status'] == 'removed' else major, purpose)
            if change['status'] in ('added', 'removed'):
                buckets[change['status']].append(card)
                continue
            if change['renamed']:
                buckets['renamed'].append(dict(card, **change['renamed']))
            if change['synopsis']:
                diff = change['synopsis']
                buckets['synopsis_changed'].append(dict(card, added_lines=len(diff['added']),
                    removed_lines=len(diff['removed']), sample=next(iter(diff['added']), '')))
            elif any(change['sections'].values()) or change['purpose_changed']:
                buckets['sections_changed'].append(card)
    return dict(buckets,
        version=by_major[major], previous=by_major.get(base), from_major=from_major, arbitrary=arbitrary,
        versions=[dict(v, is_current=v['major'] == major) for v in order],
        notice=notice_of(by_major[major]), baseline_note=baseline_note(order) if not base else '',
        summary={key: len(items) for key, items in buckets.items()}, baseline=not base,
        baseline_groups=groups_of([r for g in index()['groups'] for r in g['rows']
                                    if major in r['present_tokens'].split()]) if not base else [])
