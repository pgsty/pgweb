"""Load a pgnls message bundle (JSON lines, optionally gzip) into nls_message.

Source fields are always refreshed; the human state is only written when the
local row has never been saved by a reviewer, so re-importing a newer
calibration never overwrites review work done on the site."""

import gzip
import json

from django.db import transaction

from .models import Message

SCHEMA = 'pgnls-message-bundle-v1'
SOURCE_FIELDS = ('number', 'component', 'msgid', 'msgid_plural', 'msgctxt', 'flags', 'plural_forms',
                 'original_forms', 'suggested_forms', 'suggestion_source', 'calibration', 'old_assessment',
                 'assessment_reason', 'context', 'plural_issue', 'revision', 'workbook_sha256', 'pg_major')


class BundleError(ValueError):
    pass


def read(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        header = None
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if header is None:
                if row.get('kind') != 'header' or row.get('schema') != SCHEMA:
                    raise BundleError('Not a pgnls message bundle: ' + str(path))
                header = row
                continue
            yield header, row


def source_values(row, header):
    values = {k: row.get(k) for k in SOURCE_FIELDS}
    values['msgid_plural'] = values['msgid_plural'] or ''
    values['flags'] = values['flags'] or []
    values['plural_forms'] = values['plural_forms'] or ''
    values['plural_issue'] = values['plural_issue'] or ''
    values['workbook_sha256'] = values['workbook_sha256'] or header.get('workbook_sha256', '')
    for key in ('original_forms', 'suggested_forms', 'calibration', 'context'):
        values[key] = values[key] or {}
    for key in ('suggestion_source', 'assessment_reason'):
        values[key] = values[key] or ''
    values['old_assessment'] = values['old_assessment'] or 'unreviewed'
    # Bundles from the multi-version runs carry their PostgreSQL major; the original v19 bundles predate it.
    values['pg_major'] = values.pop('pg_major', None) or header.get('pg_major') or 19
    if values['msgid'] is None or not values['component'] or not values['revision']:
        raise BundleError('Row {} lacks component, msgid or revision.'.format(row.get('id')))
    return values


def human_values(row):
    human = row.get('human') or {}
    version = int(human.get('version') or 0)
    # A row nobody has reviewed follows the recommendation; only reviewer edits carry their own text.
    forms = (human.get('forms') if version else None) or row.get('suggested_forms') or {}
    values = {'status': human.get('status') or 'pending', 'forms': forms, 'note': human.get('note') or '',
              'version': version, 'source_revision': human.get('source_revision') or row.get('revision') if version else ''}
    if version and human.get('updated_at'):
        from datetime import datetime
        try:
            values['updated_at'] = datetime.fromisoformat(human['updated_at']).replace(tzinfo=None)
        except ValueError:
            pass
    return values, human.get('reviewer') or ''


@transaction.atomic
def load(path, check=False):
    """Returns {'new', 'updated', 'kept', 'total'}; `kept` rows had local review state that was preserved."""
    report = {'new': 0, 'updated': 0, 'kept': 0, 'total': 0}
    existing = {m.id: m for m in Message.objects.all()}
    reviewers = {}
    for header, row in read(path):
        report['total'] += 1
        source = source_values(row, header)
        human, reviewer = human_values(row)
        message = existing.get(row['id'])
        if message is None:
            message = Message(id=row['id'], **source, **human)
            if human['version']:
                message.history = [{'version': human['version'], 'status': human['status'], 'forms': human['forms'],
                                    'note': human['note'], 'reviewer': reviewer, 'updated_at': row['human'].get('updated_at')}]
            report['new'] += 1
        else:
            for key, value in source.items():
                setattr(message, key, value)
            if message.version == 0:
                for key, value in human.items():
                    setattr(message, key, value)
                report['updated'] += 1
            else:
                report['kept'] += 1
        if reviewer and message.version and message.updated_by_id is None:
            reviewers[message.id] = reviewer
        if not check:
            message.save()
    if not check and reviewers:
        from django.contrib.auth.models import User
        users = {u.username: u for u in User.objects.filter(username__in=set(reviewers.values()))}
        for mid, name in reviewers.items():
            if name in users:
                Message.objects.filter(pk=mid).update(updated_by=users[name])
    if check:
        transaction.set_rollback(True)
    return report
