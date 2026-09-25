"""错误码大全的取数与组装。视图只负责拼上下文，这里负责形状。"""

import re
from base64 import urlsafe_b64encode
from copy import deepcopy

from django.core.cache import cache

from .models import (DEPTHS, ErrorCode, ErrorCodeRelease,
                     EVIDENCE_TIERS, SEVERITY_LABEL, TIER_LABEL)


CACHE_KEY = 'pgweb:wiki:errcode-index:v2'
CACHE_SECONDS = 300

# 手册附录只给码和条件名；这里再给宏名称、严重等级与已知版本范围，说明另起一行。
COLUMNS = ('状态码', '条件名', '宏名称', '严重等级', '版本')


def major_of(version):
    """'9.1.0' → '9.1'，'12.0' → '12'，'7.4' → '7.4'。"""
    parts = str(version or '').split('.')
    if not parts or not parts[0]:
        return ''
    return '.'.join(parts[:2]) if int(parts[0]) < 10 else parts[0]


def since_of(code):
    """Preserve exact patch boundaries; known_present_by is only an observed lower bound."""
    return (code.introduced or {}).get('release') or code.known_present_by or (
        code.present_in[0] if code.present_in else '')


def since_label(code):
    return '引入版本' if (code.introduced or {}).get('release') else '最早已知存在'


def until_of(code, majors=()):
    return (code.removed or {}).get('release', '')


def status_text(code, majors=()):
    if code.status != 'removed':
        return '预发行' if code.status == 'preview' else '有效'
    until = until_of(code)
    return '于 {} 移除'.format(until) if until else '已移除（边界未取证）'


def row_of(code, text, majors=()):
    return {
        'status_text': status_text(code),
        'sqlstate': code.sqlstate,
        'url': code.url,
        'condition_name': code.condition_name,
        'macro': code.primary_macro or (code.macros[0] if code.macros else ''),
        'name': text.get('name', ''),
        'summary': text.get('summary', ''),
        'severity': code.severity,
        'severity_label': code.severity_label,
        'tier': code.evidence_tier,
        'tier_label': code.tier_label,
        'depth': code.depth,
        'status': code.status,
        'since': since_of(code),
        'since_label': since_label(code),
        'until': until_of(code, majors),
        'version_range': code.version_range,
        'versions': code.formal_present_in,
        'class_code': code.klass_id,
        'removed': code.status == 'removed',
    }


def index_payload():
    """导航索引 + 按类分组的大表格。"""
    releases = list(ErrorCodeRelease.objects.all())
    majors = [r.major for r in releases]
    groups, current = [], None
    for code in ErrorCode.objects.select_related('klass').defer('facts', 'texts', 'evidence'):
        if current is None or current['code'] != code.klass_id:
            current = {
                'code': code.klass.code,
                'anchor': code.klass.anchor,
                'name': code.klass.name,
                'name_zh': code.klass.name_zh,
                'label': code.klass.label,
                'summary': code.klass.summary,
                'rows': [],
            }
            groups.append(current)
        current['rows'].append(row_of(code, {'name': code.name_zh, 'summary': code.summary_zh}, majors))
    for group in groups:
        group['count'] = len(group['rows'])

    return {
        'groups': groups,
        'columns': COLUMNS,
        'total': sum(group['count'] for group in groups),
        'class_count': len(groups),
        'latest_major': releases[-1].major if releases else '',
        'latest_release': releases[-1].release if releases else '',
        'earliest_major': min((row['since'] for g in groups for row in g['rows'] if row['since']),
                              key=lambda v: [int(p) for p in v.split('.')], default=''),
        'releases': releases,
        'formal_releases': [r for r in releases if not r.is_preview],
        'filters': filters(groups),
        'stats': stats(groups),
    }


