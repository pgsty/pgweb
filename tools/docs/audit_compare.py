#!/usr/bin/env python3
"""Exhaustively check comparison accounting and emit a bilingual audit digest.

This checks every selectable version pair against the source snapshot, preserving
full note bodies and identifying every omitted row with its supporting source.
It complements (does not replace) the independent SGML/source-coverage audit.
"""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
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
    selected_examples = {('17.0', '18.0'), ('17.0', '18.6'), ('17.11', '18.6'),
                         ('18.0', '18.6'), ('10.0', '18.6')}

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
                branches = [key[0].split('.')[0]]
                for variant in item['variants']:
                    vkey = note_key(variant)
                    assert vkey not in variants, (start, finish, 'duplicate variant')
                    variants[vkey] = variant
                    assert variant['html'] == originals[vkey]['html']
                    branches.append(vkey[0].split('.')[0])
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
                   'digest': digest([report['history'], [source_id(key) for key in shown], pair_decisions])}
            pairs.append(row)
            if (start, finish) in selected_examples:
                examples.append(dict(row, history=report['history'], candidates=report['candidate_count'],
                                     cves=report['cve_count']))
        print(f"Audited {number + 1}/{len(versions)} starting versions ({len(pairs)} pairs)", file=sys.stderr)

    return {'format': 1, 'snapshot_generated_at': snapshot['generated_at'],
            'release_count': len(versions), 'same_branch_pairs': same_branch, 'cross_branch_pairs': cross_branch,
            'pair_count': len(pairs), 'pair_digest': digest(pairs), 'examples': examples,
            'decision_count': len(decisions), 'decisions': list(decisions.values()), 'pairs': pairs}


def audit_chunk(paths_and_numbers):
    source_path, security_path, numbers = paths_and_numbers
    return audit(read(source_path), read(security_path), numbers)


def audit_parallel(source_path, security_path, jobs):
    source = read(source_path)
    count = sum(not r.get('placeholder') for r in source['releases'])
    chunks = [(source_path, security_path, set(range(offset, count, jobs))) for offset in range(jobs)]
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
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'data/compare/releases.json.gz')
    parser.add_argument('--security', type=Path, default=ROOT / 'data/compare/security.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=1, help='Independent audit workers (default: 1)')
    args = parser.parse_args()
    result = (audit_parallel(args.snapshot, args.security, args.jobs) if args.jobs > 1 else
              audit(read(args.snapshot), read(args.security)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ('decisions', 'pairs')},
                     ensure_ascii=False, indent=2))
