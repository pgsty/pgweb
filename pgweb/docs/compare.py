"""Bounded PostgreSQL release comparisons over the published source snapshots.

This is a release-note history, not an assertion about every commit in a binary.
Each older branch contributes its releases up to the next major's initial release;
the selected branch contributes through the selected minor. Subtract the source
history, including known backports, and retain uncertain matches rather than
silently discard distinct changes. CVE applicability is calculated independently
from PostgreSQL's security matrix, never from mentions in release-note prose.
"""

from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from django.http import JsonResponse

from pgweb.util.contexts import render_pgweb
from pgweb.util.decorators import queryparams


DATA_DIR = Path(__file__).resolve().parents[2] / 'data' / 'compare'
CATEGORIES = (
    ('feature', '新功能'), ('bugfix', 'BUG 修复'), ('security', '安全相关'),
    ('performance', '性能改进'), ('compatibility', '兼容性变化'),
    ('improvement', '其他改进'),
)
CATEGORY_LABELS = dict(CATEGORIES)


class _Snapshot(dict):
    """A file snapshot is immutable; compiled indexes share its cache lifetime."""


@lru_cache(maxsize=4)
def _read_snapshot(path, mtime, size):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        data = _Snapshot(json.load(stream))
    if data.get('format') != 1:
        raise ValueError('Unsupported comparison snapshot format')
    return data


def load_snapshot(filename):
    """Read a transport snapshot for offline build/audit tools, not page views."""
    path = DATA_DIR / filename
    stat = path.stat()
    return _read_snapshot(str(path), stat.st_mtime_ns, stat.st_size)


def load_active_snapshot(filename):
    """Read the activated database collection without a file fallback."""
    from .compare_store import ComparisonDataUnavailable, load_database_snapshot

    kind = 'releases' if filename == 'releases.json.gz' else 'security'
    try:
        return load_database_snapshot(kind, language='zh')
    except ComparisonDataUnavailable as error:
        raise OSError(str(error)) from error


def version_key(value):
    return tuple(int(part) for part in value.split('.'))


def resolve_version(value, releases):
    value = (value or '').strip()
    # Accept both a version and the unmodified result of SELECT version().
    match = re.fullmatch(r'(\d+)(?:\.(\d+))?(?:\.(\d+))?', value)
    if not match:
        match = re.match(r'^PostgreSQL\s+(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\s|$)', value, re.I)
    if not match or int(match[1]) < 9 or (int(match[1]) == 9 and match[2] is None) or (int(match[1]) >= 10 and match[3] is not None):
        raise ValueError('请输入已收录的 PostgreSQL 版本，例如 9.6.24、17、17.11 或 SELECT version() 的结果。')
    if int(match[1]) == 9:
        canonical = '9.{}.{}'.format(int(match[2]), int(match[3] or 0))
    else:
        canonical = '{}.{}'.format(int(match[1]), int(match[2] or 0))
    if canonical not in releases:
        raise ValueError('未收录 PostgreSQL {} 的发布说明，请从列表中选择。'.format(canonical))
    if releases[canonical].get('placeholder'):
        raise ValueError('PostgreSQL {} 的发布说明尚未提供可对比的变更条目。'.format(canonical))
    return canonical


def _effective_date(release, as_of):
    return release.get('date') or release.get('source_as_of') or as_of[:10]


def release_history(releases, selected, as_of):
    """Follow branch inheritance, stopping before later maintenance releases."""
    selected_key = version_key(selected['version'])
    initial = {version_key(r['major']): r for r in releases if r['minor'] == 0}
    end = _effective_date(selected, as_of)
    history = []
    for release in releases:
        key = version_key(release['version'])
        if key > selected_key:
            continue
        major = version_key(release['major'])
        if major < version_key(selected['major']):
            following = next((initial[m] for m in sorted(initial) if m > major), None)
            cutoff = min(end, _effective_date(following, as_of)) if following else end
        else:
            cutoff = end
        if _effective_date(release, as_of) <= cutoff:
            history.append(release)
    return sorted(history, key=lambda r: version_key(r['version']))


def _commit_id(value):
    match = re.search(r'(?:/|\b)([a-f0-9]{7,40})(?:$|[?#])', value, re.I)
    return match[1].lower() if match else ''


