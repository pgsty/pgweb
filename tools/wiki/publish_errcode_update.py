#!/usr/bin/env python3
"""Publish a fixed SQLSTATE addition and its six appendix patches atomically.

Default: validate the complete baseline and show the diff without writing.
The payload contains each destination's own baseline; never copy another site's
authored articles or run the all-pages docloader for a single-page update.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
import django
django.setup()

from django.db import connection, transaction
from pgweb.docs.models import DocPage
from pgweb.search import indexer, service
from pgweb.search.models import IndexedPage, SearchEntry
from pgweb.wiki import importer
from pgweb.wiki.models import ErrorCode, ErrorCodeClass, ErrorCodeRelease


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), default=str).encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else encoded(value)).hexdigest()


def baseline():
    codes = list(ErrorCode.objects.order_by('sqlstate').values())
    for row in codes:
        row['class_code'] = row.pop('klass_id')
        row.pop('imported_at')
    return dict(format=2, codes=codes,
                classes=list(ErrorCodeClass.objects.order_by('code').values()),
                releases=list(ErrorCodeRelease.objects.order_by('position').values()))


def validate(payload):
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        database = cursor.fetchone()[0]
    if database != 'pgweb' and not database.startswith('test_pgweb_'):
        raise ValueError('PGSQL.CC pgweb or isolated test_pgweb_* required')
    before = baseline()
    if digest(before) != payload['baseline_sha256']:
        raise ValueError('SQLSTATE baseline changed after preparation')
    after = importer.prepare(payload['snapshot'])
    old = {r['sqlstate']: r for r in before['codes']}
    new = {r['sqlstate']: r for r in after['codes']}
    if new.keys() - old.keys() != {'22P07'} or old.keys() - new.keys():
        raise ValueError('expected exactly one new SQLSTATE')
    if any(old[k] != new[k] for k in old):
        raise ValueError('existing SQLSTATE article/evidence changed')
    addition = new['22P07']
    if (addition['condition_name'] != 'datum_version_mismatch'
            or addition['primary_macro'] != 'ERRCODE_DATUM_VERSION_MISMATCH'
            or addition['class_code'] != '22'
            or addition['present_in'] != ['14', '15', '16', '17', '18', '19']
            or addition['preview_in'] != ['19']
            or addition['evidence'].get('runtimes')
            or addition['runtime_verification']):
        raise ValueError('new SQLSTATE definition, version scope or evidence differs')
    old_classes = {r['code']: r for r in before['classes']}
    for r in after['classes']:
        expected = dict(old_classes.pop(r['code']))
        if r['code'] == '22':
            expected['sqlstate_count'] += 1
        if r != expected:
            raise ValueError('unexpected class change')
    if old_classes:
        raise ValueError('missing class')
    boundaries = {'14': '14.25', '15': '15.20', '16': '16.16',
                  '17': '17.12', '18': '18.7', '19': '19rc2'}
    for language in ('en', 'zh'):
        sections = addition['texts'][language]['sections']
        rendered = '\n'.join(section.get('html', '') for section in sections)
        if any(release not in rendered for release in boundaries.values()):
            raise ValueError('rendered entry must show every minor-release boundary')
    if any(source['kind'] != 'upstream_source' for source in addition['evidence']['sources']):
        raise ValueError('release sources must be identified as upstream source evidence')
    if len(after['releases']) != len(before['releases']):
        raise ValueError('release identity set changed')
    for old_release, release in zip(before['releases'], after['releases']):
        major = release['major']
        if major != old_release['major']:
            raise ValueError('release order or identity changed')
        if major in boundaries:
            if release['release'] != boundaries[major] or release['code_count'] != old_release['code_count'] + 1:
                raise ValueError('release boundary/count differs')
        elif release != old_release:
            raise ValueError('unselected release changed')
    if {str(p['version']) for p in payload['pages']} != set(boundaries) or len(payload['pages']) != 6:
        raise ValueError('exactly six appendix versions required')
    for p in payload['pages']:
        page = DocPage.objects.get(version=p['version'], file='errcodes-appendix.html')
        if page.pk != p['id'] or digest(page.content.encode()) != p['before_sha256']:
            raise ValueError('manual appendix changed after preparation')
        if digest(p['content'].encode()) != p['after_sha256']:
            raise ValueError('manual patch checksum differs')
        if page.title != p['title'] or '22P07' not in p['content'] or 'datum_version_mismatch' not in p['content']:
            raise ValueError('manual patch identity differs')
    return after, dict(database=database, codes_before=len(old), codes_after=len(new),
                      added=['22P07'], existing_articles_preserved=len(old), appendix_pages=6)


def publish(payload, rollback=False):
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('LOCK TABLE sqlstate,sqlstate_class,sqlstate_version IN SHARE ROW EXCLUSIVE MODE')
            # Same per-version locks used by the ordinary manual indexer.
            for p in payload['pages']:
                cursor.execute('SELECT pg_advisory_xact_lock(%s,%s)', [indexer.LOCK_NAMESPACE, int(p['version'])])
        # A doc loader need not share the indexer's advisory locks. Hold page
        # locks before checking hashes so a concurrent refresh cannot be lost.
        list(DocPage.objects.select_for_update().filter(
            pk__in=[p['id'] for p in payload['pages']]).order_by('pk'))
        snapshot, report = validate(payload)
        report['import'] = importer.import_snapshot(snapshot)
        for p in payload['pages']:
            page = DocPage.objects.select_for_update().get(pk=p['id'])
            page.content = p['content']
            page.save(update_fields=['content'])
            entries = indexer.extract_page(page.file, page.title, page.content, str(p['version']))
            document, _ = IndexedPage.objects.update_or_create(page_id=page.pk,
                defaults={'source_hash': indexer.source_hash(page.title, page.content)})
            objects = [indexer.entry_object(document.pk, int(p['version']), e) for e in entries]
            SearchEntry.objects.bulk_create(objects, batch_size=100, update_conflicts=True,
                unique_fields=['document', 'key'], update_fields=['entity_key', 'kind', 'subtype',
                'name', 'name_key', 'aliases', 'anchor', 'heading', 'signature', 'body', 'preview', 'vector', 'version'])
            document.entries.exclude(key__in=[e['key'] for e in entries]).delete()
        report['search'] = indexer.rebuild_errcodes()
        report['rolled_back'] = rollback
        if rollback:
            transaction.set_rollback(True)
        else:
            transaction.on_commit(service.forget_catalog)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--export-baseline', type=Path)
    parser.add_argument('--test-database', help='administrator-prepared isolated test_pgweb_* database')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--rollback', action='store_true', help='exercise the transaction then roll back; use an isolated database')
    args = parser.parse_args()
    if args.test_database:
        if not args.test_database.startswith('test_pgweb_'):
            raise ValueError('isolated test_pgweb_* database required')
        connection.close()
        connection.settings_dict['NAME'] = args.test_database
    if args.rollback and not connection.settings_dict['NAME'].startswith('test_pgweb_'):
        raise ValueError('rollback rehearsal requires an isolated test_pgweb_* database')
    if args.export_baseline:
        if args.export_baseline.exists():
            raise ValueError('new baseline destination required')
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            data = dict(baseline=baseline(), pages=[dict(id=p.pk, version=str(int(p.version_id)),
                title=p.title, content=p.content) for p in DocPage.objects.filter(
                file='errcodes-appendix.html', version__in=[14,15,16,17,18,19]).order_by('version')])
        args.export_baseline.write_bytes(gzip.compress(encoded(data), mtime=0))
        print(json.dumps(dict(sha256=digest(data['baseline']), codes=len(data['baseline']['codes']))))
    else:
        payload = json.loads(gzip.decompress(args.input.read_bytes()))
        report = publish(payload, args.rollback) if args.write or args.rollback else validate(payload)[1]
        print(json.dumps(report, ensure_ascii=False))
