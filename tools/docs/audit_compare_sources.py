#!/usr/bin/env python3
"""Independently audit release inventory, upstream provenance and every entry.

Reads the official archive and the English release SGML carried by independently
verified source archives. It does not derive the expected version list from the
Django version table, the comparison builder, or the snapshot being checked.
Use --refresh for a new online observation, --offline to replay cached evidence.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Comment, Tag

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pgweb.docs.compare_data import sgml_commit_entries  # noqa: E402

ARCHIVE_URL = 'https://www.postgresql.org/docs/release/'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url, cache, offline, refresh):
    path = cache / (digest(url.encode()) + '.body')
    if path.exists() and not refresh:
        return path.read_bytes()
    if offline:
        raise ValueError('Missing offline evidence: ' + url)
    with urlopen(Request(url, headers={'User-Agent': 'PGSQL.CC-release-audit/2'}), timeout=90) as response:
        data = response.read()
    path.write_bytes(data)
    return data


def parse_source(data):
    # xref and anchor are declared EMPTY in old SGML, even without '/>'.
    data = re.sub(r'<(xref|anchor)\b([^>]*?)/?>', r'<\1\2/>', data)
    # DocBook link is NOT the void HTML <link> metadata element.
    data = re.sub(r'<(/?)link\b', r'<\1sgmllink', data)
    return BeautifulSoup(data, 'html.parser')


def inventory(soup):
    result = {}
    for release in soup.find_all('sect1'):
        match = re.fullmatch(r'release-(\d+)(?:-(\d+))?', release.get('id', ''), re.I)
        if not match:
            continue
        version = '{}.{}'.format(match[1], match[2] or 0)
        parts = {'migration': [], 'changes': []}
        for section in release.find_all('sect2'):
            heading = section.find('title', recursive=False)
            label = heading.get_text().strip() if heading else ''
            kind = 'changes' if re.fullmatch('Changes|变更|更改|变化', label, re.I) else 'migration' if re.search('Migration|迁移|Incompatibilit|不兼容', label, re.I) else None
            if kind:
                parts[kind].extend(item for item in section.find_all('listitem') if not item.find_parent('listitem'))
        # Formalpara date must come before Changes, not a date quoted in prose.
        formal = release.find('formalpara')
        text = formal.get_text(' ', strip=True) if formal else ''
        date = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text)
        parts['date'] = date[1] if date else ''
        result[version] = parts
    return result


def comparable_body(raw, html):
    """Compare ALL translated prose, ignoring only documented renderer output.

    DocBook expands xrefs into localized chapter numbers or target names. Links
    to those same targets are ignored on both sides. Their target identity is
    separately audited. Whitespace, curly quotes, section signs, soft hyphens and
    the trademark glyph are renderer typography; other punctuation is retained.
    """
    targets = {node.get('linkend', '').lower() for node in raw.find_all('xref')}
    outputs = []
    for source, native in [(raw, True), (html, False)]:
        node = BeautifulSoup(str(source), 'html.parser')
        for comment in node.find_all(string=lambda n: isinstance(n, Comment)):
            comment.extract()
        for link in list(node.find_all(['a', 'ulink', 'xref', 'sgmllink'])):
            if link.attrs is None:
                continue
            href = link.get('href', '')
            parsed = urlsplit(href)
            target = (parsed.fragment or Path(parsed.path).stem).lower()
            if (link.name == 'xref' or link.get_text().strip() == '§' or
                    link.name == 'sgmllink' and link.get('linkend', '').lower() in targets or
                    href.startswith('/docs/') and target in targets):
                link.decompose()
        outputs.append(re.sub(r'[\s“”‘’"\u00ad§®]+', '', node.get_text()))
    return outputs


def structure(item):
    # Translation may change inline markup, but must preserve paragraphs,
    # executable examples and nested recovery procedures in full.
    return dict(Counter(node.name for node in item.find_all(['para', 'programlisting', 'screen', 'listitem'])))


def branch_groups(texts):
    """Independent line-oriented reading of every upstream Author block.

    In particular, a Branch line may contain a Release annotation before its
    hash. This verifier intentionally does not reuse the builder's expression.
    """
    parents = {}

    def root(commit):
        parents.setdefault(commit, commit)
        while parents[commit] != commit:
            commit = parents[commit]
        return commit

    for text in texts:
        for comment in re.findall(r'<!--(.*?)-->', text, re.S):
            groups = []
            seen_branches = set()
            for line in comment.splitlines():
                if line.startswith('Author:'):
                    groups.append([])
                    seen_branches = set()
                elif line.startswith('Branch:'):
                    commit = re.search(r'\[([a-f0-9]{7,40})\]', line)
                    if commit:
                        branch = line.split()[1]
                        if not groups or branch in seen_branches:
                            groups.append([])
                            seen_branches = set()
                        groups[-1].append(commit[1])
                        seen_branches.add(branch)
            for group in groups:
                if group:
                    for commit in group[1:]:
                        parents[root(commit)] = root(group[0])
                    root(group[0])
    sets = {}
    for commit in parents:
        sets.setdefault(root(commit), []).append(commit)
    return {commit: sorted(sets[root(commit)]) for commit in parents}


def entry_commits(item, major):
    """Read comment and link identifiers independently of the builder."""
    comments = list(item.find_all(string=lambda node: isinstance(node, Comment)))
    for sibling in item.previous_siblings:
        if isinstance(sibling, Comment):
            comments.append(sibling)
        elif isinstance(sibling, Tag) or str(sibling).strip():
            break
    commits = set()
    for comment in comments:
        blocks = []
        seen_branches = set()
        for line in str(comment).splitlines():
            branch = line.split()[1] if line.startswith('Branch:') else None
            if line.startswith('Author:') or not blocks or branch and branch in seen_branches:
                blocks.append([])
                seen_branches = set()
            blocks[-1].append(line)
            if branch:
                seen_branches.add(branch)
        for block in blocks:
            branches = []
            for line in block:
                found = re.search(r'\[([a-f0-9]{7,40})\]', line)
                if found and line.startswith('Branch:'):
                    branches.append((line.split()[1], found[1]))
                elif found and re.match(r'^\d{4}-\d{2}-\d{2}\s', line):
                    commits.add(found[1])
            if branches:
                matching = [commit for branch, commit in branches if branch == 'REL_{}_STABLE'.format(major)]
                commits.add(matching[0] if matching else branches[0][1])
    for link in item.find_all('ulink', url=True):
        url = link['url']
        if 'commit_baseurl' in url or 'postgr.es/c/' in url:
            found = re.search(r'([a-f0-9]{7,40})$', url)
            if found:
                commits.add(found[1])
    return sorted(commits)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pgdoc-root', type=Path, default=ROOT.parent / 'pgdoc')
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'data/compare/releases.json.gz')
    parser.add_argument('--language', choices=['zh', 'en'], default='zh')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/compare/source-audit.json')
    parser.add_argument('--cache', type=Path, default=ROOT / 'tmp/compare-source-audit')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    if args.offline and args.refresh:
        parser.error('--offline and --refresh are mutually exclusive')
    args.cache.mkdir(parents=True, exist_ok=True)
    archive = fetch(ARCHIVE_URL, args.cache, args.offline, args.refresh)
    official = sorted({a.get_text(strip=True) for a in BeautifulSoup(archive, 'html.parser').find_all('a') if re.fullmatch(r'\d+\.\d+', a.get_text(strip=True)) and int(a.get_text(strip=True).split('.')[0]) >= 10}, key=lambda value: tuple(map(int, value.split('.'))))
    if not official or official[0] != '10.0':
        raise ValueError('Official archive did not yield the expected PostgreSQL 10+ inventory')
    snapshot_bytes = args.snapshot.read_bytes()
    snapshot = json.loads(gzip.decompress(snapshot_bytes))
    actual = [r['version'] for r in snapshot['releases'] if r['status'] == 'stable']
    errors = []
    if actual != official:
        errors.append({'kind': 'release_inventory', 'missing': sorted(set(official) - set(actual)), 'unexpected': sorted(set(actual) - set(official))})
    metadata = json.loads((args.pgdoc_root / 'en/SOURCES.json').read_text())
    by_build = {item['version']: item for item in metadata['entries'] + metadata.get('incremental_imports', [])}
    sources = {}
    provenance = []
    builds = {r['major']: r['manual_build'] for r in snapshot['releases']}

    def verify_source(pair):
        major, build = pair
        path = args.pgdoc_root / 'en' / build / ('release-' + major + '.sgml')
        body = path.read_bytes()
        meta = by_build[build]
        row = {'major': major, 'build': build, 'file': str(path.relative_to(args.pgdoc_root)), 'sha256': digest(body)}
        if meta.get('kind') == 'git-tag':
            url = 'https://raw.githubusercontent.com/postgres/postgres/{}/doc/src/sgml/release-{}.sgml'.format(meta['commit'], major)
            expected = fetch(url, args.cache, args.offline, args.refresh)
            row.update({'url': url, 'git_commit': meta['commit'], 'verified': body == expected})
        elif 'archive' in meta:
            # A devel placeholder is recorded as such, with no claim of an
            # immutable latest development version or release date.
            archive_path = args.pgdoc_root / meta['archive']
            checksum_url = meta['url'] + '.sha256'
            expected_sha = fetch(checksum_url, args.cache, args.offline, args.refresh).decode().split()[0]
            archive_sha = digest(archive_path.read_bytes())
            member = '{}/doc/src/sgml/release-{}.sgml'.format(meta['archive_root'], major)
            with tarfile.open(archive_path) as tar:
                expected = tar.extractfile(member).read()
            row.update({'url': meta['url'], 'checksum_url': checksum_url, 'archive_sha256': archive_sha, 'verified': body == expected and archive_sha == expected_sha == meta['archive_sha256']})
        else:
            raise ValueError('Unverifiable source build: ' + build)
        return major, row, body.decode()

    # The development placeholder contains no entries and is not a selectable
    # comparison target. Scope proof concerns releases plus the beta snapshot.
    pairs = [(major, build) for major, build in builds.items() if any(r['major'] == major and r['entries'] for r in snapshot['releases'])]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for major, row, text in pool.map(verify_source, pairs):
            provenance.append(row)
            if not row['verified']:
                errors.append({'kind': 'source_authenticity', 'major': major})
            zh = (args.pgdoc_root / 'zh' / major / ('release-' + major + '.sgml')).read_text()
            sources[major] = {'en': inventory(parse_source(text)), 'zh': inventory(parse_source(zh)), 'canonical': sgml_commit_entries(text, major), 'text': text, 'zh_sha256': digest(zh.encode())}
    aliases = branch_groups([source['text'] for source in sources.values()])
    reports = []
    totals = Counter()
    structure_differences = []
    for release in snapshot['releases']:
        if not release['entries']:
            continue
        version = release['version']
        source = sources[release['major']]
        en = source['en'].get(version)
        zh = source['zh'].get(version)
        if en is None or zh is None:
            errors.append({'kind': 'source_release_missing', 'version': version})
            continue
        row = {'version': version, 'status': release['status'], 'date': release['date'], 'changes': len(en['changes']), 'migration': len(en['migration']), 'cves': [], 'entries_verified': 0}
        if release['status'] == 'stable' and en['date'] != release['date']:
            errors.append({'kind': 'release_date', 'version': version, 'expected': en['date'], 'actual': release['date']})
        cves = set()
        for kind in ['migration', 'changes']:
            entries = release['entries'][:release['compatibility_count']] if kind == 'migration' else release['entries'][release['compatibility_count']:]
            if len(en[kind]) != len(zh[kind]) or len(en[kind]) != len(entries):
                errors.append({'kind': 'entry_count', 'version': version, 'part': kind, 'en': len(en[kind]), 'zh': len(zh[kind]), 'snapshot': len(entries)})
                continue
            for index, (original, translated, entry) in enumerate(zip(en[kind], zh[kind], entries)):
                key = '{}/{}/{:03d}'.format(version, kind, index + 1)
                canonical = source['canonical'][version][kind][index]
                expected_cves = sorted(set(re.findall(r'\bCVE-\d{4}-\d+\b', original.get_text())))
                if entry['cves'] != expected_cves:
                    errors.append({'kind': 'cve_set', 'entry': key})
                cves.update(expected_cves)
                bodies = comparable_body(translated if args.language == 'zh' else original, entry['html'])
                if bodies[0] != bodies[1]:
                    errors.append({'kind': 'complete_rendered_body', 'entry': key})
                if structure(original) != structure(translated):
                    structure_differences.append({'entry': key, 'en': structure(original), 'zh': structure(translated)})
                commits = entry_commits(original, release['major'])
                translated_commits = entry_commits(translated, release['major'])
                original_ids = {alias for commit in commits for alias in aliases.get(commit, [commit])}
                translated_ids = {alias for commit in translated_commits for alias in aliases.get(commit, [commit])}
                if original_ids or translated_ids:
                    if not original_ids.intersection(translated_ids):
                        errors.append({'kind': 'bilingual_entry_alignment', 'entry': key, 'en': commits, 'zh': translated_commits})
                    else:
                        totals['bilingual_entries_with_matching_commits'] += 1
                else:
                    totals['bilingual_entries_without_commit_evidence'] += 1
                if commits != canonical['commits']:
                    errors.append({'kind': 'source_commit_extraction', 'entry': key, 'expected': commits, 'actual': canonical['commits']})
                expected_groups = sorted({tuple(aliases.get(commit, [commit])) for commit in commits})
                if [list(group) for group in expected_groups] != entry.get('commit_groups'):
                    errors.append({'kind': 'commit_groups', 'entry': key})
                if canonical['identity_text'] != entry.get('identity_text') or key != entry.get('source_entry_id'):
                    errors.append({'kind': 'canonical_identity', 'entry': key})
                row['entries_verified'] += 1
                totals['entries'] += 1
                totals['entries_with_source_commits'] += bool(commits)
                totals['entries_without_source_commits'] += not bool(commits)
                totals['paragraphs'] += len(original.find_all('para'))
                totals['examples'] += len(original.find_all(['programlisting', 'screen']))
                totals['nested_items'] += len(original.find_all('listitem'))
        row['cves'] = sorted(cves)
        reports.append(row)
    report = {
        'format': 1, 'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'inventory_url': ARCHIVE_URL, 'inventory_sha256': digest(archive),
        'snapshot_sha256': digest(snapshot_bytes), 'minimum_major': 10, 'language': args.language,
        'stable_release_count': len(official), 'stable_versions': official,
        'unreleased_skips': ['18.5'], 'preview_builds': [r['build'] for r in snapshot['releases'] if r['status'] == 'preview'],
        'sources': sorted(provenance, key=lambda row: int(row['major'])),
        'translated_sources': [{'major': major, 'sha256': source['zh_sha256']} for major, source in sorted(sources.items(), key=lambda item: int(item[0]))],
        'totals': dict(totals), 'releases': reports,
        'structure_differences': structure_differences, 'errors': errors,
        'body_verification': 'Every translated entry is compared in full after removing only whitespace/renderer typography and generated cross-reference labels. Per-entry counts, dates, CVE sets, canonical identities and distinct commit groups are checked independently against English source SGML. Translation semantics are not established by structural checks alone.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'stable_releases': len(official), 'totals': totals, 'structure_differences': len(structure_differences), 'errors': len(errors), 'output': str(args.output)}, ensure_ascii=False))
    return bool(errors or structure_differences)


if __name__ == '__main__':
    sys.exit(main())
