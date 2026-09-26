#!/usr/bin/env python3
"""Exhaustively check comparison accounting and emit a bilingual audit digest.

This checks every selectable version pair against the source snapshot, preserving
full note bodies and identifying every omitted row with its supporting source.
It complements (does not replace) the independent SGML/source-coverage audit.
"""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
import django  # noqa: E402
django.setup()
from pgweb.docs import compare  # noqa: E402


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read(path):
    with (gzip.open if path.suffix == '.gz' else open)(path, 'rt') as stream:
        return compare._Snapshot(json.load(stream))


def verify_original_fields(original, loaded, location='snapshot'):
    """A DB round trip may enrich records, but must preserve every source field."""
    if isinstance(original, dict):
        assert isinstance(loaded, dict), (location, 'mapping changed type')
        for key, value in original.items():
            assert key in loaded, (location, 'missing original field', key)
            verify_original_fields(value, loaded[key], location + '.' + key)
    elif isinstance(original, list):
        assert isinstance(loaded, list) and len(original) == len(loaded), (location, 'list length changed')
        for position, (source_value, loaded_value) in enumerate(zip(original, loaded)):
            verify_original_fields(source_value, loaded_value, f'{location}[{position}]')
    else:
        assert original == loaded, (location, 'original value changed', original, loaded)


def audit_single_releases(snapshot, security):
    from pgweb.docs.compare_presenter import release_report

    records = []
    for release in snapshot['releases']:
        if release.get('placeholder'):
            continue
        report = release_report(snapshot, security, release['version'])
        entries = [entry for group in report['groups'] for entry in group['entries']]
        verify_original_fields(release['entries'], entries, 'single_release.' + release['version'])
        assert report['total'] == len(release['entries'])
        assert report['groups'][0].get('migration_html', '') == release.get('migration_html', '')
        cves = sorted({cve for entry in release['entries'] for cve in entry.get('cves', [])})
        assert sorted(cve['id'] for cve in report['cves']) == cves
        assert report['cve_count'] == len(cves)
        records.append([release['version'], [entry.get('source_entry_id', entry['id']) for entry in entries], cves])
    return {'single_release_count': len(records), 'single_release_digest': digest(records)}


def audit_relations(snapshot):
    """Check DB relationships against fresh source identities, not patch IDs."""
    rows, by_patch, by_statement = {}, defaultdict(set), defaultdict(set)
    index = compare._release_index(snapshot)
    for release in snapshot['releases']:
        for position, entry in enumerate(release['entries']):
            assert all(field in entry for field in ('db_id', 'patch_ids', 'statement_hash', 'relations')), (
                release['version'], entry['id'], 'missing database relationship metadata')
            identifier = entry['db_id']
            assert identifier not in rows, ('duplicate database occurrence', identifier)
            source_id = entry.get('source_entry_id', entry['id'])
            part = source_id.split('/')[1] if '/' in source_id else ('migration' if entry['category'] == 'compatibility' else 'changes')
            prose = re.sub(r'\s+', ' ', entry.get('identity_text', entry.get('text', entry['title']))).strip()
            statement = json.dumps([part, prose], ensure_ascii=False, separators=(',', ':')).encode()
            assert entry['statement_hash'] == hashlib.sha256(statement).hexdigest(), (
                source_id, 'persisted statement identity differs from complete source prose')
            required, _, fingerprint = index.identities[(release['version'], position)]
            patches = frozenset(commit for _, commit in required)
            assert len(patches) == len(set(entry['patch_ids'])), (source_id, 'persisted patch group count disagrees')
            row = {'release': release, 'entry': entry, 'patches': patches, 'part': part, 'prose': fingerprint[-1]}
            rows[identifier] = row
            for patch in patches:
                by_patch[patch].add(identifier)
            by_statement[(part, fingerprint[-1], release.get('date'))].add(identifier)

    records, types = [], Counter()
    for identifier, row in rows.items():
        release, entry = row['release'], row['entry']
        candidates = set(by_statement[(row['part'], row['prose'], release.get('date'))])
        for patch in row['patches']:
            candidates.update(by_patch[patch])
        expected = {}
        for target in candidates - {identifier}:
            other = rows[target]
            same_prose = row['part'] == other['part'] and row['prose'] == other['prose']
            same_day = bool(release.get('date') and release['date'] == other['release'].get('date'))
            shared = row['patches'] & other['patches']
            if not shared:
                if row['patches'] and other['patches']:
                    continue
                if not (same_prose and same_day):
                    continue
            scope = release['major'] != other['release']['major'] and row['part'] == other['part']
            if row['patches'] and other['patches']:
                equivalent = (scope and row['patches'] == other['patches'] and
                              ((release['minor'] > 0 and other['release']['minor'] > 0) or same_prose))
            else:
                equivalent = scope and same_day and same_prose
            expected[target] = 'equivalent' if equivalent else 'related'
        actual = {relation['target']: relation['type'] for relation in entry['relations']}
        assert len(actual) == len(entry['relations']), (identifier, 'repeated relationship')
        assert actual == expected, (entry.get('source_entry_id'), 'persisted relationships differ from source', actual, expected)
        for relation in entry['relations']:
            target = rows[relation['target']]
            overlap = sorted(set(entry['patch_ids']) & set(target['entry']['patch_ids']))
            assert relation['evidence']['patch_ids'] == overlap
            assert relation['evidence']['same_day'] == bool(
                release.get('date') and release['date'] == target['release'].get('date'))
            if 'statement_hash' in relation['evidence']:
                assert relation['evidence']['statement_hash'] == entry['statement_hash'] == target['entry']['statement_hash']
            assert any(reverse['target'] == identifier and reverse['type'] == relation['type']
                       for reverse in target['entry']['relations']), (identifier, 'asymmetric relationship')
            types[relation['type']] += 1
            records.append([entry.get('source_entry_id', entry['id']),
                            target['entry'].get('source_entry_id', target['entry']['id']), relation['type']])
    return {'relation_count': len(records), 'relation_types': dict(types), 'relation_digest': digest(sorted(records))}