class _ReleaseIndex:
    """Compile individual commit equivalences without joining independent fixes."""

    def __init__(self, releases):
        parents = {}

        def root(commit):
            parents.setdefault(commit, commit)
            while parents[commit] != commit:
                parents[commit] = parents[parents[commit]]
                commit = parents[commit]
            return commit

        def union(group):
            if group:
                first = root(group[0])
                for commit in group[1:]:
                    parents[root(commit)] = first

        raw = {}
        self.titles = {}
        for release in releases:
            for position, entry in enumerate(release['entries']):
                commits = [_commit_id(value) for value in entry.get('commits', [])]
                commits = [value for value in commits if value]
                aliases = [_commit_id(value) for value in entry.get('commit_aliases', [])]
                aliases = [value for value in aliases if value]
                groups = entry.get('commit_groups')
                if groups is None:
                    # A flattened alias list is only one equivalence class when
                    # there is one concrete commit. Older snapshots with several
                    # commits remain conservative until explicit groups exist.
                    groups = [commits + aliases] if len(commits) == 1 else [[c] for c in commits]
                parsed_groups = []
                for group in groups:
                    parsed = [_commit_id(value) for value in group]
                    parsed = [value for value in parsed if value]
                    union(parsed)
                    if parsed:
                        parsed_groups.append(parsed)
                for commit in commits + aliases:
                    root(commit)
                raw[(release['version'], position)] = (parsed_groups, commits + aliases + [value for group in parsed_groups for value in group])
                if re.search(r'[\u3400-\u9fff]', entry['title']):
                    for cve in entry.get('cves', []):
                        self.titles.setdefault((cve, release['version']), entry['title'])
        # Link abbreviated hashes only when the longer reference is unambiguous.
        # Truncating every hash to seven characters can merge unrelated commits.
        references = sorted(parents)
        for position, commit in enumerate(references[:-1]):
            longer = []
            for candidate in references[position + 1:]:
                if not candidate.startswith(commit):
                    break
                longer.append(candidate)
            if longer and all(longer[-1].startswith(candidate) for candidate in longer):
                union([commit, longer[-1]])
        self.identities = {}
        self.row_contexts = {}
        statements_by_release_commit = defaultdict(set)
        for release in releases:
            for position, entry in enumerate(release['entries']):
                groups, known = raw[(release['version'], position)]
                source_id = entry.get('source_entry_id', '')
                source_part = re.search(r'/(migration|changes)/', source_id)
                migration = (source_part[1] == 'migration' if source_part else entry['category'] == 'compatibility')
                namespace = 'compatibility' if migration else 'change'
                required = frozenset((namespace, root(group[0])) for group in groups)
                supplied = frozenset((namespace, root(commit)) for commit in known)
                # Exact full prose on the same release day is a conservative
                # fallback for older release notes without commit references.
                # Preserve SQL operators, punctuation and meaningful qualifiers.
                # The independently aligned upstream English prose makes this
                # fallback identical for the Chinese and English sites.
                prose = re.sub(r'\s+', ' ', entry.get('identity_text', entry.get('text', entry['title']))).strip()
                fingerprint = (namespace, release.get('date', ''), hashlib.sha256(prose.encode()).hexdigest())
                self.identities[(release['version'], position)] = (required, supplied, fingerprint)
                scope = required | supplied
                self.row_contexts[(release['version'], entry['id'])] = (release['minor'] == 0, fingerprint[-1], scope)
                for commit in scope:
                    statements_by_release_commit[(release['version'], commit)].add(fingerprint[-1])
        # Upstream sometimes combines independent fixes in one source commit.
        # Preserve the commit evidence, but distinguish its separate statements.
        self.multi_statement_commits = {commit[1] for (_, commit), statements in statements_by_release_commit.items()
                                        if len(statements) > 1}


def _release_index(snapshot):
    index = getattr(snapshot, '_comparison_index', None)
    if index is None:
        index = _ReleaseIndex(snapshot['releases'])
        if hasattr(snapshot, '__dict__'):
            snapshot._comparison_index = index
    return index


def _entry_reference(release, entry):
    """Small, language-independent references for an explainable comparison."""
    return {
        'id': entry['id'], 'source_entry_id': entry.get('source_entry_id', entry['id']),
        'version': release['version'], 'source_url': entry.get('source_url', release.get('source_url', '')),
        'title': entry['title'],
    }


def _unique_references(references):
    return list({(ref['version'], ref['id']): ref for ref in references}.values())


