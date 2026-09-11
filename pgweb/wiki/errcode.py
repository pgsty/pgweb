"""错误码大全的取数与组装。视图只负责拼上下文，这里负责形状。"""

from django.core.cache import cache

from .models import (DEPTHS, ErrorCode, ErrorCodeRelease, ErrorCodeText,
                     EVIDENCE_TIERS, SEVERITY_LABEL, TIER_LABEL)


CACHE_KEY = 'pgweb:wiki:errcode-index'
CACHE_SECONDS = 300

# 手册附录只给码和条件名。这里多给的四列都是能帮人做判断的：
# 一句话说明、严重级、证据强度、版本区间。
COLUMNS = ('错误码', '条件名', '说明', '严重级', '证据', '版本')


def summaries():
    """每个码的中文一句话与短名。263 行，一次查完。"""
    rows = {}
    for text in ErrorCodeText.objects.filter(lang='zh').only('errcode_id', 'name', 'summary'):
        rows[text.errcode_id] = {'name': text.name, 'summary': text.summary}
    return rows


def row_of(code, text):
    return {
        'sqlstate': code.sqlstate,
        'url': code.url,
        'condition_name': code.condition_name,
        'name': text.get('name', ''),
        'summary': text.get('summary', ''),
        'severity': code.severity,
        'severity_label': code.severity_label,
        'tier': code.evidence_tier,
        'tier_label': code.tier_label,
        'depth': code.depth,
        'status': code.status,
        'version_range': code.version_range,
        'versions': code.formal_present_in,
        'class_code': code.klass_id,
        'removed': code.status == 'removed',
    }


def index_payload():
    """导航索引 + 按类分组的大表格。"""
    text_of = summaries()
    groups, current = [], None
    for code in ErrorCode.objects.select_related('klass').all():
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
        current['rows'].append(row_of(code, text_of.get(code.sqlstate, {})))
    for group in groups:
        group['count'] = len(group['rows'])

    releases = list(ErrorCodeRelease.objects.all())
    return {
        'groups': groups,
        'columns': COLUMNS,
        'total': sum(group['count'] for group in groups),
        'class_count': len(groups),
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
        {'param': 'severity', 'label': '严重级', 'options': options('severity', SEVERITY_LABEL)},
        {'param': 'tier', 'label': '证据', 'options': options('tier', dict(EVIDENCE_TIERS))},
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


def forget():
    cache.delete(CACHE_KEY)


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


def fact_rows(code):
    """事实卡。留空的字段照实留空，不要编一个值出来。"""
    rows = [
        ('条件名', code.condition_name, ''),
        ('宏', '、'.join(code.macros), ''),
        ('类别', '{} {}'.format(code.klass.code, code.klass.label), code.klass.url),
        ('严重级', code.severity_label, ''),
        ('状态', code.status_label, ''),
    ]
    if code.aliases:
        rows.append(('别名宏', '、'.join(code.aliases), ''))
    if code.known_present_by:
        rows.append(('已知存在于', code.known_present_by + ' 起', ''))
    if code.introduced:
        release = (code.introduced or {}).get('release')
        if release:
            rows.append(('引入版本', release, ''))
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


def source_index(code):
    return {source.source_id: source for source in code.sources.all()}


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
        out.append({'type': 'section', 'section': section})
        for panel in placement.get(section.get('anchor'), ()):
            out.append({'type': panel})
    for panel in placement.get(None, ()):
        out.append({'type': panel})
    return out


def detail_payload(sqlstate, wanted_version=''):
    code = (ErrorCode.objects.select_related('klass')
            .prefetch_related('texts', 'sources', 'claims', 'cases', 'runtimes',
                              'messages__templates', 'presence')
            .get(sqlstate=sqlstate))
    texts = {text.lang: text for text in code.texts.all()}
    text = texts.get('zh') or texts.get('en')

    sources = source_index(code)
    claims = []
    for claim in code.claims.all():
        claims.append({
            'statement': claim.statement, 'method': claim.method, 'limits': claim.limits,
            'sources': [sources[s] for s in claim.sources if s in sources],
        })

    messages = []
    for message in code.messages.all():
        messages.append({
            'id': message.message_id,
            'severity': message.severity,
            'limits': message.limits,
            'path': message.path,
            'templates': list(message.templates.all()),
            'sources': [sources[s] for s in message.sources if s in sources],
        })

    gaps = ((code.facts.get('history_boundary') or {}).get('gaps')) or []
    version = pick_version(code, wanted_version)

    siblings = [c for c in ErrorCode.objects.filter(klass=code.klass).exclude(sqlstate=sqlstate)]

    sections = text.sections if text else []
    return {
        'code': code,
        'klass': code.klass,
        'text': text,
        'name': texts['zh'].name if 'zh' in texts else '',
        'sections': sections,
        'toc': [s for s in sections if s.get('anchor') and s.get('heading')],
        'blocks': blocks(sections, messages, list(code.cases.all()), claims,
                         list(code.sources.all()), list(code.runtimes.all())),
        'facts': fact_rows(code),
        'version_bar': version_bar(code),
        'versions': version_options(code),
        'version': version,
        'doc_url': '/docs/{}/{}'.format(version['value'], DOC_FILE) if version else '',
        'messages': messages,
        'claims': claims,
        'sources': list(code.sources.all()),
        'cases': list(code.cases.all()),
        'runtimes': list(code.runtimes.all()),
        'siblings': siblings,
        'gaps': gaps,
        'removed_without_evidence': code.status == 'removed' and not code.removed,
    }
