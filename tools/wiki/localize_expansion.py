#!/usr/bin/env python3
"""Localize fixed Wiki expansion snapshots without changing source facts or a database."""
import argparse
from collections import defaultdict
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
TECHNICAL_PATH = ROOT / 'data/wiki/translations/technical_values.json'
TECHNICAL_VALUES = set(json.loads(TECHNICAL_PATH.read_text())) if TECHNICAL_PATH.exists() else set()
FILES = ('data_types.json.gz', 'index_methods.json', 'plan_nodes.json.gz', 'operators.json.gz',
         'operator_classes.json.gz', 'foreign_data_wrappers.json.gz', 'table_methods.json.gz',
         'psql_commands.json.gz', 'command_tools.json.gz', 'connection_parameters.json.gz',
         'statistics_metrics.json.gz', 'storage_structures.json.gz', 'protocol_messages.json.gz',
         'procedural_languages.json.gz', 'text_search_components.json.gz', 'authentication_methods.json.gz',
         'collations_encodings.json.gz', 'logical_decoding_plugins.json.gz')


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith('.gz') else raw)


def write(path, value):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(gzip.compress(raw, mtime=0) if str(path).endswith('.gz') else raw)


def plain(value):
    text = value.get_text(' ', strip=True) if hasattr(value, 'get_text') else value
    return ' '.join(text.replace('\u200b', '').replace('\xa0', ' ').split())


def cjk(value):
    return bool(re.search(r'[\u3400-\u9fff]', value))


def sources(root, commit):
    result = {}
    for name in FILES:
        raw = subprocess.run(['git', '-C', str(root), 'show', commit + ':data/wiki/' + name],
                             check=True, capture_output=True).stdout
        result[name] = json.loads(gzip.decompress(raw) if name.endswith('.gz') else raw)
    return result


def needed_pages(datasets):
    result = set()

    def visit(value, major):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('url', 'source_url', 'manual_path') and isinstance(child, str):
                    path = urlsplit(child).path
                    match = re.match(r'^/docs/(\d+(?:\.\d+)?|devel)/([^/]+\.html)$', path)
                    if match:
                        result.add((str(major), match[2]))
                    elif key == 'manual_path' and re.fullmatch(r'[a-z0-9_-]+\.html', path):
                        result.add((str(major), path))
                elif key != 'comparison_data':
                    visit(child, major)
        elif isinstance(value, list):
            for child in value:
                visit(child, major)
    for data in datasets.values():
        for item in data['items']:
            for major, snapshot in item['versions'].items():
                visit(snapshot, major)
    return sorted(result)


def export_bundle(datasets, path):
    import psycopg2
    needed = needed_pages(datasets)
    bundle = {
        'format': 1, 'pages': {},
        'source_snapshot_hashes': {name: sha(json.dumps(data, sort_keys=True))
                                   for name, data in datasets.items()},
    }
    for language, database in [('en', 'center'), ('zh', 'pgweb')]:
        with psycopg2.connect('dbname=' + database) as connection:
            connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
            with connection.cursor() as cursor:
                for major, file in needed:
                    tree = '0' if major == '20' else major
                    cursor.execute('SELECT content FROM docs WHERE version=%s AND file=%s', [tree, file])
                    row = cursor.fetchone()
                    if row and row[0]:
                        bundle['pages'].setdefault(major + '/' + file, {})[language] = row[0]
                if language == 'zh':
                    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='pgext' AND table_name='universe'")
                    bundle['extension_columns'] = [r[0] for r in cursor.fetchall()]
                    cursor.execute('SELECT name, en_desc, zh_desc FROM pgext.universe ORDER BY name')
                    bundle['extensions'] = {name: {'en': en, 'zh': zh} for name, en, zh in cursor.fetchall()}
    write(path, bundle)
    print(json.dumps({'pages_requested': len(needed), 'en': sum('en' in p for p in bundle['pages'].values()),
                      'zh': sum('zh' in p for p in bundle['pages'].values()), 'extension_columns': bundle['extension_columns']}))


def fingerprint(node):
    code = tuple(plain(c) for c in node.select('code, tt, kbd, pre') if plain(c))
    numbers = tuple(re.findall(r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])', plain(node)))
    return code, numbers