def filters(groups):
    """筛选下拉。计数就地算，不再查库。"""
    rows = [row for group in groups for row in group['rows']]

    def options(key, labels):
        counts = {}
        for row in rows:
            counts[row[key]] = counts.get(row[key], 0) + 1
        return [{'value': value, 'label': labels.get(value, value), 'count': counts[value]}
                for value in sorted(counts, key=lambda v: -counts[v]) if counts.get(value)]

    return [
        {'param': 'class', 'label': '类别',
         'options': [{'value': g['code'], 'label': '{} {}'.format(g['code'], g['label']),
                      'count': g['count']} for g in groups]},
        {'param': 'severity', 'label': '严重等级', 'options': options('severity', SEVERITY_LABEL)},
        {'param': 'depth', 'label': '深度', 'options': options('depth', dict(DEPTHS))},
    ]


def stats(groups):
    rows = [row for group in groups for row in group['rows']]
    tiers = {}
    for row in rows:
        tiers[row['tier']] = tiers.get(row['tier'], 0) + 1
    return {
        'total': len(rows),
        'classes': len(groups),
        'tiers': [{'key': key, 'label': TIER_LABEL.get(key, key), 'count': tiers.get(key, 0)}
                  for key, _ in reversed(EVIDENCE_TIERS) if tiers.get(key)],
    }


def index(request=None):
    payload = cache.get(CACHE_KEY)
    if payload is None:
        payload = index_payload()
        cache.set(CACHE_KEY, payload, CACHE_SECONDS)
    return payload


def class_nav(current=''):
    """The 44 classes as the sub-navigation under SQL 状态码 in the side card."""
    return [{'title': '{} {}'.format(g['code'], g['label']), 'link': '/docs/sqlstate/#' + g['anchor'],
             'active': g['code'] == current} for g in index()['groups']]


def sibling_groups(class_code):
    """The index table restricted to one class, for the bottom of a detail page."""
    return [g for g in index()['groups'] if g['code'] == class_code]


def forget():
    cache.delete_many([CACHE_KEY, DOC_CACHE_KEY, 'pgweb:wiki:errcode-index'])


# ---------------------------------------------------------------- 详情页

DOC_FILE = 'errcodes-appendix.html'
DOC_CACHE_KEY = 'pgweb:wiki:errcode-docmajors'


def doc_majors():
    """本站有中文《附录 A 错误代码》译文的大版本。"""
    majors = cache.get(DOC_CACHE_KEY)
    if majors is None:
        from pgweb.docs.models import DocPage
        majors = sorted({str(v).split('.')[0]
                         for v in DocPage.objects.filter(file=DOC_FILE).values_list('version', flat=True)})
        cache.set(DOC_CACHE_KEY, majors, CACHE_SECONDS)
    return majors


def version_options(code):
    """版本选择器。只切本站手册链接——源码证据锚在它被核验的那个提交上，切不了。"""
    available = set(doc_majors())
    options = [{'value': major, 'label': major, 'preview': False, 'has_doc': major in available}
               for major in code.formal_present_in]
    for major in code.preview_in:
        options.append({'value': major, 'label': major + ' 预发行', 'preview': True,
                        'has_doc': major in available})
    return options


def pick_version(code, wanted):
    """默认落在最新正式版，不落在预发行——预发行要读得明确选。"""
    options = [o for o in version_options(code) if o['has_doc']]
    if not options:
        return None
    for option in options:
        if option['value'] == wanted:
            return option
    formal = [o for o in options if not o['preview']]
    return (formal or options)[-1]


def card(code):
    """详情页顶部的事实卡：类别与严重等级 / 条件名与宏名称 / 起始版本与状态。"""
    return {
        'macro': code.primary_macro or (code.macros[0] if code.macros else ''),
        'aliases': [m for m in code.macros if m != code.primary_macro] + list(code.aliases),
        'since': since_of(code),
        'since_label': since_label(code),
        'status_text': status_text(code),
    }


