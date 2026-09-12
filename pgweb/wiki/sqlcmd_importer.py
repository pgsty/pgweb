"""本地 SQL 参考页 → 自包含快照 → 幂等导入；一期完全不联网。"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

import bleach
from bs4 import BeautifulSoup
from django.db import transaction
from django.db.models import Q

from pgweb.docs.models import DocPage

from .catalog_importer import text_of
from .guc_importer import DOC_ATTRS, DOC_TAGS, collapse, rewrite_href
from .models import (SECTION_KEYS, SQLCMD_GROUP_ORDER, SqlCommand,
                     sqlcmd_group_of, sqlcmd_slug, sqlcmd_split)
from .sqlcmd_common import (compare, major_of, section_text, sections_at, version_rows)

FORMAT = 1
CACHE_DIR = 'tmp/sqlcmd-sources'
SLUG_RE = re.compile(r'^[a-z][a-z0-9-]{0,63}$')
FILE_RE = re.compile(r'^sql-[a-z0-9-]+\.html$')
TAGS = list(dict.fromkeys(DOC_TAGS + ['var', 'h3', 'h6', 'caption', 'tfoot', 'acronym']))
ATTRS = dict(DOC_ATTRS, **{tag: ['class'] for tag in
                         ('pre', 'em', 'var', 'dl', 'dt', 'dd', 'ul', 'ol', 'li')})
COMMAND_FIELDS = ('name', 'aliases', 'verb', 'object', 'group', 'purpose', 'purpose_zh',
                  'first_version', 'last_version', 'present_in', 'changed_in', 'synopsis',
                  'related', 'versions', 'changes', 'editorial', 'position', 'source_rev')
SNAPSHOT_FIELDS = ('name', 'file', 'anchor', 'slug', 'lang', 'purpose_zh', 'purpose',
                   'synopsis_text', 'synopsis_html', 'sections', 'sections_same_as', 'related')
VERSION_FIELDS = ('major', 'label', 'status', 'support_status', 'doc_slug', 'command_count',
                  'added_count', 'removed_count', 'changed_count', 'position')


def loaded_versions():
    trees = (DocPage.objects.filter(Q(version__gte=10) | Q(version=0), file='sql-commands.html')
             .values_list('version', flat=True))
    return version_rows(major_of(tree) for tree in trees)


def clean_html(html, doc_slug, filename, command_links=None, major=''):
    """共用 GUC 白名单并保留 SQL 手册样式；pre 的空白原样保留。"""
    fragment = BeautifulSoup(html, 'html.parser')
    for junk in fragment.select('script, style, iframe, object, a.indexterm, a.id_link'):
        junk.decompose()
    for anchor in list(fragment.find_all('a')):
        if not anchor.get('href') and not text_of(anchor):
            anchor.decompose()
            continue
        href = (anchor.get('href') or '').strip()
        if not href:
            continue
        parsed = urlsplit(href)
        # 先拒绝不安全协议，免得相对链接改写把它伪装成 /docs/ 路径。
        if parsed.scheme and parsed.scheme not in ('https', 'http', 'mailto'):
            del anchor['href']
            continue
        target = (command_links or {}).get(parsed.path)
        if target and not parsed.scheme and not parsed.netloc:
            anchor['href'] = '/docs/sql/{}/?v={}'.format(target, major)
        else:
            anchor['href'] = rewrite_href(href, doc_slug, filename)
    collapse(fragment)
    return bleach.clean(str(fragment), tags=TAGS, attributes=ATTRS, strip=True).strip()


def toc_entries(content):
    soup = BeautifulSoup(content or '', 'html.parser')
    entries = {}
    for link in soup.select('span.refentrytitle a[href]'):
        filename = urlsplit(link['href']).path
        if not FILE_RE.fullmatch(filename):
            continue
        purpose = link.find_parent('dt')
        purpose = purpose.select_one('span.refpurpose') if purpose else None
        entries[filename] = {'name': text_of(link).upper(),
                             'purpose_zh': text_of(purpose).lstrip('—–- ')}
    return entries


def parse_page(content, filename, version, toc=None, command_links=None):
    soup = BeautifulSoup(content or '', 'html.parser')
    entry = soup.select_one('div.refentry')
    if entry is None:
        return None
    title = entry.select_one('div.refnamediv span.refentrytitle')
    name = ' '.join((text_of(title) or (toc or {}).get('name', '')).upper().split())
    if not name or not SLUG_RE.fullmatch(sqlcmd_slug(name)):
        raise ValueError('无法识别命令名称：{} @ {}'.format(filename, version['major']))
    namediv = entry.select_one('div.refnamediv p')
    purpose = re.split(r'\s*[—–]\s*', text_of(namediv), maxsplit=1)
    purpose = purpose[1] if len(purpose) == 2 else (toc or {}).get('purpose_zh', '')
    synopsis = []
    for pre in entry.select('div.refsynopsisdiv pre.synopsis'):
        cleaned = clean_html(str(pre), version['doc_slug'], filename)
        pre = BeautifulSoup(cleaned, 'html.parser').find('pre')
        synopsis.append(pre.decode_contents().strip('\n'))
    synopsis_html = '\n\n'.join(synopsis)
    synopsis_text = '\n'.join(' '.join(line.split()) for line in
                             BeautifulSoup(synopsis_html, 'html.parser').get_text().splitlines())
    related, sections = [], []
    for node in entry.select('div.refsect1'):
        # 只采一级参考小节，保留其中 refsect2/3 的标题与内容。
        if node.find_parent('div', class_='refsect1'):
            continue
        heading = node.find(['h2', 'h3'])
        section_title = text_of(heading)
        key = SECTION_KEYS.get(section_title, 'other')
        if key == 'see_also':
            for link in node.find_all('a', href=True):
                target = (command_links or {}).get(urlsplit(link['href']).path)
                if target and target not in related:
                    related.append(target)
        if heading:
            heading.decompose()
        sections.append({'key': key, 'title': section_title,
                         'html': clean_html(node.decode_contents(), version['doc_slug'], filename,
                                            command_links if key == 'see_also' else None,
                                            version['major'])})
    return {'name': name, 'file': filename, 'anchor': entry.get('id', ''),
            'slug': version['doc_slug'], 'lang': 'zh', 'purpose_zh': purpose, 'purpose': '',
            'synopsis_text': synopsis_text, 'synopsis_html': synopsis_html,
            'sections': sections, 'sections_same_as': '', 'related': related}


def build_changes(snapshots, order):
    out = []
    for left, right in zip(order, order[1:]):
        a, b = snapshots.get(left), snapshots.get(right)
        if a:
            a = dict(a, sections=sections_at(snapshots, left))
        if b:
            b = dict(b, sections=sections_at(snapshots, right))
        change = compare(a, b, left, right)
        if change:
            out.append(change)
    return out


def dedupe_sections(snapshots, order):
    seen = {}
    for major in order:
        snapshot = snapshots.get(major)
        if not snapshot or not snapshot['sections']:
            continue
        content = json.dumps(snapshot['sections'], ensure_ascii=False, sort_keys=True)
        if content in seen:
            snapshot['sections'] = []
            snapshot['sections_same_as'] = seen[content]
        else:
            seen[content] = major


def assign_positions(commands):
    buckets = defaultdict(list)
    for item in commands:
        buckets[item['group']].append(item)
    for group, members in buckets.items():
        members.sort(key=lambda item: (item['object'], {'CREATE': 0, 'ALTER': 1, 'DROP': 2}.get(
            item['verb'], 3), item['name']))
        for position, item in enumerate(members):
            item['position'] = SQLCMD_GROUP_ORDER[group] * 1000 + position
    commands.sort(key=lambda item: item['position'])


def export_snapshot(fetch=False, cache_dir=CACHE_DIR):
    versions = loaded_versions()
    if not versions:
        raise ValueError('本站没有已收录的 SQL 命令目录（sql-commands.html）')
    generated = datetime.now(timezone.utc).isoformat()
    rev = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=Path(__file__).resolve().parents[2],
                         capture_output=True, text=True, timeout=10)
    source_rev = '{}@{}'.format(generated, rev.stdout.strip() or 'unknown')
    report = {'versions': {}, 'sections': {}, 'orphans': [], 'unmapped_groups': [], 'renamed': [],
              'upstream': {'fetched': False}}
    if fetch:
        report['upstream'].update(requested=True, note='一期未实现 9.x 英文层抓取', cache_dir=str(cache_dir))
    by_slug = {}
    for version in versions:
        major = version['major']
        tree = 0 if version['doc_slug'] == 'devel' else major
        pages = dict(DocPage.objects.filter(version=tree, file__startswith='sql-')
                     .order_by('file').values_list('file', 'content'))
        toc = toc_entries(pages['sql-commands.html'])
        # 先识别全部参考页名称，另见链接不能靠去掉 sql- 来猜规范 slug。
        command_links = {}
        for filename, content in pages.items():
            if not FILE_RE.fullmatch(filename):
                continue
            soup = BeautifulSoup(content or '', 'html.parser')
            if soup.select_one('div.refentry'):
                name = text_of(soup.select_one('div.refnamediv span.refentrytitle'))
                name = name or toc.get(filename, {}).get('name', '')
                command_links[filename] = sqlcmd_slug(name)
        counts = Counter()
        for filename, slug in command_links.items():
            snap = parse_page(pages[filename], filename, version, toc.get(filename), command_links)
            item = by_slug.setdefault(slug, {'slug': slug, 'aliases': [], 'versions': {}})
            if major in item['versions']:
                raise ValueError('{} @ {} 有重复参考页'.format(snap['name'], major))
            item['versions'][major] = snap
            alias = filename[4:-5]
            if alias not in item['aliases']:
                item['aliases'].append(alias)
            if filename not in toc:
                report['orphans'].append({'major': major, 'file': filename, 'name': snap['name']})
            counts.update(section['key'] for section in snap['sections'])
        missing = sorted(set(toc) - set(command_links))
        if missing:
            raise ValueError('{} 目录有参考页缺失：{}'.format(major, ', '.join(missing)))
        version['command_count'] = len(command_links)
        report['versions'][major] = len(command_links)
        report['sections'][major] = {'commands': len(command_links), 'total': sum(counts.values()),
                                      'keys': dict(counts)}
    order = [version['major'] for version in versions]
    commands = list(by_slug.values())
    for item in commands:
        present = [major for major in order if major in item['versions']]
        last = item['versions'][present[-1]]
        name = last['name']
        verb, object_name = sqlcmd_split(name)
        changes = build_changes(item['versions'], order)
        item.update(name=name, verb=verb, object=object_name, group=sqlcmd_group_of(name),
                    purpose='', purpose_zh=last['purpose_zh'], first_version=present[0],
                    last_version=present[-1], present_in=present,
                    changed_in=[change['to'] for change in changes if change['synopsis']],
                    synopsis=last['synopsis_text'], related=last['related'], changes=changes,
                    editorial={}, source_rev=source_rev)
        if item['group'] == 'misc':
            report['unmapped_groups'].append(name)
        for change in changes:
            if change['renamed']:
                report['renamed'].append(dict(change['renamed'], name=name,
                                               **{'from': change['from'], 'to': change['to']}))
        dedupe_sections(item['versions'], order)
    assign_positions(commands)
    for version in versions:
        changes = [c for item in commands for c in item['changes'] if c['to'] == version['major']]
        version.update(added_count=sum(c['status'] == 'added' for c in changes),
                       removed_count=sum(c['status'] == 'removed' for c in changes),
                       changed_count=sum(bool(c['synopsis']) for c in changes))
    total = sum(len(item['versions']) for item in commands)
    deduped = sum(bool(s['sections_same_as']) for item in commands for s in item['versions'].values())
    report['dedupe'] = {'snapshots': total, 'same_as': deduped, 'ratio': round(deduped / total, 4)}
    section_text.cache_clear()
    snapshot = {'format': FORMAT, 'generated_at': generated, 'source_rev': source_rev,
                'default_major': next((v['major'] for v in versions if v['status'] == 'stable'), order[-1]),
                'stats': {'commands': len(commands), 'versions': len(versions), 'snapshots': total,
                          'synopsis_changes': sum(len(item['changed_in']) for item in commands),
                          'removed': sum(item['last_version'] != order[-1] for item in commands)},
                'harvest': report, 'versions': versions, 'commands': commands}
    validate(snapshot)
    return snapshot


def require(item, fields, label):
    if not isinstance(item, dict):
        raise ValueError('{} 不是对象'.format(label))
    absent = [field for field in fields if field not in item]
    if absent:
        raise ValueError('{} 缺少字段：{}'.format(label, '、'.join(absent)))


def validate(snapshot):
    require(snapshot, ('format', 'generated_at', 'source_rev', 'default_major', 'stats',
                       'harvest', 'versions', 'commands'), '快照')
    if snapshot['format'] != FORMAT:
        raise ValueError('快照格式应为 {}'.format(FORMAT))
    for key in ('versions', 'commands'):
        if not isinstance(snapshot[key], list) or not snapshot[key]:
            raise ValueError('快照缺少 {}'.format(key))
    for version in snapshot['versions']:
        require(version, VERSION_FIELDS, '版本')
    order = [v['major'] for v in snapshot['versions']]
    if len(set(order)) != len(order) or order != sorted(order, key=lambda v: tuple(map(int, v.split('.')))):
        raise ValueError('版本重复或顺序不对')
    if snapshot['default_major'] not in order:
        raise ValueError('default_major 引用了未知版本')
    seen, alias_owner = set(), {}
    for item in snapshot['commands']:
        require(item, ('slug',) + COMMAND_FIELDS, '命令')
        slug = item['slug']
        if not SLUG_RE.fullmatch(slug) or slug in seen:
            raise ValueError('命令 slug 无效或重复：{}'.format(slug))
        seen.add(slug)
        if item['group'] not in SQLCMD_GROUP_ORDER or not item['versions']:
            raise ValueError('{} 分组或版本无效'.format(slug))
        present = [v for v in order if v in item['versions']]
        if (set(item['versions']) - set(order) or present != item['present_in'] or
                item['first_version'] != present[0] or item['last_version'] != present[-1]):
            raise ValueError('{} 版本覆盖不一致'.format(slug))
        for alias in [slug, *item['aliases']]:
            if not SLUG_RE.fullmatch(alias.lower()) or alias_owner.get(alias.lower(), slug) != slug:
                raise ValueError('命令别名冲突或无效：{}'.format(alias))
            alias_owner[alias.lower()] = slug
        for major, snap in item['versions'].items():
            label = '{} @ {}'.format(slug, major)
            require(snap, SNAPSHOT_FIELDS, label)
            if not FILE_RE.fullmatch(snap['file']):
                raise ValueError('{} 手册文件名无效'.format(label))
            for section in snap['sections']:
                require(section, ('key', 'title', 'html'), label + ' 小节')
                if section['key'] not in set(SECTION_KEYS.values()) | {'other'}:
                    raise ValueError('{} 小节 key 无效'.format(label))
            pointer = snap['sections_same_as']
            if pointer and (pointer not in present or present.index(pointer) >= present.index(major)
                            or snap['sections'] or not sections_at(item['versions'], pointer)):
                raise ValueError('{} sections_same_as 无效'.format(label))
        for change in item['changes']:
            require(change, ('from', 'to', 'status', 'renamed', 'synopsis', 'sections',
                              'purpose_changed'), slug + ' 变化')
        if item['changed_in'] != [c['to'] for c in item['changes'] if c['synopsis']]:
            raise ValueError('{} changed_in 不一致'.format(slug))
    for version in snapshot['versions']:
        if version['command_count'] != sum(version['major'] in c['versions'] for c in snapshot['commands']):
            raise ValueError('{} 命令数不一致'.format(version['major']))
    return True


def changed_slugs(snapshot):
    stored = {row.slug: row for row in SqlCommand.objects.all()}
    added, updated, unchanged = [], [], []
    for item in snapshot['commands']:
        row = stored.get(item['slug'])
        bucket = added if row is None else updated if any(
            getattr(row, field) != item[field] for field in COMMAND_FIELDS) else unchanged
        bucket.append(item['slug'])
    return added, updated, unchanged, sorted(set(stored) - {c['slug'] for c in snapshot['commands']})


def preview(snapshot):
    validate(snapshot)
    added, updated, unchanged, missing = changed_slugs(snapshot)
    return {'versions': len(snapshot['versions']), 'commands': len(snapshot['commands']),
            'added': len(added), 'updated': len(updated), 'unchanged': len(unchanged),
            'missing': missing, 'removed': 0,
            'note': '快照缺少 {} 条命令，未加 --prune 时保留。'.format(len(missing)) if missing else '',
            'harvest': snapshot['harvest']}


@transaction.atomic
def import_snapshot(snapshot, prune=False):
    report = preview(snapshot)
    added, updated, _, missing = changed_slugs(snapshot)
    write = set(added + updated)
    for item in snapshot['commands']:
        if item['slug'] in write:
            SqlCommand.objects.update_or_create(slug=item['slug'], defaults={
                field: item[field] for field in COMMAND_FIELDS})
    if prune:
        report['removed'] = len(missing)
        SqlCommand.objects.filter(slug__in=missing).delete()
        report['note'] = ''
    report['pruned'] = bool(prune)
    from . import sqlcmd
    sqlcmd.forget()
    return report


def digest(snapshot):
    data = json.dumps({key: snapshot[key] for key in ('versions', 'commands')},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()
