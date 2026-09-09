"""Explicit, transactional indexing of local PG manuals, keyed by source hashes."""
import re
from collections import Counter

from django.db import connection, transaction
from django.contrib.postgres.search import SearchVector
from django.db.models import Value

from pgweb.docs.models import DocPage
from .extract import extract_page, source_hash
from .lexicon import index_text
from .models import IndexedPage, SearchEntry


def eligible_page(page):
    if not page.file.endswith('.html') or page.file in ('bookindex.html', 'index.html'):
        return False
    # Older release notes are copied into newer manuals but their reader routes redirect.
    release = re.match(r'release-(\d+)(?:-|\.)', page.file)
    return not release or int(release.group(1)) == int(page.version_id)


def entry_object(document_id, version, entry):
    title = index_text(' '.join([entry['name'], *entry['aliases'], entry['signature'], entry['heading']]))
    body = index_text(entry['body'])
    vector = (SearchVector(Value(title), config='simple', weight='A') +
              SearchVector(Value(body), config='simple', weight='D'))
    return SearchEntry(document_id=document_id, version=version, vector=vector, **entry)


def rebuild_version(version, force=False, dry_run=False, progress=None):
    report = Counter()
    pages = list(DocPage.objects.filter(version=version).order_by('file'))
    hashes = dict(IndexedPage.objects.filter(page__version=version).values_list('page_id', 'source_hash'))
    changed, eligible = [], []
    for page in pages:
        if not eligible_page(page):
            continue
        eligible.append(page.pk)
        fingerprint = source_hash(page.title, page.content)
        if not force and hashes.get(page.pk) == fingerprint:
            report['unchanged'] += 1
            continue
        entries = extract_page(page.file, page.title, page.content, str(int(version)))
        changed.append((page, fingerprint, entries))
        report['pages'] += 1
        report['entries'] += len(entries)
        report.update({'kind:' + k: n for k, n in Counter(e['kind'] for e in entries).items()})
        if progress and report['pages'] % 100 == 0:
            progress('{} pages extracted'.format(report['pages']))
    if dry_run:
        return dict(report)
    with transaction.atomic():
        # Serialize publication per version; lock changed source rows while publishing.
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [734021, int(version)])
        for page, fingerprint, entries in changed:
            # Reject a changed source rather than publishing results for the wrong text.
            current = DocPage.objects.select_for_update().get(pk=page.pk)
            if (current.file != page.file or current.version_id != page.version_id
                    or source_hash(current.title, current.content) != fingerprint):
                raise ValueError('Source changed while indexing: ' + page.file)
            document, _ = IndexedPage.objects.update_or_create(page_id=page.pk, defaults={'source_hash': fingerprint})
            objects = [entry_object(document.pk, version, entry) for entry in entries]
            SearchEntry.objects.bulk_create(objects, batch_size=100, update_conflicts=True,
                                            unique_fields=['document', 'key'],
                                            update_fields=['entity_key', 'kind', 'subtype', 'name', 'name_key', 'aliases',
                                                           'anchor', 'heading', 'signature', 'body', 'preview', 'vector', 'version'])
            document.entries.exclude(key__in=[entry['key'] for entry in entries]).delete()
        IndexedPage.objects.filter(page__version=version).exclude(page_id__in=eligible).delete()
    return dict(report)
