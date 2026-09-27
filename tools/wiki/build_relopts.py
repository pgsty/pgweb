#!/usr/bin/env python3
"""Build documented relation options from the local PGSQL.CC manual.

.venv/bin/python tools/wiki/build_relopts.py [--check]
.venv/bin/python tools/wiki/build_relopts.py --export-sources /tmp/relopts-sources.json
.venv/bin/python tools/wiki/build_relopts.py --input-sources /tmp/relopts-sources.json --check

The database is read in one read-only repeatable-read transaction and must be
pgweb. Source content hashes pin the exact Chinese manual used. The optional
source bundle allows byte-for-byte rebuilding after the live manuals change.
No database mutation, network fetch or PGpedia content is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pgweb.wiki.relopts_data import CATEGORIES, COVERAGE_NOTES, INDEX_SCOPES, INDEX_TYPES, LABELS

MAJORS = [str(n) for n in range(10, 21)]
FILES = ('sql-createtable.html', 'sql-createindex.html', 'sql-createview.html',
         'sql-creatematerializedview.html')
TYPE_NAMES = {'integer': '整数', 'floating point': '浮点数', 'real': '浮点数',
              'boolean': '布尔值', 'enum': '枚举值', 'string': '字符串'}


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def serialize(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def clean(node):
    """Preserve inline wording; collapse source layout, not technical symbols."""
    value = re.sub(r'\s+', ' ', node.get_text(' ', strip=True)).strip()
    value = re.sub(r' +([，。；：、！？）])', r'\1', value)
    value = re.sub(r'([（]) +', r'\1', value)
    return value


def paragraphs(node):
    """Flatten nested notes and lists once, without dropping their paragraphs."""
    out = []
    for child in node.find_all(['p', 'pre', 'dt']):
        if child.name == 'dt':
            # CHECK OPTION nests LOCAL / CASCADED terms inside its description.
            value = clean(child).removesuffix(' #')
        elif child.name == 'pre':
            value = child.get_text().strip()
        else:
            value = clean(child)
        if value:
            out.append(value)
    return out or [clean(node)]


def term_names(dt):
    term = dt.select_one('.term') or dt
    return [clean(c) for c in term.select('code')
            if 'type' not in c.get('class', []) and not c.find('code')]


def dt_type(dt, default=''):
    node = dt.select_one('code.type')
    return clean(node) if node else default


def anchor(dt, fallback=''):
    return dt.get('id') or next((n.get('id') for n in dt.select('[id]')
                                if n.get('id') and not n['id'].startswith('id-')), fallback)


def list_entries(section):
    entries = []
    for dt in section.select('dt'):
        names = term_names(dt)
        if not names or any(not re.fullmatch(r'[a-z][a-z0-9_.]*', n) for n in names):
            raise ValueError(f'Unrecognized storage parameter term: {clean(dt)}')
        dd = dt.find_next_sibling('dd')
        if dd is None:
            raise ValueError(f'Missing definition for {names}')
        entries.append((names, dt, dd))
    if not entries:
        raise ValueError('Empty storage parameter list')
    return entries


def read_database():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    django.setup()
    from django.db import connection, transaction
    from pgweb.core.models import Version
    from pgweb.docs.models import DocPage
    bundle = {'format': 1, 'releases': {}}
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute('SELECT current_database()')
            if cursor.fetchone()[0] != 'pgweb':
                raise ValueError('Refusing a database other than pgweb')
        for major in MAJORS:
            tree = 0 if major == '20' else int(major)
            version = Version.objects.get(tree=tree)
            # Referenced GUC definitions supply semantics when CREATE TABLE has
            # only a one-line cross-reference. Never confuse their defaults with
            # a relation option's explicit value.
            pages = {p.file: p.content for p in DocPage.objects.filter(version_id=tree)
                     if p.file in FILES or p.file.startswith('runtime-config-')}
            for file in FILES:
                if not pages.get(file):
                    raise ValueError(f'Missing {major}/{file}')
            bundle['releases'][major] = {
                'latestminor': version.latestminor, 'testing': version.testing,
                'supported': version.supported, 'docsgit': version.docsgit,
                'pages': pages,
            }
    return bundle


class Manual:
    def __init__(self, major, metadata):
        self.major = major
        self.url_major = 'devel' if major == '20' else major
        self.metadata = metadata
        self.pages = metadata['pages']
        self.parsed = {}
        self.used = set(FILES)

    def soup(self, file):
        if file not in self.parsed:
            if not self.pages.get(file):
                raise ValueError(f'Missing {self.major}/{file}')
            self.parsed[file] = BeautifulSoup(self.pages[file], 'html.parser')
        return self.parsed[file]

    def source(self, file, part='', label=None):
        self.used.add(file)
        return {
            'label': label or 'PostgreSQL ' + self.major + ' 中文手册',
            'url': f'/docs/{self.url_major}/{file}' + ('#' + part if part else ''),
            'path': file, 'sha256': digest(self.pages[file]),
        }

    def release(self):
        if self.major == '20':
            label, channel = '20 开发版', 'devel'
        elif self.metadata['testing']:
            label, channel = f"{self.major} beta {self.metadata['latestminor']}", 'preview'
        else:
            label = f"{self.major}.{self.metadata['latestminor']}"
            channel = 'stable' if self.metadata['supported'] else 'historical'
        revision = digest('\n'.join(f'{file}:{digest(self.pages[file])}' for file in sorted(self.used)))
        ref = self.metadata.get('docsgit') or f'本地中文手册 {label}'
        return {'major': self.major, 'label': label, 'channel': channel,
                'revision': revision, 'ref': ref}

    def guc_definition(self, dd, base):
        """Return the primary GUC cross-reference, not incidental references."""
        aliases = {base}
        if base.startswith('autovacuum_freeze_') or base.startswith('autovacuum_multixact_freeze_'):
            aliases.add(base.removeprefix('auto'))
        if base == 'autovacuum_parallel_workers':
            aliases.add('autovacuum_max_parallel_workers')
        for a in dd.select('a[href]'):
            href = a['href']
            if clean(a) not in aliases or '#GUC-' not in href:
                continue
            parsed = urlsplit(href)
            file = parsed.path.rsplit('/', 1)[-1]
            if not file.startswith('runtime-config-'):
                continue
            node = self.soup(file).find(id=parsed.fragment)
            if not node:
                raise ValueError(f'Missing GUC anchor {self.major}/{href}')
            dt = node if node.name == 'dt' else node.find_parent('dt')
            if not dt:
                raise ValueError(f'Unexpected GUC definition {href}')
            desc = dt.find_next_sibling('dd')
            if desc is None:
                raise ValueError(f'Missing GUC definition {href}')
            return (clean(a), paragraphs(desc), self.source(file, parsed.fragment,
                    '对应全局参数：' + clean(a)))
        return None


def definition(manual, scope, name, dt, dd, file, fallback, extra_sections=None):
    base = name.removeprefix('toast.')
    if base not in LABELS:
        raise ValueError(f'No Chinese editorial label for {scope}.{name}')
    option_type = dt_type(dt, INDEX_TYPES.get(base, '') if scope in INDEX_SCOPES.get(base, ()) else '')
    facts = [{'label': '适用对象', 'value': CATEGORIES[scope]}]
    if option_type:
        facts.append({'label': '取值类型', 'value': TYPE_NAMES.get(option_type, option_type)})
    desc = paragraphs(dd)
    source = manual.source(file, anchor(dt, fallback))
    related = []
    sections = list(extra_sections or [])
    if scope == 'toast':
        sections.insert(0, {'title': 'TOAST 参数的继承', 'paragraphs': [
            '该选项控制主表附属的 TOAST 表。在主表的 WITH 或 ALTER TABLE SET 子句中使用 toast. 前缀设置；若未设置对应的 TOAST 选项，而主表已设置同名选项，TOAST 表会使用主表的值。',
            '下列手册说明同时介绍主表与 TOAST 形式。自动 ANALYZE 不适用于 TOAST 表；此目录仅展开该版本手册明确列出的 toast. 选项。']})
        related.append({'label': '主表参数 ' + base, 'url': '/docs/relopts/table-' + base.replace('_', '-') + f'/?v={manual.major}'})
    elif scope == 'view':
        sections.insert(0, {'title': '视图选项', 'paragraphs': [
            '普通视图不存储查询结果。此选项控制视图的安全或更新语义，使用 CREATE VIEW 的 WITH 子句或 ALTER VIEW 设置，不是表或索引的物理存储参数。']})
    elif scope == 'table':
        sections.insert(0, {'title': '适用范围', 'paragraphs': [
            '这是关系级设置，作用于当前表或物化视图。它不等同于会话级或实例级 GUC；同名的全局参数另有独立入口。']})
    if scope in INDEX_SCOPES.get(base, ()):
        sections.insert(0, {'title': '索引访问方法', 'paragraphs': [
            f'此条目适用于 {CATEGORIES[scope]}。使用 CREATE INDEX 的 WITH 子句设置，或用 ALTER INDEX SET 修改已有索引。参数的行为、默认值与适用范围应按该索引方法阅读。']})
        if base == 'fillfactor' and scope != 'btree':
            sections[0]['paragraphs'].append('手册将四种索引方法的 fillfactor 合并说明，其中的 90 默认值及 10–100 取值范围明确针对 B-tree，不能直接套用到本索引方法。')
    guc = manual.guc_definition(dd, base)
    sources = [source]
    if guc:
        guc_name, body, guc_source = guc
        sections.append({'title': '对应全局参数：' + guc_name, 'paragraphs': [
            '以下为该版本全局参数的说明，用于理解作用与单位。文中全局默认值、可设置位置和生效方式属于 GUC；关系选项的覆盖规则仍以上面的关系级说明为准。'] + body})
        sources.append(guc_source)
        related.append({'label': '全局参数 ' + guc_name,
                        'url': f'/docs/guc/{guc_name}/?v={manual.major}'})
    sql_slug = 'create-view' if scope == 'view' else ('create-index' if scope in INDEX_SCOPES.get(base, ()) else 'create-table')
    related.append({'label': sql_slug.upper().replace('-', ' '), 'url': f'/docs/sql/{sql_slug}/?v={manual.major}'})
    syntax = f'WITH ({name} = value)'
    # Only extract default/range facts whose context unambiguously applies.
    if base == 'fillfactor' and scope in {'table', 'btree'}:
        facts += [{'label': '默认值', 'value': '100' if scope == 'table' else '90'},
                  {'label': '取值范围', 'value': '10–100（百分比）'}]
    elif base == 'check_option':
        facts.append({'label': '可选值', 'value': 'local、cascaded'})
    elif base in {'buffering', 'fastupdate', 'deduplicate_items', 'pages_per_range', 'autosummarize'}:
        body = ' '.join(desc)
        match = re.search(r'默认值(?:为|是)(?: +)?([A-Za-z0-9]+)', body)
        if match:
            facts.append({'label': '默认值', 'value': match.group(1)})
    return {'description': desc, 'signature': syntax, 'facts': facts,
            'sections': sections, 'sources': sources, 'related': related}


def parse_manual(manual):
    result = []
    table = manual.soup('sql-createtable.html')
    section = table.find(id='SQL-CREATETABLE-STORAGE-PARAMETERS')
    if section is None:
        raise ValueError('Missing table storage parameters section')
    introduction = [clean(p) for p in section.find_all('p', recursive=False)]
    material = manual.soup('sql-creatematerializedview.html')
    material_dt = next((dt for dt in material.select('dt') if 'storage_parameter' in clean(dt)), None)
    if not material_dt:
        raise ValueError('Missing materialized view storage parameter contract')
    material_body = paragraphs(material_dt.find_next_sibling('dd'))
    for names, dt, dd in list_entries(section):
        for name in names:
            scope = 'toast' if name.startswith('toast.') else 'table'
            extra = [{'title': '表存储参数的共同规则', 'paragraphs': introduction},
                     {'title': '物化视图', 'paragraphs': material_body}]
            snap = definition(manual, scope, name, dt, dd, 'sql-createtable.html', section['id'], extra)
            snap['sources'].append(manual.source('sql-creatematerializedview.html', anchor(material_dt)))
            result.append((scope, name, snap))

    index = manual.soup('sql-createindex.html').find(id='SQL-CREATEINDEX-STORAGE-PARAMETERS')
    if index is None:
        raise ValueError('Missing index storage parameters section')
    for names, dt, dd in list_entries(index):
        for name in names:
            if name not in INDEX_SCOPES:
                raise ValueError(f'Unmapped index option {name}')
            # Verify the surrounding per-AM section, so a changed upstream
            # scope does not silently inherit a stale editorial assignment.
            block = dt.find_parent('div', class_='variablelist')
            preceding = block.find_previous_sibling('p') if block else None
            scope_text = clean(preceding).lower() if preceding else ''
            expected_words = {'btree': ('b-', 'b树'), 'hash': ('hash',),
                              'gist': ('gist',), 'spgist': ('sp-gist',),
                              'gin': ('gin',), 'brin': ('brin',)}
            for scope in INDEX_SCOPES[name]:
                if not any(word in scope_text for word in expected_words[scope]):
                    raise ValueError(f'Unexpected AM context for {scope}.{name}: {scope_text}')
                result.append((scope, name, definition(manual, scope, name, dt, dd,
                    'sql-createindex.html', index['id'])))

    view = manual.soup('sql-createview.html')
    outer_dt = next((dt for dt in view.select('dt') if 'view_option_name' in clean(dt)), None)
    if not outer_dt:
        raise ValueError('Missing view option list')
    view_options = outer_dt.find_next_sibling('dd')
    for names, dt, dd in list_entries(view_options):
        for name in names:
            if name not in {'check_option', 'security_barrier', 'security_invoker'}:
                raise ValueError(f'Unknown view option {name}')
            extra = []
            if name == 'check_option':
                check_dt = next(dt for dt in view.select('dt')
                    if clean(dt).startswith('WITH [ CASCADED | LOCAL ] CHECK OPTION'))
                extra.append({'title': '写入检查的语义', 'paragraphs': paragraphs(check_dt.find_next_sibling('dd'))})
            elif name in {'security_barrier', 'security_invoker'}:
                # The option's short definition explicitly points to the notes
                # below. Include matching explanatory paragraphs there too.
                notes = [clean(p) for p in view.select('p')
                         if name in p.get_text() and p.find_parent('dd') is None]
                if notes:
                    extra.append({'title': '安全语义', 'paragraphs': notes})
            result.append(('view', name, definition(manual, 'view', name, dt, dd,
                'sql-createview.html', anchor(outer_dt), extra)))

    # OIDS lives outside the storage parameter subsection. Preserve its
    # explicitly documented compatibility semantics without calling it a GUC.
    with_dt = next((dt for dt in table.select('dt') if 'storage_parameter' in clean(dt)
                    and clean(dt).startswith('WITH')), None)
    if with_dt:
        with_dd = with_dt.find_next_sibling('dd')
        if 'OIDS' in clean(with_dd):
            snap = definition(manual, 'compat', 'oids', with_dt, with_dd,
                              'sql-createtable.html', '')
            snap['signature'] = 'WITH (OIDS = TRUE | FALSE)' if int(manual.major) <= 11 else 'WITH (OIDS = FALSE)'
            snap['facts'] = [{'label': '适用对象', 'value': '表的历史兼容语法'},
                             {'label': '取值', 'value': 'TRUE / FALSE' if int(manual.major) <= 11 else '仅 FALSE'}]
            snap['sections'].insert(0, {'title': '兼容选项', 'paragraphs': [
                '这是 CREATE TABLE 中关于行 OID 的历史语法，不是通常保存在 pg_class.reloptions 中的物理调优参数。请按所选版本阅读允许的值。']})
            result.append(('compat', 'oids', snap))
    return result


def build(bundle):
    if bundle.get('format') != 1 or set(bundle['releases']) != set(MAJORS):
        raise ValueError('Expected all PG10–20 source releases')
    items = {}
    releases = []
    for major in MAJORS:
        manual = Manual(major, bundle['releases'][major])
        definitions = parse_manual(manual)
        release = manual.release()
        releases.append(release)
        seen = set()
        for scope, name, snapshot in definitions:
            base = name.removeprefix('toast.')
            slug = ('table' if scope == 'compat' else scope) + '-' + base.replace('_', '-')
            if slug in seen:
                raise ValueError(f'Duplicate {major}/{slug}')
            seen.add(slug)
            title, summary = LABELS[base]
            if base == 'fillfactor':
                title = ('表' if scope == 'table' else CATEGORIES[scope].replace(' 索引', '')) + '填充因子'
            if scope == 'toast':
                title = 'TOAST ' + title
                summary = '对 TOAST 表单独设置。' + summary
            item = items.setdefault(slug, {'slug': slug, 'name': name, 'name_zh': title,
                'category': CATEGORIES[scope], 'summary': summary,
                'aliases': [scope + '.' + base] if scope != 'toast' else [base], 'versions': {}})
            snapshot['release'] = release
            item['versions'][major] = snapshot
    return {'format': 1, 'kind': 'relopts', 'releases': releases,
            'coverage_notes': COVERAGE_NOTES, 'items': sorted(items.values(), key=lambda item: item['slug'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/wiki/relopts.json')
    parser.add_argument('--input-sources', type=Path)
    parser.add_argument('--export-sources', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    bundle = json.loads(args.input_sources.read_text()) if args.input_sources else read_database()
    if args.export_sources:
        args.export_sources.parent.mkdir(parents=True, exist_ok=True)
        args.export_sources.write_text(serialize(bundle))
    result = build(bundle)
    encoded = serialize(result)
    if args.check:
        if not args.output.exists() or args.output.read_text() != encoded:
            raise SystemExit('Relation options snapshot differs; regenerate and review.')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    counts = {major: sum(major in item['versions'] for item in result['items']) for major in MAJORS}
    print(json.dumps({'items': len(result['items']), 'snapshots': sum(counts.values()),
                      'versions': counts, 'check': args.check}, ensure_ascii=False))


if __name__ == '__main__':
    main()