def audit(snapshot, security, start_numbers=None):
    releases = {r['version']: r for r in snapshot['releases'] if not r.get('placeholder')}
    versions = sorted(releases, key=compare.version_key)
    originals = {(r['version'], e['id']): e for r in releases.values() for e in r['entries']}
    index = compare._release_index(snapshot)
    identities = {(r['version'], e['id']): index.identities[(r['version'], p)]
                  for r in releases.values() for p, e in enumerate(r['entries'])}
    decisions = {}
    pairs = []
    examples = []
    same_branch = cross_branch = 0
    selected_examples = {('9.0.0', '9.1.0'), ('9.0.0', '18.6'), ('9.6.0', '9.6.24'),
                         ('9.6.24', '10.0'), ('17.0', '18.0'), ('17.0', '18.6'),
                         ('17.11', '18.6'), ('18.0', '18.6'), ('10.0', '18.6')}

    def source_id(key):
        return originals[key].get('source_entry_id', key[1])

    def note_key(item):
        return item['version'], item['id']

    for number, start in enumerate(versions):
        if start_numbers is not None and number not in start_numbers:
            continue
        for finish in versions[number:]:
            report = compare.build_report(snapshot, security, start, finish)
            candidates = {(v, e['id']) for v in report['history']['candidates'] for e in releases[v]['entries']}
            source_keys = {(v, e['id']) for v in report['history']['source'] for e in releases[v]['entries']}
            rows = [e for group in report['groups'] for e in group['entries']]
            shown = [note_key(e) for e in rows]
            shown_set = set(shown)
            omitted = [note_key(e) for e in report['exclusions']]
            assert Counter(shown + omitted) == Counter(candidates), (start, finish, 'candidate accounting')
            assert report['total'] + report['excluded_count'] == len(candidates)
            assert report['excluded_count'] == report['duplicate_count'] + report['already_in_source_count']
            assert report['candidate_count'] == len(candidates)
            assert Counter(e['category'] for e in rows) == Counter(
                {item['key']: item['count'] for item in report['stats'][1:] if item['count']})

            variants = {}
            for item in rows:
                key = note_key(item)
                assert item['html'] == originals[key]['html']
                branches = [releases[key[0]]['major']]
                for variant in item['variants']:
                    vkey = note_key(variant)
                    assert vkey not in variants, (start, finish, 'duplicate variant')
                    variants[vkey] = variant
                    assert variant['html'] == originals[vkey]['html']
                    branches.append(releases[vkey[0]]['major'])
                assert len(branches) == len(set(branches)), (start, finish, 'same-branch merge')

            pair_decisions = []
            for omitted_entry in report['exclusions']:
                key = note_key(omitted_entry)
                matches = [note_key(ref) for ref in omitted_entry['matches']]
                reason, method = omitted_entry['reason'], omitted_entry['method']
                assert matches
                if reason == 'already_in_source':
                    assert set(matches) <= source_keys
                    assert omitted_entry['entry']['html'] == originals[key]['html']
                else:
                    assert set(matches) <= shown_set
                    assert key in variants
                required, _, fingerprint = identities[key]
                if method == 'commits':
                    supplied = set().union(*(identities[ref][1] for ref in matches))
                    if reason == 'backport_duplicate':
                        supplied.update(commit for ref in source_keys for commit in identities[ref][1]
                                        if compare._same_commit_scope(index, releases[key[0]], originals[key],
                                                                      {'version': ref[0], 'id': ref[1]}))
                    assert required and required <= supplied, (start, finish, key, 'incomplete commit evidence')
                    for ref in matches:
                        if releases[key[0]]['minor'] == 0 or releases[ref[0]]['minor'] == 0:
                            assert identities[ref][-1][-1] == fingerprint[-1], (key, ref, 'partial major backport')
                else:
                    assert all(identities[ref][-1] == fingerprint for ref in matches)
                    assert not required or all(not identities[ref][0] for ref in matches)
                decision = [source_id(key), reason, method, sorted(source_id(ref) for ref in matches)]
                pair_decisions.append(decision)
                decisions[(decision[0], reason, method, tuple(decision[3]))] = decision

            if releases[start]['major'] == releases[finish]['major']:
                same_branch += 1
                interval = [r for r in releases.values()
                            if r['major'] == releases[start]['major'] and
                            releases[start]['minor'] < r['minor'] <= releases[finish]['minor']]
                expected = [(r['version'], e['id']) for r in sorted(interval, key=lambda r: r['minor'], reverse=True)
                            for e in r['entries']]
                assert shown == expected, (start, finish, 'minor interval loss')
                assert not omitted
            else:
                cross_branch += 1

            row = {'from': start, 'to': finish, 'count': report['total'],
                   'source_known': report['already_in_source_count'], 'duplicates': report['duplicate_count'],
                   'digest': digest([report['history'], [source_id(key) for key in shown], pair_decisions]),
                   'cve_count': report['cve_count'],
                   'security_digest': digest([
                       [[cve['id'], cve.get('target_state_evidence')] for cve in report['cves']],
                       [cve['id'] for cve in report['security_regressions']],
                       [cve['id'] for cve in report['remaining_cves']],
                   ])}
            pairs.append(row)
            if (start, finish) in selected_examples:
                examples.append(dict(row, history=report['history'], candidates=report['candidate_count'],
                                     cves=report['cve_count']))
        print(f"Audited {number + 1}/{len(versions)} starting versions ({len(pairs)} pairs)", file=sys.stderr)

    return {'format': 1, 'snapshot_generated_at': snapshot['generated_at'],
            'release_count': len(versions), 'same_branch_pairs': same_branch, 'cross_branch_pairs': cross_branch,
            'pair_count': len(pairs), 'pair_digest': digest(pairs), 'examples': examples,
            'decision_count': len(decisions), 'decisions': list(decisions.values()), 'pairs': pairs}


