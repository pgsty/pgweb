#!/usr/bin/env python3
"""Snapshot the PostgreSQL security advisory registry for /docs/compare/.

Run with the project Python. The default fetches the current index and reuses
cached advisory pages; --refresh also refreshes every archive and advisory.
--offline replays the same cached HTML without network access. No application
database is required. All archived branches linked by PostgreSQL are included.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
SOURCE_URL = 'https://www.postgresql.org/support/security/'
CNA_URL = 'https://cveawg.mitre.org/api/cve/'
CVE_RE = re.compile(r'CVE-\d{4}-\d+')
VERSION_RE = re.compile(r'\d+(?:\.\d+){0,2}')


def text(node):
    return ' '.join(node.get_text(' ', strip=True).split())


def version_key(value):
    return tuple(int(part) for part in value.split('.'))


def major_version(value):
    parts = value.split('.')
    return parts[0] if int(parts[0]) >= 10 else '.'.join(parts[:2])


def affected_bounds(label, fixed):
    """Preserve explicitly listed introduction versions instead of assuming .0.

    Bare major labels mean that the advisory does not state a narrower lower
    bound. The raw label remains in ``affected`` for future reprocessing.
    """
    major = major_version(fixed)
    versions = VERSION_RE.findall(label)
    if not versions or any(major_version(v) != major for v in versions):
        raise ValueError('Affected range {!r} does not match {}'.format(label, fixed))
    minimum = versions[0]
    lower = minimum if len(minimum.split('.')) > len(major.split('.')) else None
    if lower and version_key(lower) >= version_key(fixed):
        raise ValueError('Affected range {!r} is not below {}'.format(label, fixed))
    return major, lower


def parse_index(html, source_url=SOURCE_URL):
    """Return the advisory URLs and linked branch archives from an index."""
    soup = BeautifulSoup(html, 'html.parser')
    tables = [table for table in soup.select('table')
              if [text(th) for th in table.select('thead th')][:3] == ['Reference', 'Affected', 'Fixed']]
    if len(tables) != 1:
        raise ValueError('Expected one security registry table at {}'.format(source_url))
    advisories = {}
    for row in tables[0].select('tbody tr'):
        cells = row.find_all('td', recursive=False)
        if not cells:
            continue
        if len(cells) != 5:
            raise ValueError('Unexpected security registry row at {}'.format(source_url))
        link = cells[0].find('a', string=CVE_RE)
        if not link:
            raise ValueError('Security registry row has no CVE at {}'.format(source_url))
        cve_id = text(link)
        if not CVE_RE.fullmatch(cve_id):
            raise ValueError('Invalid CVE ID: {}'.format(cve_id))
        advisories[cve_id] = urljoin(source_url, link['href'])
    if not advisories:
        raise ValueError('Security registry is empty at {}'.format(source_url))
    archives = {}
    for link in soup.select('a[href]'):
        url = urljoin(source_url, link['href'])
        match = re.fullmatch(r'/support/security/(\d+(?:\.\d+)?)/', urlparse(url).path)
        if match and urlparse(url).netloc == 'www.postgresql.org':
            archives[match.group(1)] = url
    return advisories, archives


def parse_detail(html, source_url):
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('#pgContentWrap')
    if content is None:
        raise ValueError('Missing advisory content at {}'.format(source_url))
    heading = content.find('h1')
    cve_id = text(heading) if heading else ''
    if not CVE_RE.fullmatch(cve_id):
        raise ValueError('Invalid advisory ID at {}'.format(source_url))
    title = content.find('h3')
    if title is None:
        raise ValueError('Missing advisory title at {}'.format(source_url))
    paragraphs = []
    for sibling in title.next_siblings:
        if getattr(sibling, 'name', None) == 'h2':
            break
        if getattr(sibling, 'name', None) == 'p':
            paragraphs.append(text(sibling))
    result = {
        'id': cve_id,
        'title': text(title),
        'description_en': '\n\n'.join(paragraphs),
        'url': source_url,
        'score': None,
        'vector': '',
        'cvss_version': '',
        'component': '',
        'fixed': {},
        'introduced': {},
        'affected': {},
        'published': {},
    }
    version_tables = [table for table in content.select('table')
                      if [text(th) for th in table.select('thead th')][:2] == ['Affected Version', 'Fixed In']]
    if len(version_tables) != 1:
        raise ValueError('Missing version information at {}'.format(source_url))
    for row in version_tables[0].select('tbody tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) not in (2, 3):
            raise ValueError('Unexpected advisory version row at {}'.format(source_url))
        affected, fixed = map(text, cells[:2])
        published = text(cells[2]) if len(cells) == 3 else ''
        if not VERSION_RE.fullmatch(fixed):
            raise ValueError('Invalid fixed release {!r} at {}'.format(fixed, source_url))
        major, introduced = affected_bounds(affected, fixed)
        if major in result['fixed']:
            raise ValueError('Multiple affected intervals for {} at {}'.format(major, source_url))
        result['fixed'][major] = fixed
        result['affected'][major] = affected
        if introduced:
            result['introduced'][major] = introduced
        if published:
            datetime.strptime(published, '%Y-%m-%d')
            result['published'][major] = published
    if not result['fixed']:
        raise ValueError('Empty version information at {}'.format(source_url))
    for heading in content.find_all('h2'):
        match = re.fullmatch(r'CVSS\s+(\d+(?:\.\d+)?)', text(heading))
        if not match:
            continue
        result['cvss_version'] = match.group(1)
        table = heading.find_next_sibling('table')
        if table is None:
            raise ValueError('Missing CVSS table at {}'.format(source_url))
        for row in table.select('tr'):
            key, value = row.find('th'), row.find('td')
            if key is None or value is None:
                continue
            key, value = text(key), text(value)
            if key == 'Overall Score':
                result['score'] = float(value)
                if not 0 <= result['score'] <= 10:
                    raise ValueError('Invalid CVSS score at {}'.format(source_url))
            elif key == 'Component':
                result['component'] = value
            elif key == 'Vector':
                result['vector'] = value
    result['first_published'] = min(result['published'].values(), default=None)
    return result


def add_cna_ranges(record, payload):
    """Use PostgreSQL's own machine-readable affected intervals when complete.

    Its last interval sometimes spans unsupported branches, e.g. [11.20,
    13.22). Those versions have no entry in the fixed-release table but must
    not be presented as unaffected. Other providers or nonnumeric version
    syntaxes retain the official web registry's bounds instead of guessing.
    """
    if payload.get('cveMetadata', {}).get('cveId') != record['id']:
        raise ValueError('CNA record identity mismatch for {}'.format(record['id']))
    cna = payload.get('containers', {}).get('cna', {})
    if cna.get('providerMetadata', {}).get('shortName') != 'PostgreSQL':
        return
    affected = [item for item in cna.get('affected', [])
                if item.get('product', '').lower() == 'postgresql']
    if not affected or any(item.get('defaultStatus') != 'unaffected' for item in affected):
        return
    ranges = []
    for product in affected:
        for item in product.get('versions', []):
            if item.get('status') != 'affected':
                continue
            start, end = item.get('version', ''), item.get('lessThan', '')
            if (item.get('changes') or not VERSION_RE.fullmatch(start) or
                    not VERSION_RE.fullmatch(end) or version_key(start) >= version_key(end)):
                return
            ranges.append({'from': start, 'until': end})
    if not ranges:
        return
    record['affected_ranges'] = sorted(ranges, key=lambda item: version_key(item['from']))
    record['cna_url'] = CNA_URL + record['id']
    # A lower bound inside one branch is also exposed through the simpler map.
    for item in ranges:
        if major_version(item['from']) == major_version(item['until']):
            major, lower = affected_bounds(item['from'], item['until'])
            if lower:
                record['introduced'][major] = lower


def fetch_html(url, cache_dir, refresh=False, offline=False):
    name = urlparse(url).path.strip('/').replace('/', '_') + '.html'
    path = cache_dir / name
    if path.exists() and (offline or not refresh):
        return path.read_text(encoding='utf-8')
    if offline:
        raise ValueError('Missing cached source: {}'.format(path))
    request = Request(url, headers={'User-Agent': 'PGSQL.CC release comparison snapshot'})
    with urlopen(request, timeout=45) as response:
        html = response.read().decode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(html, encoding='utf-8')
    temporary.replace(path)
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/compare/security.json')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / 'tmp/compare-security')
    parser.add_argument('--refresh', action='store_true', help='Refresh every cached source')
    parser.add_argument('--offline', action='store_true', help='Only use previously cached HTML')
    args = parser.parse_args()
    if args.refresh and args.offline:
        parser.error('--refresh and --offline are mutually exclusive')

    def fetch(url):
        return fetch_html(url, args.cache_dir, refresh=args.refresh, offline=args.offline)

    index_html = fetch_html(SOURCE_URL, args.cache_dir, refresh=True, offline=args.offline)
    advisories, archives = parse_index(index_html)
    print('Reading {} branch archives.'.format(len(archives)), flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for url, html in zip(archives.values(), pool.map(fetch, archives.values())):
            archive_advisories, _ = parse_index(html, url)
            advisories.update(archive_advisories)
    print('Reading {} official CVE advisories.'.format(len(advisories)), flush=True)
    records = []
    ordered = sorted(advisories.items(), key=lambda pair: tuple(map(int, pair[0].split('-')[1:])), reverse=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        urls = [url for _, url in ordered]
        for (expected_id, url), html in zip(ordered, pool.map(fetch, urls)):
            record = parse_detail(html, url)
            if record['id'] != expected_id:
                raise ValueError('Advisory identity mismatch at {}'.format(url))
            records.append(record)
            if len(records) % 50 == 0:
                print('Parsed {}/{} advisories.'.format(len(records), len(ordered)), flush=True)
    # PostgreSQL's CNA has published structured records since 2023. Older
    # records come from other providers and keep the archived web evidence.
    cna_records = [record for record in records if int(record['id'].split('-')[1]) >= 2023]
    print('Reading {} recent CNA records for exact affected intervals.'.format(len(cna_records)), flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        urls = [CNA_URL + record['id'] for record in cna_records]
        for record, payload in zip(cna_records, pool.map(fetch, urls)):
            add_cna_ranges(record, json.loads(payload))
    snapshot = {
        'format': 1,
        'source_url': SOURCE_URL,
        'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'covered_majors': sorted(archives, key=version_key),
        'source_urls': [SOURCE_URL] + sorted(archives.values()),
        'cves': records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.chmod(0o644)
    temporary.replace(args.output)
    print('Wrote {} CVEs across {} branches to {}.'.format(len(records), len(archives), args.output))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Security snapshot failed: {}'.format(exc), file=sys.stderr)
        sys.exit(1)
