"""Snapshot and synchronize only pgext.universe."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction

from .catalog import CACHE_KEY


COLUMNS = json.loads(Path(__file__).with_name('columns.json').read_text())


def json_text(value):
    return json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def export_snapshot(source):
    """The caller supplies a psycopg connection for a read-only snapshot."""
    source.set_session(isolation_level='REPEATABLE READ', readonly=True)
    tables = {}
    with source, source.cursor() as cursor:
        for table, columns in COLUMNS.items():
            cursor.execute('SELECT {} FROM pgext.{} ORDER BY id'.format(', '.join(columns), table))
            tables[table] = [dict(zip(columns, row)) for row in cursor.fetchall()]
    snapshot = {'format': 2, 'exported_at': datetime.now(timezone.utc).isoformat(), 'tables': tables}
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot):
    if snapshot.get('format') != 2 or set(snapshot.get('tables', {})) != set(COLUMNS):
        raise ValueError('Expected a version 2 snapshot containing only universe; re-export with the current sync tool')
    for table, columns in COLUMNS.items():
        rows = snapshot['tables'][table]
        if not isinstance(rows, list) or not rows:
            raise ValueError('{} must contain a nonempty list of records'.format(table))
        if any(set(row) != set(columns) for row in rows):
            raise ValueError('{} columns differ from the catalog schema'.format(table))
        if len({row['id'] for row in rows}) != len(rows) or len({row['name'] for row in rows}) != len(rows):
            raise ValueError('{} contains duplicate IDs or names'.format(table))


def import_snapshot(snapshot, *, dry_run=False, prune=False):
    validate_snapshot(snapshot)
    report = {'snapshot': hashlib.sha256(json_text(snapshot['tables']).encode()).hexdigest(),
              'dry_run': dry_run, 'tables': {}}
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('pgweb.ext.sync'))")
        # Staging tables have no identity sequence, triggers, or permanent writes.
        for table, columns in COLUMNS.items():
            cursor.execute('CREATE TEMP TABLE ext_stage_{} (LIKE pgext.{}) ON COMMIT DROP'.format(table, table))
            cursor.execute('INSERT INTO ext_stage_{0} SELECT * FROM jsonb_populate_recordset(NULL::pgext.{0}, %s::jsonb)'.format(table),
                           [json_text(snapshot['tables'][table])])
            compare = 'ROW({}) IS DISTINCT FROM ROW({})'.format(
                ', '.join('t.' + c for c in columns), ', '.join('s.' + c for c in columns))
            cursor.execute('''SELECT count(*) FILTER (WHERE t.id IS NULL),
                                     count(*) FILTER (WHERE t.id IS NOT NULL AND {compare}),
                                     count(*) FILTER (WHERE t.id IS NOT NULL AND NOT ({compare}))
                              FROM ext_stage_{table} s LEFT JOIN pgext.{table} t ON t.id = s.id'''.format(table=table, compare=compare))
            created, updated, unchanged = cursor.fetchone()
            cursor.execute('SELECT count(*) FROM pgext.{0} t WHERE NOT EXISTS (SELECT FROM ext_stage_{0} s WHERE s.id=t.id)'.format(table))
            missing = cursor.fetchone()[0]
            report['tables'][table] = {'source': len(snapshot['tables'][table]), 'created': created,
                                       'updated': updated, 'unchanged': unchanged,
                                       'deleted': missing if prune else 0, 'retained': 0 if prune else missing}
        if not dry_run:
            if prune:
                for table in COLUMNS:
                    cursor.execute('DELETE FROM pgext.{0} t WHERE NOT EXISTS (SELECT FROM ext_stage_{0} s WHERE s.id=t.id)'.format(table))
            for table, columns in COLUMNS.items():
                changed = 'ROW({}) IS DISTINCT FROM ROW({})'.format(
                    ', '.join('t.' + c for c in columns), ', '.join('excluded.' + c for c in columns))
                cursor.execute('''INSERT INTO pgext.{table} AS t ({cols}) SELECT {cols} FROM ext_stage_{table}
                                  ON CONFLICT (id) DO UPDATE SET {updates} WHERE {changed}'''.format(
                    table=table, cols=', '.join(columns), changed=changed,
                    updates=', '.join('{0} = excluded.{0}'.format(c) for c in columns if c != 'id')))
            # Explicit source IDs must not leave the local identity behind.
            if report['tables']['universe']['created']:
                cursor.execute("SELECT setval(pg_get_serial_sequence('pgext.universe', 'id'), (SELECT max(id) FROM pgext.universe), true)")
            transaction.on_commit(lambda: cache.delete(CACHE_KEY))
        for table in COLUMNS:
            cursor.execute('DROP TABLE ext_stage_{}'.format(table))
    return report
