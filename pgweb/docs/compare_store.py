"""Lossless PostgreSQL release storage and explicit cross-release evidence.

Raw source dictionaries are retained per language. Query columns and relations
are projections, not a replacement for release-note occurrences. Imports are
atomic, and serving never falls back to files when a manifest or row is missing.
"""

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime
from threading import RLock
import hashlib
import json
import re

from django.db import DatabaseError, connections, transaction
from django.db.models.fields.json import KeyTransform
from django.utils import timezone

from .models import CompareDataset, CompareEntry, ComparePatch, CompareRelease


RELATION_RULE = 1
IMPORT_LOCK = 7071636
LANGUAGES = frozenset({'zh', 'en'})
HASH = re.compile(r'[0-9a-f]{7,40}', re.I)


class ComparisonDataUnavailable(RuntimeError):
    pass


class DatabaseSnapshot(dict):
    pass


class _RevisionChanged(Exception):
    pass


def digest(value):
    fingerprint = hashlib.sha256()
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    for chunk in encoder.iterencode(value):
        fingerprint.update(chunk.encode('utf-8'))
    return fingerprint.hexdigest()


def version_parts(version):
    if not isinstance(version, str) or not re.fullmatch(r'\d+(?:\.\d+){1,2}', version):
        raise ValueError('Invalid complete release version: {!r}'.format(version))
    parts = [int(part) for part in version.split('.')]
    if parts[0] >= 10 and len(parts) == 2:
        return str(parts[0]), parts[1], parts[0] * 10000 + parts[1]
    if parts[0] == 9 and len(parts) == 3:
        return '{}.{}'.format(*parts[:2]), parts[2], parts[0] * 10000 + parts[1] * 100 + parts[2]
    raise ValueError('Comparison releases must use 9.x.y or major.minor from PostgreSQL 10')


def entry_part(entry):
    source_id = entry.get('source_entry_id', '')
    match = re.search(r'/(migration|changes)/', source_id)
    return match[1] if match else ('migration' if entry.get('category') == 'compatibility' else 'changes')


def statement_hash(entry):
    prose = re.sub(r'\s+', ' ', entry.get('identity_text', entry.get('text', entry['title']))).strip()
    return digest([entry_part(entry), prose])


def _source_hash(entry):
    return entry.get('source_hash') or statement_hash(entry)


def _same_statement_anchor(left, right):
    """Recognize comment-only source corrections without using position alone."""
    if (not left.get('source_entry_id') or left.get('source_entry_id') != right.get('source_entry_id') or
            statement_hash(left) != statement_hash(right)):
        return False
    a = {commit for group in _groups(left) for commit in group}
    b = {commit for group in _groups(right) for commit in group}
    return not a or not b or bool(a & b)


def _groups(entry):
    groups = entry.get('commit_groups')
    if groups is None:
        commits = entry.get('source_commits', entry.get('commits', []))
        groups = [commits + entry.get('commit_aliases', [])] if len(commits) == 1 else [[c] for c in commits]
    if not isinstance(groups, list):
        raise ValueError('commit_groups must be an array')
    parsed = []
    for group in groups:
        if not isinstance(group, list) or not group or any(not isinstance(c, str) or not HASH.fullmatch(c) for c in group):
            raise ValueError('Invalid independent commit group')
        parsed.append(sorted(set(c.lower() for c in group)))
    return parsed


def _dataset_key(kind, language):
    if kind == 'security':
        return 'security', ''
    if kind != 'releases' or language not in LANGUAGES:
        raise ValueError('Expected releases with zh/en language, or security')
    return 'releases:' + language, language


