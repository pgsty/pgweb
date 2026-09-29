"""Compose the Versions encyclopedia from existing, independently owned data.

Release occurrences and security facts come only from activated database
snapshots. Manual availability is checked against loaded pages and the existing
local PDF files without asserting their language. No lifecycle dates are inferred for pre-releases.
"""

from collections import Counter, defaultdict
from urllib.parse import quote, urlencode

from django.db.models import Count

from pgweb.core.models import Version
from pgweb.docs.compare import CATEGORIES, CATEGORY_LABELS, version_key
from pgweb.docs.compare_store import load_database_snapshot
from pgweb.docs.models import DocPage
from pgweb.docs.versions import DEVEL_MAJOR_VERSION
from pgweb.core.models import TESTING_SHORTSTRING

ROOT = '/wiki/versions/'
POLICY_URL = 'https://www.postgresql.org/support/versioning/'
STATE_LABELS = {
    'current': '当前稳定版', 'supported': '支持中', 'eol': '已停止支持',
    'beta': '预览版', 'devel': '开发版',
}
INDEX_FILES = ('index.html', 'postgres.html', 'postgres.htm', 'book01.htm')


def version_state(version):
    if version.tree == 0:
        return 'devel'
    if version.testing:
        return 'beta'
    if version.current:
        return 'current'
    return 'supported' if version.supported else 'eol'


def version_tag(version):
    state = version_state(version)
    if state == 'devel':
        return '开发版'
    if state == 'beta':
        kind = TESTING_SHORTSTRING[version.testing] or 'beta'
        return '{} {}'.format(kind, version.latestminor) if version.latestminor else kind
    return '当前' if state == 'current' else ''


def branch_of(version):
    return str(DEVEL_MAJOR_VERSION) if version.tree == 0 else str(version.numtree)


def release_url(version, anchor=''):
    return '/docs/compare/?' + urlencode({'release': version}) + ('#' + quote(anchor, safe='') if anchor else '')


def release_summary(release):
    counts = Counter(entry.get('category') for entry in release.get('entries', []))
    identifiers = sorted({cve for entry in release.get('entries', []) for cve in entry.get('cves', [])})
    return {
        'version': release['version'], 'build': release.get('build') or release['version'],
        'status': release['status'], 'date': release.get('date', ''),
        'source_as_of': release.get('source_as_of', ''), 'url': release_url(release['version']),
        'manual_url': release.get('manual_url', ''), 'source_url': release.get('source_url', ''),
        'entry_count': len(release.get('entries', [])), 'categories': dict(counts),
        'compatibility_count': sum('/migration/' in entry.get('source_entry_id', '')
                                   for entry in release.get('entries', [])),
        'cves': identifiers, 'cve_count': len(identifiers),
    }


def present_branch(version, releases, page_count=0, index_file=''):
    """Keep PostgreSQL 9.x identities and distinguish previews from releases."""
    branch = branch_of(version)
    state = version_state(version)
    published = sorted((r for r in releases if not r.get('placeholder')),
                       key=lambda r: version_key(r['version']), reverse=True)
    initial = next((r for r in published if r['minor'] == 0), None)
    slug = 'devel' if version.tree == 0 else branch
    stable = state not in ('beta', 'devel')
    return {
        'branch': branch, 'url': ROOT + branch + '/', 'state': state,
        'state_label': STATE_LABELS[state], 'tag': version_tag(version),
        'build': str(DEVEL_MAJOR_VERSION) + 'devel' if version.tree == 0 else version.versionstring,
        'first_release': version.firstreldate.isoformat() if stable else '',
        'end_of_life': version.eoldate.isoformat() if stable else '',
        'latest_release_date': version.reldate.isoformat()
        if stable and version.reldate >= version.firstreldate else '',
        'manual_url': '/docs/{}/{}'.format(slug, index_file) if index_file else '',
        'manual_slug': slug, 'manual_pages': page_count,
        'manual_loaded_at': version.docsloaded.isoformat() if version.docsloaded else '',
        'source_revision': version.docsgit,
        'release_count': len(published),
        'entry_count': sum(len(r.get('entries', [])) for r in published),
        'initial': release_summary(initial) if initial else None,
        'latest': release_summary(published[0]) if published else None,
        'comparison_url': '/docs/compare/?' + urlencode({'from': initial['version'], 'to': published[0]['version']})
        if initial and len(published) > 1 else '',
    }


def load_catalog():
    """One shared version inventory; the existing loader verifies its manifest."""
    releases = load_database_snapshot('releases', language='zh')
    security = load_database_snapshot('security', language='zh')
    by_branch = defaultdict(list)
    for release in releases['releases']:
        by_branch[release['major']].append(release)
    indexes = dict(DocPage.objects.filter(file__in=INDEX_FILES).values_list('version_id', 'file'))
    pages = {row['version_id']: row['count'] for row in
             DocPage.objects.values('version_id').annotate(count=Count('id'))}
    rows = [present_branch(version, by_branch[branch_of(version)], pages.get(version.tree, 0),
                           indexes.get(version.tree, '')) for version in Version.objects.all()]
    rows.sort(key=lambda row: version_key(row['branch']), reverse=True)
    return {'rows': rows, 'release_snapshot': releases, 'security_snapshot': security,
            'by_branch': by_branch, 'release_as_of': releases.get('generated_at', '')[:10],
            'security_as_of': security.get('fetched_at', '')[:10]}