def _prose_matches(records, required):
    # Identical prose is useful when references are absent; it cannot override
    # known, different commits. Short repeated release-note text occurs in the
    # real sources, so it is not an unconditional identity.
    return [ref for candidate_required, ref in records if not required or not candidate_required]


def _same_commit_scope(index, release, entry, reference):
    """A maintenance backport can be just part of a major-release feature.

    For example, the Snowball update adds Estonian in 18, whereas its 17.5
    backport only fixes out-of-memory handling. The upstream Author block links
    these commits but does not make the release-note statements equivalent.
    A single maintenance commit can also cover independent statements (for
    example, CVE-2014-0065 and CVE-2014-0066). Such shared groups require the same
    full-prose check as initial-major statements.
    """
    initial, prose, commits = index.row_contexts[(release['version'], entry['id'])]
    other_initial, other_prose, other_commits = index.row_contexts[(reference['version'], reference['id'])]
    multi_statement = any(commit[1] in index.multi_statement_commits for commit in commits & other_commits)
    return not (initial or other_initial or multi_statement) or prose == other_prose


def _release_summary(release):
    summary = {key: value for key, value in release.items() if key != 'entries'}
    if release['status'] != 'stable':
        summary['label'] = release.get('build') or release['version']
    else:
        summary['label'] = release['major'] if release['minor'] == 0 and '.' in release['major'] else release['version']
    summary['status_label'] = {'preview': '尚未正式发布', 'devel': '开发快照'}.get(
        release['status'], '受支持版本' if release.get('supported', True) else '历史版本')
    summary['eol'] = release.get('eol_date') or release.get('eol', '')
    today = date.today()
    for field, count_key in (('date', 'age_days'), ('eol', 'support_days')):
        value = summary.get(field)
        if value:
            try:
                delta = (today - date.fromisoformat(value)).days
                summary[count_key] = delta if field == 'date' else -delta
            except ValueError:
                pass
    return summary


def _inherited_security_fix(cve, release, releases):
    """Return dated evidence of a later major inheriting an earlier CVE fix."""
    fixed_branches = cve.get('fixed', {})
    if not fixed_branches or version_key(release['major']) <= max(version_key(branch) for branch in fixed_branches):
        return None
    initial_version = release['major'] + '.0'
    initial = release if release['minor'] == 0 else releases.get(initial_version, {})
    initial_date = initial.get('date')
    if not initial_date:
        return None
    # JSON object order is not significant and JSONB does not preserve it.
    # Choose the same valid evidence for file and database snapshots.
    for branch in sorted(fixed_branches, key=version_key, reverse=True):
        version = fixed_branches[branch]
        fixed_date = cve.get('published', {}).get(branch) or releases.get(version, {}).get('date')
        if fixed_date and fixed_date <= initial_date:
            return {
                'kind': 'major_inherits_prior_security_fixes',
                'policy_url': 'https://www.postgresql.org/support/security/',
                'target_initial_version': initial_version, 'target_initial_date': initial_date,
                'fixed_version': version, 'fixed_date': fixed_date,
            }
    return None


def _security_state(cve, release, releases=None):
    major = str(release['major'])
    version = version_key(release['version'])
    if cve.get('affected_ranges'):
        if any(version_key(r['from']) <= version < version_key(r['until']) for r in cve['affected_ranges']):
            return 'vulnerable'
        fixed = cve.get('fixed', {}).get(major)
        return 'fixed' if fixed and version >= version_key(fixed) else 'unaffected'
    fixed = cve.get('fixed', {}).get(major)
    if not fixed:
        if release.get('supported', True):
            return 'unaffected'
        # Historical branches are no longer investigated for new CVEs. Their
        # omission cannot generally mean "unaffected". A later major's initial
        # release does, however, include all prior security fixes (the official
        # security policy), when both the branch ordering and dates prove it.
        if _inherited_security_fix(cve, release, releases or {}):
            return 'unaffected'
        return 'unknown'
    introduced = cve.get('introduced', {}).get(major, major + '.0')
    if version < version_key(introduced):
        return 'unaffected'
    return 'fixed' if version >= version_key(fixed) else 'vulnerable'


