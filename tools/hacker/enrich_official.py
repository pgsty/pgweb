#!/usr/bin/env python3
"""Add explicitly matched PostgreSQL contributor facts to a PGNexus snapshot.

Raw official pages and their SHA-256 manifest are kept under tmp/hacker/official.
Only exact full names (ignoring case, accents and whitespace) are matched; no
aliases, reordered names or organization guesses are used. Original PGNexus
fields remain unchanged. The output can be passed to the normal hacker importer.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import unicodedata
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    'contributors': 'https://www.postgresql.org/community/contributors/',
    'committers': 'https://www.postgresql.org/developer/committers/',
    'core': 'https://www.postgresql.org/developer/core/',
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def normalized_name(name):
    value = unicodedata.normalize('NFKD', name)
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(value.casefold().split())


def archive_sources(folder, refresh=False, contributors_html=None):
    folder.mkdir(parents=True, exist_ok=True)
    if contributors_html:
        destination = folder / 'contributors.html'
        if contributors_html.resolve() != destination.resolve():
            shutil.copy2(contributors_html, destination)
    metadata = []
    for key, url in SOURCES.items():
        path = folder / (key + '.html')
        if refresh or not path.exists():
            request = Request(url, headers={
                'User-Agent': 'PGSQL.CC public PostgreSQL developer directory archival',
            })
            with urlopen(request, timeout=45) as response:
                content = response.read()
            path.write_bytes(content)
        raw = path.read_bytes()
        metadata.append({
            'key': key,
            'url': url,
            'path': path.name,
            'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw),
            'retrieved_at': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        })
    write_json(folder / 'sources.json', metadata)
    return metadata


def parse_identity(cell):
    parts = list(cell.stripped_strings)
    if not parts:
        return None
    heading = parts[0]
    match = re.fullmatch(r'(.+?)\s*\(([^()]+)\)', heading)
    name, email = heading, ''
    if match:
        candidate = match.group(2).replace(' at ', '@').replace(' dot ', '.')
        if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', candidate):
            name, email = match.group(1).strip(), candidate
    rest = parts[1:]
    organization = rest[0] if len(rest) >= 2 else ''
    location = rest[-1] if rest else ''
    link = cell.find('a', href=True)
    organization_url = link['href'] if link else ''
    if link:
        organization = link.get_text(' ', strip=True)
        if len(rest) == 1:
            location = ''
    return {
        'name': name,
        'email': email,
        'organization': organization,
        'organization_url': organization_url,
        'location': location,
        'original_text': cell.get_text('\n', strip=True),
    }


def parse_contributors(path):
    soup = BeautifulSoup(path.read_bytes(), 'html.parser')
    people = []
    for table in soup.select('table.contributor-table'):
        heading = table.find_previous('h2')
        if heading is None:
            raise ValueError('Official contributor table has no category heading')
        role = heading.get_text(' ', strip=True)
        detailed = bool(table.select('th'))
        for row in table.select('tbody tr'):
            cells = row.find_all('td', recursive=False)
            identity_cells = cells[:1] if detailed else cells
            for cell in identity_cells:
                person = parse_identity(cell)
                if person:
                    person.update({
                        'role': role,
                        'contribution': cells[1].get_text(' ', strip=True) if detailed and len(cells) > 1 else '',
                        'source_url': SOURCES['contributors'],
                    })
                    people.append(person)
    if not people:
        raise ValueError('No official contributor profiles found; source layout may have changed')
    return people


def parse_committers(path):
    soup = BeautifulSoup(path.read_bytes(), 'html.parser')
    heading = next((h for h in soup.select('#pgContentWrap h2')
                    if h.get_text(' ', strip=True) == 'Committers'), None)
    if heading is None:
        raise ValueError('Official committer heading not found')
    names = [li.get_text(' ', strip=True) for li in heading.find_next('ul').find_all('li')]
    if not names:
        raise ValueError('No official committers found')
    return names


def unique_index(people):
    result = {}
    for person in people:
        result.setdefault(normalized_name(person['name']), []).append(person)
    return result


def make_enrichment(profiles, official_people, committers, metadata):
    index = unique_index(official_people)
    committer_index = unique_index([{'name': name} for name in committers])
    by_key = {source['key']: source for source in metadata}
    matches, unmatched, ambiguous = {}, [], []
    seen = set()
    for profile in profiles:
        source_id = str(profile.get('source_id', profile.get('id', '')))
        if not source_id or source_id in seen:
            raise ValueError('Snapshot contains missing or duplicate source_id: ' + source_id)
        seen.add(source_id)
        name = profile['name']
        candidates = index.get(normalized_name(name), [])
        committer_candidates = committer_index.get(normalized_name(name), [])
        if len(candidates) > 1 or len(committer_candidates) > 1:
            ambiguous.append({'source_id': source_id, 'name': name})
            continue
        if not candidates and not committer_candidates:
            unmatched.append({'source_id': source_id, 'name': name})
            continue
        person = candidates[0] if candidates else None
        official = {key: person[key] if person else '' for key in (
            'role', 'organization', 'organization_url', 'location', 'contribution', 'source_url', 'original_text',
        )}
        official['name'] = person['name'] if person else committer_candidates[0]['name']
        official['roles'] = []
        sources = []
        emails = []
        if person:
            sources.append(by_key['contributors'])
            official['roles'].append({'role': person['role'], 'source_url': person['source_url']})
            if person['email']:
                emails.append({'email': person['email'], 'source_url': person['source_url']})
        if committer_candidates:
            sources.append(by_key['committers'])
            official['roles'].append({'role': 'Committer', 'source_url': SOURCES['committers']})
            if not person:
                official.update(role='Committer', source_url=SOURCES['committers'])
        if person and person['role'] == 'Core Team':
            sources.append(by_key['core'])
        matches[source_id] = {
            'source_id': source_id,
            'name': name,
            'match': 'exact' if name == official['name'] else 'normalized_full_name',
            'emails': emails,
            'official': official,
            'sources': sources,
        }
    report = {
        'input_count': len(profiles),
        'official_contributor_count': len(official_people),
        'official_committer_count': len(committers),
        'matched_count': len(matches),
        'email_profile_count': sum(bool(entry['emails']) for entry in matches.values()),
        'unmatched': unmatched,
        'ambiguous': ambiguous,
    }
    return matches, report


def enrich(snapshot, matches):
    result = deepcopy(snapshot)
    for profile in result['profiles']:
        source_id = str(profile.get('source_id', profile.get('id', '')))
        match = matches.get(source_id)
        if not match:
            continue
        data = profile.setdefault('data', {})
        data['official'] = match['official']
        data['official_sources'] = match['sources']
        data['official_match'] = match['match']
        emails = data.setdefault('emails', [])
        for email in match['emails']:
            if email not in emails:
                emails.append(email)
    return result


def add_review_notes(snapshot, review):
    """Retain independently checked source identity questions on each record."""
    added = 0
    for profile in snapshot['profiles']:
        source_id = str(profile.get('source_id', profile.get('id', '')))
        note = review.get('profiles', {}).get(source_id)
        if note:
            notes = profile.setdefault('data', {}).setdefault('review_notes', [])
            if note not in notes:
                notes.append(deepcopy(note))
                added += 1
    return added


def add_external_sources(snapshot, supplement):
    """Merge separately verified professional references, retaining their sources."""
    for profile in snapshot['profiles']:
        source_id = str(profile.get('source_id', profile.get('id', '')))
        extra = supplement.get('profiles', {}).get(source_id, {})
        for field in ('links', 'external_sources'):
            for entry in extra.get(field, []):
                existing = profile.setdefault('data', {}).setdefault(field, [])
                if entry not in existing:
                    existing.append(deepcopy(entry))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Collected PGNexus snapshot')
    parser.add_argument('--output', type=Path, required=True, help='Separate enriched snapshot')
    parser.add_argument('--sources-dir', type=Path, default=ROOT / 'tmp/hacker/official')
    parser.add_argument('--contributors-html', type=Path, help='Seed archive with an already fetched official page')
    parser.add_argument('--refresh', action='store_true', help='Fetch fresh copies of the three official pages')
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('--output must differ from --input to preserve the collected snapshot')
    snapshot = json.loads(args.input.read_text(encoding='utf-8'))
    sources = archive_sources(args.sources_dir, args.refresh, args.contributors_html)
    contributors = parse_contributors(args.sources_dir / 'contributors.html')
    committers = parse_committers(args.sources_dir / 'committers.html')
    matches, report = make_enrichment(snapshot['profiles'], contributors, committers, sources)
    enriched = enrich(snapshot, matches)
    review_path = args.sources_dir / 'identity-review.json'
    if review_path.exists():
        report['review_notes_added'] = add_review_notes(enriched, json.loads(review_path.read_text(encoding='utf-8')))
    extra_path = args.sources_dir / 'external-sources.json'
    if extra_path.exists():
        add_external_sources(enriched, json.loads(extra_path.read_text(encoding='utf-8')))
    write_json(args.sources_dir / 'contributors.json', contributors)
    write_json(args.sources_dir / 'enrichment.json', {'sources': sources, 'profiles': matches})
    write_json(args.sources_dir / 'report.json', report)
    write_json(args.output, enriched)
    print(json.dumps({key: value for key, value in report.items() if key not in ('unmatched', 'ambiguous')},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