def audit_chunk(data_and_numbers):
    source, security, numbers = data_and_numbers
    return audit(source, security, numbers)


def audit_parallel(source, security, jobs):
    count = sum(not r.get('placeholder') for r in source['releases'])
    # Load the activated DB manifest only once. Each worker receives the same
    # pinned dataset even if another process imports an update during the audit.
    chunks = [(source, security, set(range(offset, count, jobs))) for offset in range(jobs)]
    from django.db import connections
    connections.close_all()
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        partials = list(executor.map(audit_chunk, chunks))
    result = partials[0]
    pairs = sorted((pair for part in partials for pair in part['pairs']),
                   key=lambda p: (compare.version_key(p['from']), compare.version_key(p['to'])))
    decisions = {digest(decision): decision for part in partials for decision in part['decisions']}
    examples = sorted((example for part in partials for example in part['examples']),
                      key=lambda p: (compare.version_key(p['from']), compare.version_key(p['to'])))
    result.update(
        same_branch_pairs=sum(part['same_branch_pairs'] for part in partials),
        cross_branch_pairs=sum(part['cross_branch_pairs'] for part in partials),
        pair_count=len(pairs), pair_digest=digest(pairs), examples=examples,
        decision_count=len(decisions), decisions=list(decisions.values()), pairs=pairs,
    )
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument('--snapshot', type=Path, default=ROOT / 'data/compare/releases.json.gz')
    source_group.add_argument('--database', nargs='?', const='default', metavar='ALIAS',
                              help='Read active DB data using this Django database alias (default: default)')
    parser.add_argument('--language', choices=['zh', 'en'], help='Required for --database')
    parser.add_argument('--security', type=Path, default=ROOT / 'data/compare/security.json')
    parser.add_argument('--reference', type=Path, help='Verify every original field against this release snapshot')
    parser.add_argument('--security-reference', type=Path, help='Verify the active security data against this snapshot')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=1, help='Independent audit workers (default: 1)')
    args = parser.parse_args()
    if args.database:
        if not args.language:
            parser.error('--database requires --language zh or --language en')
        from pgweb.docs.compare_store import load_database_snapshot
        source = load_database_snapshot('releases', language=args.language, using=args.database)
        security = load_database_snapshot('security', language=args.language, using=args.database)
        origin = {'kind': 'database', 'alias': args.database, 'language': args.language,
                  'release_revision': source.database_revision, 'security_revision': security.database_revision}
    else:
        source, security = read(args.snapshot), read(args.security)
        origin = {'kind': 'snapshot', 'releases': str(args.snapshot), 'security': str(args.security),
                  'release_content_digest': digest(source), 'security_content_digest': digest(security)}
    if args.reference:
        reference = read(args.reference)
        verify_original_fields(reference, source)
        origin['reference_digest'] = digest(reference)
    if args.security_reference:
        reference = read(args.security_reference)
        verify_original_fields(reference, security, 'security')
        origin['security_reference_digest'] = digest(reference)
    singles = audit_single_releases(source, security)
    relations = audit_relations(source) if args.database else {}
    result = audit_parallel(source, security, args.jobs) if args.jobs > 1 else audit(source, security)
    result.update(singles, **relations, input=origin)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ('decisions', 'pairs')},
                     ensure_ascii=False, indent=2))