def compare_security(security, source, target, releases, titles=None):
    gained, regressions, remaining = [], [], []
    by_version = {release['version']: release for release in releases}
    if titles is None:
        titles = _ReleaseIndex(releases).titles

    def item_for(cve):
        item = dict(cve)
        item['fixed_version'] = cve.get('fixed', {}).get(str(target['major']), '')
        score = item.get('score')
        item['severity'] = '' if score is None else ('严重' if score >= 9 else '高危' if score >= 7 else '中危' if score >= 4 else '低危' if score > 0 else '无')
        for fixed in (item['fixed_version'], cve.get('fixed', {}).get(str(source['major']))):
            if (cve['id'], fixed) in titles:
                item['title'] = titles[(cve['id'], fixed)]
                break
        return item

    for cve in security.get('cves', []):
        source_state = _security_state(cve, source, by_version)
        target_state = _security_state(cve, target, by_version)
        if source_state == 'vulnerable' and target_state in ('fixed', 'unaffected'):
            item = item_for(cve)
            item['status_label'] = '目标版本已修复' if target_state == 'fixed' else '目标版本不受影响'
            if target_state == 'unaffected' and not cve.get('affected_ranges'):
                evidence = _inherited_security_fix(cve, target, by_version)
                if evidence:
                    item['target_state_evidence'] = evidence
            gained.append(item)
        elif target_state == 'vulnerable' and source_state in ('fixed', 'unaffected'):
            regressions.append(item_for(cve))
        if target_state == 'vulnerable':
            remaining.append(item_for(cve))
    for rows in (gained, regressions, remaining):
        rows.sort(key=lambda c: (float(c.get('score') or 0), c['id']), reverse=True)
    return gained, regressions, remaining


