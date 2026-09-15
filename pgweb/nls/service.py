"""Read models and apply review decisions. Every write is one transaction with an
optimistic version check, so two reviewers can never silently overwrite each other."""

import difflib
import json
from collections import Counter
from datetime import datetime

from django.db import connection, transaction
from django.db.models import Count, Max, Q

from .models import HISTORY_LIMIT, Message, STATUSES
from .validate import MAX_NOTE, ValidationError, check_approval, check_forms

STATUS_KEYS = tuple(key for key, _label in STATUSES)
# The pseudo component: every message at once, for cross-component search and consistent wording.
ALL = '*'
PERMISSION = 'nls.review'
LOGIN_URL = '/account/login/?next=/nls/'
DEFAULT_MAJOR = 19


def majors():
    """Imported PostgreSQL major versions, newest first."""
    rows = Message.objects.order_by('-pg_major').values_list('pg_major', flat=True).distinct()
    return [DEFAULT_MAJOR] + [m for m in rows if m != DEFAULT_MAJOR]


def checked_major(value):
    try:
        major = int(value or DEFAULT_MAJOR)
    except (TypeError, ValueError):
        raise ValidationError('未知 PostgreSQL 大版本。')
    if major not in majors():
        raise ValidationError('该 PostgreSQL 大版本尚未导入。')
    return major
TABLE_FIELDS = ('id', 'number', 'component', 'msgid', 'msgid_plural', 'original_forms', 'suggested_forms',
                'calibration', 'old_assessment', 'assessment_reason', 'plural_issue', 'revision',
                'status', 'forms', 'note', 'source_revision', 'version', 'updated_at', 'updated_by__username')


def can_edit(user):
    return bool(user and user.is_authenticated and user.has_perm(PERMISSION))


def user_info(user):
    return {'authenticated': bool(user and user.is_authenticated),
            'name': user.get_username() if user and user.is_authenticated else '',
            'can_edit': can_edit(user), 'login_url': LOGIN_URL}


def now():
    return datetime.now()


def isoformat(value):
    return value.isoformat(sep=' ', timespec='seconds') if value else None


def display_status(row):
    stale = row['status'] != 'pending' and row['version'] > 0 and row['source_revision'] != row['revision']
    return 'stale' if stale else row['status']


def component_stats(major=DEFAULT_MAJOR):
    """[{name, total, approved, pending, flagged, rejected}] in name order, so the page opens on a small component."""
    rows = Message.objects.filter(pg_major=major).values('component', 'status').annotate(n=Count('id'))
    stats = {}
    for row in rows:
        entry = stats.setdefault(row['component'], {'name': row['component'], 'total': 0, 'approved': 0,
                                                    'pending': 0, 'flagged': 0, 'rejected': 0})
        entry[row['status']] += row['n']
        entry['total'] += row['n']
    return sorted(stats.values(), key=lambda c: c['name'])


def bootstrap(user, major=DEFAULT_MAJOR):
    components = component_stats(major)
    counts = Counter()
    for c in components:
        for key in STATUS_KEYS:
            counts[key] += c[key]
    last = Message.objects.filter(pg_major=major).aggregate(last=Max('updated_at'))['last']
    forms = sum(len(f) for f in Message.objects.filter(pg_major=major).values_list('suggested_forms', flat=True)) if components else 0
    return {'total': sum(c['total'] for c in components), 'forms': forms, 'components': components,
            'counts': dict(counts), 'storage': {'kind': 'PostgreSQL', 'table': 'nls_message', 'last_saved': isoformat(last)},
            'major': major, 'majors': majors(), 'user': user_info(user)}


def record(row):
    """The table row the browser renders. Same shape as the pgnls review-app."""
    calibration = {k: v for k, v in (row['calibration'] or {}).items() if k != 'previous_forms'}
    return {'id': row['id'], 'number': row['number'], 'component': row['component'], 'english': row['msgid'],
            'english_plural': row['msgid_plural'], 'original_forms': row['original_forms'],
            'suggested_forms': row['suggested_forms'], 'calibration': calibration,
            'old_assessment': row['old_assessment'], 'assessment_reason': row['assessment_reason'],
            'plural_issue': row['plural_issue'] or None, 'revision': row['revision'],
            'status': display_status(row), 'stored_status': row['status'], 'forms': row['forms'], 'note': row['note'],
            'version': row['version'], 'updated_at': isoformat(row['updated_at']),
            'reviewer': row['updated_by__username'] or ''}


