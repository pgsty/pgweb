#!/usr/bin/env python3
"""Export predefined roles and OID types from loaded PG10–20 Chinese manuals.

Only reads the local Django database in a read-only repeatable-read transaction.
No neighbouring-version content, guessed release commits, or network inputs are
used. --check verifies the committed files without writing them.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pgweb.wiki.role_oid_data import OID_LABELS, ROLE_LABELS


def plain(node):
    """Keep code tokens separate while returning only readable plain text."""
    value = ' '.join(node.get_text(' ', strip=True).replace('\u200b', '').split())
    value = re.sub(r'\s+([，。；：、！？）”])', r'\1', value)
    return re.sub(r'([（“])\s+', r'\1', value)


def unique(values):
    return list(dict.fromkeys(values))


def manual_document(content, major, channel):
    soup = BeautifulSoup(content, 'html.parser')
    body = soup.select_one('div.sect1')
    home = soup.select_one('a[accesskey="h"]')
    if not body or not home or not home.get('title'):
        raise ValueError(f'PG{major}: missing manual section/build identity')
    ref = home['title']
    revision = hashlib.sha256(content.encode()).hexdigest()
    release = dict(major=str(major), label=ref.removeprefix('PostgreSQL ').removesuffix(' 手册'),
                   revision=revision, ref=ref, channel=channel)
    for marker in body.select('a.id_link'):
        marker.decompose()
    return body, release


def source_links(file, anchor, release):
    slug = 'devel' if release['major'] == '20' else release['major']
    location = f'{file}#{anchor}'
    return [
        {'label': release['ref'], 'url': f'/docs/{slug}/{location}',
         'sha256': release['revision']},
        {'label': f'PostgreSQL {slug} 英文原文',
         'url': f'https://www.postgresql.org/docs/{slug}/{location}'},
    ]


def related_links(nodes, major, file):
    slug = 'devel' if str(major) == '20' else str(major)
    base = f'/docs/{slug}/{file}'
    result, seen = [], set()
    for node in nodes:
        for link in node.select('a[href]'):
            href = link['href']
            if urlsplit(href).scheme or href.startswith('//'):
                continue
            url = urljoin(base, href)
            label = plain(link) or link.get('title', '')
            if label and url not in seen:
                seen.add(url)
                result.append(dict(label=label, url=url))
    return result


def role_names(node):
    return set(re.findall(r'\bpg_[a-z_]+\b', plain(node)))


def role_rows(body):
    """Accept the 10–17 table and 18+ grouped definition lists."""
    result = {}
    definitions = body.select('dl.variablelist > dt')
    if definitions:
        for term in definitions:
            names = [plain(code) for code in term.select('code.varname')]
            details = term.find_next_sibling('dd')
            if not names or details is None or not term.get('id'):
                raise ValueError('Malformed predefined role definition')
            paragraphs = details.find_all('p')
            for name in names:
                own, common = [], []
                for paragraph in paragraphs:
                    # A group dt can define four distinct roles. A paragraph
                    # beginning with a role belongs to that role, even if it
                    # names other roles while describing its membership.
                    first = re.match(r'^(pg_[a-z_]+)\b', plain(paragraph))
                    if first and first.group(1) in names:
                        if first.group(1) == name:
                            own.append(paragraph)
                    else:
                        common.append(paragraph)
                if not own or name in result:
                    raise ValueError(f'Missing/duplicate description: {name}')
                result[name] = (own, common, term['id'])
    else:
        table = body.select_one('div.table')
        if table is None or not table.get('id'):
            raise ValueError('Missing predefined role table')
        outer = body.find_all('p', recursive=False)
        for row in table.select('tbody tr'):
            cells = row.find_all('td', recursive=False)
            if len(cells) != 2:
                raise ValueError('Predefined role table needs exactly two columns')
            name = plain(cells[0])
            if not re.fullmatch(r'pg_[a-z_]+', name) or name in result:
                raise ValueError(f'Unexpected/duplicate role name: {name}')
            relevant = [p for p in outer if name in role_names(p)]
            result[name] = ([cells[1]], relevant, table['id'])
    if not result:
        raise ValueError('Empty predefined role inventory')
    return result


def parse_roles(content, major, channel):
    body, release = manual_document(content, major, channel)
    file = 'default-roles.html' if int(major) <= 13 else 'predefined-roles.html'
    entries = {}
    for name, (own, context, anchor) in role_rows(body).items():
        if name not in ROLE_LABELS:
            raise ValueError(f'Add Chinese editorial label for new role: {name}')
        description = unique(plain(p) for p in own)
        paragraphs = unique(plain(p) for p in context if plain(p) not in description)
        entries[name] = dict(
            description=description,
            facts=[{'label': '本版名称', 'value': name},
                   {'label': '手册称谓', 'value': '默认角色' if int(major) <= 13 else '预定义角色'}],
            sections=([{'title': '作用与权限边界', 'paragraphs': paragraphs}] if paragraphs else []),
            sources=source_links(file, anchor, release),
            related=related_links(own + context, major, file), release=deepcopy(release))
    return release, entries


def oid_rows(body):
    table = body.find(id='DATATYPE-OID-TABLE')
    if table is None:
        raise ValueError('Missing DATATYPE-OID-TABLE')
    result = {}
    for row in table.select('tbody tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) != 4:
            raise ValueError('OID table needs exactly four columns')
        name = plain(cells[0])
        if not re.fullmatch(r'oid|reg[a-z]+', name) or name in result:
            raise ValueError(f'Unexpected/duplicate OID table type: {name}')
        result[name] = dict(reference=plain(cells[1]), meaning=plain(cells[2]),
                            example=plain(cells[3]))
    if 'oid' not in result:
        raise ValueError('OID table does not contain oid')
    return result


def ordered_sections(nodes):
    """Group the chapter by subject without moving prose or code examples.

    A section can have several prose/code blocks. In particular the simplified
    information_schema example stays between its introduction and warning;
    splitting at every code block would turn that warning into another topic.
    The boundaries follow the chapter's discussion, not a count of examples.
    """
    sections, current, block = [], None, None
    title = '存储与取值范围'
    for node in nodes:
        paragraph = plain(node) if node.name == 'p' else ''
        if paragraph:
            if '别名类型' in paragraph and '输入和输出例程' in paragraph:
                title = '名称解析与搜索路径'
            elif '早绑定' in paragraph or '后绑定' in paragraph:
                title = '早绑定与后绑定'
            elif 'information_schema' in paragraph and 'pg_relation_size' in paragraph:
                title = '从信息模式查找 OID'
            elif '依赖关系' in paragraph and '存储' in paragraph:
                title = '依赖关系'
            elif '事务隔离' in paragraph:
                title = '事务隔离与规划限制'
        if current is None or current['title'] != title:
            current = {'title': title, 'paragraphs': [], 'blocks': []}
            sections.append(current)
            block = None
        if block is None or 'code' in block:
            block = {'paragraphs': []}
            current['blocks'].append(block)
        if node.name == 'pre':
            block['code'] = node.get_text().strip().replace('\u200b', '')
        elif paragraph:
            block['paragraphs'].append(paragraph)
    return sections


def prose_blocks(body):
    """Keep admonitions in their original position, excluding tables/navigation."""
    for node in body.find_all(recursive=False):
        if node.name in {'p', 'pre'}:
            yield node
        elif node.name == 'div' and set(node.get('class', [])) & {'note', 'warning', 'caution', 'tip', 'important'}:
            yield from node.find_all(['p', 'pre'])


def parse_oid(content, major, channel):
    body, release = manual_document(content, major, channel)
    file = 'datatype-oid.html'
    rows = oid_rows(body)
    paragraphs = body.find_all('p', recursive=False)
    extra_names = {'oid8', 'xid', 'xid8', 'cid', 'tid'}
    extra = {}
    for name in extra_names:
        own = [p for p in paragraphs if name in {plain(c) for c in p.select('code.type')}]
        if own:
            extra[name] = own
    names = set(rows) | set(extra)
    if unknown := names - OID_LABELS.keys():
        raise ValueError(f'Add Chinese editorial label for new identifier type: {sorted(unknown)}')

    # Every direct prose/code node before the transaction-ID paragraph belongs
    # to the OID/alias discussion. Do not apply OID alias rules to xid/cid/tid.
    shared = []
    for node in prose_blocks(body):
        if node.name == 'p' and 'xid' in {plain(c) for c in node.select('code.type')}:
            break
        shared.append(node)
    entries = {}
    for name in sorted(names):
        facts = []
        if name in rows:
            row = rows[name]
            description = [row['meaning'] + '。']
            facts = [{'label': '引用目录', 'value': row['reference']},
                     {'label': '表示对象', 'value': row['meaning']},
                     {'label': '输入值示例', 'value': row['example']}]
            sections = ordered_sections(shared)
            context = shared
            anchor = 'DATATYPE-OID-TABLE'
        else:
            context = extra[name]
            description = unique(plain(p) for p in context)
            sections = []
            anchor = body['id']
            # These are the types of system columns, not OID alias types.
            if name in {'xid', 'cid', 'tid'}:
                columns = {'xid': 'xmin、xmax', 'cid': 'cmin、cmax', 'tid': 'ctid'}[name]
                facts.append({'label': '对应系统列', 'value': columns})
            if name in {'xid', 'xid8', 'cid', 'tid'}:
                context = context + [p for p in paragraphs if p.select('a[href^="ddl-system-columns.html"]')]
        related = related_links(context, major, file)
        if name in rows and rows[name]['reference'].startswith('pg_'):
            catalogue = rows[name]['reference']
            related.insert(0, {'label': f'{catalogue} 系统目录',
                               'url': f'/docs/catalog/{catalogue}/?v={major}'})
        entries[name] = dict(description=description, facts=facts, sections=sections,
                             sources=source_links(file, anchor, release),
                             related=related, release=deepcopy(release))
    return release, entries


def assemble(kind, pages):
    labels = ROLE_LABELS if kind == 'role' else OID_LABELS
    parser = parse_roles if kind == 'role' else parse_oid
    items, releases = {}, []
    for major, content, channel in pages:
        release, versions = parser(content, str(major), channel)
        releases.append(release)
        for name, snapshot in versions.items():
            name_zh, category, summary = labels[name]
            item = items.setdefault(name, dict(slug=name, name=name, name_zh=name_zh,
                                              category=category, summary=summary,
                                              aliases=[], versions={}))
            item['versions'][str(major)] = snapshot
    return {'format': 1, 'kind': kind, 'releases': releases,
            'items': [items[name] for name in sorted(items)]}


def local_snapshots():
    """Read all inputs at one database snapshot; never migrate or populate."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    django.setup()
    from django.db import connection, transaction
    from pgweb.core.models import Version
    from pgweb.docs.models import DocPage
    pages = {'role': [], 'oid': []}
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        for major in range(10, 21):
            tree = 0 if major == 20 else major
            version = Version.objects.get(tree=tree)
            channel = ('devel' if major == 20 else 'preview' if version.testing else
                       'stable' if version.supported else 'historical')
            for kind, file in [('role', 'default-roles.html' if major <= 13 else 'predefined-roles.html'),
                               ('oid', 'datatype-oid.html')]:
                page = DocPage.objects.get(version_id=tree, file=file)
                if not page.content:
                    raise ValueError(f'PG{major}: empty source {file}')
                pages[kind].append((major, page.content, channel))
    return {kind: assemble(kind, inputs) for kind, inputs in pages.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/wiki')
    args = parser.parse_args()
    snapshots = local_snapshots()
    for kind, filename in [('role', 'roles.json'), ('oid', 'oid_types.json')]:
        snapshot = snapshots[kind]
        payload = json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n'
        target = args.output_dir / filename
        if args.check:
            if not target.exists() or target.read_text() != payload:
                raise ValueError(f'{target}: snapshot differs from current local manuals')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(payload)
        counts = {r['major']: sum(r['major'] in x['versions'] for x in snapshot['items'])
                  for r in snapshot['releases']}
        print(json.dumps({'kind': kind, 'items': len(snapshot['items']),
                          'versions': counts, 'file': str(target),
                          'checked': args.check}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