def version_groups(code):
    """本站手册里有附录 A 的版本，按受支持、历史、预发行与开发版分组，链接到该版的附录 A。

    只列本站已加载的手册版本；该版本不含此状态码时只显示、不链接。
    """
    from pgweb.docs.versions import manual_groups
    available = set(doc_majors())
    groups = manual_groups()
    present = set(code.present_in)
    sampled = {r.major: r for r in ErrorCodeRelease.objects.all()}

    def entry(major, label, tree):
        if str(tree) not in available:
            return None
        major = str(major)
        is_present = major in present
        release = sampled.get(major)
        state = 'present' if is_present else 'absent' if release else 'unknown'
        note = ('已收录：' if is_present else '未定义于已采样构建：') + release.release if release else '尚未采样'
        return {'major': major, 'label': label, 'present': is_present, 'state': state, 'note': note,
                'url': '/docs/{}/{}'.format('devel' if tree == 0 else major, DOC_FILE)}

    supported = [entry(m, str(m), m) for m in groups['supported']]
    historical = [entry(m, str(m), m) for m in groups['historical']]
    special = [entry(t['major'], '{} {}'.format(t['major'], t['label']), t['major']) for t in groups['testing']]
    if groups['devel']:
        special.append(entry(groups['devel'], '{} dev'.format(groups['devel']), 0))
    return [{'kind': kind, 'items': [e for e in items if e]}
            for kind, items in (('supported', supported), ('historical', historical), ('special', special))
            if any(items)]


def fact_rows(code):
    """事实卡。留空的字段照实留空，不要编一个值出来。"""
    rows = [
        ('条件名', code.condition_name, ''),
        ('宏名称', '、'.join(code.macros), ''),
        ('类别', '{} {}'.format(code.klass.code, code.klass.label), code.klass.url),
        ('严重等级', code.severity_label, ''),
        ('状态', code.status_label, ''),
    ]
    if code.aliases:
        rows.append(('别名宏', '、'.join(code.aliases), ''))
    rows.append((since_label(code), since_of(code), ''))
    rows.append(('移除版本', until_of(code), ''))
    rows.append(('版本覆盖', code.version_range, ''))
    return [{'label': label, 'value': value, 'url': url} for label, value, url in rows if value]


def version_bar(code):
    present = set(code.present_in)
    bar = []
    for release in ErrorCodeRelease.objects.all():
        bar.append({
            'major': release.major,
            'release': release.release,
            'tag': release.tag,
            'present': release.major in present,
            'preview': release.is_preview,
        })
    return bar




REPO_BLOB = 'https://github.com/pgsty/err.pg.center/blob/main/'
LINES_RE = re.compile(r'#L(\d+)(?:-L(\d+))?$')


def source_rows(code):
    """「来源」一节的结构化渲染：上游源码在前，本仓库的核验材料在后。"""
    rows = []
    for source in code.evidence.get('sources', []):
        upstream = source['kind'] == 'upstream_source'
        match = LINES_RE.search(source['url'] or '')
        lines = ''
        if match:
            lines = match.group(1) if not match.group(2) or match.group(2) == match.group(1) \
                else '{}–{}'.format(match.group(1), match.group(2))
        rows.append({
            'id': source['source_id'],
            'anchor': evidence_anchor('sources', source['source_id']),
            'upstream': upstream,
            'path': source['path'],
            'url': source['url'] or (REPO_BLOB + source['path'] if source['path'] else ''),
            'lines': lines,
            'tag': source['tag'],
            'commit': source['commit'][:9],
            'sha': source['sha256'],
            'sha_short': source['sha256'][:8],
            'docs_url': source['docs_url'],
        })
    rows.sort(key=lambda r: (not r['upstream'], r['id']))
    return rows


# 结构化面板挂在哪一节之后。正文里没有那一节时，用退路锚点。
PANEL_AFTER = (
    ('templates', 'messages', 'meaning'),
    ('cases', 'response', 'diagnosis'),
    ('evidence', 'sources', 'versions'),
)


def blocks(sections, messages, cases, claims, sources, runtimes):
    """把正文小节与结构化面板排成一条渲染序列。

    报文模板、可复现案例、证据链都是数据库里的结构化内容，插在讲同一件事的
    那一节后面；正文里没有对应小节时挂到退路锚点，实在没有就落到末尾。
    """
    available = {
        'templates': bool(messages),
        'cases': bool(cases),
        'evidence': bool(claims or sources or runtimes),
    }
    anchors = [s.get('anchor') for s in sections]
    placement = {}
    for panel, preferred, fallback in PANEL_AFTER:
        if not available[panel]:
            continue
        anchor = preferred if preferred in anchors else (fallback if fallback in anchors else None)
        placement.setdefault(anchor, []).append(panel)

    out = []
    for section in sections:
        # 「来源」一节由结构化的源码出处渲染，不用正文里的哈希清单。
        out.append({'type': 'sources_section' if section.get('anchor') == 'sources' and sources else 'section',
                    'section': section})
        for panel in placement.get(section.get('anchor'), ()):
            out.append({'type': panel})
    for panel in placement.get(None, ()):
        out.append({'type': panel})
    return out


