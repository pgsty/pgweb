#!/usr/bin/env python3
"""Freeze every Wiki table for guarded field deltas and PG20 preservation checks."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a fresh output directory')
    import django
    django.setup()
    from django.apps import apps
    from django.db import connection, transaction
    args.output.mkdir(parents=True, mode=0o700)
    manifest = []
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cursor.execute('SELECT current_database(), current_user')
            if cursor.fetchone() != ('pgweb', 'pgweb'):
                raise ValueError('Requires PGSQL.CC pgweb database and role')
        for model in sorted(apps.get_app_config('wiki').get_models(), key=lambda m: m._meta.db_table):
            table, key = model._meta.db_table, model._meta.pk.attname
            rows = list(model.objects.order_by(key).values())
            raw = b''.join(encoded(row) + b'\n' for row in rows)
            (args.output / (table + '.jsonl.gz')).write_bytes(gzip.compress(raw, mtime=0))
            pinned = {str(row[key]): row['versions']['20'] for row in rows
                      if isinstance(row.get('versions'), dict) and '20' in row['versions']}
            if table.endswith('_version'):
                pinned.update({str(row[key]): row for row in rows if row.get('major') == '20'})
            manifest.append({'table': table, 'key': key, 'rows': len(rows),
                             'sha256': hashlib.sha256(raw).hexdigest(),
                             'pg20_sha256': hashlib.sha256(encoded(pinned)).hexdigest()})
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'tables': len(manifest), 'rows': sum(r['rows'] for r in manifest)}))


if __name__ == '__main__':
    main()
