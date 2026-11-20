#!/usr/bin/env python3
"""Read-only inventory of every Wiki domain, pinned sources and manual links.

Run in the intended Django checkout. No source fetches, imports or cache clears.
The report distinguishes unavailable evidence from verified source content.
"""
import argparse
from collections import Counter, defaultdict
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


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.anchors, self.urls = set(), set()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if not value:
                continue
            if key == 'id' or (tag == 'a' and key == 'name'):
                self.anchors.add(value)
            if key == 'href':
                self.urls.add(value)


def urls(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ('url', 'href') and isinstance(child, str):
                yield child
            else:
                yield from urls(child)
    elif isinstance(value, list):
        for child in value:
            yield from urls(child)
    elif isinstance(value, str) and 'href=' in value:
        yield from Links(value).urls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--majors', nargs='+', default=list(map(str, range(14, 20))))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    import django
    django.setup()
    from django.apps import apps
    from django.db import connection, transaction
    from pgweb.core.models import Version
    from pgweb.docs.models import DocPage
    from pgweb.wiki import topics
    from pgweb.wiki.columns import COLUMNS
    from pgweb.wiki.manuals import manual_slug
    from pgweb.wiki.models import (CatalogRelation, GucParameter, WaitEvent, PgFunction,
                                   SqlCommand, ErrorCode, LockMode)

    def save(name, data):
        (args.output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                                  default=str) + '\n')

    models = dict(topics.MODELS, catalog=CatalogRelation, guc=GucParameter,
                  waitevent=WaitEvent, func=PgFunction, sql=SqlCommand,
                  sqlstate=ErrorCode, lock=LockMode)
    table_hashes, version_tables, domains, references, failures = {}, {}, {}, [], []
    source_counts = defaultdict(Counter)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute('SELECT current_database(),current_user')
            target = cursor.fetchone()
            if target[0] != 'pgweb':
                raise ValueError('Expected the Chinese pgweb database')
            for model in apps.get_app_config('wiki').get_models():
                table = model._meta.db_table
                cursor.execute('SELECT md5((to_jsonb(t) - \'imported_at\')::text) '
                               'FROM ' + connection.ops.quote_name(table) + ' t ORDER BY 1')
                hashes = [r[0] for r in cursor.fetchall()]
                table_hashes[table] = {'rows': len(hashes), 'sha256': hashlib.sha256(
                    '\n'.join(hashes).encode()).hexdigest()}
                if table.endswith('_version'):
                    version_tables[table] = list(model.objects.values())
            cursor.execute("SELECT source,count(*) FROM search_searchentry GROUP BY source ORDER BY source")
            search_counts = dict(cursor.fetchall())
        core = list(Version.objects.values())
        current = next(manual_slug(v['tree']) for v in core if v['current'])
        manual_content = {(manual_slug(v), f): c for v, f, c in DocPage.objects
                          .filter(version__in=[int(v) for v in args.majors])
                          .values_list('version', 'file', 'content')}
        manual_files = {(manual_slug(v), f) for v, f in DocPage.objects.values_list('version', 'file')}
        anchors = {}
        identities = {kind: set(model.objects.values_list(model._meta.pk.name, flat=True))
                      for kind, model in models.items()}
        for kind, model in models.items():
            print('Auditing ' + kind, file=sys.stderr, flush=True)
            counts, samples = Counter(), {}
            for item in model.objects.all().iterator(chunk_size=100):
                snapshots = item.versions if kind != 'sqlstate' else {
                    v: {'sources': item.evidence.get('sources', [])} for v in item.present_in}
                counts.update(snapshots.keys())
                for major, snapshot in snapshots.items():
                    if major not in args.majors:
                        continue
                    release = snapshot.get('release', snapshot.get('provenance', {}))
                    label = release.get('label', release.get('release', release.get('ref', ''))) if isinstance(release, dict) else release
                    source_counts[(kind, major)][label or '(see version table / provenance)'] += 1
                    if major not in samples:
                        samples[major] = {'entity': str(item.pk), 'release': release,
                                          'source_revalidation': snapshot.get('source_revalidation'),
                                          'translation_provenance': snapshot.get('translation_provenance'),
                                          'sources': snapshot.get('sources', [])}
                    linkset = set(urls(snapshot))
                    for key in ('doc', 'zh_doc'):
                        doc = snapshot.get(key, {})
                        if doc.get('file') and doc.get('slug'):
                            linkset.add('/docs/{}/{}{}'.format(doc['slug'], doc['file'],
                                '#' + doc['anchor'] if doc.get('anchor') else ''))
                    if kind == 'sql' and snapshot.get('file'):
                        linkset.add('/docs/{}/{}{}'.format(major, snapshot['file'],
                            '#' + snapshot['anchor'] if snapshot.get('anchor') else ''))
                    for url in sorted(linkset):
                        parsed = urlsplit(unescape(url))
                        if parsed.netloc and parsed.netloc not in ('pgsql.cc', 'www.pgsql.cc'):
                            continue
                        path = unquote(parsed.path)
                        errors = []
                        match = re.fullmatch(r'/docs/(\d+(?:\.\d+)?|devel|current)/([^/]+)', path)
                        if match:
                            ver, filename = match.groups()
                            ver = current if ver == 'current' else ver
                            pair = (ver, filename)
                            if pair not in manual_files:
                                errors.append('manual_page_missing')
                            elif parsed.fragment and pair in manual_content:
                                if pair not in anchors:
                                    anchors[pair] = Links(manual_content[pair]).anchors
                                if unquote(parsed.fragment) not in anchors[pair]:
                                    errors.append('manual_anchor_missing')
                        elif path.startswith('/wiki/'):
                            parts = path.strip('/').split('/')
                            if len(parts) == 3 and parts[1] in identities and parts[1] != 'waitevent':
                                if parts[2] not in identities[parts[1]] and parts[2] != 'changes':
                                    errors.append('wiki_entity_missing')
                        else:
                            continue
                        ref = {'kind': kind, 'entity': str(item.pk), 'major': major,
                               'url': url, 'errors': errors}
                        references.append(ref)
                        if errors:
                            failures.append(ref)
            source = {'sql': 'sqlcmd', 'sqlstate': 'errcode', 'waitevent': 'wait'}.get(kind, kind)
            domains[kind] = {'entities': len(identities[kind]), 'snapshots': dict(sorted(counts.items())),
                             'search_entries': search_counts.get(source, 0), 'source_samples': samples}
        domains['versions'] = {'entities': len(core), 'search_entries': search_counts.get('versions', 0)}
        assert set(domains) == {column['slug'] for column in COLUMNS}
    save('inventory.json', {'database': target, 'current': current, 'core_versions': core,
                            'tables': table_hashes, 'version_tables': version_tables,
                            'domains': domains,
                            'source_releases': {kind: {v: dict(source_counts[(kind, v)])
                                for v in args.majors} for kind in models}})
    save('references.json', references)
    save('reference-failures.json', failures)
    summary = {'database': target, 'domains': len(domains), 'tables': len(table_hashes),
               'entities': sum(d['entities'] for d in domains.values()),
               'references': len(references), 'reference_failures': len(failures),
               'failure_kinds': dict(Counter(e for row in failures for e in row['errors']))}
    save('summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
