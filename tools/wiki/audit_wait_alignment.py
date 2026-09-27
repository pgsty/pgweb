#!/usr/bin/env python3
"""Read-only exhaustive wait-event audit against the current Chinese manuals."""
import argparse
from collections import Counter
from decimal import Decimal
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    import django
    django.setup()
    from bs4 import BeautifulSoup
    from django.db import connection, transaction
    from pgweb.docs.models import DocPage
    from pgweb.wiki import waitevent_importer as w
    from pgweb.wiki import waitevent as reader
    from pgweb.wiki.models import WaitEvent, WaitEventVersion

    def save(name, data):
        (args.output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                                  default=str) + '\n')

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute('SELECT current_database(), current_user')
            target = cursor.fetchone()
            if target[0] != 'pgweb':
                raise ValueError('Requires Chinese database pgweb')
        atlas = w.read_atlas(os.path.expanduser(w.DEFAULT_ROOT))
        stored = {e.key: e for e in WaitEvent.objects.all()}
        existing_versions = {v.major: v for v in WaitEventVersion.objects.all()}
        reader_pages = reader.doc_pages()
        references, coverage, wording, samples, internal = [], [], [], [], []
        manual_manifest, per_version = [], []
        doc_inventories = {}
        for major in w.VERSION_ORDER:
            tree = Decimal('0') if major == '20' else Decimal(major)
            page = DocPage.objects.filter(version=tree, file=w.DOC_FILE).first()
            if not page:
                raise ValueError('Missing manual ' + major)
            soup = BeautifulSoup(page.content, 'html.parser')
            anchors = {str(n.get('id') or n.get('name'))
                       for n in soup.find_all(lambda t: t.get('id') or (t.name == 'a' and t.get('name')))}
            manual_manifest.append({'major': major, 'id': page.id, 'file': page.file,
                                    'sha256': hashlib.sha256(page.content.encode()).hexdigest()})
            manual = w.keyed([w.make_row(label, name, '', desc, 'manual', major)
                              for label, name, desc in w.parse_event_tables(soup)],
                             atlas['canonical_map'], major, []) if major in w.LIVE_ORDER else {}
            doc_inventories[major] = manual
            db = {k: e.versions[major] for k, e in stored.items() if major in e.versions}
            for key, row in db.items():
                ref = row.get('doc', {})
                issues = []
                if ref.get('file') != page.file:
                    issues.append('file_missing_or_wrong')
                if ref.get('slug') != w.DOC_SLUG[major]:
                    issues.append('slug_mismatch')
                if ref.get('anchor') and ref['anchor'] not in anchors:
                    issues.append('anchor_missing')
                references.append({'key': key, 'major': major, 'doc': ref, 'issues': issues,
                                   'reader_link': reader.doc_url(row, pages=reader_pages)})
            for key in sorted(set(manual) - set(db)):
                source = w.atlas_inventory(atlas, major, []) if major in w.ATLAS_MAJORS else {}
                coverage.append({'kind': 'manual_only', 'major': major, 'key': key,
                                 'manual': manual[key], 'supported_by_atlas': key in source})
            for key in sorted(set(db) - set(manual)):
                source = w.atlas_inventory(atlas, major, []) if major in w.ATLAS_MAJORS else {}
                coverage.append({'kind': 'graph_only', 'major': major, 'key': key,
                                 'graph': db[key], 'supported_by_atlas': key in source})
            matching = sorted(set(manual) & set(db))
            selected = matching[::max(1, len(matching) // 12)][:12]
            for key in matching:
                expected = manual[key]['description_zh']
                actual = db[key].get('description_zh', '')
                row = {'key': key, 'major': major, 'field': 'versions.description_zh',
                       'before': actual, 'after': expected, 'zh_from': db[key].get('zh_from', '')}
                if key in selected:
                    samples.append(dict(row, differs=actual != expected))
                if actual != expected:
                    wording.append(row)
            per_version.append({'major': major, 'manual': len(manual), 'graph': len(db),
                                'mechanism': major in w.LIVE_ORDER,
                                'manual_only': len(set(manual)-set(db)),
                                'graph_only': len(set(db)-set(manual)),
                                'description_drift': sum(x['major']==major for x in wording)})
        summary_sample = []
        grouped = {}
        for event in stored.values():
            grouped.setdefault(event.type, []).append(event.key)
        sampled_keys = {key for keys in grouped.values()
                        for key in sorted(keys)[::max(1, len(keys) // 4)][:4]}
        for key, event in stored.items():
            present = [v for v in w.VERSION_ORDER if v in event.versions]
            if event.present_in != present or event.first_version != present[0] or event.last_version != present[-1]:
                internal.append({'key': key, 'present': present, 'stored': event.present_in,
                                 'first': event.first_version, 'last': event.last_version})
            # The latest present manual describes the headline entity; keep authored dossier prose separate.
            candidates = [(v, doc_inventories[v][key]['description_zh']) for v in reversed(present)
                          if key in doc_inventories[v] and doc_inventories[v][key]['description_zh']]
            if candidates and event.summary_zh != candidates[0][1]:
                wording.append({'key': key, 'major': candidates[0][0], 'field': 'summary_zh',
                                'before': event.summary_zh, 'after': candidates[0][1]})
            if key in sampled_keys and candidates:
                summary_sample.append({'key': key, 'major': candidates[0][0], 'field': 'summary_zh',
                                       'before': event.summary_zh, 'after': candidates[0][1],
                                       'differs': event.summary_zh != candidates[0][1]})
        fresh = w.export_snapshot(fetch=False)
        w.validate(fresh)
        fresh_map = {e['key']: e for e in fresh['events']}
        source_diffs = []
        facts = ('type', 'type_slug', 'name', 'slug', 'aliases', 'type_variants',
                 'first_version', 'last_version', 'present_in')
        for key in sorted(set(fresh_map) | set(stored)):
            if key not in fresh_map or key not in stored:
                source_diffs.append({'key': key, 'kind': 'entity_set', 'fresh': key in fresh_map})
                continue
            for field in facts:
                before, after = getattr(stored[key], field), fresh_map[key][field]
                if before != after:
                    source_diffs.append({'key': key, 'field': field, 'before': before, 'after': after})
        (args.output / 'source-export.json.gz').write_bytes(gzip.compress(json.dumps(fresh, ensure_ascii=False).encode(), mtime=0))
        save('manual-manifest.json', manual_manifest)
        save('references.json', references)
        save('reference-failures.json', [r for r in references if r['issues']])
        save('coverage-differences.json', coverage)
        save('wording-differences.json', wording)
        save('sample.json', samples)
        save('summary-sample.json', summary_sample)
        save('internal-differences.json', internal)
        save('source-differences.json', source_diffs)
        save('source-preview.json', w.preview(fresh))
        save('summary.json', {'database': target, 'events': len(stored), 'versions': len(existing_versions),
                              'references': len(references), 'reference_failures': sum(bool(r['issues']) for r in references),
                              'reader_link_failures': sum(not r['reader_link'] for r in references),
                              'coverage_differences': len(coverage), 'wording_fields': dict(Counter(r['field'] for r in wording)),
                              'wording_entities': len({r['key'] for r in wording}),
                              'sample_count': len(samples), 'sample_drift': sum(r['differs'] for r in samples),
                              'summary_sample_count': len(summary_sample),
                              'summary_sample_drift': sum(r['differs'] for r in summary_sample),
                              'internal_differences': len(internal), 'source_fact_differences': len(source_diffs),
                              'source_rev': atlas['source_rev'], 'per_version': per_version})
    print((args.output / 'summary.json').read_text())


if __name__ == '__main__':
    main()
