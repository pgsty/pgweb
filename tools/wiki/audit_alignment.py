#!/usr/bin/env python3
"""Read-only, exhaustive reference/search/SQLSTATE audit against the current local manuals.

Domain-specific semantic comparisons accompany this report. Never publishes data.
Run from the checkout with .venv/bin/python tools/wiki/audit_alignment.py --output DIR.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')


def major(value):
    value = str(value)
    if value in ('0', '0.0', 'devel'):
        return '20'
    return value.split('.')[0] if int(value.split('.')[0]) >= 10 else value


def slug(value):
    return 'devel' if value == '20' else value


class Anchors(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.anchors = set()
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if value and (name == 'id' or (tag == 'a' and name == 'name')):
                self.anchors.add(value)


def plain(value):
    return ' '.join(unescape(re.sub(r'<[^>]*>', '', value)).split())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    import django
    django.setup()
    from django.db import connection, transaction
    from pgweb.docs.models import DocPage
    from pgweb.search import indexer
    from pgweb.search.models import SearchEntry
    from pgweb.wiki import errcode
    from pgweb.wiki.documents import reference_gaps
    from pgweb.wiki.models import (CatalogRelation, GucParameter, WaitEvent,
                                   PgFunction, SqlCommand, ErrorCode)
    from pgweb.wiki.snapshot import model_hash

    def save(name, value):
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                                   default=str) + '\n')

    domains = {'catalog': CatalogRelation, 'guc': GucParameter, 'wait': WaitEvent,
               'func': PgFunction, 'sqlcmd': SqlCommand, 'errcode': ErrorCode}
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute('SELECT current_database(), current_user')
            target = cursor.fetchone()
            if target[0] != 'pgweb':
                raise ValueError('This Chinese-manual audit requires database pgweb')
            cursor.execute('SELECT id,version,file,md5(title),md5(content) FROM docs ORDER BY id')
            manifest = cursor.fetchall()
            save('docs-manifest.json', manifest)
            snapshot = {}
            for table in ('sqlstate', 'sqlstate_class', 'sqlstate_version', 'catalog',
                          'catalog_version', 'guc', 'guc_version', 'waitevent',
                          'waitevent_version', 'sqlcmd', 'func', 'func_version'):
                cursor.execute('SELECT to_jsonb(t) FROM ' + table + ' t ORDER BY to_jsonb(t)::text')
                snapshot[table] = [json.loads(r[0]) if isinstance(r[0], str) else r[0]
                                   for r in cursor.fetchall()]
            (args.output / 'tables.json.gz').write_bytes(gzip.compress(
                json.dumps(snapshot, ensure_ascii=False, default=str).encode(), mtime=0))

        entities = {d: list(m.objects.all()) for d, m in domains.items()}
        refs, internal, fingerprints = [], [], []
        for domain, rows in entities.items():
            for item in rows:
                if model_hash(item) != item.content_hash:
                    fingerprints.append({'domain': domain, 'entity': item.pk})
                if domain == 'errcode':
                    continue
                keys = set(item.versions)
                ordered = sorted(keys, key=lambda v: tuple(map(int, v.split('.'))))
                if (keys != set(item.present_in) or item.first_version != ordered[0]
                        or item.last_version != ordered[-1]):
                    internal.append({'domain': domain, 'entity': item.pk,
                                     'versions': ordered, 'present_in': item.present_in,
                                     'first_version': item.first_version,
                                     'last_version': item.last_version})
                refs_by_version = item.docs if domain == 'guc' else item.versions
                for version, value in refs_by_version.items():
                    if domain == 'guc':
                        parts = urlsplit(value.get('url', ''))
                        path = parts.path.split('/')
                        coordinate = {'file': path[-1], 'anchor': value.get('anchor', '') or parts.fragment,
                                      'slug': path[-2] if len(path) > 1 else ''}
                    else:
                        coordinate = value if domain == 'sqlcmd' else value.get('doc', {})
                    refs.append({'domain': domain, 'entity': item.pk, 'version': version,
                                 'status': coordinate.get('status', value.get('status', '')),
                                 **{k: coordinate.get(k, '') for k in ('file', 'anchor', 'slug')}})

        # SQLSTATE prose is authored evidence, not a copy of the appendix. Check its
        # actual manual links and keep pinned source URLs/evidence immutable.
        for item in entities['errcode']:
            for lang, text in item.texts.items():
                for url in sorted(set(re.findall(r'(?:https://www\.postgresql\.org)?/docs/(?:\d+(?:\.\d+)?|devel)/[^\s)<>"\]]+', text.get('body_md', '')))):
                    parts = urlsplit(url)
                    path = parts.path.split('/')
                    refs.append({'domain': 'errcode', 'entity': item.pk,
                                 'version': major(path[-2]), 'slug': path[-2],
                                 'file': path[-1], 'anchor': parts.fragment,
                                 'language': lang, 'url': url})

        wanted = {r['file'] for r in refs if r['file']} | {'errcodes-appendix.html'}
        pages = {(major(v), f): c for v, f, c in DocPage.objects.filter(file__in=wanted)
                 .values_list('version', 'file', 'content')}
        anchors = {}
        for ref in refs:
            pair = (ref['version'], ref['file'])
            errors = []
            if not ref['file'] and ref.get('status') == 'not_documented_in_runtime_config':
                ref['errors'] = []
                ref['unavailable'] = 'source_url_missing'
                continue
            if pair not in pages:
                errors.append('file_missing')
            elif ref['anchor']:
                if pair not in anchors:
                    anchors[pair] = Anchors(pages[pair]).anchors
                if unquote(ref['anchor']).lstrip('#') not in anchors[pair]:
                    errors.append('anchor_missing')
            if ref['slug'] != slug(ref['version']):
                errors.append('slug_mismatch')
            ref['errors'] = errors
        save('references.json', refs)
        save('reference-failures.json', [r for r in refs if r['errors']])
        save('internal-coverage-failures.json', internal)
        save('fingerprint-failures.json', fingerprints)

        search_failures, search_summary = [], {}
        builders = {'catalog': indexer.catalog_entry, 'guc': indexer.guc_entry,
                    'wait': indexer.waitevent_entry, 'func': indexer.func_entry,
                    'sqlcmd': indexer.sqlcmd_entry}
        for domain, rows in entities.items():
            expected = {}
            for item in rows:
                if domain == 'errcode':
                    entry = indexer.errcode_entry(item, item.texts.get('zh') or item.texts.get('en'),
                                                 errcode.card(item))
                else:
                    entry = builders[domain](item)
                expected[entry['key']] = {k: v for k, v in entry.items() if not k.startswith('_')}
            actual = list(SearchEntry.objects.filter(source=domain).values())
            counts = Counter(row['key'] for row in actual)
            for row in actual:
                want = expected.get(row['key'])
                fields = ['unexpected_key'] if want is None else [k for k, v in want.items() if row[k] != v]
                fields += [k for k in ('document_id', 'version') if row[k] is not None]
                if counts[row['key']] != 1:
                    fields.append('duplicate_key')
                if fields:
                    search_failures.append({'domain': domain, 'key': row['key'], 'url': row['url'],
                                            'fields': fields})
            for key in expected.keys() - counts.keys():
                search_failures.append({'domain': domain, 'key': key, 'fields': ['missing']})
            search_summary[domain] = {'entities': len(rows), 'entries': len(actual),
                                      'failures': sum(r['domain'] == domain for r in search_failures)}
        save('search-failures.json', search_failures)

        sql_differences, class_drift, condition_drift, condition_labels = [], [], [], []
        code_by_id = {c.pk: c for c in entities['errcode']}
        for version in ['9.' + str(v) for v in range(7)] + list(map(str, range(10, 21))):
            content = pages.get((version, 'errcodes-appendix.html'), '')
            names = defaultdict(set)
            for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', content, re.S | re.I):
                cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)
                if len(cells) >= 2 and re.fullmatch('[0-9A-Z]{5}', plain(cells[0])):
                    names[plain(cells[0])].add(plain(cells[1]))
                elif len(cells) == 1:
                    match = re.match(r'(?:类|Class|分类)\s*([0-9A-Z]{2})\s*[—–-]\s*(.*)', plain(cells[0]))
                    if match and version == '20':
                        current = next((c for c in snapshot['sqlstate_class'] if c['code'] == match[1]), None)
                        if current and current['name_zh'] != match[2]:
                            class_drift.append({'class': match[1], 'before': current['name_zh'], 'after': match[2]})
            observed = set(names)
            stored = {c.pk for c in entities['errcode'] if version in c.present_in}
            for code in sorted(observed - stored):
                sql_differences.append({'version': version, 'code': code, 'kind': 'manual_only',
                                        'reason': 'unsampled_devel' if version == '20' else 'requires_source_review'})
            for code in sorted(stored - observed):
                sql_differences.append({'version': version, 'code': code, 'kind': 'source_only',
                                        'reason': 'tag_sample_not_manual_tree'})
            for code in sorted(observed & set(code_by_id)):
                if not names[code].issubset(set(code_by_id[code].condition_names) | {code_by_id[code].condition_name}):
                    row = {'version': version, 'code': code, 'manual': sorted(names[code]),
                           'source': code_by_id[code].condition_names}
                    # 9.0 translates the condition column; it is not an identifier conflict.
                    (condition_labels if version == '9.0' else condition_drift).append(row)
        source_changes = []
        source_root = Path('~/pg.center/err').expanduser()
        for code in entities['errcode']:
            source = json.loads((source_root / 'data/errcodes' / (code.pk + '.json')).read_text())
            for key in ('condition_name', 'condition_names', 'introduced', 'removed',
                        'known_present_by', 'present_in_snapshots', 'preview_in_snapshots'):
                if code.facts.get(key) != source.get(key):
                    source_changes.append({'code': code.pk, 'field': key, 'stored': code.facts.get(key),
                                           'source': source.get(key)})
        gaps = [g for c in entities['errcode'] for g in reference_gaps({'sqlstate': c.pk, 'evidence': c.evidence})]
        save('sqlstate.json', {'coverage_differences': sql_differences, 'condition_differences': condition_drift,
                               'condition_presentation_differences': condition_labels,
                               'class_text_drift': class_drift, 'source_fact_differences': source_changes,
                               'evidence_gaps': gaps,
                               'text_scope': '263 authored bilingual documents; appendix has condition identifiers, not equivalent prose. Keep evidence narratives and site summaries.'})
        summary = {'database': target, 'tables': {k: len(v) for k, v in snapshot.items()},
                   'manuals': len(manifest), 'manual_hash': hashlib.sha256(json.dumps(manifest, default=str).encode()).hexdigest(),
                   'references': {d: {'checked': sum(r['domain'] == d for r in refs),
                                      'source_urls_unavailable': sum(r['domain'] == d and bool(r.get('unavailable')) for r in refs),
                                      'failed': sum(r['domain'] == d and bool(r['errors']) for r in refs)} for d in domains},
                   'reference_errors': dict(Counter(e for r in refs for e in r['errors'])),
                   'internal_coverage_failures': len(internal), 'fingerprint_failures': len(fingerprints),
                   'search': search_summary,
                   'sqlstate': {'coverage_differences': len(sql_differences),
                                'condition_differences': len(condition_drift), 'class_text_drift': len(class_drift),
                                'condition_presentation_differences': len(condition_labels),
                                'source_fact_differences': len(source_changes), 'evidence_gaps': len(gaps)}}
        save('summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
