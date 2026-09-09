#!/usr/bin/env python3
"""Sync only pgext.universe into the local or production PGWeb DB."""

import argparse
from contextlib import closing
import gzip
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db', default='data', help='Source libpq database name or service/DSN (default: data)')
    parser.add_argument('--input', help='Read a saved .json.gz snapshot instead; - reads gzip from stdin')
    parser.add_argument('--export', type=Path, metavar='FILE.json.gz', help='Export a fixed, compressed snapshot and exit')
    parser.add_argument('--target', choices=['local', 'production'], default='local')
    parser.add_argument('--database', help='Override target database name, e.g. for an isolated test database')
    parser.add_argument('--ssh-host', default='pg')
    parser.add_argument('--remote-root', default='/data/app/pgweb')
    parser.add_argument('--dry-run', action='store_true', help='Compare only; no permanent table or sequence writes')
    parser.add_argument('--prune', action='store_true', help='Remove target rows absent from this complete source snapshot')
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
    from pgweb.ext.sync import export_snapshot, import_snapshot, json_text, validate_snapshot
    try:
        if args.input:
            payload = sys.stdin.buffer.read() if args.input == '-' else Path(args.input).read_bytes()
            snapshot = json.loads(gzip.decompress(payload))
        else:
            with closing(psycopg2.connect(args.source_db if '=' in args.source_db or '://' in args.source_db else 'dbname=' + args.source_db)) as source:
                snapshot = export_snapshot(source)
        validate_snapshot(snapshot)
        if args.export:
            args.export.write_bytes(gzip.compress(json_text(snapshot).encode(), mtime=0))
            print('Exported {} extensions to {}'.format(len(snapshot['tables']['universe']), args.export))
            return 0
        if args.target == 'production':
            remote = ['.venv/bin/python', 'tools/ext/sync_catalog.py', '--input', '-']
            if args.database:
                remote += ['--database', args.database]
            if args.dry_run:
                remote.append('--dry-run')
            if args.prune:
                remote.append('--prune')
            command = 'cd {} && {}'.format(shlex.quote(args.remote_root), shlex.join(remote))
            result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '--', args.ssh_host, command],
                                    input=gzip.compress(json_text(snapshot).encode(), mtime=0), capture_output=True)
            if result.returncode:
                raise ValueError('Remote sync failed: ' + result.stderr.decode().strip())
            report = json.loads(result.stdout)
        else:
            report = import_snapshot(snapshot, dry_run=args.dry_run, prune=args.prune)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not args.dry_run:
            print('Refresh the search index: .venv/bin/python manage.py index_docs --extensions', file=sys.stderr)
        return 0
    except (OSError, ValueError, DatabaseError, psycopg2.Error) as exc:
        print('Catalog sync failed: {}'.format(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