def _validate(snapshot, kind):
    if not isinstance(snapshot, dict) or snapshot.get('format') != 1:
        raise ValueError('Unsupported comparison source format')
    if kind == 'security':
        if not isinstance(snapshot.get('cves'), list):
            raise ValueError('Security snapshot has no CVE records')
        ids = [item.get('id') for item in snapshot['cves']]
        if len(set(ids)) != len(ids) or any(not re.fullmatch(r'CVE-\d{4}-\d+', value or '') for value in ids):
            raise ValueError('Invalid or duplicate CVE identity')
        return
    if not isinstance(snapshot.get('releases'), list) or not snapshot['releases']:
        raise ValueError('Release snapshot is empty')
    versions = []
    for release in snapshot['releases']:
        major, minor, _ = version_parts(release.get('version'))
        if str(release.get('major')) != major or release.get('minor') != minor:
            raise ValueError('Release version coordinates disagree: ' + release['version'])
        versions.append(release['version'])
        if release.get('status') not in {'stable', 'preview', 'devel'} or not isinstance(release.get('entries'), list):
            raise ValueError('Invalid release state: ' + release['version'])
        if release.get('date'):
            date.fromisoformat(release['date'])
        ids = []
        for entry in release['entries']:
            for field in ('id', 'title', 'html', 'text', 'category'):
                if not isinstance(entry.get(field), str) or not entry[field]:
                    raise ValueError('Missing entry field ' + field)
            ids.append(entry['id'])
            _groups(entry)
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate display identity within ' + release['version'])
        if 'entry_count' in release and release['entry_count'] != len(release['entries']):
            raise ValueError('Release entry count disagrees: ' + release['version'])
    if len(versions) != len(set(versions)):
        raise ValueError('Duplicate release version')
    for field, count in [('release_count', len(versions)), ('entry_count', sum(len(r['entries']) for r in snapshot['releases']))]:
        if field in snapshot and snapshot[field] != count:
            raise ValueError('Snapshot {} disagrees'.format(field))


def _remember(row, field, value, language, now, provenance):
    """Retain previous source values, including unknown extension fields."""
    previous = deepcopy(getattr(row, field))
    if language in previous and previous[language] != value:
        row.revisions = list(row.revisions) + [{
            'language': language, 'hash': digest(previous[language]),
            'payload': previous[language], 'replaced_at': now.isoformat(), 'replaced_by': provenance,
        }]
    previous[language] = deepcopy(value)
    setattr(row, field, previous)


def _save_projected(row, fields, now, using, counters, name):
    state = {field: getattr(row, field) for field in fields}
    # Date columns are derived query projections; use their portable string form.
    state = {key: value.isoformat() if isinstance(value, date) else value for key, value in state.items()}
    fingerprint = digest(state)
    if row.content_hash == fingerprint:
        counters[name + '_unchanged'] += 1
        return
    created = row._state.adding
    row.content_hash = fingerprint
    row.imported_at = now
    row.save(using=using)
    counters[name + ('_created' if created else '_updated')] += 1


RELEASE_FIELDS = ('major', 'minor', 'sort_num', 'status', 'released_at', 'active_languages', 'payloads')
ENTRY_FIELDS = ('release_id', 'part', 'position', 'category', 'statement_hash', 'patch_ids', 'cves',
                'active_languages', 'payloads', 'relations')
PATCH_FIELDS = ('commits', 'evidence', 'merged_into_id')


