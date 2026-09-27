"""Copy cloud evidence and a package-derived Pigsty anchor using two tables."""

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import re

from django.core.cache import cache
from django.db import connection, transaction

from .sync import json_text


CACHE_KEY = 'pgweb:ext:cloud:v1'
SOURCE_DSN = 'host=/tmp port=5432 dbname=data user=postgres'
FORMAT = 'pgweb-cloud-v1'
COLUMNS = {
    'cloud': ('service', 'pg_major', 'provider', 'service_name', 'engine_status',
              'data_status', 'list_scope', 'source_url', 'engine_url', 'checked_at', 'note', 'provenance'),
    'cloud_fact': ('service', 'pg_major', 'raw_name', 'extension', 'status', 'version', 'note', 'extra'),
}
KEYS = {'cloud': ('service', 'pg_major'), 'cloud_fact': ('service', 'pg_major', 'raw_name')}
PACKAGE_COLUMNS = ('pg', 'os', 'name', 'pkg', 'ext', 'state', 'hide', 'org', 'version', 'count')


def package_anchor(baseline, packages, majors, captured_at):
    """Keep package evidence separate from extension-control version claims."""
    direct = defaultdict(list)
    distributions = defaultdict(list)
    templates = defaultdict(set)
    for item in baseline:
        for column in ('rpm_pkg', 'deb_pkg'):
            if item[column]:
                templates[(column, item[column])].add(item['pkg'])
    for item in packages:
        direct[(item['ext'], item['pg'])].append(item)
        distributions[(item['pkg'], item['pg'])].append(item)
    coverage, facts = [], []
    for major in sorted(majors):
        coverage.append({
            'service': 'pigsty', 'pg_major': major, 'provider': 'Pigsty', 'service_name': 'Pigsty',
            'engine_status': 'GA', 'data_status': 'PARTIAL', 'list_scope': 'PG_MAJOR',
            'source_url': 'https://pgext.cloud/', 'engine_url': 'https://pigsty.cc/docs/pgsql/',
            'checked_at': captured_at,
            'note': 'Pigsty 打包基线；可用性来自包矩阵，含 PGDG 与 Pigsty 仓库，按操作系统汇总。',
            'provenance': {'origin': 'pgext.pkg', 'generated_anchor': True,
                           'collected_at': captured_at, 'baseline_count': len(baseline)},
        })
        for item in baseline:
            rows = direct[(item['name'], major)]
            relation = 'extension'
            if not rows:
                family = {item['pkg']}
                for column in ('rpm_pkg', 'deb_pkg'):
                    if item[column]:
                        family.update(templates[(column, item[column])])
                rows = [row for pkg in sorted(family) for row in distributions[(pkg, major)]]
                relation = 'distribution' if rows else 'unrecorded'
            rows = sorted(rows, key=lambda row: (row['os'], row['ext'], row['name']))
            available = sum(row['state'] == 'AVAIL' for row in rows)
            missing = sum(row['state'] == 'MISS' for row in rows)
            not_applicable = sum(row['state'] == 'N/A' for row in rows)
            versions = sorted({row['version'] for row in rows if row['state'] == 'AVAIL' and row['version']})
            availability = ('SUPPORTED' if available else
                            'UNSUPPORTED' if rows and not_applicable == len(rows) else 'UNKNOWN')
            supported_majors = item.get('pg_ver') or []
            compatibility_boundary = None
            if relation == 'distribution' and availability == 'SUPPORTED' and str(major) not in supported_majors:
                # The distribution can exist on a major while this bundled
                # child is absent. Catalog compatibility is a conservative
                # boundary here, never proof of installed package contents.
                availability = 'UNKNOWN'
                compatibility_boundary = 'unverified_major'
            note = {'extension': '依据实际包矩阵；版本为当前可用包版本，平台间可能不同。',
                    'distribution': '依据相同发行包的可用性；未将发行包版本当作该子扩展版本。',
                    'unrecorded': '包矩阵未记录此扩展；已收录打包目录，可用性未知。'}[relation]
            if compatibility_boundary:
                note = '发行包可用，但目录未确认该子扩展支持此 PG 大版本；扩展可用性未知。'
            facts.append({
                'service': 'pigsty', 'pg_major': major, 'raw_name': item['name'], 'extension': item['name'],
                'status': availability if availability != 'UNKNOWN' else 'OTHER',
                'version': ', '.join(versions) if relation == 'extension' and versions else None,
                'note': note,
                'extra': {'origin': 'pgext.pkg', 'packaged': True, 'package_relation': relation,
                          'availability': availability, 'package_versions': versions,
                          'supported_majors': supported_majors, 'compatibility_boundary': compatibility_boundary,
                          'available': available, 'missing': missing, 'not_applicable': not_applicable,
                          'targets': len(rows), 'platforms': rows},
            })
    return coverage, facts


