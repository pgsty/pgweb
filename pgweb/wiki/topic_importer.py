"""Validate and import the four fixed reference snapshots without touching manuals."""

from copy import deepcopy
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from django.db import transaction

from . import topics


def text(value, label, required=False):
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError('{} must be {}text'.format(label, 'nonempty ' if required else ''))
    return value


def strings(value, label, required=False):
    if not isinstance(value, list) or (required and not value):
        raise ValueError('{} must be a list'.format(label))
    for item in value:
        text(item, label, required=True)


def links(value, label, required=False):
    if not isinstance(value, list) or (required and not value):
        raise ValueError('{} must contain links'.format(label))
    for link in value:
        if not isinstance(link, dict):
            raise ValueError('Invalid link')
        text(link.get('label'), label, required=True)
        url = text(link.get('url'), label, required=True)
        parsed = urlsplit(url)
        if not ((url.startswith(('/docs/', '/wiki/')) and not parsed.netloc) or
                (parsed.scheme == 'https' and parsed.hostname and not parsed.username)):
            raise ValueError('Unsafe or unsupported source URL: ' + url)


def prepare(data):
    if not isinstance(data, dict) or data.get('format') != 1 or data.get('kind') not in topics.TOPICS:
        raise ValueError('Expected a format=1 reference snapshot with a known kind')
    kind = data['kind']
    releases = data.get('releases')
    if not isinstance(releases, list) or not releases:
        raise ValueError('Missing sampled releases')
    release_map = {}
    for release in releases:
        if not isinstance(release, dict):
            raise ValueError('Invalid sampled release')
        major = release.get('major')
        if not isinstance(major, str) or not re.fullmatch(r'\d{1,2}', major) or major in release_map:
            raise ValueError('Invalid or duplicate major version')
        for key in ('label', 'revision', 'ref', 'channel'):
            text(release.get(key), 'release.' + key, required=True)
        release_map[major] = release
    items = data.get('items')
    if not isinstance(items, list) or not items:
        raise ValueError('Refusing an empty reference snapshot')
    result, slugs, observed = [], set(), set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Invalid reference entity')
        row = {key: deepcopy(item.get(key)) for key in
               ('slug', 'name', 'name_zh', 'category', 'summary', 'aliases', 'versions')}
        slug = row['slug']
        if not isinstance(slug, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,95}', slug) or slug in slugs:
            raise ValueError('Invalid or duplicate slug: ' + str(slug))
        slugs.add(slug)
        for field in ('name', 'name_zh', 'category', 'summary'):
            text(row[field], slug + '.' + field, required=True)
        strings(row['aliases'], slug + '.aliases')
        if not isinstance(row['versions'], dict) or not row['versions']:
            raise ValueError('Missing version snapshots for ' + slug)
        for major, snapshot in row['versions'].items():
            if major not in release_map or not isinstance(snapshot, dict):
                raise ValueError('Unknown release in ' + slug)
            observed.add(major)
            strings(snapshot.get('description'), slug + '.description', required=True)
            text(snapshot.get('signature', ''), slug + '.signature')
            facts = snapshot.get('facts', [])
            if not isinstance(facts, list):
                raise ValueError('Invalid facts')
            for fact in facts:
                if not isinstance(fact, dict):
                    raise ValueError('Invalid fact')
                text(fact.get('label'), slug + '.fact.label', required=True)
                text(fact.get('value'), slug + '.fact.value', required=True)
            sections = snapshot.get('sections', [])
            if not isinstance(sections, list):
                raise ValueError('Invalid sections')
            for section in sections:
                if not isinstance(section, dict):
                    raise ValueError('Invalid section')
                text(section.get('title'), slug + '.section', required=True)
                strings(section.get('paragraphs', []), slug + '.paragraphs')
                text(section.get('code', ''), slug + '.code')
                blocks = section.get('blocks', [])
                if not isinstance(blocks, list):
                    raise ValueError('Invalid section blocks')
                for block in blocks:
                    if not isinstance(block, dict):
                        raise ValueError('Invalid section block')
                    strings(block.get('paragraphs', []), slug + '.block.paragraphs')
                    text(block.get('code', ''), slug + '.block.code')
            links(snapshot.get('sources'), slug + '.sources', required=True)
            links(snapshot.get('related', []), slug + '.related')
            snapshot.setdefault('release', deepcopy(release_map[major]))
            if snapshot['release'] != release_map[major]:
                raise ValueError('Mismatched source build in ' + slug)
            for field in ('label', 'revision', 'ref', 'channel'):
                text(snapshot['release'].get(field), slug + '.release.' + field, required=True)
        row['content_hash'] = topics.digest(row)
        result.append(row)
    if observed != set(release_map):
        raise ValueError('A declared release has no sampled entities')
    return kind, result


def load(path):
    return prepare(json.loads(Path(path).read_text(encoding='utf-8')))


def apply(kind, rows, check=False, prune=False):
    model = topics.TOPICS[kind]['model']
    report = dict(kind=kind, total=len(rows), snapshots=sum(len(r['versions']) for r in rows),
                  created=0, updated=0, unchanged=0, removed=0, check=check)
    with transaction.atomic():
        current = dict(model.objects.values_list('slug', 'content_hash'))
        for row in rows:
            slug = row['slug']
            state = ('created' if slug not in current else
                     'unchanged' if current[slug] == row['content_hash'] else 'updated')
            report[state] += 1
            if not check and state != 'unchanged':
                model.objects.update_or_create(slug=slug,
                                               defaults={k: v for k, v in row.items() if k != 'slug'})
        missing = set(current) - {r['slug'] for r in rows}
        if prune:
            report['removed'] = len(missing)
            if not check:
                model.objects.filter(slug__in=missing).delete()
        if not check:
            transaction.on_commit(lambda: topics.forget(kind))
    return report