def _patch_registry(incoming, existing, dataset_key, now, using, counters):
    parents = {}

    def root(value):
        parents.setdefault(value, value)
        while parents[value] != value:
            parents[value] = parents[parents[value]]
            value = parents[value]
        return value

    def union(values):
        if values:
            first = root(values[0])
            for value in values[1:]:
                parents[root(value)] = first

    # Only CURRENT source groups establish edges. Historical groups identify
    # prior rows but must not make an erroneous old merge irreversible.
    for group in incoming:
        union(group)
    # A unique extended hash is an alias; ambiguous short hashes stay separate.
    hashes = sorted(parents)
    for position, short in enumerate(hashes[:-1]):
        longer = []
        for candidate in hashes[position + 1:]:
            if not candidate.startswith(short):
                break
            longer.append(candidate)
        if longer and all(longer[-1].startswith(value) for value in longer):
            union([short, longer[-1]])
    components, old_ids, split_from = defaultdict(list), defaultdict(list), defaultdict(list)
    for commit in parents:
        components[root(commit)].append(commit)
    prefix_roots = defaultdict(set)
    for commit in parents:
        for length in range(7, len(commit) + 1):
            prefix_roots[commit[:length]].add(root(commit))
    for row in existing.values():
        matches = {}
        for commit in row.commits:
            roots = set(prefix_roots.get(commit, ()))
            roots.update(root(commit[:length]) for length in range(7, len(commit) + 1) if commit[:length] in parents)
            if len(roots) == 1:
                matches[commit] = roots.pop()
        roots = set(matches.values())
        if not roots:
            continue
        seed = row.evidence.get('identity_seed', min(row.commits))
        anchor = matches.get(seed) or min(roots)
        old_ids[anchor].append(row.id)
        if len(roots) > 1:
            for component in roots:
                split_from[component].append(row.id)
    lookup, redirects = {}, {}
    for component, commits in sorted(components.items()):
        commits.sort()
        previous = sorted(old_ids[component])
        key = previous[0] if previous else digest(['postgresql-patch', commits[0]])[:32]
        row = existing.get(key) or ComparePatch(id=key, commits=[], evidence={}, content_hash='')
        old = {'commits': row.commits, 'evidence': row.evidence, 'merged_into_id': row.merged_into_id}
        row.commits = commits
        row.merged_into_id = None
        row.evidence = dict(row.evidence, kind='commit-correspondence', active=True,
                            identity_seed=row.evidence.get('identity_seed', commits[0]))
        if split_from[component]:
            row.evidence['split_from'] = sorted(set(row.evidence.get('split_from', [])) | set(split_from[component]))
        if previous[1:]:
            row.evidence['merged_ids'] = sorted(set(row.evidence.get('merged_ids', [])) | set(previous[1:]))
        if not row._state.adding and old != {'commits': row.commits, 'evidence': row.evidence, 'merged_into_id': row.merged_into_id}:
            row.revisions = list(row.revisions) + [dict(old, replaced_at=now.isoformat(), source_dataset=dataset_key)]
        _save_projected(row, PATCH_FIELDS, now, using, counters, 'patch')
        existing[key] = row
        for commit in commits:
            lookup[commit] = key
        for obsolete in previous[1:]:
            loser = existing[obsolete]
            old_loser = {'commits': loser.commits, 'evidence': loser.evidence, 'merged_into_id': loser.merged_into_id}
            loser.merged_into_id = key
            loser.evidence = dict(loser.evidence, active=False)
            if old_loser != {'commits': loser.commits, 'evidence': loser.evidence, 'merged_into_id': loser.merged_into_id}:
                loser.revisions = list(loser.revisions) + [dict(old_loser, replaced_at=now.isoformat(), source_dataset=dataset_key)]
            _save_projected(loser, PATCH_FIELDS, now, using, counters, 'patch')
            redirects[obsolete] = key
    active_ids = set(lookup.values())
    for row in existing.values():
        if row.id not in active_ids and row.evidence.get('active', True):
            row.revisions = list(row.revisions) + [{'commits': row.commits, 'evidence': row.evidence,
                                                   'merged_into_id': row.merged_into_id, 'replaced_at': now.isoformat()}]
            row.evidence = dict(row.evidence, active=False)
            _save_projected(row, PATCH_FIELDS, now, using, counters, 'patch')
        if row.merged_into_id:
            target = row.merged_into_id
            while target in redirects:
                target = redirects[target]
            redirects[row.id] = target
    return lookup, redirects


def _relations(entries, releases):
    """Persistent facts across occurrences, independent of a comparison pair."""
    by_patch, by_statement = defaultdict(list), defaultdict(list)
    active = {key: row for key, row in entries.items() if row.active_languages}
    for row in active.values():
        for patch in row.patch_ids:
            by_patch[patch].append(row.id)
        by_statement[row.statement_hash].append(row.id)
    result = {}
    for row in active.values():
        candidates = set(by_statement[row.statement_hash])
        for patch in row.patch_ids:
            candidates.update(by_patch[patch])
        relations = []
        left = releases[row.release_id]
        for key in sorted(candidates - {row.id}):
            other = active[key]
            if not set(row.active_languages) & set(other.active_languages):
                continue
            right = releases[other.release_id]
            overlap = sorted(set(row.patch_ids) & set(other.patch_ids))
            same_statement = row.statement_hash == other.statement_hash
            same_day = bool(left.released_at and left.released_at == right.released_at)
            if not overlap and not (same_statement and same_day and (not row.patch_ids or not other.patch_ids)):
                continue
            same_scope = left.major != right.major and row.part == other.part
            if row.patch_ids and other.patch_ids:
                equivalent = (same_scope and set(row.patch_ids) == set(other.patch_ids) and
                              ((left.minor > 0 and right.minor > 0) or same_statement))
            else:
                equivalent = same_scope and same_day and same_statement
            evidence = {'patch_ids': overlap, 'same_day': same_day}
            if same_statement:
                evidence['statement_hash'] = row.statement_hash
            relations.append({'target': key, 'type': 'equivalent' if equivalent else 'related',
                              'rule': RELATION_RULE, 'evidence': evidence})
        result[row.id] = relations
    return result