def build_report(snapshot, security, from_version, to_version):
    releases = snapshot['releases']
    by_version = {r['version']: r for r in releases}
    source, target = by_version[from_version], by_version[to_version]
    if version_key(from_version) > version_key(to_version):
        raise ValueError('目标版本须不早于起始版本；请交换两个版本后对比升级变化。')
    source_history = release_history(releases, source, snapshot['generated_at'])
    target_history = release_history(releases, target, snapshot['generated_at'])
    index = _release_index(snapshot)
    known_commits, known_texts = defaultdict(list), defaultdict(list)
    for release in source_history:
        for position, entry in enumerate(release['entries']):
            required, supplied, fingerprint = index.identities[(release['version'], position)]
            reference = _entry_reference(release, entry)
            for commit in supplied:
                known_commits[commit].append(reference)
            known_texts[fingerprint].append((required, reference))
    seen_commits, seen_texts = defaultdict(list), defaultdict(list)
    groups = []
    exclusions = []
    already_in_source_count, duplicate_count, candidate_count = 0, 0, 0
    represented_majors = {}
    source_versions = {r['version'] for r in source_history}
    cross_major = source['major'] != target['major']
    counts = Counter()
    for release in target_history:
        if release['version'] in source_versions:
            continue
        entries = []
        for position, entry in enumerate(release['entries']):
            candidate_count += 1
            required, supplied, fingerprint = index.identities[(release['version'], position)]
            if cross_major:
                # One entry can describe multiple independent commits. Retain it
                # unless every concrete change is already known in the source.
                source_matches = []
                method = ''
                applicable_known = {
                    commit: [ref for ref in known_commits[commit] if _same_commit_scope(index, release, entry, ref)]
                    for commit in required
                }
                if required and all(applicable_known.values()):
                    source_matches = [ref for commit in sorted(required) for ref in applicable_known[commit]]
                    method = 'commits'
                if not source_matches:
                    source_matches = _prose_matches(known_texts[fingerprint], required)
                    method = 'exact_prose'
                if release['major'] != source['major'] and source_matches:
                    exclusions.append(dict(
                        _entry_reference(release, entry), reason='already_in_source', method=method,
                        matches=_unique_references(source_matches),
                        entry=dict(entry),
                    ))
                    already_in_source_count += 1
                    continue
                # A multi-commit note can mix work known in the source with
                # newly gained work. Only the latter needs another report row.
                remaining = frozenset(commit for commit in required if not applicable_known[commit])
                matches = []
                if remaining:
                    per_commit = [[item for item in seen_commits[commit]
                                   if release['major'] not in represented_majors[item['id']] and
                                   _same_commit_scope(index, release, entry, item)]
                                  for commit in sorted(remaining)]
                    if all(per_commit):
                        matches = [items[0] for items in per_commit]
                        method = 'commits'
                if not matches:
                    matches = [item for item in _prose_matches(seen_texts[fingerprint], required)
                               if release['major'] not in represented_majors[item['id']]]
                    method = 'exact_prose'
                if matches:
                    matches = list({item['id']: item for item in matches}.values())
                    references = [_entry_reference(by_version[item['version']], item) for item in matches]
                    # Keep the entire other-branch note, including branch-
                    # specific instructions, even when it adds no extra fix.
                    # Attach it once; an aggregate note can cover several rows.
                    variant = dict(entry, version=release['version'],
                                   category_label=CATEGORY_LABELS[entry['category']],
                                   merge_method=method, covers=references)
                    matches[0]['variants'].append(variant)
                    for item in matches:
                        if release['version'] not in item['also_in']:
                            item['also_in'].append(release['version'])
                        represented_majors[item['id']].add(release['major'])
                    exclusions.append(dict(
                        _entry_reference(release, entry), reason='backport_duplicate', method=method,
                        matches=references,
                    ))
                    duplicate_count += 1
                    continue
            # Within one branch, every published entry is retained, including
            # repeated headings, follow-up fixes and multiple uses of a commit.
            item = dict(entry, version=release['version'],
                        category_label=CATEGORY_LABELS[entry['category']], also_in=[], variants=[])
            entries.append(item)
            represented_majors[item['id']] = {release['major']}
            counts[item['category']] += 1
            for commit in supplied:
                seen_commits[commit].append(item)
            seen_texts[fingerprint].append((required, item))
        migration = release.get('migration_html', '')
        if entries or migration:
            groups.append(dict(_release_summary(release), entries=entries, migration_html=migration))
    covered = security.get('covered_majors', [])
    cve_available = all(r['status'] == 'stable' and str(r['major']) in covered for r in (source, target))
    cves, regressions, remaining = compare_security(security, source, target, releases, index.titles) if cve_available else ([], [], [])
    warnings = []
    for release in (source, target):
        if release['status'] != 'stable':
            warnings.append('PostgreSQL {} 尚未正式发布；这里对比的是 {} 的发布说明快照。'.format(
                _release_summary(release)['label'], release.get('source_as_of') or snapshot['generated_at'][:10]))
    if source.get('date') and target.get('date') and source['date'] > target['date']:
        warnings.append('目标版本的发布日期早于起始版本，可能缺少起始分支较新的修复。')
    if regressions:
        warnings.append('目标版本仍受 {} 个起始版本不受影响的已知 CVE 影响：{}。请查看这些漏洞的修复版本。'.format(
            len(regressions), '、'.join(c['id'] for c in regressions)))
    if not cve_available:
        warnings.append('官方安全公告尚未覆盖所选测试分支，CVE 修复数量不作推断；发布说明中的安全相关条目仍完整列出。')
    total = sum(counts.values())
    return {
        'from_release': _release_summary(source), 'to_release': _release_summary(target),
        'groups': list(reversed(groups)), 'stats': [{'key': 'all', 'label': '全部变更', 'count': total}] +
        [{'key': key, 'label': label, 'count': counts[key]} for key, label in CATEGORIES],
        'total': total, 'cve_count': len(cves) if cve_available else None, 'cves': cves,
        'cve_available': cve_available,
        'security_regressions': regressions, 'remaining_cves': remaining, 'cross_major': cross_major,
        'excluded_count': len(exclusions), 'already_in_source_count': already_in_source_count,
        'duplicate_count': duplicate_count, 'candidate_count': candidate_count, 'exclusions': exclusions,
        'history': {'source': [r['version'] for r in source_history],
                    'target': [r['version'] for r in target_history],
                    'candidates': [r['version'] for r in target_history if r['version'] not in source_versions]},
        'release_count': len(groups), 'warnings': warnings,
        'source_as_of': snapshot['generated_at'][:10],
        'security_as_of': security.get('fetched_at', '')[:10],
    }


