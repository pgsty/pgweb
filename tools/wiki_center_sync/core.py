"""Build native SQL/function/SQLSTATE snapshots from a sealed Chinese projection.

File-only adapter: neither Django setup nor database access occurs here.  The
native importers remain the authority for validation, hashes and publication.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, unquote

from bs4 import BeautifulSoup

# Exact PG18 references reviewed against the frozen target pages and same-version
# pgdoc/zh/18/{plpgsql,fdwhandler}.sgml. No source bytes or evidence hashes change.
MANUAL_LINK_CORRECTIONS = {
    '/docs/18/plpgsql-control-structures.html#PLPGSQL-GET-DIAGNOSTICS':
        '/docs/18/plpgsql-control-structures.html#PLPGSQL-EXCEPTION-DIAGNOSTICS',
    '/docs/18/fdwhandler.html#FDW-CALLBACKS-SCAN':
        '/docs/18/fdw-callbacks.html#FDW-CALLBACKS-SCAN',
}


def read_rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def version_key(value):
    return tuple(map(int, value.split('.')))


def display_version_metadata(metadata):
    """Refresh the PG19 reader label; retain sampled source/measurement fields."""
    result = deepcopy(metadata)
    if result.get('major') == '19':
        result['label'] = '19 rc 1'
    return result


def write_snapshot(path, value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode()
    path.write_bytes(gzip.compress(data, mtime=0))
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def fresh_row(row, revision):
    row = deepcopy(row)
    # These are hashes of the old transport rows, not this Django projection.
    for key in ('content_hash', 'derived_content_hash', 'imported_at', 'repair_provenance'):
        row.pop(key, None)
    row['source_rev'] = revision
    return row


def chinese_text(record, dataset_hash):
    text = deepcopy(record['text'])
    if text['locale'] != 'zh-Hans' or not text.get('body_html'):
        raise ValueError('Missing selected Chinese body: ' + repr((record['collection'], record['key'], record['version'])))
    text['dataset_hash'] = dataset_hash
    text['entry_key'] = record['key']
    text['definition_version'] = record['version']
    return text


def sql_display(body):
    """Decode the exact pre + section wrappers emitted by the native projector."""
    soup = BeautifulSoup(body, 'html.parser')
    pre = soup.find('pre', recursive=False)
    if pre is None:
        raise ValueError('Native SQL body has no top-level synopsis')
    sections = []
    keys = {'描述': 'description', '参数': 'parameters', '注解': 'notes', '注意': 'notes',
            '示例': 'examples', '用法': 'usage', '诊断': 'diagnostics', '缺陷': 'bugs',
            '历史': 'history', '兼容性': 'compatibility',
            '另见': 'see_also', '参见': 'see_also', '又见': 'see_also', '输出': 'outputs'}
    for section in soup.find_all('section', recursive=False):
        heading = section.find('h2', recursive=False)
        if heading is None:
            raise ValueError('Native SQL section has no heading')
        title = heading.get_text(' ', strip=True)
        heading.extract()
        sections.append({'key': keys.get(title, 'other'), 'title': title,
                         'html': section.decode_contents()})
    if not sections:
        raise ValueError('Native SQL body has no sections')
    return {'synopsis_html': pre.decode_contents(), 'synopsis_text': pre.get_text(),
            'sections': sections, 'sections_same_as': '', 'lang': 'zh'}


def local_manual_url(url, manuals):
    """Only resolve exact same-version files and unique case-only anchor aliases."""
    parsed = urlsplit(url)
    if parsed.netloc and parsed.netloc not in ('pg.center', 'pgsql.cc'):
        return url, None
    path = parsed.path[3:] if parsed.path.startswith('/zh/') else parsed.path
    corrected = MANUAL_LINK_CORRECTIONS.get(urlunsplit(('', '', path, parsed.query, parsed.fragment)))
    if corrected:
        parsed = urlsplit(corrected)
        path = parsed.path
    parts = path.strip('/').split('/')
    if len(parts) != 3 or parts[0] != 'docs':
        return url, None
    major, filename = parts[1:]
    page = manuals.get((major, filename))
    if not page and filename.endswith('.htm'):
        candidate = filename + 'l'
        page = manuals.get((major, candidate))
        if page:
            filename = candidate
    if not page:
        return url, 'missing-page'
    anchor = unquote(parsed.fragment)
    if anchor and anchor not in page['anchors']:
        aliases = [a for a in page['anchors'] if a.casefold() == anchor.casefold()]
        if len(aliases) != 1:
            return url, 'missing-anchor'
        anchor = aliases[0]
    return urlunsplit(('', '', '/docs/{}/{}'.format(major, filename), parsed.query, anchor)), None


def attach_local_links(text, manuals, unresolved):
    fragments = [text['body_html']]
    fragments += [s.get('description_zh_html', '') for s in text.get('payload', {}).get('signatures', [])]
    links = {a['href'] for fragment in fragments for a in
             BeautifulSoup(fragment, 'html.parser').find_all('a', href=True)}
    mapping = {}
    for url in sorted(links):
        resolved, problem = local_manual_url(url, manuals)
        if problem:
            unresolved.append({'key': text['entry_key'], 'version': text['definition_version'],
                               'url': url, 'reason': problem})
        elif resolved != url:
            mapping[url] = resolved
    if mapping:
        text['link_map'] = mapping


def local_doc(snapshot, major, manuals):
    doc = snapshot.get('doc') or snapshot
    slug = 'devel' if major == '20' else major
    raw = '/docs/{}/{}{}'.format(slug, doc['file'], '#' + doc['anchor'] if doc.get('anchor') else '')
    resolved, problem = local_manual_url(raw, manuals)
    if problem:
        # Do not invent a replacement deep anchor. The verified containing page
        # is still a valid local reference; original English coordinates survive.
        resolved, problem = local_manual_url(raw.split('#', 1)[0], manuals)
    if problem:
        return None
    parsed = urlsplit(resolved)
    return {'slug': slug, 'file': parsed.path.rsplit('/', 1)[-1], 'anchor': parsed.fragment}


def source_row(raw, record):
    definition = record['definition']
    return raw[(definition['source_database'], definition['source_table'])][definition['source_key']]


def native_header(revision):
    return {'format': 1, 'generated_at': '2026-10-23T00:00:00Z', 'source_rev': revision,
            'default_major': '18', 'stats': {}, 'harvest': {'source': revision}}


def changes_receipts(table, rows, target, key):
    result = []
    for row in rows:
        old = target.get(row[key])
        result.append({'table': table, 'key': row[key], 'operation': 'update' if old else 'add',
                       'before_sha256': digest(old) if old else None,
                       'after_business_sha256': digest(row)})
    return result


def build(source_root, target_root, output_dir):
    source_root, target_root, output_dir = map(Path, (source_root, target_root, output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((source_root / 'manifest.json').read_text())
    dataset_hash = manifest['dataset_hash']
    revision = 'center-wiki:' + dataset_hash + ':selected-zh'
    records = defaultdict(lambda: defaultdict(dict))
    for record in read_rows(source_root / 'canonical.jsonl.gz'):
        if record['collection'] in ('sql', 'func', 'sqlstate'):
            records[record['collection']][record['key']][record['version']] = record
    raw = {}
    for db in ('center', 'pgweb'):
        for table, key in (('sqlcmd', 'slug'), ('func', 'slug'), ('sqlstate', 'sqlstate')):
            raw[(db, table)] = {r[key]: r for r in read_rows(source_root / 'raw' / db / (table + '.jsonl.gz'))}
    targets = {table: {r[key]: r for r in read_rows(target_root / (table + '.jsonl.gz'))}
               for table, key in (('sqlcmd', 'slug'), ('func', 'slug'), ('sqlstate', 'sqlstate'))}
    source_versions = {r['major']: r for r in read_rows(source_root / 'raw/center/func_version.jsonl.gz')}
    manuals = {(r['version'], r['file']): r for r in read_rows(target_root / 'manual-pages.jsonl.gz')}
    unresolved = []
    receipts, outputs = [], {}
    report = {'dataset_hash': dataset_hash, 'selected_locale': 'zh-Hans',
              'sql_alias_mapping': {'wait-for': 'wait'}, 'outputs': outputs}

    commands = []
    for key, versions in sorted(records['sql'].items()):
        # The native dataset retains both inherited keys. PGSQL.CC has always
        # canonicalized WAIT to wait and redirects wait-for with its query intact.
        if key == 'wait' and 'wait-for' in records['sql']:
            continue
        first = next(iter(versions.values()))
        row = fresh_row(source_row(raw, first), revision)
        row['slug'] = 'wait' if key == 'wait-for' else key
        row['aliases'] = sorted(set(row.get('aliases', [])) | {key, row['slug']})
        prior = targets['sqlcmd'].get(row['slug'])
        if prior:
            row['editorial'] = deepcopy(prior.get('editorial', {}))
        row['versions'] = {}
        for version, record in sorted(versions.items(), key=lambda p: version_key(p[0])):
            snap = deepcopy(source_row(raw, record)['versions'][version])
            text = chinese_text(record, dataset_hash)
            attach_local_links(text, manuals, unresolved)
            text['display'] = sql_display(text['body_html'])
            snap['center_zh'] = text
            coordinate = local_doc(snap, version, manuals)
            if coordinate:
                snap['zh_doc'] = coordinate
            snap['purpose_zh'] = text['summary']
            snap['related'] = ['wait' if name == 'wait-for' else name for name in snap.get('related', [])]
            row['versions'][version] = snap
        row['present_in'] = sorted(row['versions'], key=version_key)
        row['first_version'], row['last_version'] = row['present_in'][0], row['present_in'][-1]
        row['purpose_zh'] = row['versions'][row['last_version']]['center_zh']['summary']
        row['related'] = ['wait' if name == 'wait-for' else name for name in row.get('related', [])]
        commands.append(row)
    majors = sorted({v for row in commands for v in row['versions']}, key=version_key)
    sql_versions = []
    for position, major in enumerate(majors):
        meta = display_version_metadata(source_versions.get(major, {}))
        previous = majors[position - 1] if position else ''
        sql_versions.append({'major': major, 'label': meta.get('label', major),
            'status': meta.get('status', 'historical'), 'support_status': meta.get('support_status', 'end-of-life'),
            'doc_slug': 'devel' if major == '20' else major, 'position': position,
            'command_count': sum(major in r['versions'] for r in commands),
            'added_count': sum(major in r['versions'] and previous not in r['versions'] for r in commands) if previous else 0,
            'removed_count': sum(previous in r['versions'] and major not in r['versions'] for r in commands) if previous else 0,
            'changed_count': sum(major in r['changed_in'] for r in commands)})
    snapshot = dict(native_header(revision), versions=sql_versions, commands=commands)
    outputs['sqlcmd'] = write_snapshot(output_dir / 'core-sqlcmd.json.gz', snapshot)
    receipts += changes_receipts('sqlcmd', commands, targets['sqlcmd'], 'slug')
    report['sql'] = {'commands': len(commands), 'versions': len(majors),
                     'entity_versions': sum(len(r['versions']) for r in commands),
                     'new_keys': sorted({r['slug'] for r in commands} - targets['sqlcmd'].keys())}

    functions, signature_count = [], 0
    group_labels = {r['group']: r['group_label'] for r in targets['func'].values()}
    group_labels['misc'] = '其他函数（历史）'
    for key, versions in sorted(records['func'].items()):
        row = fresh_row(source_row(raw, next(iter(versions.values()))), revision)
        row['group_label'] = group_labels.get(row['group'], row['group_label'])
        row['versions'] = {}
        for version, record in sorted(versions.items(), key=lambda p: version_key(p[0])):
            snap = deepcopy(source_row(raw, record)['versions'][version])
            snap['group_label'] = group_labels.get(snap['group'], snap['group_label'])
            text = chinese_text(record, dataset_hash)
            attach_local_links(text, manuals, unresolved)
            snap['center_zh'] = text
            snap['description_zh'] = text['payload'].get('description_zh') or text['summary']
            snap['description_zh_html'] = text['body_html']
            coordinate = local_doc(snap, version, manuals)
            if coordinate:
                snap['zh_doc'] = coordinate
            translations = {(s['text'], s.get('returns', '')): s for s in text['payload'].get('signatures', [])}
            for signature in snap['signatures']:
                translation = translations.get((signature['text'], signature.get('returns', '')))
                if not translation or not translation.get('description_zh'):
                    raise ValueError('Missing exact Chinese function signature: ' + repr((key, version, signature['text'])))
                for field in ('description_zh', 'description_zh_html', 'zh_from', 'translation_provenance'):
                    if field in translation:
                        signature[field] = deepcopy(translation[field])
                signature_count += 1
            row['versions'][version] = snap
        row['present_in'] = sorted(row['versions'], key=version_key)
        row['first_version'], row['last_version'] = row['present_in'][0], row['present_in'][-1]
        row['summary_zh'] = row['versions'][row['last_version']]['center_zh']['summary']
        functions.append(row)
    function_versions = []
    for major in sorted({v for row in functions for v in row['versions']}, key=version_key):
        meta = display_version_metadata(source_versions[major])
        meta['function_count'] = sum(major in r['versions'] for r in functions)
        meta['signature_count'] = sum(len(r['versions'][major]['signatures']) for r in functions if major in r['versions'])
        meta['zh_coverage'] = meta['function_count']
        function_versions.append(meta)
    outputs['func'] = write_snapshot(output_dir / 'core-func.json.gz',
        dict(native_header(revision), versions=function_versions, functions=functions))
    receipts += changes_receipts('func', functions, targets['func'], 'slug')
    report['func'] = {'functions': len(functions), 'entity_versions': sum(len(r['versions']) for r in functions),
                      'signatures_zh': signature_count, 'new_keys': sorted({r['slug'] for r in functions} - targets['func'].keys())}

    codes = []
    for key, versions in sorted(records['sqlstate'].items()):
        first = next(iter(versions.values()))
        old = targets['sqlstate'].get(key)
        row = fresh_row(old or source_row(raw, first), revision)
        selected = {record['text']['content_hash'] for record in versions.values()}
        if len(selected) != 1:
            raise ValueError('Version-specific SQLSTATE text requires an explicit selector: ' + key)
        text = chinese_text(first, dataset_hash)
        attach_local_links(text, manuals, unresolved)
        payload = deepcopy(text['payload'])
        # Django renders sections, while Go renders body_md. Preserve the exact
        # selected Go HTML, including entries (22020) with no legacy sections.
        payload['center_zh'] = text
        payload['manual_versions'] = sorted(versions, key=version_key)
        payload['sections'] = [{'anchor': '', 'heading': '', 'html': text['body_html']}]
        payload['name'] = payload.get('name') or text['title']
        payload['summary'] = text['summary']
        row.setdefault('texts', {})['zh'] = payload
        row['name_zh'], row['summary_zh'] = payload['name'], payload['summary']
        if old:
            for field in ('facts', 'evidence', 'present_in', 'preview_in', 'introduced', 'removed',
                          'known_present_by', 'runtime_verification', 'evidence_tier'):
                assert row[field] == old[field], (key, field)
        codes.append(row)
    classes = list(read_rows(target_root / 'sqlstate_class.jsonl.gz'))
    counts = Counter(r['class_code'] for r in codes)
    for row in classes:
        row['sqlstate_count'] = counts[row['code']]
    releases = list(read_rows(target_root / 'sqlstate_version.jsonl.gz'))
    outputs['sqlstate'] = write_snapshot(output_dir / 'core-sqlstate.json.gz',
        {'format': 2, 'generated_at': '2026-10-23T00:00:00Z', 'source_rev': revision,
         'classes': classes, 'releases': releases, 'codes': codes})
    receipts += changes_receipts('sqlstate', codes, targets['sqlstate'], 'sqlstate')
    report['sqlstate'] = {'codes': len(codes), 'new_keys': sorted({r['sqlstate'] for r in codes} - targets['sqlstate'].keys()),
                          'existing_facts_and_evidence_unchanged': True}
    report['receipts'] = str((output_dir / 'core-receipts.json').resolve())
    report['unresolved_manual_links'] = len(unresolved)
    (output_dir / 'core-unresolved-links.json').write_text(json.dumps(unresolved, ensure_ascii=False, indent=2) + '\n')
    (output_dir / 'core-receipts.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2) + '\n')
    (output_dir / 'core-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report