def align_page(en_html, zh_html):
    """Align unchanged semantic containers; never use neighbouring major versions."""
    en, zh = (BeautifulSoup(content, 'html.parser') for content in (en_html, zh_html))
    for soup in (en, zh):
        for link in soup.select('a.id_link'):
            link.decompose()
    candidates = defaultdict(list)

    def pair(a, b, locator):
        if a is None or b is None or a.name != b.name:
            return
        left, right = plain(a), plain(b)
        if left and cjk(right) and not cjk(left) and fingerprint(a) == fingerprint(b):
            candidates[left].append({'text': right, 'html': b.decode_contents(), 'locator': locator})

    def pair_tree(a, b, locator):
        if a is None or b is None or a.name != b.name:
            return
        pair(a, b, locator)
        aa = [n for n in a.children if getattr(n, 'name', None)]
        bb = [n for n in b.children if getattr(n, 'name', None)]
        if [n.name for n in aa] == [n.name for n in bb]:
            for i, (left, right) in enumerate(zip(aa, bb)):
                pair_tree(left, right, locator + '/' + left.name + '[' + str(i) + ']')

    # Stable IDs anchor paragraphs; cardinality and code/numeric fingerprints
    # prevent shifted definitions and changed values from being substituted.
    for a in en.select('[id]'):
        ident = a.get('id')
        b = zh.find(id=ident)
        if b is None:
            continue
        pair_tree(a, b, '#' + ident)
        if a.name == 'dt':
            pair_tree(a.find_next_sibling('dd'), b.find_next_sibling('dd'), '#' + ident + '/dd')
        for tag in ('p', 'h1', 'h2', 'h3', 'h4'):
            aa = [n for n in a.find_all(tag) if n.find_parent(id=True) is a]
            bb = [n for n in b.find_all(tag) if n.find_parent(id=True) is b]
            if len(aa) == len(bb):
                for i, (left, right) in enumerate(zip(aa, bb)):
                    pair(left, right, '#' + ident + '/' + tag + '[' + str(i) + ']')
    # Table columns and parameter definitions have stable technical names even
    # when the older manual did not give every row an ID.
    for tag in ('tr', 'dt'):
        def keyed(soup):
            out = defaultdict(list)
            for node in soup.find_all(tag):
                head = node.find(['td', 'th'], recursive=False) if tag == 'tr' else node
                if not head:
                    continue
                tokens = tuple(plain(code) for code in head.select('code, tt') if plain(code))
                if tokens:
                    out[tokens].append(node)
            return out
        aa, bb = keyed(en), keyed(zh)
        for key in aa.keys() & bb.keys():
            if len(aa[key]) != 1 or len(bb[key]) != 1:
                continue
            a, b = aa[key][0], bb[key][0]
            if tag == 'dt':
                a, b = a.find_next_sibling('dd'), b.find_next_sibling('dd')
                if a is None or b is None:
                    continue
            pair_tree(a, b, tag + ':' + '|'.join(key))
            left = a.find_all(['p', 'td'], recursive=tag == 'dt')
            right = b.find_all(['p', 'td'], recursive=tag == 'dt')
            if len(left) == len(right):
                for i, (x, y) in enumerate(zip(left, right)):
                    pair(x, y, tag + ':' + '|'.join(key) + '[' + str(i) + ']')
    return {key: rows[0] for key, rows in candidates.items() if len({r['text'] for r in rows}) == 1}


def build_alignment(bundle):
    result = {}
    for i, (key, page) in enumerate(bundle['pages'].items()):
        if 'en' in page and 'zh' in page:
            result[key] = align_page(page['en'], page['zh'])
        if i % 100 == 0:
            print('Aligned', i, '/', len(bundle['pages']), flush=True)
    return result