def _read_dataset(dataset, using='default', annotate=False):
    if dataset.kind == 'security':
        output = deepcopy(dataset.metadata)
    else:
        versions = [member['version'] for member in dataset.members]
        # Fetch only the requested language, without historical revisions or ORM
        # instances. The returned JSON objects become the snapshot directly.
        releases = {row['version']: row for row in CompareRelease.objects.using(using)
                    .filter(pk__in=versions).annotate(source_payload=KeyTransform(dataset.language, 'payloads'))
                    .values('version', 'active_languages', 'source_payload').iterator(chunk_size=500)}
        entry_ids = [key for member in dataset.members for key in member['entries']]
        fields = ['id', 'release_id', 'active_languages', 'source_payload']
        if annotate:
            fields += ['patch_ids', 'statement_hash', 'relations']
        entries = {row['id']: row for row in CompareEntry.objects.using(using)
                   .filter(pk__in=entry_ids).order_by()
                   .annotate(source_payload=KeyTransform(dataset.language, 'payloads'))
                   .values(*fields).iterator(chunk_size=500)}
        if len(releases) != len(versions) or len(entries) != len(entry_ids):
            raise ComparisonDataUnavailable('Comparison database is missing manifest members')
        output = deepcopy(dataset.metadata)
        output['releases'] = []
        for member in dataset.members:
            row = releases[member['version']]
            if dataset.language not in row['active_languages'] or row['source_payload'] is None:
                raise ComparisonDataUnavailable('Comparison release language has not been imported')
            release = row['source_payload']
            release['entries'] = []
            for key in member['entries']:
                entry = entries[key]
                if (entry['release_id'] != row['version'] or dataset.language not in entry['active_languages'] or
                        entry['source_payload'] is None):
                    raise ComparisonDataUnavailable('Comparison entry language or release disagrees with manifest')
                release['entries'].append(entry['source_payload'])
            output['releases'].append(release)
    if digest(output) != dataset.content_hash:
        raise ComparisonDataUnavailable('Comparison database content hash disagrees with activated manifest')
    if dataset.kind == 'releases':
        if len(output['releases']) != dataset.release_count or sum(len(r['entries']) for r in output['releases']) != dataset.entry_count:
            raise ComparisonDataUnavailable('Comparison database counts disagree with activated manifest')
        if annotate:
            visible = set(entry_ids)
            for member, release in zip(dataset.members, output['releases']):
                for key, entry in zip(member['entries'], release['entries']):
                    row = entries[key]
                    entry.update(db_id=key, patch_ids=row['patch_ids'], statement_hash=row['statement_hash'],
                                 relations=[relation for relation in row['relations'] if relation['target'] in visible])
    return output


def export_database_snapshot(kind='releases', language='zh', using='default'):
    key, _ = _dataset_key(kind, language)
    try:
        dataset = CompareDataset.objects.using(using).get(pk=key)
    except CompareDataset.DoesNotExist as exc:
        raise ComparisonDataUnavailable('Comparison dataset {} has not been imported'.format(key)) from exc
    return _read_dataset(dataset, using)


ARCHIVE_MODELS = {
    'releases': CompareRelease, 'patches': ComparePatch,
    'entries': CompareEntry, 'datasets': CompareDataset,
}


def export_database_archive(using='default'):
    """Backup all four tables, including retired occurrences and revisions."""
    rows = {}
    with transaction.atomic(using=using):
        with connections[using].cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [IMPORT_LOCK])
        for name, model in ARCHIVE_MODELS.items():
            rows[name] = [{key: value.isoformat() if isinstance(value, date) else value for key, value in row.items()}
                          for row in model.objects.using(using).order_by('pk').values()]
    return {'storage_format': 1, 'rows': rows, 'content_hash': digest(rows)}


