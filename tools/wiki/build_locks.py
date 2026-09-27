#!/usr/bin/env python3
"""Build the lock atlas from immutable PostgreSQL source revisions.

Usage: .venv/bin/python tools/wiki/build_locks.py [--fetch] [--check]
Without --fetch all inputs must already exist in tmp/lock-sources/<revision>/.
--check reproduces the business payload and compares with the committed JSON.
No database or Django initialization is needed. Sources and output are UTF-8.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pgweb.wiki.lock_data import COVERAGE_NOTES, MODE_DEFINITIONS, REVISIONS, command_specs

PATHS = {
    'mvcc': 'doc/src/sgml/mvcc.sgml',
    'lock-source': 'src/backend/storage/lmgr/lock.c',
    'heap-source': 'src/backend/access/heap/heapam.c',
    'table-source': 'src/backend/commands/tablecmds.c',
    'index-source': 'src/backend/catalog/index.c',
    'copy-source': 'src/backend/commands/copy.c',
    'ri-source': 'src/backend/utils/adt/ri_triggers.c',
    'vacuum-source': 'src/backend/access/heap/vacuumlazy.c',
    'repack-source': 'src/backend/commands/repack.c',
}
C_MODES = dict(zip(
    ('AccessShareLock', 'RowShareLock', 'RowExclusiveLock',
     'ShareUpdateExclusiveLock', 'ShareLock', 'ShareRowExclusiveLock',
     'ExclusiveLock', 'AccessExclusiveLock'),
    [d[0] for d in MODE_DEFINITIONS[:8]],
))


def source_path(key, major):
    if key == 'vacuum-source' and int(major) <= 11:
        return 'src/backend/commands/vacuumlazy.c'
    return PATHS.get(key, 'doc/src/sgml/ref/' + key + '.sgml')


def load_source(cache, revision, path, fetch, source_repo=None):
    location = cache / revision / path
    url = f'https://raw.githubusercontent.com/postgres/postgres/{revision}/{path}'
    if not location.exists() and source_repo:
        # A local clone is only a transport optimization: read the exact pinned
        # Git object, never its working files or whatever branch is checked out.
        found = subprocess.run(['git', '-C', str(source_repo), 'show', f'{revision}:{path}'],
                               capture_output=True)
        if found.returncode == 0:
            location.parent.mkdir(parents=True, exist_ok=True)
            location.write_bytes(found.stdout)
    if not location.exists():
        if not fetch:
            raise ValueError(f'Missing cached source {location}; use --fetch')
        location.parent.mkdir(parents=True, exist_ok=True)
        partial = location.with_suffix(location.suffix + '.partial')
        download = subprocess.run(['curl', '--fail', '--location', '--compressed', '--silent', '--show-error',
                                   '--retry', '1', '--retry-all-errors', '--max-time', '30', '--user-agent',
                                   'PGSQL.CC lock atlas source builder', url, '-o', str(partial)])
        if download.returncode:
            # Same immutable blob via the GitHub contents API. Check Git's blob
            # digest as well as the SHA-256 stored in the output provenance.
            fallback = f'https://api.github.com/repos/postgres/postgres/contents/{path}?ref={revision}'
            request = urllib.request.Request(fallback, headers={
                'Accept': 'application/vnd.github+json', 'User-Agent': 'PGSQL.CC source builder'})
            with urllib.request.urlopen(request, timeout=45) as response:
                blob = json.load(response)
            data = base64.b64decode(blob['content'])
            digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if digest != blob['sha']:
                raise ValueError(f'Git blob checksum mismatch: {path}@{revision}')
            partial.write_bytes(data)
            location.with_suffix(location.suffix + '.metadata.json').write_text(json.dumps({
                'retrieval_url': fallback, 'git_blob_sha1': digest}))
        partial.replace(location)
    raw = location.read_bytes()
    evidence = dict(url=url, sha256=hashlib.sha256(raw).hexdigest(),
                    revision=revision, path=path,
                    kind='source' if path.startswith('src/') else
                    ('documentation' if path.endswith('mvcc.sgml') else 'command-documentation'))
    return raw.decode(), evidence


def text(markup):
    return ' '.join(re.sub(r'<[^>]*>', '', markup).split())


def mode_slug(label):
    label = label.replace('EXCL.', 'EXCLUSIVE')
    return label.lower().replace(' ', '-')


def parse_matrix(sgml, scope):
    match = re.search(r'<table\b[^>]*\bid="' + scope + r'-lock-compatibility"[^>]*>.*?</table>', sgml, re.S)
    if not match:
        raise ValueError(f'Missing {scope} matrix')
    # These are deliberately small CALS tables with one explicit entry per
    # value. Older SGML permits unclosed colspec tags, so it is not XML.
    table = match.group(0)
    head = re.search(r'<thead>(.*?)</thead>', table, re.S).group(1)
    header_row = re.findall(r'<row>(.*?)</row>', head, re.S)[-1]
    headers = [mode_slug(text(n)) for n in re.findall(r'<entry\b[^>]*>(.*?)</entry>', header_row, re.S)]
    expected = [d[0] for d in MODE_DEFINITIONS if d[4] == scope]
    if headers != expected:
        raise ValueError(f'Unexpected {scope} headers {headers}')
    result = {}
    body = re.search(r'<tbody>(.*?)</tbody>', table, re.S).group(1)
    for row in re.findall(r'<row>(.*?)</row>', body, re.S):
        cells = re.findall(r'<entry\b[^>]*>(.*?)</entry>', row, re.S)
        if len(cells) != len(headers) + 1:
            raise ValueError('Incomplete matrix row')
        values = [text(c) for c in cells[1:]]
        if any(v not in ('', 'X') for v in values):
            raise ValueError('Unknown matrix symbol')
        result[mode_slug(text(cells[0]))] = [h for h, v in zip(headers, values) if v == 'X']
    if list(result) != expected:
        raise ValueError('Incomplete matrix')
    for a, conflicts in result.items():
        for b in result:
            if (b in conflicts) != (a in result[b]):
                raise ValueError(f'Asymmetric {a}/{b}')
    return result


def parse_lock_source(source):
    body = re.search(r'LockConflicts\[\]\s*=\s*\{(.*?)\n\};', source, re.S).group(1)
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    entries = body.split(',')
    if len(entries) != 9:
        raise ValueError('Unexpected LockConflicts layout')
    result = {}
    for mode, entry in zip(C_MODES.values(), entries[1:]):
        result[mode] = [C_MODES[n] for n in re.findall(r'LOCKBIT_ON\((\w+)\)', entry)]
    return result


def check_tuple_source(source, relation_conflicts, row_conflicts):
    body = re.search(r'tupleLockExtraInfo\[[^\]]*\]\s*=\s*\{(.*?)\n\};', source, re.S).group(1)
    # Older releases use positional initializers; newer releases designated ones.
    mapped = re.findall(r'\b(' + '|'.join(C_MODES) + r')\b', re.sub(r'/\*.*?\*/', '', body, flags=re.S))
    if len(mapped) != 4:
        raise ValueError('Unexpected tupleLockExtraInfo layout')
    row_names = [d[0] for d in MODE_DEFINITIONS[8:]]
    derived = {a: [b for b, target in zip(row_names, mapped)
                   if C_MODES[target] in relation_conflicts[C_MODES[owner]]]
               for a, owner in zip(row_names, mapped)}
    if derived != row_conflicts:
        raise ValueError('Row documentation/source conflict disagreement')


def parse_alter_modes(source):
    body = source.split('\nAlterTableGetLockLevel(List *cmds)', 1)[1].split('\n}\n', 1)[0]
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    result = {}
    cases = list(re.finditer(r'case (AT_\w+):', body))
    for index, match in enumerate(cases):
        end = body.find('break;', match.end())
        block = body[match.end():end]
        values = re.findall(r'cmd_lockmode\s*=\s*(\w+Lock)\s*;', block)
        if len(set(values)) == 1:
            result[match.group(1)] = C_MODES[values[0]]
    return result


def check_command_evidence(major, sources):
    """Fail closed if the particularly easy-to-confuse source rules change."""
    checks = {
        'copy-source': [r'is_from\s*\?\s*RowExclusiveLock\s*:\s*AccessShareLock'],
        'index-source': [r'(?:heap|table)_open\(heapId,\s*ShareLock\)',
                         r'index_open\(indexId,\s*AccessExclusiveLock\)'],
        'ri-source': [r'FOR KEY SHARE OF x', r'(?:heap|table)_open\([^;]*RowShareLock\)'],
        'vacuum-source': [r'ConditionalLockRelation(?:Oid)?\([^;]*AccessExclusiveLock\)'],
        'table-source': [r'parent_rel\s*=\s*(?:heap|table)_openrv\(parent,\s*ShareUpdateExclusiveLock\)',
                         r'parent_rel\s*=\s*(?:heap|table)_openrv\(parent,\s*AccessShareLock\)'],
    }
    for key, patterns in checks.items():
        for pattern in patterns:
            if not re.search(pattern, sources[major, key][0], re.S):
                raise ValueError(f'PG{major}: verify changed command evidence {key}: {pattern}')
    if int(major) >= 12 and 'SHARE UPDATE EXCLUSIVE' not in text(sources[major, 'reindex'][0]):
        raise ValueError(f'PG{major}: missing concurrent reindex documentation')
    if int(major) >= 19:
        if 'DO SELECT [ FOR { UPDATE | NO KEY UPDATE | SHARE | KEY SHARE } ]' not in sources[major, 'insert'][0]:
            raise ValueError(f'PG{major}: missing DO SELECT row lock syntax')
        repack = sources[major, 'repack-source'][0]
        if not re.search(r'return ShareUpdateExclusiveLock;.*?return AccessExclusiveLock;', repack, re.S):
            raise ValueError(f'PG{major}: verify changed REPACK phases')


def command_source_url(major, slug, key, evidence):
    docslug = 'devel' if major == '20' else major
    if evidence['kind'] == 'source':
        return evidence['url'].replace('raw.githubusercontent.com/postgres/postgres/',
                                       'github.com/postgres/postgres/blob/')
    filename = 'explicit-locking' if key == 'mvcc' else 'sql-' + key.replace('_', '')
    return f'https://www.postgresql.org/docs/{docslug}/{filename}.html'


def build(cache, fetch, source_repo=None):
    specs = command_specs()
    jobs = []
    for major, (_, revision) in REVISIONS.items():
        keys = {'mvcc', 'lock-source', 'heap-source', 'table-source'}
        keys.update(s['source'] for s in specs if s['minimum'] <= int(major) <= s['maximum'])
        for key in sorted(keys):
            jobs.append((major, key, revision, source_path(key, major)))
    def read(job):
        major, key, revision, path = job
        return (major, key), load_source(cache, revision, path, fetch, source_repo)
    with ThreadPoolExecutor(max_workers=12) as pool:
        sources = dict(pool.map(read, jobs))
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    modes = [dict(slug=d[0], name=d[1], name_zh=d[2], abbrev=d[3], scope=d[4],
                  summary=d[5], position=i, versions={}) for i, d in enumerate(MODE_DEFINITIONS)]
    versions = []
    coverage = {}
    for major, (ref, revision) in REVISIONS.items():
        relation = parse_matrix(sources[major, 'mvcc'][0], 'table')
        row = parse_matrix(sources[major, 'mvcc'][0], 'row')
        code_relation = parse_lock_source(sources[major, 'lock-source'][0])
        if code_relation != relation:
            raise ValueError(f'PG{major}: table documentation/source disagreement')
        check_tuple_source(sources[major, 'heap-source'][0], code_relation, row)
        alter_modes = parse_alter_modes(sources[major, 'table-source'][0])
        check_command_evidence(major, sources)
        all_conflicts = {**relation, **row}
        all_evidence = [evidence for (v, _), (_, evidence) in sources.items() if v == major]
        matrix_evidence = [sources[major, key][1] for key in ('mvcc', 'lock-source', 'heap-source')]
        commands = {d[0]: [] for d in MODE_DEFINITIONS}
        skipped = []
        for spec in specs:
            if not spec['minimum'] <= int(major) <= spec['maximum']:
                continue
            mode = spec['mode']
            if mode == 'from-source':
                mode = alter_modes.get(spec['enum'])
                if not mode:
                    if ('case ' + spec['enum'] + ':') in sources[major, 'table-source'][0]:
                        raise ValueError(f'PG{major} unsupported lock decision for {spec["enum"]}')
                    skipped.append(spec['label'])
                    continue
            evidence = sources[major, spec['source']][1]
            variant = hashlib.sha256((spec['slug']+'|'+spec['label']).encode()).hexdigest()[:12]
            commands[mode].append(dict(slug=spec['slug'], label=spec['label'],
                                       note=spec['note'], variant=variant,
                                       source_url=command_source_url(major, spec['slug'], spec['source'], evidence),
                                       source=evidence))
        for mode in modes:
            mode['versions'][major] = dict(conflicts=all_conflicts[mode['slug']],
                                           commands=commands[mode['slug']], sources=matrix_evidence)
        versions.append(dict(major=major, label=('19 beta4' if major=='19' else '20 devel' if major=='20' else major),
                             status=('preview' if major=='19' else 'devel' if major=='20' else 'stable' if major=='18' else 'historical'),
                             doc_slug='devel' if major=='20' else major, revision=revision, ref=ref,
                             fetched_at=now, sources=all_evidence,
                             official_url=f'https://www.postgresql.org/docs/{"devel" if major=="20" else major}/explicit-locking.html'))
        coverage[major] = dict(table_cells=64, row_cells=16, verified_against_source=True,
                               command_associations=sum(map(len, commands.values())),
                               command_variants=len({c['variant'] for cs in commands.values() for c in cs}),
                               unavailable_alter_variants=skipped)
    return dict(format=1, generated_at=now, default_major='18', versions=versions,
                modes=modes, coverage=dict(versions=coverage, notes=COVERAGE_NOTES,
                                          discovery_url='https://pglocks.org/'))


def semantic(snapshot):
    # Observation time is not a fact change; all source revisions/hashes remain.
    snapshot = json.loads(json.dumps(snapshot))
    snapshot.pop('generated_at', None)
    for version in snapshot['versions']:
        version.pop('fetched_at', None)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--cache', type=Path, default=ROOT / 'tmp/lock-sources')
    parser.add_argument('--source-repo', type=Path, help='Read exact pinned objects from a local PostgreSQL clone before fetching')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/wiki/locks.json')
    args = parser.parse_args()
    snapshot = build(args.cache, args.fetch, args.source_repo)
    if args.check:
        if semantic(snapshot) != semantic(json.loads(args.output.read_text())):
            raise SystemExit('Snapshot differs from pinned source and editorial definitions')
        print('Verified committed snapshot against all pinned source inputs.')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(snapshot['coverage']['versions'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
