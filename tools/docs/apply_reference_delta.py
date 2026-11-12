#!/usr/bin/env python3
"""Apply a reviewed, frozen reference delta without replacing concurrent edits.

Inputs are complete per-table JSONL.gz inventories. Only fields changed between
the two inventories are written. Existing IDs, unrelated columns, and rows
absent from the delta survive. A conflicting live field aborts the transaction.
"""
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), default=str)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load(path, key):
    with gzip.open(path, 'rt') as stream:
        rows = [json.loads(line) for line in stream]
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError('duplicate identity in ' + path.name)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--target', choices=('local', 'production'), default='local')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    django.setup()
    from django.apps import apps
    from django.core.cache import cache
    from django.conf import settings
    from django.db import connection, transaction
    from django.utils import timezone
    from pgweb.wiki.snapshot import model_hash

    models = {model._meta.db_table: model for model in apps.get_models()
              if model._meta.app_label in ('wiki', 'featurematrix')}
    manifest = json.loads((args.before / 'manifest.json').read_bytes())
    if {entry['table'] for entry in manifest} != {p.name[:-9] for p in args.after.glob('*.jsonl.gz')}:
        raise ValueError('complete table membership differs')
    host = settings.DATABASES['default'].get('HOST', '')
    if args.target == 'local' and host not in ('', 'localhost', '127.0.0.1', '::1') and not host.startswith('/'):
        raise ValueError('local mode requires a loopback or Unix-socket connection')
    receipt = {'written': args.write, 'target': args.target, 'tables': [], 'concurrent_equal_rows': []}
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database(), current_user')
            if cursor.fetchone() != ('pgweb', 'pgweb'):
                raise ValueError('requires the PGSQL.CC database and role')
            cursor.execute("SET LOCAL lock_timeout = '10s'")
            cursor.execute('SELECT pg_advisory_xact_lock(724130611)')
        for entry in manifest:
            table = entry['table']
            model = models[table]
            key = model._meta.pk.attname
            before = load(args.before / (table + '.jsonl.gz'), key)
            after = load(args.after / (table + '.jsonl.gz'), key)
            if not before.keys() <= after.keys():
                raise ValueError('deleting identities is not supported: ' + table)
            fields = {f.attname: f for f in model._meta.concrete_fields}
            changed = []
            for identity, desired in after.items():
                original = before.get(identity)
                touched = {k for k in fields if k not in (key, 'content_hash', 'imported_at', 'source_rev')
                           and k in desired and (original is None or desired[k] != original.get(k))}
                if not touched:
                    continue
                current = model.objects.select_for_update().filter(pk=identity).first()
                if current is None:
                    if original is not None:
                        raise ValueError(f'live identity removed: {table}/{identity}')
                    current = model(**{k: deepcopy(v) for k, v in desired.items()
                                       if k in fields and k not in ('content_hash', 'imported_at')})
                    if 'content_hash' in fields:
                        current.content_hash = model_hash(current)
                    current.save(force_insert=True)
                    changed.append({'key': identity, 'created': True, 'fields': sorted(touched)})
                    continue
                if original is None:
                    # Another publisher may already have added the same identity.
                    # Exact supplied business fields must agree; never erase its work.
                    if any(canonical(getattr(current, k)) != canonical(desired[k]) for k in touched):
                        raise ValueError(f'concurrent new identity differs: {table}/{identity}')
                    receipt['concurrent_equal_rows'].append([table, identity])
                    continue
                updates = {}
                for k in touched:
                    live = getattr(current, k)
                    if canonical(live) == canonical(desired[k]):
                        continue
                    if canonical(live) != canonical(original.get(k)):
                        raise ValueError(f'concurrent field differs: {table}/{identity}/{k}')
                    updates[k] = deepcopy(desired[k])
                    setattr(current, k, updates[k])
                if not updates:
                    continue
                if 'content_hash' in fields:
                    updates['content_hash'] = model_hash(current)
                if 'imported_at' in fields:
                    updates['imported_at'] = timezone.now()
                model.objects.filter(pk=identity).update(**updates)
                changed.append({'key': identity, 'fields': sorted(updates),
                                'before_sha256': digest(original), 'input_sha256': digest(desired)})
            receipt['tables'].append({'table': table, 'updated': len(changed), 'rows': changed})
            print(table, len(changed), flush=True)
        if args.write:
            transaction.on_commit(cache.clear)
        else:
            transaction.set_rollback(True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print('committed' if args.write else 'validated and rolled back', flush=True)


if __name__ == '__main__':
    main()