def text_fields(item):
    """Enumerate display prose; technical source records and comparisons stay intact."""
    for field in ('summary', 'category'):
        yield '/' + field, item, field
    for major, snapshot in item['versions'].items():
        prefix = '/versions/' + major

        def scalar(parent, key, path):
            if isinstance(parent.get(key), str):
                yield path + '/' + key, parent, key

        def array(parent, key, path):
            for i, value in enumerate(parent.get(key, [])):
                if isinstance(value, str):
                    yield path + '/' + key + '/' + str(i), parent[key], i
        yield from array(snapshot, 'description', prefix)
        for i, fact in enumerate(snapshot.get('facts', [])):
            for key in ('label', 'value'):
                yield from scalar(fact, key, prefix + '/facts/' + str(i))
        for i, section in enumerate(snapshot.get('sections', [])):
            path = prefix + '/sections/' + str(i)
            yield from scalar(section, 'title', path)
            yield from array(section, 'paragraphs', path)
            for j, block in enumerate(section.get('blocks', [])):
                yield from array(block, 'paragraphs', path + '/blocks/' + str(j))
        for key in ('tables', 'collection_tables'):
            for i, table in enumerate(snapshot.get(key, [])):
                path = prefix + '/' + key + '/' + str(i)
                for field in ('title', 'caption'):
                    yield from scalar(table, field, path)
                for j, column in enumerate(table['columns']):
                    yield from scalar(column, 'label', path + '/columns/' + str(j))
                for j, row in enumerate(table['rows']):
                    for field, value in row.items():
                        cellpath = path + '/rows/' + str(j) + '/' + field
                        if isinstance(value, str):
                            yield cellpath, row, field
                        elif isinstance(value, dict):
                            yield from scalar(value, 'text', cellpath)
        for i, capability in enumerate(snapshot.get('capabilities', [])):
            for key in ('label', 'value', 'note'):
                yield from scalar(capability, key, prefix + '/capabilities/' + str(i))
        for i, option in enumerate(snapshot.get('storage_options', [])):
            yield from array(option, 'description', prefix + '/storage_options/' + str(i))
        if 'memory' in snapshot:
            yield from scalar(snapshot['memory'], 'description', prefix + '/memory')
        for i, link in enumerate(snapshot.get('related', [])):
            yield from scalar(link, 'label', prefix + '/related/' + str(i))


def collect_texts(datasets):
    result = defaultdict(set)
    for data in datasets.values():
        for item in data['items']:
            for path, parent, key in text_fields(item):
                value = plain(parent[key])
                if value and not cjk(value):
                    result[value].add(data['kind'] + ':' + path.split('/versions/')[-1].split('/', 1)[-1])
    return {text: sorted(where) for text, where in sorted(result.items())}


def technical(text):
    """Canonical identifiers, syntax and example results are not translated prose."""
    prose = re.search(r'\b(?:is|are|allows|would|will|used|specifies|controls|equivalent|means|returns)\b', text)
    return (text in TECHNICAL_VALUES or not re.search(r'[A-Za-z]', text) or
            bool(re.fullmatch(r'[\w./:+*<>=!?|&~#@%$\\\-\[\](),{}]+', text)) or
            (text.startswith(('SELECT ', 'CREATE ', 'ALTER ', '--', '-?', '\\', 'src/', 'contrib/', 'https://')) and not prose and '—' not in text) or
            bool(re.fullmatch(r'-[A-Za-z0-9][\s\S]*', text)) or
            bool(re.fullmatch(r'(?:psql|libpq) \d+\S*', text)) or
            bool(re.fullmatch(r'[~!@#$%^&*+|<>=?/`\-]+\([\w.\s,\[\]\"]+\)', text)) or
            bool(re.fullmatch(r'(?:pg_catalog\.)?\"[\w.]+\"', text)) or
            bool(re.fullmatch(r'(?:character|varchar|bpchar|interval|time|timestamp|double precision)[( \[].*', text)) or
            bool(re.fullmatch(r'(?:ISO|ECMA|ASRO|KOI|Windows|IBM|UTF|EUC|JIS|MULE|Shift|SJIS|ABC|TCVN|VSCII|UHC|JOHAB|GBK|GB)[A-Za-z0-9_, .()/+\-]*', text)) or
            bool(re.fullmatch(r'[A-Z][A-Z0-9_]*(?: [A-Z][A-Z0-9_]*)+', text)) or
            bool(re.fullmatch(r'Byte\d+\(.*\)|Int\d+\(.*\)|String\(.*\)', text)) or
            bool(re.fullmatch(r"'.*'(?:\:\:\w+)?", text)) or
            text in {'double precision', 'timestamp with time zone', 'timestamp without time zone'} or
            text in {'Seq Scan', 'Index Scan', 'Index Only Scan', 'Bitmap Heap Scan', 'Bitmap Index Scan', 'Tid Scan', 'Tid Range Scan', 'Subquery Scan', 'Function Scan', 'Table Function Scan', 'Values Scan', 'CTE Scan', 'Named Tuplestore Scan', 'WorkTable Scan', 'Foreign Scan', 'Custom Scan', 'Nested Loop', 'Merge Join', 'Hash Join', 'Merge Append', 'Gather Merge', 'Incremental Sort', 'Recursive Union', 'Sample Scan'} or
            bool(re.fullmatch(r'\d{4}-\d{2}-\d{2} · [0-9a-f]+ · [\w./-]+', text)) or
            bool(re.fullmatch(r'(?:[A-Z]\.)?[0-9.]+ (?:TOAST|test_decoding)', text)) or
            bool(re.fullmatch(r'Int(?:16|32|64) ?[\[(][A-Za-z_ ]+[\])]', text)) or
            text in {'Table AM', 'Foreign Insert', 'Foreign Update', 'Foreign Delete', 'Custom Scan (%s)', '&amp;', '<a href=\"dictionaries.html\">'} or
            bool(re.fullmatch(r'(?:Mskanji|WIN\d+) , [A-Za-z0-9 ,]+', text)) or
            text.startswith(('... / Append', '... / MergeAppend', '| Append', 'outer: (', 'transvalue = ')) or
            ' → ' in text or
            bool(re.fullmatch(r'[\w]+(?:\([^)]*\))?(?:, [\w]+(?:\([^)]*\))?)+', text)))


