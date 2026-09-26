"""Present complete releases and persisted relationships in version reports."""

from collections import Counter
from urllib.parse import urlencode, quote


def release_report(snapshot, security, version):
    """A single release includes its entire occurrence list, including a GA."""
    from .compare import CATEGORIES, CATEGORY_LABELS, _release_summary

    release = next(row for row in snapshot['releases'] if row['version'] == version)
    entries = [dict(entry, version=version, category_label=CATEGORY_LABELS[entry['category']],
                    also_in=[], variants=[]) for entry in release['entries']]
    counts = Counter(entry['category'] for entry in entries)
    identifiers = sorted({cve for entry in entries for cve in entry.get('cves', [])})
    registry = {cve['id']: cve for cve in security.get('cves', [])}
    cves = []
    for identifier in identifiers:
        item = dict(registry.get(identifier, {}), id=identifier)
        item.setdefault('url', 'https://www.postgresql.org/support/security/' + identifier + '/')
        item['fixed_version'] = item.get('fixed', {}).get(release['major'], '')
        item['title'] = next(entry['title'] for entry in entries if identifier in entry.get('cves', []))
        cves.append(item)
    cves.sort(key=lambda item: (float(item.get('score') or 0), item['id']), reverse=True)
    summary = _release_summary(release)
    warnings = []
    if release['status'] != 'stable':
        warnings.append('PostgreSQL {} 尚未正式发布；以下为该构建的发布说明快照。'.format(summary['label']))
    return {
        'mode': 'release', 'from_release': None, 'to_release': summary,
        'groups': [dict(summary, entries=entries)],
        'stats': [{'key': 'all', 'label': '全部变更', 'count': len(entries)}] +
        [{'key': key, 'label': label, 'count': counts[key]} for key, label in CATEGORIES],
        'total': len(entries), 'release_count': 1, 'cross_major': False,
        'cve_count': len(cves), 'cves': cves, 'cve_available': True,
        'remaining_cves': [], 'security_regressions': [], 'warnings': warnings,
        'candidate_count': len(entries), 'already_in_source_count': 0,
        'duplicate_count': 0, 'excluded_count': 0, 'exclusions': [],
        'source_as_of': snapshot['generated_at'][:10],
        'security_as_of': security.get('fetched_at', '')[:10],
    }


def attach_entry_relations(snapshot, report):
    """Expose stored equivalent/related facts without changing report counts."""
    from .compare import _release_summary, version_key

    entries = {}
    for release in snapshot['releases']:
        for entry in release['entries']:
            if entry.get('db_id'):
                entries[entry['db_id']] = (release, entry)
    for group in report['groups']:
        for entry in group['entries']:
            related = []
            for relation in entry.get('relations', []):
                target = entries.get(relation['target'])
                if not target:
                    continue
                release, target_entry = target
                related.append({
                    'db_id': target_entry['db_id'], 'kind': relation['type'],
                    'version': release['version'], 'label': _release_summary(release)['label'],
                    'title': target_entry['title'], 'evidence': relation.get('evidence', {}),
                    'url': '/docs/compare/?' + urlencode({'release': release['version']}) + '#' + quote(target_entry['id']),
                    'source_url': target_entry.get('source_url', release.get('source_url', '')),
                })
            entry['related_changes'] = sorted(related, key=lambda item: (version_key(item['version']), item['db_id']), reverse=True)
    return report