def component_table(name, major=DEFAULT_MAJOR):
    query = Message.objects.filter(pg_major=major)
    if name != ALL:
        query = query.filter(component=name)
    rows = list(query.order_by('component', 'number').values(*TABLE_FIELDS))
    if not rows:
        raise ValidationError('未知组件。')
    return {'component': name, 'major': major, 'records': [record(r) for r in rows], 'total': len(rows)}


def state(message):
    """The saved state the browser applies after a write."""
    return {'id': message.id, 'status': message.display_status, 'stored_status': message.status, 'forms': message.forms, 'note': message.note,
            'version': message.version, 'updated_at': isoformat(message.updated_at), 'reviewer': message.reviewer,
            'source_revision': message.source_revision}


def word_diff(before, after):
    """Word-level segments of `before` marked where they differ from `after`; text is preserved exactly."""
    import re
    a, b = re.findall(r'\s+|\S+', before), re.findall(r'\s+|\S+', after)
    return [{'text': ''.join(a[i:j]), 'changed': op != 'equal'}
            for op, i, j, _k, _l in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if i < j]


def translation_diff(before, after):
    result = []
    for form, value in after.items():
        original = before.get(form, '')
        left, right = [], []
        for op, a, b, c, d in difflib.SequenceMatcher(None, original, value, autojunk=False).get_opcodes():
            if a < b:
                left.append({'text': original[a:b], 'changed': op != 'equal'})
            if c < d:
                right.append({'text': value[c:d], 'changed': op != 'equal'})
        result.append({'form': form, 'before': left, 'after': right, 'changed': original != value})
    return result


def similar(message, limit=12):
    """Nearest messages by trigram distance on the English text (pg_trgm GiST index)."""
    with connection.cursor() as cur:
        cur.execute('''SELECT m.id, m.component, m.msgid, m.msgid_plural, m.forms, m.status, m.version,
                              u.username, similarity(m.msgid, %s) AS similarity
                       FROM nls_message m LEFT JOIN auth_user u ON u.id = m.updated_by_id
                       WHERE m.id <> %s AND m.pg_major = %s
                       ORDER BY m.msgid <-> %s, (m.status = 'approved') DESC, (m.version > 0) DESC, m.id
                       LIMIT 40''', [message.msgid, message.id, message.pg_major, message.msgid])
        rows = cur.fetchall()
    merged = {}
    for mid, component, msgid, plural, forms, status, version, username, score in rows:
        if score < 0.15:
            continue
        # Django's psycopg2 backend leaves jsonb from raw SQL undecoded.
        if isinstance(forms, str):
            forms = json.loads(forms)
        kind = 'approved' if status == 'approved' else 'human' if version > 0 else 'candidate'
        for form, text in (forms or {}).items():
            if not text:
                continue
            key = (msgid, plural, form, text)
            source = {'component': component, 'state': kind, 'reviewer': username or ''}
            if key in merged:
                if source not in merged[key]['sources']:
                    merged[key]['sources'].append(source)
                continue
            merged[key] = {'id': mid, 'english': msgid, 'english_plural': plural, 'form': form, 'translation': text,
                           'similarity': float(score), 'kind': kind, 'exact': msgid == message.msgid,
                           'same_component': component == message.component, 'sources': [source],
                           'diff': word_diff(msgid, message.msgid)}
    ranked = sorted(merged.values(), key=lambda r: (-r['similarity'], r['kind'] != 'approved', not r['same_component'], r['id']))
    return ranked[:limit]


def references(message):
    calibration = message.calibration or {}
    return {'id': message.id, 'engine': 'PostgreSQL pg_trgm', 'references': similar(message),
            'context': message.context or {},
            'previous_diff': translation_diff(calibration.get('previous_forms', message.suggested_forms), message.suggested_forms)}