def restore_database_archive(archive, *, check=False, using='default'):
    """Restore a complete backup to an empty store; never overwrite live edits."""
    if (archive.get('storage_format') != 1 or set(archive.get('rows', {})) != set(ARCHIVE_MODELS) or
            digest(archive['rows']) != archive.get('content_hash')):
        raise ValueError('Invalid comparison storage archive')
    with transaction.atomic(using=using):
        with connections[using].cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [IMPORT_LOCK])
        if any(model.objects.using(using).exists() for model in ARCHIVE_MODELS.values()):
            if export_database_archive(using) == archive:
                return {'unchanged': True}
            raise ValueError('Archive restoration requires empty comparison tables')
        for name, model in ARCHIVE_MODELS.items():
            fields = {field.attname: field for field in model._meta.concrete_fields}
            objects = []
            for original in archive['rows'][name]:
                if set(original) != set(fields):
                    raise ValueError('Archive fields disagree with model ' + name)
                values = deepcopy(original)
                for key, field in fields.items():
                    if values[key] is not None and field.get_internal_type() == 'DateTimeField':
                        values[key] = datetime.fromisoformat(values[key])
                    elif values[key] is not None and field.get_internal_type() == 'DateField':
                        values[key] = date.fromisoformat(values[key])
                objects.append(model(**values))
            model.objects.using(using).bulk_create(objects, batch_size=500)
        patches = set(ComparePatch.objects.using(using).values_list('id', flat=True))
        entries = set(CompareEntry.objects.using(using).values_list('id', flat=True))
        for row in CompareEntry.objects.using(using).all():
            if not set(row.patch_ids) <= patches or any(relation['target'] not in entries for relation in row.relations):
                raise ValueError('Archive has dangling comparison relations')
        for dataset in CompareDataset.objects.using(using).all():
            _read_dataset(dataset, using)
        if export_database_archive(using) != archive:
            raise ValueError('Restored database archive differs from input')
        if check:
            transaction.set_rollback(True, using=using)
        else:
            transaction.on_commit(_load_revision.cache_clear, using=using)
    return {name: len(rows) for name, rows in archive['rows'].items()}


_snapshot_cache = {}
_snapshot_cache_lock = RLock()


def _clear_snapshot_cache():
    with _snapshot_cache_lock:
        _snapshot_cache.clear()


def _load_revision(key, revision, using):
    # Retain only the current revision per dataset. Drop the old full snapshot
    # before building a replacement, and serialize cold loads within a worker.
    with _snapshot_cache_lock:
        cached = _snapshot_cache.get((using, key))
        if cached and cached[0] == revision:
            return cached[1]
        _snapshot_cache.pop((using, key), None)
        del cached
        result = _read_revision(key, revision, using)
        _snapshot_cache[(using, key)] = (revision, result)
        return result


_load_revision.cache_clear = _clear_snapshot_cache


def _read_revision(key, revision, using):
    dataset = CompareDataset.objects.using(using).defer('revisions').get(pk=key)
    if dataset.revision != revision:
        raise _RevisionChanged()
    try:
        output = _read_dataset(dataset, using, annotate=True)
    except ComparisonDataUnavailable:
        if CompareDataset.objects.using(using).filter(pk=key, revision=revision).exists():
            raise
        raise _RevisionChanged()
    if not CompareDataset.objects.using(using).filter(pk=key, revision=revision).exists():
        raise _RevisionChanged()
    result = DatabaseSnapshot(output)
    result.database_revision = revision
    result.database_key = key
    return result


def load_database_snapshot(kind='releases', language='zh', using='default'):
    key, _ = _dataset_key(kind, language)
    try:
        for _ in range(3):
            revision = CompareDataset.objects.using(using).filter(pk=key).values_list('revision', flat=True).first()
            if revision is None:
                raise ComparisonDataUnavailable('Comparison dataset {} has not been imported'.format(key))
            try:
                return _load_revision(key, revision, using)
            except _RevisionChanged:
                continue
        raise ComparisonDataUnavailable('Comparison dataset changed during loading; retry shortly')
    except DatabaseError as exc:
        raise ComparisonDataUnavailable('Comparison database storage is unavailable') from exc