def export_snapshot(source):
    """One read-only repeatable-read transaction covers clouds and packages."""
    source.set_session(isolation_level='REPEATABLE READ', readonly=True)
    tables = {}
    with source, source.cursor() as cursor:
        cursor.execute('SELECT current_database(), transaction_timestamp()')
        source_database, captured_at = cursor.fetchone()
        captured_at = captured_at.astimezone(timezone.utc).isoformat()
        for table, columns in COLUMNS.items():
            cursor.execute('SELECT {} FROM pgext.{} ORDER BY {}'.format(
                ', '.join(columns), table, ', '.join(KEYS[table])))
            tables[table] = [dict(zip(columns, row)) for row in cursor.fetchall()]
        if any(row['service'] == 'pigsty' for row in tables['cloud']):
            raise ValueError('Source already contains pigsty; review the anchor mapping before export')
        cursor.execute('SELECT name, pkg, rpm_pkg, deb_pkg, pg_ver FROM pgext.extension ORDER BY name')
        baseline = [dict(zip(('name', 'pkg', 'rpm_pkg', 'deb_pkg', 'pg_ver'), row)) for row in cursor.fetchall()]
        cursor.execute('SELECT {} FROM pgext.pkg ORDER BY pg, os, ext, name'.format(', '.join(PACKAGE_COLUMNS)))
        packages = [dict(zip(PACKAGE_COLUMNS, row)) for row in cursor.fetchall()]
    majors = {row['pg_major'] for row in tables['cloud']}
    coverage, facts = package_anchor(baseline, packages, majors, captured_at)
    tables['cloud'].extend(coverage)
    tables['cloud_fact'].extend(facts)
    snapshot = {'format': FORMAT, 'exported_at': captured_at, 'source_database': source_database, 'tables': tables}
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot):
    if snapshot.get('format') != FORMAT or set(snapshot.get('tables', {})) != set(COLUMNS):
        raise ValueError('Expected a pgweb-cloud-v1 snapshot containing only cloud and cloud_fact')
    identifiers = {}
    canonical = set()
    for table, columns in COLUMNS.items():
        rows = snapshot['tables'][table]
        if not isinstance(rows, list) or not rows:
            raise ValueError('{} must contain a nonempty list'.format(table))
        identifiers[table] = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(columns):
                raise ValueError('{} columns differ from the schema'.format(table))
            key = tuple(row[c] for c in KEYS[table])
            if key in identifiers[table]:
                raise ValueError('Duplicate {} key: {}'.format(table, key))
            identifiers[table].add(key)
            if not isinstance(row['service'], str) or not re.fullmatch(r'[a-z][a-z0-9_]*', row['service']):
                raise ValueError('Invalid service identifier')
            if type(row['pg_major']) is not int or not 10 <= row['pg_major'] <= 99:
                raise ValueError('Invalid PostgreSQL major')
            if table == 'cloud':
                if row['engine_status'] not in {'GA', 'PREVIEW', 'EXISTING_ONLY', 'UNAVAILABLE', 'UNKNOWN'}:
                    raise ValueError('Invalid engine status')
                if row['data_status'] not in {'COMPLETE', 'PARTIAL', 'MISSING'}:
                    raise ValueError('Invalid data status')
                if row['data_status'] == 'COMPLETE' and row['engine_status'] in {'UNAVAILABLE', 'UNKNOWN'}:
                    raise ValueError('Complete evidence cannot have an unavailable or unknown engine')
                if row['list_scope'] not in {'PG_MAJOR', 'PG_MAJOR_PARTIAL', 'PG_RANGE', 'SERVICE_WIDE',
                                             'CURRENT_MAJOR', 'DELEGATED', 'UNVERSIONED', 'INSTANCE_ONLY'}:
                    raise ValueError('Invalid list scope')
                if any(not isinstance(row[c], str) or not row[c].strip() for c in ('provider', 'service_name')):
                    raise ValueError('Missing service name or provider')
                if any(not isinstance(row[c], str) or not row[c].startswith('https://') for c in ('source_url', 'engine_url')):
                    raise ValueError('Source URLs must use HTTPS')
                if not isinstance(row['provenance'], dict) or not row['checked_at']:
                    raise ValueError('Missing provenance or source capture time')
                try:
                    timestamp = row['checked_at']
                    if not isinstance(timestamp, datetime):
                        timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    if timestamp.tzinfo is None:
                        raise ValueError('Source capture time needs a timezone')
                except (TypeError, AttributeError) as exc:
                    raise ValueError('Invalid source capture time') from exc
            else:
                if key[:2] not in identifiers['cloud']:
                    raise ValueError('Fact has no matching service-major coverage: {}'.format(key))
                if not isinstance(row['raw_name'], str) or not row['raw_name'] or row['raw_name'] != row['raw_name'].strip():
                    raise ValueError('Invalid raw extension name')
                if row['status'] not in {'SUPPORTED', 'UNSUPPORTED', 'OTHER'}:
                    raise ValueError('Invalid fact status')
                if row['extension'] is not None:
                    name = row['extension']
                    if not isinstance(name, str) or not name or name != name.strip():
                        raise ValueError('Invalid canonical extension name')
                    identity = key[:2] + (name,)
                    if identity in canonical:
                        raise ValueError('Duplicate canonical extension fact: {}'.format(identity))
                    canonical.add(identity)