def patterned(text):
    rules = [
        (r'(.+?) -- access method routine to recheck a tuple in EvalPlanQual', r'\1：在 EvalPlanQual 中重新检查元组的访问方法例程。'),
        (r'deprecated, use (.+) instead', r'已弃用，请改用 \1'),
        (r'Section ([\d.]+)', r'第 \1 节'),
        (r'Table ([\d.\-]+)', r'表 \1'),
        (r'The matching libpq source declares the keyword (\w+), but the Parameter Key Words section does not document it. Its declaration is retained as source evidence; this does not establish a supported operational use.', r'对应版本的 libpq 源码声明了关键字 \1，但“参数关键字”一节并未记载它。此处保留声明作为源码证据；这不代表它是受支持的使用方式。'),
        (r'(.+) operator class for (.+); member of (.+)\.', r'\2 类型的 \1 操作符类，属于 \3 家族。'),
        (r'(.+) operator family (.+)\.', r'\1 操作符家族 \2。'),
        (r'Text search configuration (.+)\.', r'全文检索配置 \1。'),
        (r'Snowball stemmer for (.+) language\.', r'用于 \1 语言的 Snowball 词干提取器。'),
        (r'(.+) untrusted procedural language', r'\1 非可信过程语言'),
        (r'(.+) procedural language', r'\1 过程语言'),
        (r'Commutator: (.+)', r'交换操作符：\1'),
        (r'Negator: (.+)', r'取反操作符：\1'),
        (r'(.+) classes', r'\1 操作符类'),
        (r'(.+) families', r'\1 操作符家族'),
        (r'(.+) family', r'\1 家族'),
        (r'(.+) data type', r'\1 数据类型'),
        (r'(.+) columns', r'\1 字段'),
        (r'(.+) catalog', r'\1 系统目录'),
        (r'(.+) configuration', r'\1 配置'),
        (r'(.+) template', r'\1 模板'),
        (r'(.+) dictionary', r'\1 词典'),
        (r'(.+) index access method', r'\1 索引访问方法'),
        (r'(.+) Index AM', r'\1 索引访问方法'),
        (r'Text names recorded by this source: (.+)', r'此源码记录的文本名称：\1'),
        (r'Callbacks in this build: (.+)', r'此构建的回调：\1'),
        (r'Chapter (\d+)(.*)', r'第 \1 章\2'),
        (r'([\d., +−\-–]+) bytes', r'\1 字节'),
        (r'([\d., +−\-–]+) years', r'\1 年'),
        (r'([\d., +−\-–]+) digits', r'\1 位数字'),
    ]
    for pattern, replacement in rules:
        if re.fullmatch(pattern, text):
            return re.sub(pattern, replacement, text)
    return None