KIND_LABELS = {'primary': '主消息', 'detail': 'DETAIL', 'hint': 'HINT', 'context': 'CONTEXT'}
EVIDENCE_LABELS = {'sources': '来源', 'claims': '断言', 'messages': '报文',
                   'runtimes': '运行记录', 'cases': '案例'}


def evidence_anchor(kind, identity):
    return 'evidence-' + kind + '-' + urlsafe_b64encode(identity.encode()).decode().rstrip('=')


def evidence_records(code):
    records = deepcopy(code.evidence)
    targets = {}
    for kind, label in EVIDENCE_LABELS.items():
        for row in records.get(kind, []):
            identity = row[kind[:-1] + '_id']
            row['anchor'] = evidence_anchor(kind, identity)
            url = row.get('url') or (REPO_BLOB + row['path'] if kind == 'sources' and row.get('path') else '')
            target = dict(kind=kind, label=label, id=identity,
                          url=url or '#' + row['anchor'], external=bool(url),
                          text=row.get('path') or identity, location=row.get('location', ''),
                          tag=row.get('tag', ''), unresolved=False)
            targets.setdefault(identity, []).append(target)

    def resolve(ids, kind=None):
        result = []
        for identity in ids:
            matches = [t for t in targets.get(identity, []) if kind is None or t['kind'] == kind]
            result.extend(matches or [dict(id=identity, text=identity, unresolved=True)])
        return result

    for claim in records.get('claims', []):
        claim['references'] = resolve(claim['sources']) + resolve(claim['runtime'], 'runtimes')
    for message in records.get('messages', []):
        message['references'] = resolve(message['sources'])
        for template in message['templates']:
            template['kind_label'] = KIND_LABELS.get(template['kind'], template['kind'])
    for run in records.get('runtimes', []):
        run['references'] = resolve(run['cases'], 'cases')
    return records


def detail_payload(sqlstate, wanted_version=''):
    code = ErrorCode.objects.select_related('klass').get(sqlstate=sqlstate)
    text = code.texts.get('zh') or code.texts.get('en') or {}
    evidence = evidence_records(code)
    sources, claims, cases, runtimes, messages = [evidence.get(key, [])
                                                for key in ('sources', 'claims', 'cases', 'runtimes', 'messages')]
    gaps = ((code.facts.get('history_boundary') or {}).get('gaps')) or []
    version = pick_version(code, wanted_version)
    sections = [s for s in text.get('sections', [])
                if s.get('heading') or not re.match(r'^\s*(<|&lt;)h1', s.get('html', ''))]
    if sources and not any(s.get('anchor') == 'sources' for s in sections):
        sections.append({'anchor': 'sources', 'heading': '来源', 'html': ''})
    return {
        'code': code, 'klass': code.klass, 'text': text, 'name': code.name_zh,
        'sections': sections,
        'toc': [s for s in sections if s.get('anchor') and s.get('heading')],
        'blocks': blocks(sections, messages, cases, claims, sources, runtimes),
        'facts': fact_rows(code), 'card': card(code),
        'version_groups': version_groups(code), 'version_bar': version_bar(code),
        'versions': version_options(code), 'version': version,
        'doc_url': '/docs/{}/{}'.format(version['value'], DOC_FILE) if version else '',
        'messages': messages, 'claims': claims, 'sources': sources, 'source_rows': source_rows(code),
        'cases': cases, 'runtimes': runtimes, 'sibling_groups': sibling_groups(code.klass_id),
        'gaps': gaps, 'removed_without_evidence': code.status == 'removed' and not code.removed,
    }