def filter_branches(catalog, query='', state=''):
    query = query.casefold().strip()
    result = []
    for row in catalog['rows']:
        if state and row['state'] != state:
            continue
        text = ' '.join(str(row[key]) for key in
                        ('branch', 'build', 'state_label', 'first_release', 'end_of_life')).casefold()
        if query and query not in text and not any(
                query in (entry.get('text', '') + ' ' + entry.get('title', '')).casefold()
                for release in catalog['by_branch'][row['branch']] for entry in release.get('entries', [])):
            continue
        result.append(row)
    return result


def branch_security(branch, releases, security):
    """Separate branch-specific security facts from mere release-note mentions."""
    mentions = defaultdict(list)
    for release in releases:
        for entry in release.get('entries', []):
            for cve in entry.get('cves', []):
                mentions[cve].append({'build': release.get('build') or release['version'],
                                      'version': release['version'],
                                      'title': entry.get('title', ''),
                                      'url': release_url(release['version'], entry.get('id', ''))})
    registry = {item['id']: item for item in security.get('cves', [])}
    identifiers = set(mentions)
    identifiers.update(item['id'] for item in registry.values()
                       if branch in item.get('fixed', {}) or branch in item.get('affected', {}))
    rows = []
    available = {r['version'] for r in releases if not r.get('placeholder')}
    for identifier in sorted(identifiers, reverse=True):
        cve = registry.get(identifier, {})
        fixed = cve.get('fixed', {}).get(branch, '')
        rows.append({'id': identifier, 'title': cve.get('title') or identifier,
                     'url': cve.get('url') or 'https://www.postgresql.org/support/security/' + identifier + '/',
                     'score': cve.get('score'), 'vector': cve.get('vector', ''),
                     'description': cve.get('description_zh') or cve.get('description_en', ''),
                     'description_language': 'zh' if cve.get('description_zh') else 'en',
                     'fixed': fixed, 'fixed_url': release_url(fixed) if fixed in available else '',
                     'affected': cve.get('affected', {}).get(branch, ''),
                     'component': cve.get('component', ''), 'mentions': mentions[identifier],
                     'evidence': 'branch-matrix' if fixed or branch in cve.get('affected', {}) else 'release-note-mention'})
    return rows


def manual_resources(row):
    """Link only local editions; inherited PDFs have no verified language manifest."""
    from pathlib import Path
    from django.conf import settings

    branch = row['branch']
    pdfs = []
    for code, label in (('A4', 'A4 PDF'), ('US', 'US Letter PDF')):
        filename = 'postgresql-{}-{}.pdf'.format(branch, code)
        path = Path(settings.STATIC_CHECKOUT) / 'documentation' / 'pdf' / branch / filename
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size:
            pdfs.append({'label': label, 'bytes': size,
                         'url': '/files/documentation/pdf/{}/{}'.format(branch, filename)})
    return pdfs


def detail_payload(catalog, branch, query='', kind=''):
    row = next(item for item in catalog['rows'] if item['branch'] == branch)
    releases = sorted((r for r in catalog['by_branch'][branch] if not r.get('placeholder')),
                      key=lambda r: version_key(r['version']), reverse=True)
    initial = next((r for r in releases if r['minor'] == 0), None)
    initial_entries = initial.get('entries', []) if initial else []
    counts = Counter(entry.get('category') for entry in initial_entries)
    entries = []
    for entry in initial_entries:
        if kind and entry.get('category') != kind:
            continue
        if query and query.casefold() not in (entry.get('text', '') + ' ' + entry.get('title', '')).casefold():
            continue
        entries.append(dict(entry, category_label=CATEGORY_LABELS.get(entry.get('category'), '变更'),
                            url=release_url(initial['version'], entry.get('id', '')),
                            migration='/migration/' in entry.get('source_entry_id', '')))
    return {
        'version': row, 'releases': [release_summary(release) for release in releases],
        'initial_entries': entries, 'initial_entry_count': len(initial_entries),
        'migration_html': initial.get('migration_html', '') if initial else '',
        'category_filters': [{'key': key, 'label': label, 'count': counts[key]} for key, label in CATEGORIES],
        'security_rows': branch_security(branch, releases, catalog['security_snapshot']),
        'security_covered': branch in catalog['security_snapshot'].get('covered_majors', []),
        'release_as_of': catalog['release_as_of'], 'security_as_of': catalog['security_as_of'],
        'policy_url': POLICY_URL,
    }


def collection_summary():
    """Cheap Wiki card metadata; never loads release bodies."""
    branches = sorted((branch_of(version) for version in Version.objects.only('tree')), key=version_key)
    return {'count': len(branches), 'first': branches[0] if branches else '',
            'last': branches[-1] if branches else '', 'url': ROOT}


def search_rows():
    """One searchable major branch, retaining 9.x identities and source text."""
    catalog = load_catalog()
    rows = []
    for row in catalog['rows']:
        summary = '{}；记录构建 {}。收录 {} 个发布版本、{} 条原始变更。'.format(
            row['state_label'], row['build'], row['release_count'], row['entry_count'])
        prose = [summary]
        if row['first_release']:
            prose.append('首次正式发布于 {}，支持结束于 {}。'.format(row['first_release'], row['end_of_life']))
        for release in catalog['by_branch'][row['branch']]:
            if not release.get('placeholder'):
                prose.append(release.get('build') or release['version'])
                if release['minor'] == 0:
                    prose.extend(entry.get('text', '') for entry in release.get('entries', []))
        rows.append({'branch': row['branch'], 'name': 'PostgreSQL ' + row['branch'],
                     'summary': summary, 'body': '\n'.join(prose), 'url': row['url']})
    return rows