def import_snapshot(snapshot, *, dry_run=False):
    """Atomic changed-row upsert; absence never deletes existing evidence."""
    validate_snapshot(snapshot)
    report = {'snapshot': hashlib.sha256(json_text(snapshot['tables']).encode()).hexdigest(),
              'dry_run': dry_run, 'tables': {}}
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('pgweb.ext.cloud_sync'))")
        cursor.execute('LOCK TABLE pgext.universe IN SHARE MODE')
        cursor.execute('LOCK TABLE pgext.cloud, pgext.cloud_fact IN SHARE ROW EXCLUSIVE MODE')
        for table, columns in COLUMNS.items():
            cursor.execute('CREATE TEMP TABLE cloud_stage_{} (LIKE pgext.{}) ON COMMIT DROP'.format(table, table))
            cursor.execute('INSERT INTO cloud_stage_{0} SELECT * FROM jsonb_populate_recordset(NULL::pgext.{0}, %s::jsonb)'.format(table),
                           [json_text(snapshot['tables'][table])])
        cursor.execute('''SELECT DISTINCT s.extension FROM cloud_stage_cloud_fact s
                          LEFT JOIN pgext.universe u ON u.name=s.extension
                          WHERE s.extension IS NOT NULL AND u.name IS NULL ORDER BY s.extension''')
        missing = [row[0] for row in cursor.fetchall()]
        if missing:
            raise ValueError('Sync Universe first; cloud facts reference missing names: ' + ', '.join(missing))
        # Detect a renamed raw label before either a dry-run or an apply. It must
        # be curated explicitly, never silently replace a target-only fact.
        cursor.execute('''SELECT s.service, s.pg_major, s.extension, s.raw_name, t.raw_name
                          FROM cloud_stage_cloud_fact s JOIN pgext.cloud_fact t
                          ON s.service=t.service AND s.pg_major=t.pg_major AND s.extension=t.extension
                          WHERE s.raw_name<>t.raw_name''')
        conflicts = cursor.fetchall()
        if conflicts:
            raise ValueError('Canonical/raw-name conflicts require review: ' + str(conflicts))
        for table, columns in COLUMNS.items():
            join = ' AND '.join('t.{0}=s.{0}'.format(c) for c in KEYS[table])
            compare = 'ROW({}) IS DISTINCT FROM ROW({})'.format(
                ', '.join('t.' + c for c in columns), ', '.join('s.' + c for c in columns))
            cursor.execute('''SELECT count(*) FILTER (WHERE t.service IS NULL),
                                     count(*) FILTER (WHERE t.service IS NOT NULL AND {compare}),
                                     count(*) FILTER (WHERE t.service IS NOT NULL AND NOT ({compare}))
                              FROM cloud_stage_{table} s LEFT JOIN pgext.{table} t ON {join}'''.format(
                table=table, compare=compare, join=join))
            created, updated, unchanged = cursor.fetchone()
            cursor.execute('SELECT count(*) FROM pgext.{table} t WHERE NOT EXISTS '
                           '(SELECT FROM cloud_stage_{table} s WHERE {join})'.format(table=table, join=join))
            retained = cursor.fetchone()[0]
            report['tables'][table] = {'source': len(snapshot['tables'][table]), 'created': created,
                                       'updated': updated, 'unchanged': unchanged, 'retained': retained}
        if not dry_run:
            for table, columns in COLUMNS.items():
                changed = 'ROW({}) IS DISTINCT FROM ROW({})'.format(
                    ', '.join('t.' + c for c in columns), ', '.join('excluded.' + c for c in columns))
                cursor.execute('''INSERT INTO pgext.{table} AS t ({cols}) SELECT {cols} FROM cloud_stage_{table}
                                  ON CONFLICT ({keys}) DO UPDATE SET {updates} WHERE {changed}'''.format(
                    table=table, cols=', '.join(columns), keys=', '.join(KEYS[table]), changed=changed,
                    updates=', '.join('{0}=excluded.{0}'.format(c) for c in columns if c not in KEYS[table])))
            transaction.on_commit(lambda: cache.delete(CACHE_KEY))
        for table in COLUMNS:
            cursor.execute('DROP TABLE cloud_stage_{}'.format(table))
    return report
