"""Freeze Catalog/GUC/Wait native imports from the selected center Chinese rows.

No database reads or writes. Native comparison helpers are used after Django setup;
measurements and editorial/diagnostic evidence always start with the target rows.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

DOMAINS = {'catalog': ('catalog', 'relations', 'name'),
           'guc': ('guc', 'parameters', 'name'),
           'waitevent': ('waitevent', 'events', 'key')}
RUNTIME_GUC = ('setting', 'boot_val', 'unit', 'context', 'min_val', 'max_val', 'enumvals', 'human')
MEASURED_COLUMN = ('attnum', 'type_oid', 'type_modifier', 'array_dimensions', 'not_null')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def load(path):
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def major_key(value):
    return tuple(map(int, value.split('.')))


def first_sentence(value):
    return re.split(r'(?<=[。！？])\s*|(?<=\.)\s+', value or '', maxsplit=1)[0]


def text_record(row):
    """Keep original text bytes/hash and the precise definition selection separately."""
    text = deepcopy(row['text'])
    if text['version'] != row['version']:
        raise ValueError('Cross-version selected text: ' + row['key'])
    text.update({'collection': row['collection'], 'entry_key': row['key'],
                 'definition': deepcopy(row['definition'])})
    return text


def local_links(snapshot, version, pages, receipts, collection, key):
    """Resolve only a same-edition coordinate actually present in the frozen target."""
    from bs4 import BeautifulSoup
    from pgweb.wiki.center_text import local_url, localized_html
    slug = 'devel' if version == '20' else version
    base = '/docs/{}/'.format(slug)
    text = snapshot['center_zh']
    mapping = {}

    def resolve(original, relation_page=False):
        value = local_url(original)
        parsed = urlsplit(urljoin(base, value))
        if parsed.netloc:
            return original
        match = re.fullmatch(r'/docs/([^/]+)/([^/]+)', parsed.path)
        if not match:
            return value
        edition, filename = match.groups()
        edition = 'devel' if edition == '20' else edition
        known = pages.get(edition, {})
        if filename not in known:
            candidates = [f for f in known if f.casefold() == filename.casefold()]
            if not candidates and filename.endswith('.htm'):
                candidates = [f for f in known if f.casefold() == (filename + 'l').casefold()]
            if len(candidates) != 1:
                receipts.append({'collection': collection, 'key': key, 'version': version,
                                 'rule': 'unresolved-manual-link', 'href': original})
                return value
            filename = candidates[0]
        anchor = parsed.fragment
        if anchor and anchor not in known[filename]:
            matches = [a for a in known[filename] if a.casefold() == anchor.casefold()]
            if len(matches) == 1:
                anchor = matches[0]
            elif relation_page and filename.upper().removesuffix('.HTML') in known[filename]:
                anchor = filename.upper().removesuffix('.HTML')
                receipts.append({'collection': collection, 'key': key, 'version': version,
                                 'rule': 'same-relation-page-anchor', 'href': original,
                                 'anchor': anchor})
            else:
                # Keep the original source link; unresolved anchors are review evidence.
                receipts.append({'collection': collection, 'key': key, 'version': version,
                                 'rule': 'unresolved-manual-anchor', 'href': original})
        return urlunsplit(('', '', '/docs/{}/{}'.format(edition, filename), parsed.query, anchor))

    for link in BeautifulSoup(text.get('body_html', ''), 'html.parser').select('a[href], img[src]'):
        field = 'href' if link.name == 'a' else 'src'
        original = link[field]
        resolved = resolve(original)
        if resolved != original:
            mapping[original] = resolved
    if mapping:
        text['link_map'] = mapping
    doc = snapshot.get('doc') or {}
    if doc.get('file'):
        href = '/docs/{}/{}{}'.format(slug, doc['file'], '#' + doc['anchor'] if doc.get('anchor') else '')
        parsed = urlsplit(resolve(href, relation_page=collection == 'catalog'
                                  and doc['file'] in ('catalog-' + key.replace('_', '-') + '.html',
                                                      'view-' + key.replace('_', '-') + '.html')))
        doc['file'] = parsed.path.rsplit('/', 1)[-1]
        doc['anchor'] = parsed.fragment
        doc['slug'] = slug
    if collection == 'guc':
        snapshot['doc_html'] = localized_html(text.get('body_html', ''), base, link_map=mapping)


def merge_catalog(old, row, receipts):
    from pgweb.wiki.catalog_importer import catalog_type_key
    facts, text = row['definition']['facts'], row['text']
    out = deepcopy(old if old is not None else facts)
    key, version = row['definition']['source_key'], row['version']
    translations = {c['name']: c for c in text.get('payload', {}).get('columns', [])}
    source = {c['name']: c for c in facts.get('columns', [])}
    target_columns = list(out.get('columns') or [])
    target_names = {c['name'] for c in target_columns}
    mapped = set()
    columns = []
    for original in target_columns:
        col = deepcopy(original)
        name = col['name']
        equivalent = name
        if key == 'pg_statistic' and re.fullmatch(r'(stakind|staop|stacoll|stanumbers|stavalues)[1-5]', name):
            wildcard = re.sub(r'[1-5]$', 'N', name)
            if wildcard in source:
                equivalent = wildcard
        if key == 'pg_policies' and name == 'permissive' and 'polpermissive' in source:
            equivalent = 'polpermissive'
        selected = source.get(equivalent)
        translated = translations.get(equivalent) or translations.get(name)
        if selected:
            mapped.add(equivalent)
            if col.get('type') != selected.get('type'):
                receipts.append({'collection': 'catalog', 'key': key, 'version': version,
                                 'rule': ('type-spelling-equivalence' if catalog_type_key(col.get('type')) == catalog_type_key(selected.get('type'))
                                          else 'preserve-measured-type-over-manual'),
                                 'native': name, 'native_type': col.get('type'),
                                 'selected_type': selected.get('type')})
            # Types/order/physical attributes of a measured relation stay measured.
            for field in ('description', 'references'):
                if field in selected:
                    col[field] = deepcopy(selected[field])
            if old is None or (not old.get('runtime_verified') and not old.get('measured_attributes')):
                col['type'] = selected.get('type', col.get('type', ''))
            if translated:
                col['description_zh'] = translated.get('description_zh', '')
                col['zh_from'] = translated.get('zh_from') or 'center-selected'
            elif selected.get('description_zh'):
                col['description_zh'] = selected['description_zh']
                col['zh_from'] = selected.get('zh_from') or 'center-selected'
            if equivalent != name:
                receipts.append({'collection': 'catalog', 'key': key, 'version': version,
                                 'rule': 'documented-name-equivalence', 'native': name,
                                 'selected': equivalent})
        else:
            # Explicit OIDs, measured manual omissions, and derived view columns remain.
            receipts.append({'collection': 'catalog', 'key': key, 'version': version,
                             'rule': 'preserve-native-column-not-in-manual', 'native': name})
        columns.append(col)
    for name, selected in source.items():
        if name in mapped or name in target_names:
            continue
        col = deepcopy(selected)
        translated = translations.get(name)
        if translated:
            col['description_zh'] = translated.get('description_zh', '')
            col['zh_from'] = translated.get('zh_from') or 'center-selected'
        # The source is documentation; absence of measurement is not a false value.
        if not facts.get('measured_attributes'):
            for field in MEASURED_COLUMN:
                col.pop(field, None)
        source_order = list(source)
        before = next((n for n in source_order[source_order.index(name) + 1:]
                       if any(c['name'] == n for c in columns)), None)
        index = next((i for i, c in enumerate(columns) if c['name'] == before), len(columns))
        columns.insert(index, col)
        receipts.append({'collection': 'catalog', 'key': key, 'version': version,
                         'rule': 'add-documented-column', 'native': name})
    out['columns'] = columns
    common_native = [c['name'] for c in columns if c['name'] in source]
    common_source = [n for n in source if n in common_native]
    if common_native != common_source:
        receipts.append({'collection': 'catalog', 'key': key, 'version': version,
                         'rule': 'preserve-measured-column-order',
                         'native': common_native, 'selected': common_source})
    out['description'] = facts.get('description', out.get('description', ''))
    out['description_zh'] = text.get('summary') or text.get('payload', {}).get('description_zh', '')
    out['zh_from'] = text.get('payload', {}).get('zh_from') or 'center-selected'
    out['center_zh'] = text_record(row)
    out['center_zh']['parity_rules'] = [r for r in receipts if r.get('key') == key and r.get('version') == version]
    if old is None:
        out.setdefault('relation_oid', None)
        out.setdefault('relkind', '')
        out.setdefault('shared', False)
        out.setdefault('system_columns', [])
        out['runtime_verified'] = bool(facts.get('measured_attributes'))
        out['schema_source'] = 'runtime+documentation' if out['runtime_verified'] else 'documentation'
        out.setdefault('release', facts.get('metadata_release', ''))
    out.setdefault('doc', deepcopy(facts.get('doc') or {}))
    return out


def merge_guc(old, row, receipts):
    from pgweb.wiki.guc_common import human_value
    from pgweb.wiki.center_text import localized_html
    facts, text = row['definition']['facts'], row['text']
    out = deepcopy(old if old is not None else facts)
    metadata_major = re.match(r'^\d+(?:\.\d+)?', str(facts.get('metadata_version') or ''))
    documented = not metadata_major or metadata_major.group() != row['version']
    # Existing native rows before devel have their own measured evidence. A
    # manual-only selected center row cannot invalidate that independent evidence.
    unknown = (row['version'] == '20' or (old is None and documented)
               or bool(old and old.get('facts_source') == 'documentation'))
    # pgweb-only inherited 20 rows carry source 19 evidence, never runtime 20 facts.
    if old is None and facts.get('carried_from') and str(facts['carried_from']) != row['version']:
        unknown = True
    if unknown:
        previous = {f: deepcopy(out.get(f)) for f in RUNTIME_GUC if f in out}
        out['center_previous_runtime'] = {'version': out.get('carried_from') or row['version'],
                                          'fields': previous,
                                          'carried_from': out.get('carried_from', ''),
                                          'carry_reason': out.get('carry_reason', ''),
                                          'reason': 'No same-version measurement in selected definition'}
        out.update({'setting': None, 'boot_val': None, 'unit': '', 'context': '',
                    'min_val': None, 'max_val': None, 'enumvals': [], 'human': '',
                    'facts_source': 'documentation', 'carried_from': '', 'carry_reason': ''})
        receipts.append({'collection': 'guc', 'key': row['key'], 'version': row['version'],
                         'rule': 'documentation-only-runtime-unknown'})
    elif old is None:
        out['human'] = human_value(out.get('boot_val'), out.get('unit'))
        out['facts_source'] = 'runtime'
    for field in ('description', 'vartype', 'translation_provenance'):
        if field in facts:
            out[field] = deepcopy(facts[field])
    if not out.get('short_desc'):
        out['short_desc'] = facts.get('short_desc') or first_sentence(facts.get('description', ''))
    out.setdefault('category', facts.get('category', ''))
    out.setdefault('category_zh', '')
    out['center_zh'] = text_record(row)
    out['doc_html'] = localized_html(text.get('body_html', ''), '/docs/{}/'.format('devel' if row['version'] == '20' else row['version']))
    out['doc_same_as'] = ''
    out['description_zh'] = text.get('summary', '')
    out.setdefault('doc', deepcopy(facts.get('doc') or {}))
    return out


def merge_wait(old, row, receipts):
    out = deepcopy(old if old is not None else row['definition']['facts'])
    facts, text = row['definition']['facts'], row['text']
    for field in ('type', 'name', 'description'):
        if field in facts:
            out[field] = deepcopy(facts[field])
    out['description_zh'] = text.get('summary', '')
    out['zh_from'] = text.get('payload', {}).get('zh_from') or out.get('zh_from') or 'center-selected'
    out['center_zh'] = text_record(row)
    out.setdefault('source', deepcopy(facts.get('source') or {}))
    out.setdefault('doc', deepcopy(facts.get('doc') or {}))
    return out


def _version_rows(target, raw, present, collection):
    by_major = {v['major']: deepcopy(v) for v in target}
    source = {v['major']: v for v in raw}
    for major in present:
        if major not in by_major:
            by_major[major] = deepcopy(source[major])
    # Wait has honest pre-mechanism empty versions which remain selectable on index.
    for index, major in enumerate(sorted(by_major, key=major_key)):
        v = by_major[major]
        v['position'] = index
        if major not in {x['major'] for x in target}:
            v.update({'schema_source': 'documentation', 'runtime_verified': False})
        if major == '19':
            # The selected prose is the accepted 19rc1 manual. Runtime release,
            # source_tag/server_version/source_key retain their actual beta4 pin.
            v['label'] = '19 rc1'
            if collection == 'catalog':
                v['documentation_version'] = '19rc1'
    return list(sorted(by_major.values(), key=lambda v: v['position']))


def _catalog_finish(items, versions):
    from pgweb.wiki import catalog_importer as native
    from pgweb.wiki.models import CATALOG_KIND_ORDER
    order = [v['major'] for v in versions]
    for item in items:
        present = sorted(item['versions'], key=major_key)
        item.update(present_in=present, first_version=present[0], last_version=present[-1])
        latest = item['versions'][present[-1]]
        item.update(column_count=len(latest.get('columns') or []), relation_oid=latest.get('relation_oid'),
                    relkind=latest.get('relkind') or '', shared=bool(latest.get('shared')))
        item['changes'] = []
        for left, right in zip(order, order[1:]):
            a, b = item['versions'].get(left, {}), item['versions'].get(right, {})
            if not a and not b:
                continue
            wording = bool(a.get('runtime_verified') and b.get('runtime_verified')) and right != '20'
            change = native.compare_snapshots(a, b, left, right, wording=wording)
            if change:
                item['changes'].append(change)
        item['changed_in'] = [c['to'] for c in item['changes'] if c['status'] == 'changed' and c['structural']]
        if not item.get('summary_zh'):
            item['summary_zh'] = first_sentence(latest.get('description_zh', ''))
    items.sort(key=lambda x: (CATALOG_KIND_ORDER.get(x['kind'], 9), x['name']))
    offsets = Counter()
    for item in items:
        kind = item['kind']; item['position'] = CATALOG_KIND_ORDER.get(kind, 9) * 1000 + offsets[kind]; offsets[kind] += 1
    for v in versions:
        major = v['major']; rows = [i for i in items if major in i['versions']]
        v.update(relation_count=len(rows), column_count=sum(len(i['versions'][major].get('columns') or []) for i in rows), kinds=dict(Counter(i['kind'] for i in rows)))
        changes = [(i['name'], c) for i in items for c in i['changes'] if c['to'] == major]
        if changes:
            v['transition'] = {'from': changes[0][1]['from'], 'to': major,
                               'added_relations': [n for n, c in changes if c['status'] == 'added'],
                               'removed_relations': [n for n, c in changes if c['status'] == 'removed'],
                               'changed_relations': [n for n, c in changes if c['status'] == 'changed'],
                               'structurally_changed_relations': [n for n, c in changes if c['status'] == 'changed' and c['structural']],
                               'added_columns': sum(len(c['added_columns']) for _, c in changes if c['status'] == 'changed'),
                               'removed_columns': sum(len(c['removed_columns']) for _, c in changes if c['status'] == 'changed'),
                               'type_changes': sum(len(c['type_changes']) for _, c in changes if c['status'] == 'changed')}
        else:
            v['transition'] = {}


def _guc_finish(items, versions):
    from pgweb.wiki import guc_importer as native
    order = [v['major'] for v in versions]
    for item in items:
        # Category identity is presentation metadata, not the manual subsection heading.
        category = item.get('category', '')
        for snap in item['versions'].values():
            if category:
                snap['category'] = category
        item['changes'] = native.build_changes(item['versions'], order)
        native.refresh_facts(item, order)
        latest = item['versions'][item['last_version']]
        item['short_desc_zh'] = first_sentence(latest.get('description_zh', '')) or item.get('short_desc_zh', '')
        item['baseline'] = item['first_version'] == order[0]
        spans = []
        for major in order:
            snap = item['versions'].get(major)
            if not snap or snap.get('facts_source') == 'documentation':
                continue
            entry = native.default_entry(snap)
            if spans and {k: spans[-1].get(k) for k in entry} == entry and order.index(major) == order.index(spans[-1]['to']) + 1:
                spans[-1]['to'] = major
            else:
                spans.append(dict(entry, **{'from': major, 'to': major}))
        item['default_history'] = spans
    native.assign_positions(items)
    transitions = native.build_transitions(items, order)
    for v in versions:
        major = v['major']; t = transitions.get(major, {})
        v['parameter_count'] = sum(major in i['versions'] for i in items)
        v['transition'] = t
        for name in ('added', 'removed', 'default_changed', 'changed', 'reworded'):
            v[name + '_count'] = len(t.get(name) or [])
        if major == '20':
            v.update(schema_source='documentation', source_key='', server_version='')


def build(source_root, target_root, output_dir):
    """Produce deterministic native snapshots and exact parity/preservation receipts."""
    from django.apps import apps
    if not apps.ready:
        import os
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
        django.setup()
    from pgweb.wiki import catalog_importer, guc_importer, waitevent_importer
    source_root, target_root, output_dir = map(Path, (source_root, target_root, output_dir))
    output_dir.mkdir(parents=True, exist_ok=False)
    selected = defaultdict(list)
    with gzip.open(source_root / 'canonical.jsonl.gz', 'rt', encoding='utf-8') as handle:
        for line in handle:
            row = json.loads(line)
            if row['collection'] in DOMAINS:
                selected[row['collection']].append(row)
    manifest = json.loads((source_root / 'manifest.json').read_text())
    source_revision = 'center-selected:' + digest(manifest)
    receipts, report = [], {'source_revision': source_revision, 'domains': {}}
    pages = defaultdict(dict)
    for page in load(target_root / 'manual-pages.jsonl.gz'):
        pages[page['version']][page['file']] = set(page['anchors'])
    for collection, (table, list_key, primary) in DOMAINS.items():
        old_rows = load(target_root / (table + '.jsonl.gz'))
        target = {r[primary]: r for r in old_rows}
        raw = {}
        for database in ('pgweb', 'center'):
            raw[database] = {r[primary]: r for r in load(source_root / 'raw' / database / (table + '.jsonl.gz'))}
        grouped = defaultdict(list)
        for row in selected[collection]:
            grouped[row['definition']['source_key']].append(row)
        if set(target) - set(grouped):
            raise ValueError('Unexpected missing native identities: ' + repr(set(target) - set(grouped)))
        items = []
        merge = {'catalog': merge_catalog, 'guc': merge_guc, 'waitevent': merge_wait}[collection]
        expected_pairs, actual_pairs = set(), set()
        for key, source_rows in sorted(grouped.items()):
            old = target.get(key)
            prototype = raw[source_rows[0]['definition']['source_database']][key]
            item = deepcopy(old if old is not None else prototype)
            item.pop('content_hash', None)
            item['versions'] = {}
            for row in sorted(source_rows, key=lambda r: major_key(r['version'])):
                major = row['version']
                previous = (old or {}).get('versions', {}).get(major)
                item['versions'][major] = merge(previous, row, receipts)
                local_links(item['versions'][major], major, pages, receipts, collection, key)
                expected_pairs.add((key, major))
                actual_pairs.add((item[primary], major))
                if previous is not None and collection == 'catalog' and previous.get('runtime_verified'):
                    cols = {c['name']: c for c in item['versions'][major]['columns']}
                    for c in previous.get('columns', []):
                        for field in (*MEASURED_COLUMN, 'type'):
                            if c.get(field) != cols[c['name']].get(field):
                                raise ValueError('Measured catalog attribute changed: ' + repr((key, major, c['name'], field)))
                if previous is not None and collection == 'guc' and item['versions'][major].get('facts_source') != 'documentation':
                    for field in RUNTIME_GUC:
                        if previous.get(field) != item['versions'][major].get(field):
                            raise ValueError('Measured GUC attribute changed: ' + repr((key, major, field)))
            if expected_pairs != actual_pairs:
                raise ValueError('Identity changed')
            present = sorted(item['versions'], key=major_key)
            item.update(present_in=present, first_version=present[0], last_version=present[-1], source_rev=source_revision)
            if collection == 'waitevent':
                if old is not None and item['dossier'] != old['dossier']:
                    raise ValueError('Wait dossier modified')
                item['summary_zh'] = item['versions'][present[-1]]['description_zh']
            items.append(item)
        present = {v for i in items for v in i['versions']}
        versions = _version_rows(load(target_root / (table + '_version.jsonl.gz')),
                                 load(source_root / 'raw' / 'center' / (table + '_version.jsonl.gz')),
                                 present, collection)
        if collection == 'catalog':
            _catalog_finish(items, versions)
        elif collection == 'guc':
            _guc_finish(items, versions)
        native = {'catalog': catalog_importer, 'guc': guc_importer, 'waitevent': waitevent_importer}[collection]
        snapshot = {'format': 1, 'source_rev': source_revision, 'default_major': '18',
                    'versions': versions, list_key: items, 'stats': {'selected_version_rows': len(expected_pairs)}}
        native.validate(snapshot)
        path = output_dir / (collection + '.json.gz')
        payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        with path.open('wb') as handle:
            with gzip.GzipFile(filename='', mode='wb', fileobj=handle, mtime=0) as archive:
                archive.write(payload)
        old_pairs = {(i[primary], v) for i in old_rows for v in i['versions']}
        report['domains'][collection] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'entities': len(items), 'version_rows': len(expected_pairs), 'versions': len(versions),
            'added_entities': sorted(set(grouped) - set(target)),
            'added_version_rows': sorted(expected_pairs - old_pairs), 'removed_version_rows': sorted(old_pairs - expected_pairs),
            'native_validation': True, 'measured_preservation': True,
            'selected_text_parity': all(s['center_zh']['body_html'] == next(r['text']['body_html'] for r in grouped[i[primary]] if r['version'] == v) for i in items for v, s in i['versions'].items())}
    (output_dir / 'parity-rules.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2) + '\n')
    report['rule_counts'] = dict(Counter(r['rule'] for r in receipts))
    (output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report
