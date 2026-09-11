"""从 pgsty/err.pg.center 仓库导入错误码大全。

两步：`export_snapshot()` 把仓库读成一份自包含快照，`import_snapshot()` 把快照写进库。
拆开是为了让同一份快照分别加载本地与生产，两端结果一致；也让导入不必要求
生产机上有源仓库。

导入读权威三层：`data/errcodes/*.json`、`evidence/<CODE>.json`、`content/docs/*.md`。
`static/data/` 是作者从这三层生成的发布视图，不作为输入。
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

from django.db import transaction

from . import markup
from .models import (ErrorCode, ErrorCodeCase, ErrorCodeClaim, ErrorCodeClass, ErrorCodeMessage,
                     ErrorCodePresence, ErrorCodeRelease, ErrorCodeRuntime, ErrorCodeSource,
                     ErrorCodeTemplate, ErrorCodeText, TIER_ORDER)


FORMAT = 1
DEFAULT_ROOT = os.path.expanduser('~/pg.center/err')

CODE_FILE = re.compile(r'^[0-9A-Z]{5}$')

# 这些数组是逐补丁版审计记录，合计十一万余行，内容是「9.0.7 里仍然存在」这类重复。
# 作者已经把同样的信息压成了 presence_intervals，站点存区间。源仓库保留全量。
BULK_KEYS = ('observed_rows', 'observed_in_releases', 'evidence_refs',
             'pre9_observed_rows', 'pre9_present_in_releases', 'pre9_evidence_refs',
             'author_evidence')


def trim_facts(facts):
    """留底用的事实：去掉巨型审计数组与已经拆表的证据块。"""
    out = {k: v for k, v in facts.items() if k not in BULK_KEYS}
    boundary = out.get('history_boundary')
    if isinstance(boundary, dict):
        boundary = dict(boundary)
        pre = boundary.get('pre_range')
        if isinstance(pre, dict):
            pre = {k: v for k, v in pre.items() if k != 'evidence_refs'}
            boundary['pre_range'] = pre
        out['history_boundary'] = boundary
    intervals = out.get('presence_intervals')
    if isinstance(intervals, list):
        out['presence_intervals'] = [{k: v for k, v in i.items() if k != 'evidence_refs'}
                                     for i in intervals]
    pre_intervals = out.get('pre9_presence_intervals')
    if isinstance(pre_intervals, list):
        out['pre9_presence_intervals'] = [{k: v for k, v in i.items() if k != 'evidence_refs'}
                                          for i in pre_intervals]
    return out


# ------------------------------------------------------------------ 正文解析

FRONT_MATTER = re.compile(r'^---\n(.*?)\n---\n', re.S)
FM_SCALAR = re.compile(r'^(?P<key>[a-z_]+):\s*(?P<value>.*?)\s*$', re.M)
TITLE_SPLIT = re.compile(r'^\s*[0-9A-Z]{5}\s*[—–-]\s*')


def front_matter(text):
    """够用的 front matter 解析：全是标量，只有 translation 一层嵌套。"""
    match = FRONT_MATTER.match(text)
    if not match:
        return {}, text
    raw, body = match.group(1), text[match.end():]
    data = {}
    for line in raw.split('\n'):
        if line.startswith('  ') and 'translation' in data:
            key, _, value = line.strip().partition(':')
            data['translation'][key.strip()] = value.strip().strip('"')
        elif line.strip() == 'translation:':
            data['translation'] = {}
        else:
            found = FM_SCALAR.match(line)
            if found:
                data[found.group('key')] = found.group('value').strip('"')
    return data, body


def chinese_name(title, sqlstate, condition_name):
    """中文短名。标题有四种写法，取不出中文就留空，不要回落到英文。"""
    text = TITLE_SPLIT.sub('', title or '')
    if condition_name:
        text = text.replace(condition_name, '')
    text = text.strip(' 　:：()（）')
    return text if re.search(r'[一-鿿]', text) else ''


# ------------------------------------------------------------------ 链接改写

REL_CODE = re.compile(r'\]\((?:\.\./)+([0-9a-zA-Z]{5})/\)')
REL_EVIDENCE = re.compile(r'\]\((?:\.\./)+data/evidence/[0-9a-zA-Z]{5}\.json\)')
REL_CASES = re.compile(r'\]\((?:\.\./)+data/cases/[0-9a-zA-Z]{5}\.json\)')
REL_GUIDES = re.compile(r'\[([^\]]*)\]\((?:\.\./)+guides/\)')
PG_DOCS = re.compile(r'https://www\.postgresql\.org/docs/(?P<version>[0-9]+(?:\.[0-9]+)?)/(?P<file>[A-Za-z0-9_.-]+\.html)(?P<anchor>#[A-Za-z0-9_.-]+)?')


def rewrite_links(body, local_doc):
    """把源仓库的相对链接换成站内地址。

    源码链接锁在固定 commit 上，原样保留——那正是要的效果。
    """
    body = REL_CODE.sub(lambda m: '](/wiki/errcode/{}/)'.format(m.group(1).upper()), body)
    body = REL_EVIDENCE.sub('](#sources)', body)
    body = REL_CASES.sub('](#cases)', body)
    # 驱动指南没有搬进本站，留文字去链接，不留死链。
    body = REL_GUIDES.sub(r'\1', body)

    def doc(match):
        version, filename = match.group('version'), match.group('file')
        if local_doc(version, filename):
            return '/docs/{}/{}{}'.format(version, filename, match.group('anchor') or '')
        return match.group(0)

    return PG_DOCS.sub(doc, body)


def doc_checker():
    """本站有译文的手册页集合，用来判断 postgresql.org 链接能不能换成站内地址。"""
    try:
        from pgweb.docs.models import DocPage
        pairs = set()
        for version, filename in DocPage.objects.values_list('version', 'file'):
            major = str(version).split('.')[0]
            pairs.add((major, filename))
            pairs.add((str(version), filename))
    except Exception:
        return lambda version, filename: False
    return lambda version, filename: (version, filename) in pairs


# ------------------------------------------------------------------ 报文模板

PLACEHOLDER = re.compile(r'%[0-9]*\$?[a-zA-Z]|\{[a-z_]+\}')

TEMPLATE_FIELDS = (
    ('primary_template', 'primary', ''),
    ('primary_template_singular', 'primary', 'singular'),
    ('primary_template_plural', 'primary', 'plural'),
    ('alternate_template', 'primary', 'alternate'),
    ('detail_template', 'detail', ''),
    ('hint_template', 'hint', ''),
    ('context_template', 'context', ''),
)
TEMPLATE_LISTS = (('detail_templates', 'detail'), ('hint_templates', 'hint'),
                  ('primary_templates', 'primary'))
TEMPLATE_VARIANTS = (('primary_variants', 'primary'), ('detail_variants', 'detail'),
                     ('hint_variants', 'hint'))


def literal_of(template):
    """模板去掉占位符后的字面部分，供报文反查匹配。"""
    return ' '.join(PLACEHOLDER.sub(' ', template or '').split())


def flatten_templates(message):
    """把一条报文记录里所有形态的模板摊平。

    只认 `primary_template` 会漏掉走单复数分支、变体数组和角色映射的那些码。
    """
    rows = []

    def add(kind, role, value):
        if isinstance(value, str) and value.strip():
            rows.append({'kind': kind, 'role': role, 'template': value.strip(),
                         'literal': literal_of(value)})

    for field, kind, role in TEMPLATE_FIELDS:
        add(kind, role, message.get(field))
    for field, kind in TEMPLATE_LISTS:
        for item in message.get(field) or ():
            if isinstance(item, str):
                add(kind, '', item)
            elif isinstance(item, dict):
                add(kind, str(item.get('role') or item.get('target') or ''),
                    item.get('template') or item.get('text'))
    for field, kind in TEMPLATE_VARIANTS:
        for item in message.get(field) or ():
            if isinstance(item, dict):
                add(kind, str(item.get('target') or item.get('source') or item.get('role') or ''),
                    item.get('template') or item.get('text'))
            elif isinstance(item, str):
                add(kind, '', item)
    for item in message.get('roles') or ():
        if isinstance(item, dict):
            add('primary', str(item.get('role') or ''), item.get('template'))
    # 少数记录用 message/detail/hint 直接给出实际文本而不是模板。
    add('primary', 'observed', message.get('message'))
    add('detail', 'observed', message.get('detail'))
    add('primary', 'observed', message.get('observed_primary_example'))

    # 同一段文本换个角色标签仍是同一条报文；展示和反查都只需要一份。
    seen, unique = set(), []
    for row in rows:
        key = (row['kind'], row['template'])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


# ------------------------------------------------------------------ 导出

def evidence_tier(usage_evidence):
    """该码达到过的最高证据档。状态挂在单条证据上，一个码可以同时有好几档。"""
    best = ''
    best_rank = -1
    for item in usage_evidence or ():
        status = (item or {}).get('status') or ''
        rank = TIER_ORDER.index(status) if status in TIER_ORDER else -1
        if rank > best_rank:
            best, best_rank = status, rank
    return best


def read_json(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def read_text(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def class_pages(root):
    """类别页里的中文名与共同语义。"""
    out = {}
    folder = os.path.join(root, 'content', 'docs', 'classes')
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        if not name.endswith('.zh.md'):
            continue
        data, body = front_matter(read_text(os.path.join(folder, name)))
        sections = markup.split_sections(markup.strip_generated(body))
        meaning = next((s['markdown'] for s in sections if s['anchor'] == 'meaning'), '')
        out[name[:-len('.zh.md')]] = {
            'name_zh': TITLE_SPLIT.sub('', re.sub(r'^类别\s*[0-9A-Z]{2}\s*[—–-]\s*', '',
                                                  data.get('title', ''))).strip(),
            'summary': markup.first_sentence(meaning),
        }
    return out


def code_texts(root, sqlstate, condition_name, local_doc):
    """一个码的中英两份正文，外带两份共有的 front matter 元信息。"""
    texts = []
    meta = {'depth': '', 'editorial_review': '', 'runtime_verification': ''}
    for lang, suffix in (('en', '.md'), ('zh', '.zh.md')):
        path = os.path.join(root, 'content', 'docs', sqlstate + suffix)
        if not os.path.exists(path):
            continue
        data, body = front_matter(read_text(path))
        # 深度与审阅状态中英两份相同，读到哪份都行。
        meta['depth'] = data.get('content_depth') or meta['depth']
        meta['editorial_review'] = data.get('editorial_review') or meta['editorial_review']
        meta['runtime_verification'] = data.get('runtime_verification') or meta['runtime_verification']
        body = rewrite_links(markup.strip_generated(body), local_doc)
        sections = markup.split_sections(body)
        lead = next((s['markdown'] for s in sections if s['anchor'] == 'at-a-glance'), '')
        title = data.get('title', '')
        texts.append({
            'lang': lang,
            'title': title,
            # 语言以文件名后缀为准：526 篇里有 24 篇没有 front matter 的 lang 键。
            'name': chinese_name(title, sqlstate, condition_name) if lang == 'zh' else '',
            'description': data.get('description', ''),
            'summary': markup.first_sentence(lead),
            'body_md': body,
            'sections': [{'anchor': s['anchor'], 'heading': s['heading'],
                          'html': markup.render(s['markdown'])} for s in sections],
            'translation_source_rev': (data.get('translation') or {}).get('source_rev', ''),
        })
    return texts, meta


def code_cases(root, sqlstate):
    """可复现案例。87 个码有用例定义，其中 66 个另有可执行 SQL 片段。"""
    folder = os.path.join(root, 'verify', 'cases', sqlstate)
    case_path = os.path.join(folder, 'cases.json')
    if not os.path.exists(case_path):
        return []
    snippets = set()
    snippet_path = os.path.join(folder, 'snippets.json')
    if os.path.exists(snippet_path):
        snippets = {s.get('case_id') or s.get('id')
                    for s in read_json(snippet_path).get('snippets', [])}
    rows = []
    for position, case in enumerate(read_json(case_path).get('cases', [])):
        rows.append({
            'case_id': case.get('id', ''),
            'versions': list(case.get('versions') or []),
            'preconditions': list(case.get('preconditions') or []),
            'trigger': case.get('trigger', '') or '',
            'assertions': list(case.get('assertions') or []),
            'repair': case.get('repair', '') or '',
            'cleanup': case.get('cleanup', '') or '',
            'has_snippet': case.get('id') in snippets,
            'position': position,
        })
    return rows


def intervals_of(facts):
    rows = []
    for era, key in (('modern', 'presence_intervals'), ('pre9', 'pre9_presence_intervals')):
        for position, item in enumerate(facts.get(key) or ()):
            rows.append({
                'era': era, 'position': position,
                'start': item.get('start', '') or '', 'end': item.get('end', '') or '',
                'start_tag': item.get('start_tag', '') or '', 'end_tag': item.get('end_tag', '') or '',
                'start_major': item.get('start_major', '') or '',
                'end_major': item.get('end_major', '') or '',
                'evidence_count': len(item.get('evidence_refs') or ()),
            })
    return rows


def export_snapshot(root=DEFAULT_ROOT):
    """把源仓库读成一份自包含快照。"""
    root = os.path.expanduser(root)
    folder = os.path.join(root, 'data', 'errcodes')
    if not os.path.isdir(folder):
        raise ValueError('找不到错误码数据目录：{}'.format(folder))

    local_doc = doc_checker()
    zh_classes = class_pages(root)

    classes = []
    for item in read_json(os.path.join(root, 'data', 'classes.json'))['classes']:
        extra = zh_classes.get(item['code'], {})
        classes.append({
            'code': item['code'], 'name': item.get('name', ''),
            'name_zh': extra.get('name_zh', ''), 'summary': extra.get('summary', ''),
            'sqlstate_count': item.get('sqlstate_count') or len(item.get('sqlstates') or ()),
            'severity_classes': list(item.get('severity_classes') or ()),
        })

    versions = read_json(os.path.join(root, 'data', 'versions.json'))
    releases = []
    snapshots = list(versions.get('major_matrix') or ()) + list(versions.get('preview_snapshots') or ())
    for position, item in enumerate(snapshots):
        releases.append({
            'major': item.get('major', ''), 'channel': item.get('channel', 'formal'),
            'release': item.get('release', '') or item.get('version', '') or '',
            'tag': item.get('tag', '') or '', 'commit': item.get('commit', '') or '',
            'path': item.get('path', '') or '', 'code_count': item.get('code_count') or 0,
            'position': position,
        })

    # 展示用的是大版本；精确快照号留在 facts['present_in_snapshots'] 里。
    major_of = {}
    for item in list(versions.get('major_matrix') or ()) + list(versions.get('preview_snapshots') or ()):
        for key in (item.get('release'), item.get('version'), item.get('tag')):
            if key:
                major_of[key] = item.get('major', '')

    def majors(releases_seen):
        out = []
        for release in releases_seen:
            major = major_of.get(release, release)
            if major and major not in out:
                out.append(major)
        return out

    codes = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith('.json') or not CODE_FILE.match(name[:-5]):
            continue
        sqlstate = name[:-5]
        facts = read_json(os.path.join(folder, name))
        evidence_path = os.path.join(root, 'evidence', name)
        evidence = read_json(evidence_path) if os.path.exists(evidence_path) else {}

        condition_name = facts.get('condition_name') or ''
        texts, meta = code_texts(root, sqlstate, condition_name, local_doc)
        cases = code_cases(root, sqlstate)

        messages = []
        for position, message in enumerate(evidence.get('messages') or ()):
            messages.append({
                'message_id': message.get('id', ''),
                'severity': message.get('severity', '') or message.get('severity_source', '') or '',
                'path': message.get('path', '') or '',
                'limits': message.get('limits', '') or '',
                'sources': list(message.get('sources') or message.get('source_ids') or ()),
                'raw': message,
                'position': position,
                'templates': flatten_templates(message),
            })

        codes.append({
            'sqlstate': sqlstate,
            'class_code': facts.get('class', sqlstate[:2]),
            'condition_name': condition_name,
            'condition_names': list(facts.get('condition_names') or ()),
            'aliases': list(facts.get('aliases') or ()),
            'macros': list(facts.get('macros') or ()),
            'primary_macro': facts.get('primary_macro') or '',
            'severity_classes': list(facts.get('severity_classes') or ()),
            'status': facts.get('status') or 'active',
            'introduced': facts.get('introduced'),
            'removed': facts.get('removed'),
            'known_present_by': facts.get('known_present_by') or '',
            'present_in': majors(facts.get('present_in_snapshots') or ()),
            'preview_in': majors(facts.get('preview_in_snapshots') or ()),
            'depth': meta['depth'] or 'reference',
            'editorial_review': meta['editorial_review'],
            'runtime_verification': meta['runtime_verification'],
            'evidence_tier': evidence_tier(evidence.get('usage_evidence')),
            'case_count': len(cases),
            'snippet_count': sum(1 for c in cases if c['has_snippet']),
            'facts': trim_facts(facts),
            'texts': texts,
            'cases': cases,
            'presence': intervals_of(facts),
            'messages': messages,
            'sources': [{
                'source_id': s.get('id', ''), 'kind': s.get('kind', '') or '',
                'tag': s.get('tag', '') or '', 'commit': s.get('commit', '') or '',
                'path': s.get('path', '') or '', 'location': s.get('location', '') or '',
                'url': s.get('url', '') or '', 'docs_url': s.get('docs_url', '') or '',
                'sha256': s.get('sha256', '') or '', 'position': position,
            } for position, s in enumerate(evidence.get('sources') or ())],
            'claims': [{
                'claim_id': c.get('id', ''), 'statement': c.get('statement', '') or '',
                'method': c.get('method', '') or '', 'limits': c.get('limits', '') or '',
                'sources': list(c.get('sources') or ()), 'runtime': list(c.get('runtime') or ()),
                'position': position,
            } for position, c in enumerate(evidence.get('claims') or ())],
            'runtimes': [{
                'runtime_id': r.get('id', ''), 'run_id': r.get('run_id', '') or '',
                'status': r.get('status', '') or '', 'target': r.get('target', '') or '',
                'server_version': r.get('server_version', '') or '',
                'cases': list(r.get('cases') or ()), 'limits': r.get('limits', '') or '',
                'raw': r, 'position': position,
            } for position, r in enumerate(evidence.get('runtime') or ())],
        })

    for code in codes:
        code['source_rev'] = hashlib.sha256(
            json.dumps(code, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()

    return {
        'format': FORMAT,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'root': root,
        'classes': classes,
        'releases': releases,
        'codes': codes,
    }


# ------------------------------------------------------------------ 导入

CODE_FIELDS = ('condition_name', 'condition_names', 'aliases', 'macros', 'primary_macro',
               'severity_classes', 'status', 'introduced', 'removed', 'known_present_by',
               'present_in', 'preview_in', 'depth', 'editorial_review', 'runtime_verification',
               'evidence_tier', 'case_count', 'snippet_count', 'facts', 'source_rev')

CHILDREN = (
    ('texts', ErrorCodeText), ('presence', ErrorCodePresence), ('sources', ErrorCodeSource),
    ('claims', ErrorCodeClaim), ('runtimes', ErrorCodeRuntime), ('cases', ErrorCodeCase),
)


def validate(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError('快照不是一个对象')
    if snapshot.get('format') != FORMAT:
        raise ValueError('快照格式为 {}，期望 {}'.format(snapshot.get('format'), FORMAT))
    for key in ('classes', 'releases', 'codes'):
        if not isinstance(snapshot.get(key), list) or not snapshot[key]:
            raise ValueError('快照缺少 {}'.format(key))
    for code in snapshot['codes']:
        if not CODE_FILE.match(code.get('sqlstate', '')):
            raise ValueError('错误码格式不对：{!r}'.format(code.get('sqlstate')))
    return True


def preview(snapshot):
    """不写库，只报告这次导入会改动什么。"""
    validate(snapshot)
    existing = dict(ErrorCode.objects.values_list('sqlstate', 'source_rev'))
    incoming = {c['sqlstate'] for c in snapshot['codes']}
    unchanged = sum(1 for c in snapshot['codes'] if existing.get(c['sqlstate']) == c['source_rev'])
    added = sorted(incoming - set(existing))
    return {
        'classes': len(snapshot['classes']), 'releases': len(snapshot['releases']),
        'codes': len(incoming), 'added': added,
        'unchanged': unchanged, 'changed': len(incoming) - unchanged - len(added),
        'missing': sorted(set(existing) - incoming),
        'texts': sum(len(c['texts']) for c in snapshot['codes']),
        'messages': sum(len(c['messages']) for c in snapshot['codes']),
        'templates': sum(len(m['templates']) for c in snapshot['codes'] for m in c['messages']),
        'claims': sum(len(c['claims']) for c in snapshot['codes']),
        'cases': sum(len(c['cases']) for c in snapshot['codes']),
    }


SUMMARY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'data', 'wiki', 'errcode-summaries.json')


def summary_overrides(path=SUMMARY_FILE):
    """索引页的一句话说明。源仓库的「速览」首句太长，站点自己维护一份 ≤ 36 字的版本。"""
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}


def apply_summaries(overrides):
    """把一句话说明写进中文正文行；与源码版本无关，每次导入都核对一遍。"""
    changed = 0
    for text in ErrorCodeText.objects.filter(lang='zh', errcode_id__in=list(overrides)):
        wanted = overrides[text.errcode_id]
        if text.summary != wanted:
            text.summary = wanted
            text.save(update_fields=['summary'])
            changed += 1
    return changed


@transaction.atomic
def import_snapshot(snapshot, prune=False):
    """按 sqlstate 原位更新。无变化的码整条跳过，不重写子表。"""
    validate(snapshot)
    report = {'classes': 0, 'releases': 0, 'added': 0, 'updated': 0, 'unchanged': 0,
              'removed': 0, 'texts': 0, 'messages': 0, 'templates': 0}

    for item in snapshot['classes']:
        ErrorCodeClass.objects.update_or_create(
            code=item['code'],
            defaults={k: v for k, v in item.items() if k != 'code'})
        report['classes'] += 1

    for item in snapshot['releases']:
        ErrorCodeRelease.objects.update_or_create(
            major=item['major'],
            defaults={k: v for k, v in item.items() if k != 'major'})
        report['releases'] += 1

    existing = dict(ErrorCode.objects.values_list('sqlstate', 'source_rev'))
    for item in snapshot['codes']:
        sqlstate = item['sqlstate']
        if existing.get(sqlstate) == item['source_rev']:
            report['unchanged'] += 1
            continue

        defaults = {field: item[field] for field in CODE_FIELDS}
        defaults['klass_id'] = item['class_code']
        code, created = ErrorCode.objects.update_or_create(sqlstate=sqlstate, defaults=defaults)
        report['added' if created else 'updated'] += 1

        for key, model in CHILDREN:
            model.objects.filter(errcode=code).delete()
            model.objects.bulk_create([model(errcode=code, **row) for row in item[key]])
        report['texts'] += len(item['texts'])

        ErrorCodeMessage.objects.filter(errcode=code).delete()
        for message in item['messages']:
            templates = message.pop('templates')
            row = ErrorCodeMessage.objects.create(errcode=code, **message)
            ErrorCodeTemplate.objects.bulk_create([
                ErrorCodeTemplate(message=row, errcode=code, position=position, **template)
                for position, template in enumerate(templates)])
            report['messages'] += 1
            report['templates'] += len(templates)

    if prune:
        incoming = {c['sqlstate'] for c in snapshot['codes']}
        stale = ErrorCode.objects.exclude(sqlstate__in=incoming)
        report['removed'] = stale.count()
        stale.delete()

    report['summaries'] = apply_summaries(summary_overrides())

    return report
