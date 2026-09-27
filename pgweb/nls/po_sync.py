"""Reconcile existing messages with a fixed authoritative PO snapshot.

This is deliberately separate from candidate bundle import: source-authorized
corrections may replace current translations, but never invent human approval.
"""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from django.db import transaction

from .importer import IDENTITY_FIELDS
from .models import Message
from .validate import check_forms, ValidationError

SCHEMA = 'pgnls-authoritative-po-v1'
CONTENT = ('forms', 'plural_forms', 'flags')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def identity(row):
    return tuple(row[key] for key in IDENTITY_FIELDS)


def read(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        value = json.load(stream)
    if value.get('schema') != SCHEMA or not value.get('messages'):
        raise ValueError('Expected a nonempty authoritative PO snapshot')
    if value.get('sha256') != digest(value['messages']):
        raise ValueError('PO snapshot content digest mismatch')
    ids, identities = set(), set()
    for row in value['messages']:
        if set(row.get('desired', {})) != set(CONTENT):
            raise ValueError('Unexpected PO snapshot target fields')
        if not isinstance(row.get('expected'), str) or len(row['expected']) != 64:
            raise ValueError('Missing expected current-content digest')
        key = identity(row)
        if row['id'] in ids or key in identities:
            raise ValueError('Duplicate PO message ID or natural identity')
        ids.add(row['id']); identities.add(key)
        probe = Message(**{key: row[key] for key in IDENTITY_FIELDS}, **row['desired'])
        check_forms(probe, probe.forms)
        if any(not text for text in probe.forms.values()):
            raise ValueError('Authoritative PO translations must be complete')
    return value


def export(root, output):
    root = Path(root).expanduser().resolve()
    # Reuse the source project's lossless PO parser, without executing its CLI.
    spec = importlib.util.spec_from_file_location('_pgnls_poio', root / 'bin/poio.py')
    poio = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = poio
    spec.loader.exec_module(poio)
    existing = {identity(row): row for row in Message.objects.filter(
        language__in=('zh_CN', 'zh_TW'), pg_major__range=(14, 19))
        .values('id', *IDENTITY_FIELDS, *CONTENT)}
    rows, catalogs, seen = [], [], set()
    for language in ('zh_CN', 'zh_TW'):
        for major in range(14, 20):
            branch = 'master' if major == 19 else 'REL_{}_STABLE'.format(major)
            paths = sorted((root / language / branch).glob('*.po'))
            if not paths:
                raise ValueError('Missing PO catalogs: {} PG{}'.format(language, major))
            for path in paths:
                po = poio.read_po(path)
                if po.metadata.get('Language') != language:
                    raise ValueError('PO Language header mismatch: ' + str(path))
                source = {'path': str(path.relative_to(root)), 'sha256': po.sha256}
                catalogs.append(dict(source, messages=len(po.active)))
                for entry in po.active:
                    key = (language, major, path.stem, entry.msgctxt,
                           entry.msgid, entry.msgid_plural or '')
                    if key in seen or key not in existing:
                        raise ValueError('Duplicate or unimported source message: ' + str(key))
                    if 'fuzzy' in entry.flags:
                        raise ValueError('Authoritative PO contains a fuzzy translation: ' + str(key))
                    seen.add(key)
                    current = existing[key]
                    forms = {'' if k is None else str(k): text for k, text in entry.translations.items()}
                    rows.append({'id': current['id'], **dict(zip(IDENTITY_FIELDS, key)),
                                 'expected': digest({k: current[k] for k in CONTENT}),
                                 'desired': {'forms': forms, 'plural_forms': po.metadata.get('Plural-Forms', ''),
                                             'flags': list(entry.flags)}, 'source': source})
    if seen != set(existing):
        raise ValueError('PO set omits {} existing messages; refusing a partial snapshot'.format(len(set(existing) - seen)))
    snapshot = {'schema': SCHEMA, 'exported_at': datetime.now(timezone.utc).isoformat(),
                'source_root': str(root), 'catalogs': catalogs, 'sha256': digest(rows), 'messages': rows}
    opener = gzip.open if str(output).endswith('.gz') else open
    with opener(output, 'xt', encoding='utf-8') as stream:
        json.dump(snapshot, stream, ensure_ascii=False, separators=(',', ':'))
    return {'messages': len(rows), 'catalogs': len(catalogs), 'sha256': snapshot['sha256']}


def same_translation(before, after):
    """Dropping obsolete plural slots keeps approval only for unchanged retained forms."""
    return all(key in before and before[key] == text for key, text in after.items())


@transaction.atomic
def apply(snapshot, *, write=False, report_path=None):
    """Content preconditions permit different local/production audit histories."""
    incoming = {row['id']: row for row in snapshot['messages']}
    query = Message.objects.filter(pk__in=incoming)
    if write:
        query = query.select_for_update()
    fields = ('id', *IDENTITY_FIELDS, *CONTENT, 'status', 'version', 'history',
              'note', 'source_revision', 'revision', 'updated_at', 'updated_by_id')
    existing = {row.id: row for row in query.only(*fields)}
    if set(existing) != set(incoming):
        raise ValueError('Snapshot IDs do not all exist in this database')
    changed, details, counts = [], [], Counter()
    when = datetime.now(timezone.utc).isoformat()
    for mid, row in incoming.items():
        message = existing[mid]
        if identity({key: getattr(message, key) for key in IDENTITY_FIELDS}) != identity(row):
            raise ValueError('Message identity changed: ' + mid)
        before = {key: getattr(message, key) for key in CONTENT}
        desired = row['desired']
        if before == desired:
            counts['unchanged'] += 1
            continue
        if digest(before) != row['expected']:
            raise ValueError('Current translation or PO metadata changed after export: ' + mid)
        modified = [key for key in CONTENT if before[key] != desired[key]]
        preserved = same_translation(before['forms'], desired['forms'])
        counts.update(modified)
        saved_state = {key: getattr(message, key) for key in
                       ('status', 'version', 'note', 'source_revision', 'revision', 'updated_by_id')}
        saved_state['updated_at'] = message.updated_at.isoformat() if message.updated_at else None
        event = {'operation': 'authoritative_po_sync', 'recorded_at': when,
                 'authority': 'pgnls PO', 'snapshot_sha256': snapshot['sha256'], 'source': row['source'],
                 'before': dict(before, **saved_state),
                 'after': dict(desired, status=message.status if preserved else 'pending',
                               version=message.version + 1),
                 'approval_preserved': preserved, 'version': message.version + 1}
        # Preserve the complete existing audit trail and last human reviewer/time.
        message.history = [*message.history, event]
        message.version += 1
        for key, value in desired.items():
            setattr(message, key, value)
        if not preserved:
            message.status = 'pending'
            counts['review_required'] += 1
        changed.append(message)
        details.append({'id': mid, 'language': row['language'], 'pg_major': row['pg_major'],
                        'component': row['component'], 'msgid': row['msgid'], 'fields': modified,
                        'before': before, 'after': desired, 'approval_preserved': preserved})
    if write:
        for offset in range(0, len(changed), 200):
            Message.objects.bulk_update(changed[offset:offset + 200], (*CONTENT, 'status', 'version', 'history'), batch_size=200)
    result = {'messages': len(incoming), 'changed': len(changed), 'counts': dict(counts),
              'sha256': snapshot['sha256'], 'written': write}
    if report_path:
        Path(report_path).write_text(json.dumps(dict(result, changes=details), ensure_ascii=False, indent=2) + '\n')
    return result
