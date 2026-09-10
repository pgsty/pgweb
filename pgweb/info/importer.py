"""Batch files (tools/info/CURATION.md) to rows, idempotent by key."""

import hashlib
import json
import os
import re
from datetime import date, datetime

from django.db import transaction

from .models import DOMAINS, InfoItem
from .search import vector

# Fields copied verbatim from the batch file into the row.
CONTENT_FIELDS = ('date', 'tier', 'position', 'title', 'summary', 'url', 'author',
                  'source', 'source_date', 'image', 'domain', 'tags', 'origin')
SUMMARY_MIN, SUMMARY_MAX = 80, 300
TITLE_MAX, BRIEF_MAX = 40, 80
DATE_NAME = re.compile(r'^(\d{4}-\d{2}-\d{2})$')


class BatchError(Exception):
    """A batch file that must be fixed before it can be imported."""


def item_key(day, url, title):
    seed = '{}|{}'.format(day, url or title)
    return hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]


def parse_date(value, label):
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise BatchError('{}：日期格式必须是 YYYY-MM-DD，实际为 {!r}'.format(label, value))


def text(value):
    return '' if value is None else str(value).strip()


def load(path):
    """Read and validate one batch file; returns (date, origin, [row, ...])."""
    name = os.path.basename(path)
    stem = name[:-5] if name.endswith('.json') else name
    try:
        with open(path, encoding='utf-8') as stream:
            payload = json.load(stream)
    except FileNotFoundError:
        raise BatchError('{}：文件不存在'.format(name))
    except json.JSONDecodeError as exc:
        raise BatchError('{}：JSON 无法解析（{}）'.format(name, exc))
    if not isinstance(payload, dict):
        raise BatchError('{}：顶层必须是对象'.format(name))
    day = parse_date(payload.get('date'), name)
    if DATE_NAME.match(stem) and stem != day.isoformat():
        raise BatchError('{}：文件名与 date 字段（{}）不一致'.format(name, day.isoformat()))
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        raise BatchError('{}：items 必须是非空数组'.format(name))
    origin = {'file': name, 'origin': text(payload.get('origin'))}
    rows, seen, last_tier = [], {}, 0
    for index, raw in enumerate(items, start=1):
        rows.append(row(raw, index, day, origin, name, seen, last_tier))
        last_tier = rows[-1]['tier']
    return day, origin, rows


def row(raw, index, day, origin, name, seen, last_tier):
    label = '{} 第 {} 条'.format(name, index)
    if not isinstance(raw, dict):
        raise BatchError('{}：条目必须是对象'.format(label))
    try:
        tier = int(raw.get('tier'))
    except (TypeError, ValueError):
        raise BatchError('{}：tier 必须是 1 / 2 / 3'.format(label))
    if tier not in (1, 2, 3):
        raise BatchError('{}：tier 必须是 1 / 2 / 3，实际为 {}'.format(label, tier))
    if tier < last_tier:
        raise BatchError('{}：档位必须按 1 → 2 → 3 排列，{} 档出现在 {} 档之后'.format(label, tier, last_tier))
    try:
        position = int(raw.get('position', index))
    except (TypeError, ValueError):
        raise BatchError('{}：position 必须是整数'.format(label))
    if position != index:
        raise BatchError('{}：position 必须从 1 开始连续编号，实际为 {}'.format(label, position))
    title = text(raw.get('title'))
    if not title:
        raise BatchError('{}：title 必填'.format(label))
    if len(title) > TITLE_MAX:
        raise BatchError('{}：标题最多 {} 字，实际 {} 字'.format(label, TITLE_MAX, len(title)))
    url = text(raw.get('url'))
    if tier in (1, 2) and not url:
        raise BatchError('{}：一、二档必须有 url'.format(label))
    summary = text(raw.get('summary'))
    author, source = text(raw.get('author')), text(raw.get('source'))
    if tier == 1:
        if not author:
            raise BatchError('{}：一档必须有 author'.format(label))
        if not source:
            raise BatchError('{}：一档必须有 source'.format(label))
        if not SUMMARY_MIN <= len(summary) <= SUMMARY_MAX:
            raise BatchError('{}：一档摘要需要 {}–{} 字，实际 {} 字'.format(
                label, SUMMARY_MIN, SUMMARY_MAX, len(summary)))
    elif tier == 2 and len(summary) > BRIEF_MAX:
        raise BatchError('{}：二档说明最多 {} 字，实际 {} 字'.format(label, BRIEF_MAX, len(summary)))
    image = text(raw.get('image'))
    if image and not image.startswith('https://'):
        raise BatchError('{}：image 必须是 https 地址'.format(label))
    domain = text(raw.get('domain')) or 'pg'
    if domain not in DOMAINS:
        raise BatchError('{}：domain 必须是 {} 之一，实际为 {!r}'.format(label, ' / '.join(DOMAINS), domain))
    tags = raw.get('tags') or []
    if not isinstance(tags, list) or any(not text(tag) for tag in tags):
        raise BatchError('{}：tags 必须是非空短词数组'.format(label))
    source_date = parse_date(raw.get('source_date'), label) if text(raw.get('source_date')) else None
    key = item_key(day.isoformat(), url, title)
    if key in seen:
        raise BatchError('{}：与第 {} 条重复（同一天同一链接）'.format(label, seen[key]))
    seen[key] = index
    return {
        'key': key, 'date': day, 'tier': tier, 'position': position, 'title': title,
        'summary': summary, 'url': url, 'author': author, 'source': source,
        'source_date': source_date, 'image': image, 'domain': domain,
        'tags': [text(tag) for tag in tags], 'origin': origin,
    }


def upsert(rows, day, hide_missing=False):
    """Write one day's rows and their vectors in a single transaction."""
    report = {'new': 0, 'updated': 0, 'unchanged': 0, 'hidden': 0}
    existing = {item.key: item for item in InfoItem.objects.filter(key__in=[r['key'] for r in rows])}
    with transaction.atomic():
        for values in rows:
            item = existing.get(values['key'])
            if item is None:
                item = InfoItem(**values)
                item.save()
                report['new'] += 1
            else:
                changed = (any(getattr(item, f) != values[f] for f in CONTENT_FIELDS) or
                           item.status != 'published')
                if not changed:
                    report['unchanged'] += 1
                    continue
                for field, value in values.items():
                    setattr(item, field, value)
                item.status = 'published'
                item.save()
                report['updated'] += 1
            InfoItem.objects.filter(pk=item.pk).update(search_vector=vector(item))
        if hide_missing:
            report['hidden'] = (InfoItem.objects.filter(date=day, status='published')
                                .exclude(key__in=[r['key'] for r in rows]).update(status='hidden'))
    return report


def preview(rows):
    """What upsert would report, without writing anything."""
    report = {'new': 0, 'updated': 0, 'unchanged': 0, 'hidden': 0}
    existing = {item.key: item for item in InfoItem.objects.filter(key__in=[r['key'] for r in rows])}
    for values in rows:
        item = existing.get(values['key'])
        if item is None:
            report['new'] += 1
        elif any(getattr(item, f) != values[f] for f in CONTENT_FIELDS) or item.status != 'published':
            report['updated'] += 1
        else:
            report['unchanged'] += 1
    return report


def reindex(queryset=None):
    """Recompute every search_vector from the stored text."""
    rows = InfoItem.objects.all() if queryset is None else queryset
    count = 0
    with transaction.atomic():
        for item in rows.iterator(chunk_size=200):
            InfoItem.objects.filter(pk=item.pk).update(search_vector=vector(item))
            count += 1
    return count