def import_snapshot(snapshot, *, kind='releases', language='zh', complete=False, prune=False,
                    check=False, using='default'):
    """Import and verify in one transaction; missing rows survive unless pruned."""
    key, language = _dataset_key(kind, language)
    _validate(snapshot, kind)
    if prune and not complete:
        raise ValueError('--prune requires an explicitly complete snapshot')
    incoming = deepcopy(snapshot)
    now = timezone.now()
    counters = Counter()
    with transaction.atomic(using=using):
        with connections[using].cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [IMPORT_LOCK])
        dataset = CompareDataset.objects.using(using).filter(pk=key).first()
        old_snapshot = _read_dataset(dataset, using) if dataset else None
        if kind == 'security':
            if old_snapshot and not prune:
                found = {item['id'] for item in incoming['cves']}
                incoming['cves'].extend(item for item in old_snapshot['cves'] if item['id'] not in found)
            members = []
        else:
            release_rows = CompareRelease.objects.using(using).in_bulk()
            entry_rows = CompareEntry.objects.using(using).in_bulk()
            patch_rows = ComparePatch.objects.using(using).in_bulk()
            incoming_by_version = {release['version']: release for release in incoming['releases']}
            incoming_display = {version: {entry['id'] for entry in release['entries']} for version, release in incoming_by_version.items()}
            incoming_hashes = {version: {_source_hash(entry) for entry in release['entries']} for version, release in incoming_by_version.items()}
            commit_groups = [group for release in incoming['releases'] for entry in release['entries'] for group in _groups(entry)]
            for current in entry_rows.values():
                replacements = incoming_by_version.get(current.release_id, {}).get('entries', [])
                replaced = (current.release_id in incoming_by_version and any(
                    payload.get('id') in incoming_display[current.release_id] or
                    _source_hash(payload) in incoming_hashes[current.release_id] or
                    any(_same_statement_anchor(payload, item) for item in replacements)
                    for payload in current.payloads.values()))
                for active_language in current.active_languages:
                    payload = current.payloads[active_language]
                    retained = active_language != language or not prune
                    if retained and not replaced:
                        commit_groups.extend(_groups(payload))
            patches, redirects = _patch_registry(commit_groups, patch_rows, key, now, using, counters)
            old_members = {m['version']: m['entries'] for m in dataset.members} if dataset else {}
            by_release = defaultdict(list)
            for row in entry_rows.values():
                by_release[row.release_id].append(row)
            members = []
            incoming_versions = set()
            for release in incoming['releases']:
                version = release['version']
                incoming_versions.add(version)
                major, minor, sort_num = version_parts(version)
                row = release_rows.get(version) or CompareRelease(version=version, content_hash='')
                row.major, row.minor, row.sort_num = major, minor, sort_num
                row.status = release['status']
                row.released_at = date.fromisoformat(release['date']) if release.get('date') else None
                row.active_languages = sorted(set(row.active_languages) | {language})
                raw_release = {field: deepcopy(value) for field, value in release.items() if field != 'entries'}
                selected, used, occurrence_counts = [], set(), Counter()
                for position, entry in enumerate(release['entries']):
                    part, source_hash = entry_part(entry), _source_hash(entry)
                    occurrence_counts[(part, source_hash)] += 1
                    same_source = [existing for existing in by_release[version] if existing.id not in used and any(
                        entry_part(payload) == part and _source_hash(payload) == source_hash
                        for payload in existing.payloads.values())]
                    same_display = [existing for existing in by_release[version] if existing.id not in used and
                                    existing.payloads.get(language, {}).get('id') == entry['id']]
                    if len(same_display) > 1:
                        raise ValueError('Ambiguous prior display identity: ' + entry['id'])
                    anchored = [existing for existing in by_release[version] if existing.id not in used and any(
                        _same_statement_anchor(payload, entry) for payload in existing.payloads.values())]
                    candidates = same_display or same_source or anchored
                    if len(candidates) > 1:
                        # Identical repeated statements remain separate occurrences.
                        candidates.sort(key=lambda item: (item.position, item.id))
                    current = candidates[0] if candidates else None
                    if current is None:
                        identity = digest(['release-occurrence', version, part, source_hash,
                                           occurrence_counts[(part, source_hash)]])[:32]
                        if identity in entry_rows:
                            raise ValueError('Ambiguous occurrence identity: ' + identity)
                        current = CompareEntry(id=identity, release_id=version, content_hash='')
                    used.add(current.id)
                    current.part, current.position, current.category = part, position, entry['category']
                    current.statement_hash = statement_hash(entry)
                    current.patch_ids = sorted({patches[group[0]] for group in _groups(entry)})
                    current.cves = sorted(set(entry.get('cves', [])))
                    current.active_languages = sorted(set(current.active_languages) | {language})
                    _remember(current, 'payloads', entry, language, now, source_hash)
                    entry_rows[current.id] = current
                    by_release[version] = [item for item in by_release[version] if item.id != current.id] + [current]
                    selected.append(current.id)
                if not prune:
                    selected.extend(identity for identity in old_members.get(version, []) if identity not in used)
                if len(selected) != len(release['entries']):
                    release['entries'] = [deepcopy(entry_rows[identity].payloads[language]) for identity in selected]
                    for field, value in [('entry_count', len(selected)),
                                         ('changes_count', sum(entry_rows[identity].part == 'changes' for identity in selected)),
                                         ('compatibility_count', sum(entry_rows[identity].part == 'migration' for identity in selected))]:
                        if field in raw_release:
                            raw_release[field] = value
                            release[field] = value
                _remember(row, 'payloads', raw_release, language, now, digest(raw_release))
                _save_projected(row, RELEASE_FIELDS, now, using, counters, 'release')
                release_rows[version] = row
                members.append({'version': version, 'entries': selected})
            if old_snapshot and not prune:
                for release in old_snapshot['releases']:
                    if release['version'] not in incoming_versions:
                        incoming['releases'].append(release)
                        members.append({'version': release['version'], 'entries': old_members[release['version']]})
            selected_ids = {identity for member in members for identity in member['entries']}
            selected_versions = {member['version'] for member in members}
            for row in release_rows.values():
                if prune and row.version not in selected_versions and language in row.active_languages:
                    row.active_languages = [value for value in row.active_languages if value != language]
                    _save_projected(row, RELEASE_FIELDS, now, using, counters, 'release')
            for row in entry_rows.values():
                if prune and row.id not in selected_ids and language in row.active_languages:
                    row.active_languages = [value for value in row.active_languages if value != language]
                if row.active_languages:
                    active_language = language if language in row.active_languages else sorted(row.active_languages)[0]
                    groups = _groups(row.payloads[active_language])
                    # An imported canonical correction can supersede an older
                    # language's flattened group without changing its raw prose.
                    row.patch_ids = sorted({patches[commit] for group in groups for commit in group if commit in patches})
                else:
                    row.patch_ids = sorted({redirects.get(identity, identity) for identity in row.patch_ids})
            relations = _relations(entry_rows, release_rows)
            for row in entry_rows.values():
                row.relations = relations.get(row.id, [])
                _save_projected(row, ENTRY_FIELDS, now, using, counters, 'entry')
            for field, value in [('release_count', len(incoming['releases'])),
                                 ('entry_count', sum(len(r['entries']) for r in incoming['releases']))]:
                if field in incoming:
                    incoming[field] = value
        fingerprint = digest(incoming)
        metadata = {field: value for field, value in incoming.items() if field != 'releases'}
        if dataset is None:
            dataset = CompareDataset(key=key, kind=kind, language=language, revision=0, content_hash='')
        if (dataset.content_hash != fingerprint or dataset.members != members or
                (kind == 'releases' and counters['entry_updated'])):
            if dataset.revision:
                dataset.revisions = list(dataset.revisions) + [{
                    'revision': dataset.revision, 'content_hash': dataset.content_hash,
                    'metadata': dataset.metadata, 'members': dataset.members, 'replaced_at': now.isoformat(),
                }]
            dataset.metadata, dataset.members, dataset.content_hash = metadata, members, fingerprint
            dataset.release_count = len(incoming['releases']) if kind == 'releases' else 0
            dataset.entry_count = sum(len(r['entries']) for r in incoming['releases']) if kind == 'releases' else len(incoming['cves'])
            dataset.revision += 1
            dataset.imported_at = now
            dataset.save(using=using)
            counters['dataset_updated'] += 1
        # Verify values actually read from PostgreSQL, including arbitrary JSON.
        if _read_dataset(CompareDataset.objects.using(using).get(pk=key), using) != incoming:
            raise ValueError('Database round-trip differs from prepared import')
        counters.update(releases=dataset.release_count, entries=dataset.entry_count)
        if check:
            transaction.set_rollback(True, using=using)
        else:
            # Relations can change for another language after shared patch evidence
            # grows. Bump those manifests so no worker keeps stale projections.
            if kind == 'releases' and (counters['entry_updated'] or counters['entry_created']):
                from django.db.models import F
                CompareDataset.objects.using(using).filter(kind='releases').exclude(pk=key).update(revision=F('revision') + 1)
            transaction.on_commit(_load_revision.cache_clear, using=using)
    return dict(counters)
