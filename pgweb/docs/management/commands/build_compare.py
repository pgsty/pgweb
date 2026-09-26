"""Build and validate the release comparison snapshot from Chinese DocPages."""

from datetime import datetime, timezone
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from pgweb.core.models import Version
from pgweb.docs.compare_data import (
    FORMAT_VERSION, PARSER_VERSION, UNRELEASED_VERSIONS, commit_aliases,
    calibrate_source_entries, enrich_source_commits, parse_release, sgml_commit_entries,
)
from pgweb.docs.models import DocPage


RELEASE_FILE = re.compile(r'^release-(\d+)(?:-(\d+))?\.html$')


def build_snapshot(pgdoc_root=None):
    versions = {int(version.tree): version for version in Version.objects.filter(tree__gte=10)}
    if not versions:
        raise CommandError('No PostgreSQL >= 10 version metadata is loaded')
    devel = Version.objects.filter(tree=0).first()
    documents = {}
    for page in DocPage.objects.filter(file__startswith='release-').exclude(content__isnull=True).iterator():
        match = RELEASE_FILE.fullmatch(page.file)
        if not match or int(match.group(1)) < 10:
            continue
        major, minor = int(match.group(1)), int(match.group(2) or 0)
        version = '{}.{}'.format(major, minor)
        if version in UNRELEASED_VERSIONS:
            continue
        native = int(page.version_id) == major
        dev_page = page.version_id == 0 and major not in versions
        if not native and not dev_page:
            continue
        documents[version] = (page, major, minor, dev_page)
    errors = [
        'Missing version metadata: ' + str(major)
        for major in range(10, max(versions) + 1) if major not in versions
    ]
    for major, metadata in versions.items():
        expected = [0] if metadata.testing else range(metadata.latestminor + 1)
        for minor in expected:
            version = '{}.{}'.format(major, minor)
            if version not in documents and version not in UNRELEASED_VERSIONS:
                errors.append('Missing Chinese release note: ' + version)
    releases = []
    for version, (page, major, minor, dev_page) in sorted(documents.items(), key=lambda row: (row[1][1], row[1][2])):
        metadata = devel if dev_page else versions.get(major)
        if metadata is None:
            errors.append('Missing version metadata: ' + version)
            continue
        status = 'devel' if dev_page else ('preview' if metadata.testing else 'stable')
        if status == 'preview' and minor:
            errors.append('A preview minor is not a published patch: ' + version)
            continue
        release = parse_release(
            page.content, version, 'devel' if dev_page else str(major), status,
            build='{}devel'.format(major) if dev_page else (metadata.versionstring if metadata.testing else version),
            supported=metadata.supported,
        )
        release['manual_build'] = '{}devel'.format(major) if dev_page else metadata.versionstring
        release['eol_date'] = metadata.eoldate.isoformat() if status == 'stable' and getattr(metadata, 'eoldate', None) else ''
        release['doc_loaded_at'] = metadata.docsloaded.isoformat() if metadata.docsloaded else ''
        release['doc_git'] = metadata.docsgit
        if status == 'stable' and (not release['date'] or not release['entries']):
            errors.append('Unreadable stable release (date/entries): ' + version)
        if status != 'devel' and release['placeholder']:
            errors.append('Missing Changes section: ' + version)
        if any(not entry['title'] or not entry['text'] or not entry['html'] for entry in release['entries']):
            errors.append('Empty release entry: ' + version)
        if release['entry_count'] != release['changes_count'] + release['compatibility_count']:
            errors.append('Entry coverage mismatch: ' + version)
        releases.append(release)
    if errors:
        raise CommandError('\n'.join(errors))
    source_records, source_texts, source_entries = [], [], {}
    canonical_records, canonical_texts, canonical_entries = [], [], {}
    if pgdoc_root is not None:
        root = Path(pgdoc_root)
        for major in sorted({release['major'] for release in releases}, key=int):
            relative = Path('zh') / major / ('release-' + major + '.sgml')
            source = root / relative
            if source.is_file():
                body = source.read_bytes()
                source_texts.append(body.decode('utf-8'))
                source_entries.update(sgml_commit_entries(source_texts[-1], major))
                source_records.append({'file': str(relative), 'sha256': hashlib.sha256(body).hexdigest()})
            candidates = list((root / 'en').glob(major + '*/release-' + major + '.sgml'))
            candidates = [candidate for candidate in candidates if re.match(r'^' + major + r'(?:\.|beta|rc|devel|$)', candidate.parent.name)]
            # The exact native manual build is preferred; devel and preview
            # are pinned snapshots, never silently replaced by a nearby major.
            build = next(release['manual_build'] for release in releases if release['major'] == major)
            source = next((candidate for candidate in candidates if candidate.parent.name == build), None)
            if source is None:
                raise CommandError('Missing canonical English SGML for manual build: ' + build)
            body = source.read_bytes()
            canonical_texts.append(body.decode('utf-8'))
            canonical_entries.update(sgml_commit_entries(canonical_texts[-1], major))
            canonical_records.append({'file': str(source.relative_to(root)), 'sha256': hashlib.sha256(body).hexdigest()})
    aliases = commit_aliases(canonical_texts or source_texts)
    source_commit_counts = Counter()
    calibration_counts = Counter()
    for release in releases:
        if source_entries:
            source_commit_counts.update(enrich_source_commits(release, source_entries))
        for entry in release['entries']:
            commits = entry['commits'] or entry.get('source_commits', [])
            entry['commit_groups'] = [aliases.get(commit, [commit]) for commit in commits]
            entry['commit_aliases'] = sorted({alias for commit in commits for alias in aliases.get(commit, [commit])})
        if canonical_entries:
            try:
                calibration_counts.update(calibrate_source_entries(release, canonical_entries, aliases))
            except ValueError as error:
                raise CommandError(str(error)) from error
        release['content_hash'] = hashlib.sha256(json.dumps(
            {key: value for key, value in release.items() if key not in {'content_hash', 'doc_loaded_at', 'doc_git'}},
            ensure_ascii=False, sort_keys=True,
        ).encode()).hexdigest()
    return {
        'format': FORMAT_VERSION, 'parser_version': PARSER_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source': 'PGSQL.CC PostgreSQL 中文手册发布说明',
        'source_url': '/docs/release/',
        'minimum_major': 10,
        'excluded_unreleased': sorted(UNRELEASED_VERSIONS),
        'backport_sources': source_records,
        'backport_commit_count': len(aliases),
        'source_commit_enrichment': dict(source_commit_counts),
        'canonical_sources': canonical_records,
        'source_calibration': dict(calibration_counts),
        'releases': releases,
        'release_count': len(releases),
        'entry_count': sum(release['entry_count'] for release in releases),
    }


def write_snapshot(snapshot, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    descriptor, temporary = tempfile.mkstemp(prefix='.releases-', dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            with gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0) as compressed:
                compressed.write(data)
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Command(BaseCommand):
    help = 'Build the PostgreSQL version comparison snapshot from Chinese release notes'

    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true', help='Validate extraction and complete release coverage without writing')
        parser.add_argument('--output', default=str(Path(settings.BASE_DIR) / 'data/compare/releases.json.gz'))
        parser.add_argument('--pgdoc-root', default=str(Path(settings.BASE_DIR).parent / 'pgdoc'), help='Optional translated SGML checkout with upstream backport commit comments')

    def handle(self, *args, **options):
        snapshot = build_snapshot(options['pgdoc_root'])
        if not options['check']:
            write_snapshot(snapshot, options['output'])
        self.stdout.write(self.style.SUCCESS('{} {} releases / {} entries{}'.format(
            'Validated' if options['check'] else 'Built', snapshot['release_count'], snapshot['entry_count'],
            '' if options['check'] else ' → ' + options['output'],
        )))