def _prepare(message, decision, user, submit=False):
    """Validate one decision against the locked row and return the fields to write."""
    if decision.get('expected_version') != message.version:
        raise ValidationError('此条记录已被他人修改，请重新载入组件后再决定。')
    status = 'approved' if submit else decision.get('status', 'pending')
    if status not in STATUS_KEYS:
        raise ValidationError('无效的状态。')
    forms = decision['forms'] if 'forms' in decision else message.forms
    note = decision['note'] if 'note' in decision else message.note
    check_forms(message, forms)
    if not isinstance(note, str) or len(note) > MAX_NOTE:
        raise ValidationError('备注不是文本或长度超限。')
    if status == 'approved':
        check_approval(message, forms)
    return {'status': status, 'forms': forms, 'note': note}


def _apply(message, fields, user, when):
    message.status, message.forms, message.note = fields['status'], fields['forms'], fields['note']
    message.version += 1
    message.source_revision = message.revision
    message.updated_by = user
    message.updated_at = when
    entry = {'version': message.version, 'status': message.status, 'forms': message.forms, 'note': message.note,
             'reviewer': user.get_username(), 'updated_at': isoformat(when)}
    message.history = (message.history or [])[-(HISTORY_LIMIT - 1):] + [entry]
    message.save(update_fields=['status', 'forms', 'note', 'version', 'source_revision', 'updated_by', 'updated_at', 'history'])
    return message


@transaction.atomic
def decide(decision, user):
    """Save one message; returns its new state."""
    try:
        message = Message.objects.select_for_update().get(pk=decision.get('id'))
    except Message.DoesNotExist:
        raise ValidationError('未知消息。')
    fields = _prepare(message, decision, user)
    return state(_apply(message, fields, user, now()))


@transaction.atomic
def decide_many(component, decisions, user, submit=False, major=DEFAULT_MAJOR):
    """Save a batch for one component atomically. Submitting approves every message of the component."""
    if not isinstance(decisions, list) or not decisions:
        raise ValidationError('没有要保存的记录。')
    ids = [d.get('id') for d in decisions if isinstance(d, dict)]
    if len(ids) != len(decisions) or len(set(ids)) != len(ids):
        raise ValidationError('包含重复或无效的记录。')
    if component == ALL:
        if submit:
            raise ValidationError('提交组件必须选择具体组件，「全部组件」下只能保存。')
        messages = {m.id: m for m in Message.objects.select_for_update().filter(id__in=ids)}
    else:
        messages = {m.id: m for m in Message.objects.select_for_update().filter(
            pg_major=major, component=component, id__in=ids)}
    if set(messages) != set(ids):
        raise ValidationError('包含未知或不属于该组件的消息。')
    if submit and Message.objects.filter(pg_major=major, component=component).exclude(id__in=ids).exists():
        raise ValidationError('提交组件必须包含该组件的全部消息。')
    prepared, errors = [], []
    for d in decisions:
        message = messages[d['id']]
        try:
            prepared.append((message, _prepare(message, d, user, submit)))
        except ValidationError as exc:
            errors.append(message.msgid[:100] + ': ' + str(exc))
    if errors:
        raise ValidationError('未保存任何记录，请先修正以下条目：\n' + '\n'.join(errors[:12]))
    when = now()
    return {'results': [state(_apply(m, fields, user, when)) for m, fields in prepared]}


def export(major=DEFAULT_MAJOR):
    """pgnls-human-review-v1: what the pgnls review-app imports and the PO writer consumes."""
    saved = {}
    rows = Message.objects.filter(pg_major=major, version__gt=0).values(
        'id', 'status', 'forms', 'note', 'source_revision', 'version', 'updated_at', 'updated_by__username')
    for r in rows:
        saved[r['id']] = {'status': r['status'], 'forms': r['forms'], 'note': r['note'],
                          'source_revision': r['source_revision'], 'version': r['version'],
                          'updated_at': isoformat(r['updated_at'])}
        if r['updated_by__username']:
            saved[r['id']]['reviewer'] = r['updated_by__username']
    sha = (Message.objects.filter(pg_major=major).exclude(workbook_sha256='')
           .values_list('workbook_sha256', flat=True).first() or '')
    return {'schema': 'pgnls-human-review-v1', 'pg_major': major, 'workbook_sha256': sha,
            'exported_at': isoformat(now()), 'source': 'pgsql.cc /nls/', 'saved_state': saved}
