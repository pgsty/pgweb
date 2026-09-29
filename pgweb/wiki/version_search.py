"""Rebuildable major-branch search entries; release storage remains authoritative."""

from django.contrib.postgres.search import SearchVector
from django.db import connection, transaction
from django.db.models import Value
from django.utils.html import escape

from pgweb.search.extract import digest
from pgweb.search.indexer import LOCK_NAMESPACE
from pgweb.search.lexicon import index_text
from pgweb.search.models import SearchEntry
from pgweb.search.service import forget_catalog
from .version_data import search_rows


def rebuild_versions(dry_run=False):
    objects = []
    for row in search_rows():
        aliases = [row['branch'], 'pg' + row['branch'], 'postgres ' + row['branch'], row['name'].lower()]
        objects.append(SearchEntry(
            source='versions', document=None, version=None, key=digest(row['branch']),
            entity_key='version:' + row['branch'], kind='version', subtype='',
            name=row['name'], name_key=row['name'].lower(), aliases=aliases,
            anchor='', heading='版本发布 · PostgreSQL ' + row['branch'], signature=row['summary'],
            body=row['body'], preview='<p>{}</p><p><a href="{}">查看生命周期、发布说明与安全证据</a></p>'.format(escape(row['summary']), escape(row['url'])),
            url=row['url'], weight=0.5,
            vector=SearchVector(Value(index_text(' '.join(aliases))), config='simple', weight='A') +
                   SearchVector(Value(index_text(row['body'])), config='simple', weight='B')))
    if not dry_run:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LOCK_NAMESPACE, 0])
            SearchEntry.objects.filter(source='versions').delete()
            SearchEntry.objects.bulk_create(objects, batch_size=100)
        forget_catalog()
    return {'versions': len(objects)}