class Translator:
    def __init__(self, bundle, alignment, directory):
        self.bundle = bundle
        self.manual = defaultdict(lambda: defaultdict(list))
        for page, rows in alignment.items():
            major = page.split('/')[0]
            for text, row in rows.items():
                self.manual[major][text].append(dict(row, page=page))
        self.editorial = {}
        self.dictionary_hashes = {}
        if TECHNICAL_PATH.exists():
            self.dictionary_hashes[TECHNICAL_PATH.name] = sha(TECHNICAL_PATH.read_bytes())
        for path in sorted(directory.glob('*.tsv')):
            self.dictionary_hashes[path.name] = sha(path.read_bytes())
            for line in path.read_text().splitlines():
                if '\t' in line:
                    en, zh = line.split('\t', 1)
                    if zh:
                        self.editorial[plain(en)] = zh
        for path in sorted(directory.glob('editorial_*.json')):
            self.dictionary_hashes[path.name] = sha(path.read_bytes())
            for en, zh in read(path).items():
                if zh:
                    self.editorial[plain(en)] = zh
        self.fallback = defaultdict(set)
        self.html_cache = {}

    def translate(self, value, major, preferred=()):
        text = plain(value)
        if not text or cjk(text):
            return value, None
        if text in self.editorial:
            return self.editorial[text], {'method': 'authored dictionary', 'key': sha(text)}
        rows = self.manual[major].get(text, [])
        chosen = next((row for page in preferred for row in rows if row['page'] == page), None)
        if chosen is None and len({row['text'] for row in rows}) == 1 and rows:
            chosen = rows[0]
        if chosen:
            return chosen['text'], dict(chosen, method='same-major semantic node')
        result = patterned(text)
        if result:
            return result, {'method': 'authored template', 'key': sha(text)}
        if technical(text):
            return value, None
        return value, {'method': 'fallback', 'language': 'en'}

    def manual_html(self, html, major, path):
        key = (major, path, sha(html))
        if key in self.html_cache:
            return self.html_cache[key]
        soup = BeautifulSoup(html, 'html.parser')
        file = urlsplit(path).path.rsplit('/', 1)[-1]
        preferred = [major + '/' + file]
        # Original English links continue to lead to the exact English source.
        base = 'https://pg.center/docs/' + ('devel' if major == '20' else major) + '/' + file
        for link in soup.select('[href]'):
            if not link['href'].startswith('#'):
                link['href'] = urljoin(base, link['href'])
        used, remaining, translated = [], [], 0
        for node in list(soup.find_all(['p', 'td', 'th', 'dt', 'li', 'h1', 'h2', 'h3', 'h4', 'caption'])):
            if not any(parent is soup for parent in node.parents) or node.find_parent(['pre', 'code']):
                continue
            before = plain(node)
            after, evidence = self.translate(before, major, preferred)
            if evidence and evidence['method'] != 'fallback':
                if evidence.get('html'):
                    fragment = BeautifulSoup(evidence['html'], 'html.parser')
                    location = '/docs/' + ('devel' if major == '20' else major) + '/' + evidence['page'].split('/', 1)[1]
                    for link in fragment.select('[href]'):
                        link['href'] = urljoin(location, link['href'])
                    node.clear()
                    for child in list(fragment.contents):
                        node.append(child.extract())
                else:
                    node.clear()
                    node.append(after)
                node['lang'] = 'zh'
                translated += 1
                used.append(evidence)
            elif evidence and evidence['method'] == 'fallback' and not node.find(['p', 'td', 'th', 'li']):
                node['lang'] = 'en'
                remaining.append(before)
        language = 'mixed' if remaining and translated else 'en' if remaining else 'zh'
        result = (str(soup), language, used, sorted(set(remaining)))
        self.html_cache[key] = result
        return result


def english_sources(value):
    if isinstance(value, list):
        for row in value:
            english_sources(row)
    elif isinstance(value, dict):
        if isinstance(value.get('url'), str) and value['url'].startswith('/docs/'):
            value['original_url'] = value['url']
            value['url'] = 'https://pg.center' + value['url']
            value['language'] = 'en'
        for child in value.values():
            if isinstance(child, (dict, list)):
                english_sources(child)


