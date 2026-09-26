"""Validate a fixed snapshot and its local WebP avatars, then import atomically."""

import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import warnings

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive
from PIL import Image

from .models import HackerProfile


SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 4096 * 4096
PROFILE_FIELDS = {'source_id', 'slug', 'name', 'organization', 'country', 'bio',
                  'source_url', 'data', 'avatar'}
CONTENT_FIELDS = ('source_id', 'name', 'organization', 'country', 'bio', 'data',
                  'avatar_content_type', 'avatar_sha256')


class SnapshotError(ValueError):
    """An incomplete or invalid snapshot; no rows should be written."""


def _text(record, key, label, maximum=None, required=False):
    value = record.get(key, '')
    if value is None and not required:
        value = ''
    if not isinstance(value, str) or (required and not value.strip()):
        raise SnapshotError('{}: {} must be {}text'.format(label, key, 'nonempty ' if required else ''))
    if maximum and len(value) > maximum:
        raise SnapshotError('{}: {} exceeds {} characters'.format(label, key, maximum))
    return value


def _avatar(record, base, label):
    if record is None:
        return {'avatar': None, 'avatar_content_type': '', 'avatar_sha256': ''}
    if not isinstance(record, dict):
        raise SnapshotError('{}: avatar must be an object or null'.format(label))
    name = _text(record, 'path', label, required=True)
    digest = _text(record, 'sha256', label, required=True)
    if not SHA256.fullmatch(digest) or record.get('content_type') != 'image/webp':
        raise SnapshotError('{}: avatar needs a SHA-256 digest and image/webp content type'.format(label))
    relative = Path(name)
    path = (base / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(base):
        raise SnapshotError('{}: avatar path must stay inside the snapshot directory'.format(label))
    try:
        if path.stat().st_size > MAX_AVATAR_BYTES:
            raise SnapshotError('{}: avatar exceeds 2 MiB'.format(label))
        body = path.read_bytes()
    except OSError as exc:
        raise SnapshotError('{}: cannot read avatar {}'.format(label, name)) from exc
    if hashlib.sha256(body).hexdigest() != digest:
        raise SnapshotError('{}: avatar SHA-256 mismatch'.format(label))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(body)) as image:
                if (image.format != 'WEBP' or max(image.size) > 4096 or
                        image.width * image.height > MAX_AVATAR_PIXELS or image.n_frames != 1):
                    raise SnapshotError('{}: avatar must be a WebP image of at most 4096 × 4096 pixels'.format(label))
                image.verify()
            with Image.open(io.BytesIO(body)) as image:
                image.load()
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        if isinstance(exc, SnapshotError):
            raise
        raise SnapshotError('{}: avatar is not a valid WebP image'.format(label)) from exc
    return {'avatar': body, 'avatar_content_type': 'image/webp', 'avatar_sha256': digest}