@queryparams('from', 'to', 'version', 'release', 'format', 'q', 'kind')
def compare(request):
    from .compare_presenter import attach_entry_relations, release_report

    context = {'error': '', 'message': '', 'report': None, 'release_groups': [], 'examples': []}
    status = 200
    try:
        snapshot = load_active_snapshot('releases.json.gz')
        security = load_active_snapshot('security.json')
        releases = {r['version']: r for r in snapshot['releases']}
        stable = sorted((r for r in releases.values() if r['status'] == 'stable'),
                        key=lambda r: version_key(r['version']), reverse=True)
        if not stable:
            raise ValueError('发布说明尚未准备好，请稍后再试。')
        latest = stable[0]
        previous = next((r for r in stable if r['major'] != latest['major']), latest)
        source_input = request.GET.get('from', request.GET.get('version', previous['version']))
        single_release = request.GET.get('release')
        target_input = single_release if single_release is not None else request.GET.get('to', latest['version'])
        context['single_release'] = single_release is not None
        grouped = defaultdict(list)
        for release in sorted(releases.values(), key=lambda r: version_key(r['version']), reverse=True):
            if release.get('placeholder'):
                continue
            suffix = ('（尚未正式发布）' if release['status'] != 'stable' else
                      '（历史版本）' if not release.get('supported', True) else '')
            grouped[release['major']].append({'value': release['version'], 'label': _release_summary(release)['label'] + suffix})
        context['release_groups'] = [{'major': major, 'label': 'PostgreSQL ' + major, 'options': options}
                                     for major, options in grouped.items()]
        context['coverage'] = {'releases': len(releases), 'majors': len(grouped), 'as_of': snapshot['generated_at'][:10]}
        context['dataset_summary'] = '收录 PostgreSQL {} 起的 {} 个大版本、{} 份发布说明；数据更新于 {}。'.format(
            min(grouped, key=version_key), len(grouped),
            sum(not r.get('placeholder', False) for r in releases.values()), snapshot['generated_at'][:10])
        context['from_version'], context['to_version'] = source_input, target_input
        from_version = resolve_version(target_input if single_release is not None else source_input, releases)
        to_version = resolve_version(target_input, releases)
        context['from_version'], context['to_version'] = from_version, to_version
        if single_release is not None:
            context['report'] = release_report(snapshot, security, to_version)
            params = {'release': to_version}
        else:
            context['report'] = build_report(snapshot, security, from_version, to_version)
            params = {'from': from_version, 'to': to_version}
        attach_entry_relations(snapshot, context['report'])
        context['canonical_url'] = '/docs/compare/?' + urlencode(params)
        query = request.GET.get('q', '')[:200]
        category = request.GET.get('kind', 'all')
        if query:
            params['q'] = query
        if category in CATEGORY_LABELS:
            params['kind'] = category
        context['share_url'] = '/docs/compare/?' + urlencode(params)
        context['export_url'] = context['canonical_url'] + '&format=json'
        context['examples'] = [
            {'label': '{} → {}'.format(previous['version'], latest['version']),
             'url': '/docs/compare/?' + urlencode({'from': previous['version'], 'to': latest['version']})},
            {'label': '{}.0 → {}'.format(latest['major'], latest['version']),
             'url': '/docs/compare/?' + urlencode({'from': latest['major'] + '.0', 'to': latest['version']})},
        ]
        if request.GET.get('format') == 'json':
            response = JsonResponse(dict(format=1, **context['report']), json_dumps_params={'ensure_ascii': False})
            filename = ('postgresql-{}-changes.json'.format(to_version) if single_release is not None else
                        'postgresql-{}-to-{}.json'.format(from_version, to_version))
            response['Content-Disposition'] = 'attachment; filename="{}"'.format(filename)
            response['Cache-Control'] = 'public, max-age=300'
            return response
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        context['error'] = '版本对比数据暂不可用，请稍后再试。'
        status = 503
    except ValueError as exc:
        context['error'] = str(exc)
        status = 400
    if request.GET.get('format') == 'json':
        return JsonResponse({'error': context['error']}, status=status, json_dumps_params={'ensure_ascii': False})
    context['query'] = request.GET.get('q', '')[:200]
    context['category'] = request.GET.get('kind', 'all')
    if context['category'] not in CATEGORY_LABELS:
        context['category'] = 'all'
    title = 'PostgreSQL 版本对比'
    if context['report']:
        title = ('PostgreSQL {} 的版本变更'.format(context['report']['to_release']['label']) if context['single_release'] else
                 'PostgreSQL {} → {} 版本对比'.format(
                     context['report']['from_release']['label'], context['report']['to_release']['label']))
    context['seo'] = {
        'title': title,
        'description': '对比 PostgreSQL 大版本与小版本，查看新增功能、BUG 修复、性能改进、兼容性变化和 CVE 修复记录。',
        'canonical': context.get('canonical_url', '/docs/compare/'), 'lang': 'zh',
    }
    context['og'] = {'sitename': 'PGSQL.CC', 'type': 'website'}
    response = render_pgweb(request, 'docs', 'docs/compare.html', context)
    response.status_code = status
    return response