def localize(data, translator, source_commit):
    out = deepcopy(data)
    out['language'] = 'zh'
    out['localization'] = {'source_language': 'en', 'target_language': 'zh', 'source_commit': source_commit,
                           'source_sha256': sha(json.dumps(data, sort_keys=True)),
                           'dictionaries': translator.dictionary_hashes,
                           'manual_bundle_sha256': sha(json.dumps(translator.bundle, sort_keys=True)),
                           'tool_sha256': sha(Path(__file__).read_bytes()),
                           'policy': 'Same-major semantic-node alignment; source facts and comparison data retained.'}
    counts = defaultdict(int)
    for item in out['items']:
        original = next(row for row in data['items'] if row['slug'] == item['slug'])
        metadata = {}
        for major, snapshot in item['versions'].items():
            metadata[major] = {'language': 'zh', 'source_language': 'en', 'status': 'complete',
                               'fallback_fields': [], 'sources': [], 'original_text': {},
                               'original_snapshot_sha256': sha(json.dumps(original['versions'][major], sort_keys=True))}
        fields = list(text_fields(item))
        for path, parent, key in fields:
            major = path.split('/')[2] if path.startswith('/versions/') else max(item['versions'], key=lambda x: tuple(map(int, x.split('.'))))
            snapshot = item['versions'][major]
            preferred = [major + '/' + urlsplit(snapshot.get('manual_path', '')).path.rsplit('/', 1)[-1]]
            before = parent[key]
            extension = parent.get('extension', {}) if isinstance(parent, dict) else {}
            ext_name = extension.get('text') if isinstance(extension, dict) else None
            entry = translator.bundle.get('extensions', {}).get(ext_name, {})
            if key == 'description' and plain(entry.get('en') or '') == plain(before) and cjk(entry.get('zh') or ''):
                after = entry['zh']
                evidence = {'method': 'existing extension catalogue', 'extension': ext_name,
                            'sha256': sha(json.dumps(entry, sort_keys=True))}
                metadata[major].setdefault('extension_sources', []).append(evidence)
            else:
                after, evidence = translator.translate(before, major, preferred)
            if key == 'label' and isinstance(parent, dict) and '/related/' in path:
                link_path = urlsplit(parent.get('url', '')).path
                file = link_path.rsplit('/', 1)[-1]
                page_key = major + '/' + file
                if before == file.removesuffix('.html') and page_key in translator.bundle['pages']:
                    page_html = translator.bundle['pages'][page_key].get('zh', '')
                    title = BeautifulSoup(page_html, 'html.parser').find(['h1', 'h2'])
                    if title is not None and cjk(plain(title)):
                        after = re.sub(r'^\d+(?:\.\d+)*\.?\s*', '', plain(title)).rstrip(' #')
                        evidence = {'method': 'same-major semantic node', 'page': page_key, 'locator': 'page-title/' + title.name}
            if evidence and evidence['method'] == 'fallback':
                metadata[major]['fallback_fields'].append(path)
                translator.fallback[plain(before)].add(out['kind'] + ':' + item['slug'] + path)
                counts['fallback_display_fields'] += 1
            elif evidence:
                metadata[major]['original_text'][path] = before
                parent[key] = after
                counts['translated_display_fields'] += 1
                if evidence.get('page'):
                    metadata[major]['sources'].append((evidence['page'], evidence['locator']))
        for major, snapshot in item['versions'].items():
            meta = metadata[major]
            if snapshot.get('manual_html'):
                html, language, used, remaining = translator.manual_html(snapshot['manual_html'], major, snapshot['manual_path'])
                snapshot['manual_html'] = html
                snapshot['manual_language'] = language
                if language != 'zh':
                    meta['fallback_fields'].append('/versions/' + major + '/manual_html')
                    for text in remaining:
                        translator.fallback[text].add(out['kind'] + ':' + item['slug'] + '/versions/' + major + '/manual_html')
                    counts['manual_html_with_english'] += 1
                for entry in used:
                    if entry.get('page'):
                        meta['sources'].append((entry['page'], entry['locator']))
                path = snapshot['manual_path']
                if not path.startswith('/'):
                    path = '/docs/' + ('devel' if major == '20' else major) + '/' + path
                if language != 'zh':
                    snapshot['manual_path'] = 'https://pg.center' + path
            for field in ('sources', 'capabilities', 'storage_options', 'memory'):
                if field in snapshot:
                    english_sources(snapshot[field])
            source_rows = []
            grouped = defaultdict(set)
            for page, locator in meta['sources']:
                grouped[page].add(locator)
            for page, locators in sorted(grouped.items()):
                doc_major, file = page.split('/', 1)
                source_rows.append({'language': 'zh', 'url': '/docs/' + ('devel' if doc_major == '20' else doc_major) + '/' + file,
                                    'sha256': sha(translator.bundle['pages'][page]['zh']),
                                    'matched_nodes': sorted(locators), 'method': 'same-major semantic node'})
            meta['sources'] = source_rows
            meta['fallback_fields'] = sorted(set(meta['fallback_fields']))
            if meta['fallback_fields']:
                meta['status'] = 'partial'
            snapshot['localization'] = meta
            counts['snapshots'] += 1
        counts['entities'] += 1
    return out, dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT.parent / 'pg.center')
    parser.add_argument('--source-commit', default='a709ab85')
    parser.add_argument('--bundle', type=Path, default=ROOT / 'tmp/wiki-localization-20260930/manuals.json.gz')
    parser.add_argument('--export-sources', action='store_true')
    parser.add_argument('--align', action='store_true')
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    data = sources(args.source_root, args.source_commit)
    if args.export_sources:
        export_bundle(data, args.bundle)
    if args.align:
        write(args.bundle.with_name('alignment.json.gz'), build_alignment(read(args.bundle)))
    if args.collect:
        write(args.bundle.with_name('display-texts.json'), collect_texts(data))
    if args.build:
        bundle = read(args.bundle)
        translator = Translator(bundle, read(args.bundle.with_name('alignment.json.gz')), ROOT / 'data/wiki/translations')
        commit = subprocess.run(['git', '-C', str(args.source_root), 'rev-parse', args.source_commit],
                                capture_output=True, text=True, check=True).stdout.strip()
        report = {}
        for name, dataset in data.items():
            result, report[dataset['kind']] = localize(dataset, translator, commit)
            write(ROOT / 'data/wiki' / name, result)
            print(name, report[dataset['kind']], flush=True)
        write(args.bundle.with_name('fallbacks.json'), {text: sorted(paths) for text, paths in sorted(translator.fallback.items())})
        write(ROOT / 'data/wiki/translations/report.json', report)
        manual_remaining = {text: sorted(path for path in paths if path.endswith('/manual_html'))
                            for text, paths in translator.fallback.items()
                            if any(path.endswith('/manual_html') for path in paths)}
        display_remaining = {text: sorted(path for path in paths if not path.endswith('/manual_html'))
                             for text, paths in translator.fallback.items()
                             if any(not path.endswith('/manual_html') for path in paths)}
        coverage = {
            'manual_prose_unique': len(manual_remaining),
            'manual_prose_occurrences': sum(len(paths) for paths in manual_remaining.values()),
            'display_prose_unique': len(display_remaining),
            'display_prose_occurrences': sum(len(paths) for paths in display_remaining.values()),
            'reviewed_technical_values': len(TECHNICAL_VALUES),
            'reviewed_sql_examples': sum(value.startswith('sql_example:') for value in read(TECHNICAL_PATH).values()),
            'reviewed_technical_values_excluding_sql_examples': sum(not value.startswith('sql_example:') for value in read(TECHNICAL_PATH).values()),
            'manual_remaining': manual_remaining, 'display_remaining': display_remaining,
            'scope': 'Display prose only; original source quotes, SQL examples and canonical identifiers remain source evidence.',
        }
        write(ROOT / 'data/wiki/translations/coverage.json', coverage)
        manifest = {
            'source_commit': commit, 'source_snapshot_hashes': bundle['source_snapshot_hashes'],
            'manual_bundle_sha256': sha(json.dumps(bundle, sort_keys=True)),
            'tool_sha256': sha(Path(__file__).read_bytes()),
            'dictionaries': translator.dictionary_hashes,
            'manuals': {page: {language: sha(content) for language, content in texts.items()}
                        for page, texts in bundle['pages'].items()},
            'extension_descriptions': {name: sha(json.dumps(entry, sort_keys=True))
                                       for name, entry in bundle.get('extensions', {}).items()},
        }
        write(ROOT / 'data/wiki/translations/source_manifest.json', manifest)


if __name__ == '__main__':
    main()