def _hash(row):
    content = {key: row[key] for key in CONTENT_FIELDS}
    # The snapshot location, collection time and size are provenance, not a change to this person.
    provenance = {'snapshot', 'official_sources', 'avatar_errors', 'avatar'}
    content['data'] = {key: value for key, value in row['data'].items() if key not in provenance}
    raw = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def load(path):
    """Read and validate the whole batch, including every avatar, before any DB access."""
    path = Path(path).resolve()
    try:
        body = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
        payload = json.loads(body.decode('utf-8'), parse_constant=lambda value: _invalid_number(value))
    except (OSError, EOFError, UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotError('{}: cannot read a valid JSON snapshot: {}'.format(path.name, exc)) from exc
    if not isinstance(payload, dict) or type(payload.get('format')) is not int or payload['format'] != 1:
        raise SnapshotError('Snapshot format must be 1')
    try:
        fetched_at = parse_datetime(payload.get('fetched_at', ''))
    except (TypeError, ValueError):
        fetched_at = None
    if fetched_at is None or is_naive(fetched_at):
        raise SnapshotError('fetched_at must be an ISO 8601 timestamp with a timezone')
    profiles = payload.get('profiles')
    if not isinstance(profiles, list) or not profiles:
        raise SnapshotError('profiles must be a nonempty array')
    if type(payload.get('expected_count')) is not int or payload['expected_count'] != len(profiles):
        raise SnapshotError('expected_count must match the full profiles array')
    snapshot = {key: value for key, value in payload.items() if key not in ('profiles', 'fetched_at')}
    rows, source_ids, slugs = [], set(), set()
    for index, profile in enumerate(profiles, start=1):
        label = 'Profile {}'.format(index)
        if not isinstance(profile, dict):
            raise SnapshotError('{} must be an object'.format(label))
        row = {
            'source_id': _text(profile, 'source_id', label, 64, required=True),
            'slug': _text(profile, 'slug', label, 160, required=True),
            'name': _text(profile, 'name', label, 250, required=True),
            'organization': _text(profile, 'organization', label, 250),
            'country': _text(profile, 'country', label, 100),
            'bio': _text(profile, 'bio', label),
            'source_fetched_at': fetched_at,
        }
        if not SLUG.fullmatch(row['slug']):
            raise SnapshotError('{}: slug must use lowercase ASCII words and hyphens'.format(label))
        if row['source_id'] in source_ids or row['slug'] in slugs:
            raise SnapshotError('{}: duplicate source_id or slug'.format(label))
        source_ids.add(row['source_id'])
        slugs.add(row['slug'])
        data = profile.get('data', {})
        if not isinstance(data, dict):
            raise SnapshotError('{}: data must be an object'.format(label))
        row['data'] = copy.deepcopy(data)
        # Preserve unrecognized fields so source additions never disappear at ingestion.
        extra = {key: value for key, value in profile.items() if key not in PROFILE_FIELDS}
        if extra:
            if 'extra' in row['data']:
                raise SnapshotError('{}: extra fields conflict with data.extra'.format(label))
            row['data']['extra'] = extra
        if 'source_url' in profile:
            source_url = _text(profile, 'source_url', label)
            if 'source_url' in row['data'] and row['data']['source_url'] != source_url:
                raise SnapshotError('{}: source_url conflicts with data.source_url'.format(label))
            row['data']['source_url'] = source_url
        if 'snapshot' in row['data']:
            raise SnapshotError('{}: data.snapshot is reserved for snapshot provenance'.format(label))
        row['data']['snapshot'] = copy.deepcopy(snapshot)
        if 'avatar' in row['data']:
            raise SnapshotError('{}: data.avatar is reserved for avatar provenance'.format(label))
        row['data']['avatar'] = copy.deepcopy(profile.get('avatar'))
        row.update(_avatar(profile.get('avatar'), path.parent, label))
        row['content_hash'] = _hash(row)
        rows.append(row)
    return rows


def _invalid_number(value):
    raise SnapshotError('Invalid JSON number: {}'.format(value))


def _existing(rows, lock=False):
    # Reject slug conflicts before the first write, including with records outside this snapshot.
    queryset = HackerProfile.objects.filter(source_id__in=[row['source_id'] for row in rows])
    if lock:
        queryset = queryset.select_for_update()
    existing = {item.source_id: item for item in queryset}
    owners = dict(HackerProfile.objects.filter(slug__in=[row['slug'] for row in rows])
                  .values_list('slug', 'source_id'))
    for row in rows:
        if row['source_id'] not in existing and owners.get(row['slug'], row['source_id']) != row['source_id']:
            raise SnapshotError('Slug {} already belongs to another source_id'.format(row['slug']))
    return existing


def _retain_avatar(row, item):
    """A failed refresh of the same remote image must not erase a good local copy."""
    if (item is None or row['avatar'] is not None or not item.avatar_sha256 or
            not row['data'].get('avatar_errors')):
        return row
    source_urls = row['data'].get('avatar_sources')
    if not source_urls or source_urls != item.data.get('avatar_sources'):
        return row
    row = dict(row)
    for key in ('avatar', 'avatar_content_type', 'avatar_sha256'):
        row[key] = getattr(item, key)
    row['data'] = copy.deepcopy(row['data'])
    row['data']['avatar'] = item.data.get('avatar')
    row['content_hash'] = _hash(row)
    return row


def preview(rows):
    existing = _existing(rows)
    report = {'new': 0, 'updated': 0, 'unchanged': 0}
    for row in rows:
        item = existing.get(row['source_id'])
        row = _retain_avatar(row, item)
        report['new' if item is None else 'unchanged' if item.content_hash == row['content_hash'] else 'updated'] += 1
    return report


def upsert(rows):
    """Keep existing URLs stable; an absent person is never implicitly deleted."""
    report = {'new': 0, 'updated': 0, 'unchanged': 0}
    with transaction.atomic():
        existing = _existing(rows, lock=True)
        for row in rows:
            item = existing.get(row['source_id'])
            row = _retain_avatar(row, item)
            if item is None:
                HackerProfile.objects.create(**row)
                report['new'] += 1
            elif item.content_hash == row['content_hash']:
                report['unchanged'] += 1
            else:
                for key, value in row.items():
                    if key != 'slug':
                        setattr(item, key, value)
                item.save()
                report['updated'] += 1
    return report
