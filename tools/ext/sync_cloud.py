#!/usr/bin/env python3
"""Export or import the two-table cloud extension matrix and Pigsty anchor."""

import argparse
from contextlib import closing
import gzip
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db', default='host=/tmp port=5432 dbname=data user=postgres',
                        help='Source libpq DSN; defaults to local data on /tmp:5432 as postgres')
    parser.add_argument('--input', type=Path, help='Read this fixed JSON.gz snapshot instead of the source DB')
    parser.add_argument('--export', type=Path, help='Write a fixed JSON.gz snapshot and exit without importing')
    parser.add_argument('--database', help='Override Django target database name, e.g. an isolated test DB')
    parser.add_argument('--dry-run', action='store_true', help='Validate and compare without permanent writes')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    import psycopg2
    from django.conf import settings
    from django.db import DatabaseError
    if args.database:
        settings.DATABASES['default']['NAME'] = args.database
    django.setup()
    from pgweb.ext.cloud_sync import export_snapshot, import_snapshot, validate_snapshot
    from pgweb.ext.sync import json_text
    try:
        if args.input:
            snapshot = json.loads(gzip.decompress(args.input.read_bytes()))
        else:
            dsn = args.source_db if '=' in args.source_db or '://' in args.source_db else 'dbname=' + args.source_db
            with closing(psycopg2.connect(dsn)) as source:
                snapshot = export_snapshot(source)
        validate_snapshot(snapshot)
        if args.export:
            args.export.parent.mkdir(parents=True, exist_ok=True)
            args.export.write_bytes(gzip.compress(json_text(snapshot).encode(), mtime=0))
            print(json.dumps({'export': str(args.export),
                              'rows': {table: len(rows) for table, rows in snapshot['tables'].items()}},
                             ensure_ascii=False))
        else:
            print(json.dumps(import_snapshot(snapshot, dry_run=args.dry_run), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, DatabaseError, psycopg2.Error) as exc:
        print('Cloud sync failed: {}'.format(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
