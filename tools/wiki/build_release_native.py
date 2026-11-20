#!/usr/bin/env python3
"""Recheck native topics against immutable release archives and local manuals."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pins', type=Path, required=True)
    parser.add_argument('--tags', type=Path, required=True)
    parser.add_argument('--pgdoc', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--before', type=Path)
    parser.add_argument('--system-only', action='store_true')
    args = parser.parse_args()
    pins = json.loads(args.pins.read_text())
    tags = {line.split()[1].split('/')[-1]: line.split()[0] for line in args.tags.read_text().splitlines()}
    revisions = {}
    for major, pin in pins.items():
        tag = 'REL_' + pin['release'].replace('.', '_')
        revisions[major] = (tag, tags[tag])
        if args.system_only:
            continue
        archive = args.pgdoc / '.cache/upstream' / ('postgresql-' + pin['release'] + '.tar.bz2')
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == pin['sha256']
        destination = args.cache / tags[tag]
        with tarfile.open(archive) as stream:
            for member in stream:
                path = member.name.partition('/')[2]
                if member.isfile() and path.startswith(('src/', 'doc/src/sgml/')):
                    assert '..' not in Path(path).parts
                    target = destination / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(stream.extractfile(member).read())
        (destination / '.complete').touch()
    from tools.wiki import build_hooks, build_locks, build_relopts, build_role_oid
    from pgweb.wiki import hook_data
    build_hooks.REVISIONS = revisions
    build_locks.REVISIONS = revisions
    build_relopts.MAJORS = list(pins)
    sampled = set()
    if not args.system_only:
        for major, (_, revision) in revisions.items():
            sampled.update(build_hooks.scan_tree(args.cache / revision)[0])
    # Editorial entries belonging only to a frozen, unselected version are not
    # generated here. Selected-version membership is checked by the publisher.
    hook_data.HOOKS = {k: v for k, v in hook_data.HOOKS.items() if k in sampled}
    results = {} if args.system_only else {'hook': build_hooks.build(args.cache), 'lock': build_locks.build(args.cache, False)}
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    django.setup()
    from django.db import transaction, connection
    from pgweb.docs.models import DocPage
    if args.system_only:
        from bs4 import BeautifulSoup
        from pgweb.wiki.catalog_importer import Manual, parse_columns, relation_description
        class FrozenManual(Manual):
            def soup(self, filename):
                if filename not in self._soups:
                    path = args.pgdoc / 'en' / pins[self.tree]['release'] / 'html' / filename
                    self._soups[filename] = BeautifulSoup(path.read_text(), 'html.parser') if path.exists() else None
                return self._soups[filename]
        rows = [json.loads(line) for line in gzip.decompress((args.before / 'catalog.jsonl.gz').read_bytes()).splitlines()]
        readers = {m: FrozenManual(m) for m in pins}
        overviews = {m: readers[m].overview() for m in pins}
        relations = []
        for row in rows:
            if row['kind'] not in ('statistics', 'progress'):
                continue
            result = dict(name=row['name'], versions={})
            for major in pins:
                if major not in row['versions']:
                    continue
                doc = row['versions'][major]['doc']
                file = doc['file']
                raw = (args.pgdoc / 'en' / pins[major]['release'] / 'html' / file).read_bytes()
                table = readers[major].table(file, doc.get('anchor', ''), row['name'])
                # sys/user statistic views explicitly share the all-view schema.
                # Their own overview describes the filter; the common table is
                # the manual's definition, not an inferred adjacent version.
                if table is None and ('_sys_' in row['name'] or '_user_' in row['name']):
                    alias = row['name'].replace('_sys_', '_all_').replace('_user_', '_all_')
                    table = readers[major].table(file, doc.get('anchor', ''), alias)
                columns = parse_columns(table, row['name']) if table else []
                for column in columns:
                    column['type'] = column['documented_type']
                    column['description'] = column.pop('description_zh')
                    column['documented'] = True
                result['versions'][major] = dict(columns=columns,
                    description=relation_description(table) if table else overviews[major].get(row['name'], ''),
                    doc=dict(file=file, anchor=(table.get('id', '') if table else doc.get('anchor', '')),
                             sha256=hashlib.sha256(raw).hexdigest()))
            relations.append(result)
        (args.output / 'system-relations.json.gz').write_bytes(gzip.compress(json.dumps(relations).encode(), mtime=0))
        print('system relations', len(relations))
        return
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        results['relopts'] = build_relopts.build(build_relopts.read_database())
        for kind, filename in [('role', 'predefined-roles.html'), ('oid', 'datatype-oid.html')]:
            pages = [(m, DocPage.objects.get(version_id=m, file=filename).content,
                      'historical' if m == '14' else 'stable') for m in pins]
            results[kind] = build_role_oid.assemble(kind, pages)
    args.output.mkdir(parents=True, exist_ok=True)
    for kind, result in results.items():
        raw = json.dumps(result, ensure_ascii=False, sort_keys=True).encode()
        (args.output / (kind + '.json.gz')).write_bytes(gzip.compress(raw, mtime=0))
        print(kind, len(result.get('items', result.get('modes', []))), flush=True)


if __name__ == '__main__':
    main()
