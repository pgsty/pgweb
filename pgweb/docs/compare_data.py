"""Extract a complete, portable comparison index from translated release notes.

Only the Changes and migration/incompatibility lists become entries. Overview
lists repeat changes, and contributor acknowledgements are not release changes.
The source prose is retained; classification is a convenience, not an upstream
taxonomy. No network or database access takes place in this module.
"""

from collections import Counter
from copy import copy
from datetime import date
import hashlib
import json
import re
from urllib.parse import parse_qs, urljoin, urlsplit

import bleach
from bs4 import BeautifulSoup, Comment, NavigableString, Tag


FORMAT_VERSION = 1
PARSER_VERSION = 2
# This patch number was skipped upstream, not omitted by the importer.
UNRELEASED_VERSIONS = frozenset({'18.5'})
CATEGORIES = frozenset({
    'security', 'bugfix', 'performance', 'feature', 'compatibility', 'improvement',
})
_RELEASE_VERSION = re.compile(r'^(\d+)\.(\d+)$')
_CVES = re.compile(r'\bCVE-\d{4}-\d{4,}\b', re.I)
_DATE_LABEL = re.compile(r'(?:发布日期|Release date|Date of release|Released)\s*[:：.]*\s*', re.I)
_ISO_DATE = re.compile(r'^(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)')
_CN_DATE = re.compile(r'^(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')
_BUGFIX = re.compile(
    r'\b(?:fix(?:es|ed)?|correct(?:ed)?|repair)\b|修复|修正|纠正|更正|修补'
    r'|(?:避免|防止).*(?:崩溃|错误|死锁|溢出|泄漏|损坏|无限循环|挂起|丢失)'
    r'|(?:avoid|prevent).*\b(?:crash|corrupt|deadlock|overflow|leak|hang)', re.I,
)
_PERFORMANCE = re.compile(
    r'(?:提高|提升|改进|改善|优化|增强).*(?:性能|效率|速度)'
    r'|(?:减少|降低).*(?:开销|内存使用|内存占用|耗时|延迟)'
    r'|加快|加速|\b(?:speed up|faster|improve.*performance|reduce.*overhead)\b', re.I,
)
_SAFE_TAGS = frozenset({
    'p', 'a', 'code', 'pre', 'em', 'strong', 'b', 'i', 'span', 'br',
    'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'blockquote', 'sub', 'sup',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'caption', 'kbd', 'samp',
    'var', 'acronym', 'abbr', 'div', 'h4', 'h5', 'h6',
})
_SAFE_ATTRS = {
    'a': ['href', 'title'], 'abbr': ['title'], 'acronym': ['title'],
    'ol': ['start', 'type'], 'li': ['value'], 'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan', 'scope'],
}


def _text(node):
    """Respect source spacing around inline tags and paragraph boundaries."""
    parts = []
    for child in node.descendants:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString) and not child.find_parent(['script', 'style']):
            parts.append(str(child))
        elif child.name in {'p', 'li', 'br', 'pre', 'dt', 'dd'}:
            parts.append(' ')
    return re.sub(r'\s+', ' ', ''.join(parts)).strip()


def _heading(section):
    heading = section.find(re.compile(r'^h[2-6]$'))
    if not heading:
        return ''
    title = re.sub(r'\s*[#§]\s*$', '', _text(heading))
    return re.sub(r'^[A-Z]?\.?\d+(?:\.\d+)*\.?\s*', '', title).strip()


def _section(root, suffix, heading_pattern):
    # PG 10–12 use generated section IDs; more recent manuals use semantic IDs.
    found = root.find(id=re.compile(r'-' + suffix + r'$', re.I))
    if found:
        return found
    for candidate in root.find_all(['div', 'section']):
        if ('sect2' in candidate.get('class', []) or candidate.name == 'section') and re.search(heading_pattern, _heading(candidate), re.I):
            return candidate
    return None


def top_level_items(section):
    """Keep a nested recovery procedure inside its parent change entry."""
    if section is None:
        return []
    return [item for item in section.find_all('li') if not item.find_parent('li')]


def safe_html(fragment, base_url):
    """Keep technical markup while preventing active HTML and unsafe links."""
    soup = BeautifulSoup(str(fragment), 'html.parser')
    for node in soup.find_all(['script', 'style', 'iframe', 'object', 'embed', 'svg', 'math', 'form']):
        node.decompose()
    for node in soup.select('.id_link, .titlepage, .toc, .navheader, .navfooter'):
        node.decompose()
    for link in soup.find_all('a'):
        href = link.get('href', '').strip()
        # urljoin with our own origin allows relative manual links, while only
        # http(s) survives. The dummy origin is removed for on-site links.
        try:
            resolved = urljoin('https://pgsql.cc' + base_url, href)
            parsed = urlsplit(resolved)
        except ValueError:
            link.attrs.pop('href', None)
            continue
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            link.attrs.pop('href', None)
        elif parsed.netloc == 'pgsql.cc':
            link['href'] = parsed.path + ('?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')
        else:
            link['href'] = resolved
    return bleach.clean(
        str(soup), tags=_SAFE_TAGS, attributes=_SAFE_ATTRS,
        protocols={'http', 'https'}, strip=True, strip_comments=True,
    ).strip()


def _date_info(root):
    for paragraph in root.find_all('p'):
        raw = _text(paragraph)
        label = _DATE_LABEL.search(raw)
        if not label:
            continue
        remainder = raw[label.end():]
        match = _ISO_DATE.match(remainder) or _CN_DATE.match(remainder)
        released = ''
        if match:
            try:
                released = date(*(int(part) for part in match.groups())).isoformat()
            except ValueError:
                pass
        # An "as of" date on a preview must never become its release date.
        as_of = re.search(r'(?:截至|as of)\s*(\d{4}-\d{2}-\d{2})', remainder, re.I)
        return released, as_of.group(1) if as_of else '', remainder
    return '', '', ''


def _commits(item):
    result = set()
    for link in item.find_all('a', href=True):
        try:
            parsed = urlsplit(link['href'])
        except ValueError:
            continue
        value = ''
        if parsed.netloc.lower() == 'postgr.es':
            match = re.match(r'^/c/([0-9a-f]{7,40})/?$', parsed.path, re.I)
            value = match.group(1) if match else ''
        elif parsed.netloc.lower() == 'git.postgresql.org':
            query = parse_qs(parsed.query.replace(';', '&'))
            value = query.get('h', [''])[0]
        elif parsed.netloc.lower() == 'github.com':
            match = re.match(r'^/postgres/postgres/commit/([0-9a-f]{7,40})/?$', parsed.path, re.I)
            value = match.group(1) if match else ''
        if re.fullmatch(r'[0-9a-f]{7,40}', value, re.I):
            result.add(value.lower())
    return sorted(result)


def _comment_branch_groups(comment):
    """An author may list multiple commits without repeating the Author line."""
    groups, current, branches = [], [], set()
    for line in str(comment).splitlines():
        match = re.match(r'^Branch:\s+(\S+)(?:\s+Release:\s+\S+)?\s+\[([0-9a-f]{7,40})\]', line, re.I)
        if line.startswith('Author:') or match and match[1] in branches:
            if current:
                groups.append(current)
            current, branches = [], set()
        if match:
            current.append((match[1], match[2].lower()))
            branches.add(match[1])
    if current:
        groups.append(current)
    return groups


def commit_aliases(sources):
    """Read upstream's explicit backport equivalences from SGML comments.

    Each Author block is one commit across branches. A list item may mention
    several independent commits, so it is essential to split repeated Authors.
    Union across files accounts for shortened/extended backport lists.
    """
    parents = {}

    def root(value):
        parents.setdefault(value, value)
        while value != parents[value]:
            parents[value] = parents[parents[value]]
            value = parents[value]
        return value

    for source in sources:
        for comment in re.findall(r'<!--(.*?)-->', source, re.S):
            for block in _comment_branch_groups(comment):
                commits = [commit for branch, commit in block]
                if not commits:
                    continue
                canonical = root(commits[0].lower())
                for commit in commits[1:]:
                    parents[root(commit.lower())] = canonical
    groups = {}
    for commit in parents:
        groups.setdefault(root(commit), []).append(commit)
    return {commit: sorted(groups[root(commit)]) for commit in parents}


def sgml_commit_entries(source, major):
    """Index SGML entry titles and comment commits without rendering SGML.

    PG 10/11 HTML does not include commit links. Its SGML comments still carry
    the upstream identifiers. The caller requires matching section, position,
    count and title before enriching a rendered entry from these comments.
    """
    # These are EMPTY elements in legacy SGML. Treating an unclosed xref as
    # ordinary HTML swallows the following prose (and sometimes comments).
    source = re.sub(r'<(xref|anchor)\b([^>]*?)/?>', r'<\1\2/>', source)
    soup = BeautifulSoup(source, 'html.parser')
    records = {}
    for release in soup.find_all('sect1'):
        match = re.fullmatch(r'release-(\d+)(?:-(\d+))?', release.get('id', ''), re.I)
        if not match or match.group(1) != str(major):
            continue
        version = '{}.{}'.format(major, match.group(2) or '0')
        parts = {'migration': [], 'changes': []}
        for section in release.find_all('sect2'):
            title = section.find('title')
            if title is None:
                continue
            label = _text(title)
            if re.search(r'^(?:变更|更改|变化|Changes)$', label, re.I):
                part = 'changes'
            elif re.search(r'迁移|Migration|不兼容|Incompatibilit', label, re.I):
                part = 'migration'
            else:
                continue
            for item in section.find_all('listitem'):
                if item.find_parent('listitem'):
                    continue
                paragraph = item.find('para')
                comments = item.find_all(string=lambda node: isinstance(node, Comment))
                # Major-release authors commonly place their commit comment
                # immediately BEFORE the listitem, whereas patch notes put it
                # inside. Both belong to this record.
                for sibling in item.previous_siblings:
                    if isinstance(sibling, Comment):
                        comments.append(sibling)
                    elif isinstance(sibling, Tag) or str(sibling).strip():
                        break
                commits = set()
                for comment in comments:
                    for branches in _comment_branch_groups(comment):
                        if branches:
                            commits.add(next((commit for branch, commit in branches if branch == 'REL_{}_STABLE'.format(major)), branches[0][1]).lower())
                    commits.update(commit.lower() for commit in re.findall(r'^\d{4}-\d{2}-\d{2}\s+\[([0-9a-f]{7,40})\]', str(comment), re.M | re.I))
                for link in item.find_all('ulink', url=True):
                    found = re.search(r'(?:&commit_baseurl;|postgr\.es/c/)([0-9a-f]{7,40})', link['url'], re.I)
                    if found:
                        commits.add(found.group(1).lower())
                identity = copy(item)
                for link in identity.find_all('ulink'):
                    if '&commit_baseurl;' in link.get('url', '') or _text(link) == '§':
                        link.decompose()
                # Retain the actual cross-reference identifier, never an
                # unstable generated chapter number or translated label.
                for reference in identity.find_all('xref'):
                    reference.replace_with(' ' + reference.get('linkend', '') + ' ')
                path = [
                    _text(ancestor.find('title', recursive=False))
                    for ancestor in reversed(list(item.parents))
                    if isinstance(ancestor, Tag) and ancestor.name in {'sect3', 'sect4', 'sect5'} and
                    ancestor.find('title', recursive=False)
                ]
                parts[part].append({
                    'title': _text(paragraph) if paragraph else '',
                    'commits': sorted(commits),
                    'identity_text': _text(identity),
                    'cves': sorted(set(cve.upper() for cve in _CVES.findall(_text(identity)))),
                    'section': ' / '.join(path),
                    'source_entry_id': '{}/{}/{:03d}'.format(version, part, len(parts[part]) + 1),
                    'source_hash': hashlib.sha256(str(item).encode()).hexdigest(),
                })
        records[version] = parts
    return records


def calibrate_source_entries(release, source_records, aliases):
    """Attach language-independent provenance from the original English SGML.

    The separate source audit establishes positional bilingual correspondence
    and complete rendered prose before publication. Counts and exact CVE sets
    also fail closed here, so a missing entry cannot silently shift identities.
    """
    parts = source_records.get(release['version'])
    if parts is None:
        raise ValueError('Missing canonical release source: ' + release['version'])
    counts = Counter()
    for part, entries in [
        ('migration', release['entries'][:release['compatibility_count']]),
        ('changes', release['entries'][release['compatibility_count']:]),
    ]:
        originals = parts.get(part, [])
        if len(originals) != len(entries):
            raise ValueError('Canonical entry count mismatch: {}/{}'.format(release['version'], part))
        for entry, original in zip(entries, originals):
            if entry['cves'] != original['cves']:
                raise ValueError('Canonical CVE mismatch: ' + original['source_entry_id'])
            old_groups = {tuple(group) for group in entry.get('commit_groups', [])}
            entry.update({key: original[key] for key in ['identity_text', 'source_entry_id', 'source_hash']})
            entry['source_commits'] = original['commits']
            groups = {tuple(aliases.get(commit, [commit])) for commit in original['commits']}
            entry['commit_groups'] = [list(group) for group in sorted(groups)]
            entry['commit_aliases'] = sorted({commit for group in groups for commit in group})
            category = classify(original['title'], original['section'], original['cves'], release['minor'], part == 'migration')
            counts['category_adjusted'] += category != entry['category']
            entry['category'] = category
            counts['commit_groups_adjusted'] += groups != old_groups
            counts['entries'] += 1
    return dict(counts)


def enrich_source_commits(release, source_records):
    """Attach only independently matched comment commits; report all misses."""
    counts = Counter()
    parts = source_records.get(release['version'], {})
    compatibility_count = release['compatibility_count']
    for part, entries in [
        ('migration', release['entries'][:compatibility_count]),
        ('changes', release['entries'][compatibility_count:]),
    ]:
        originals = parts.get(part, [])
        for position, entry in enumerate(entries):
            if entry['commits']:
                continue
            counts['without_html_commits'] += 1
            if len(originals) != len(entries):
                counts['section_count_mismatch'] += 1
                continue
            source = originals[position]
            paragraph = BeautifulSoup(entry['html'], 'html.parser').find('p')
            # DocBook quote markup supplies curly quotation marks at render
            # time. Ignore these formatting marks and source whitespace only.

            def normalize(value):
                return re.sub(r'[\s§“”‘’]+', '', value)
            if paragraph is None or normalize(_text(paragraph)) != normalize(source['title']):
                counts['title_mismatch'] += 1
                continue
            if not source['commits']:
                counts['without_source_commits'] += 1
                continue
            entry['source_commits'] = source['commits']
            counts['enriched'] += 1
    return dict(counts)


def classify(title, section, cves, minor, compatibility=False):
    if cves:
        return 'security'
    if compatibility:
        return 'compatibility'
    if _BUGFIX.search(title):
        return 'bugfix'
    if _PERFORMANCE.search(title) or re.search(r'(?:一般性能|性能改进|General Performance)$', section, re.I):
        return 'performance'
    return 'feature' if minor == 0 else 'improvement'


def _entry(item, release, section, compatibility=False):
    ancestors = [ancestor for ancestor in item.parents if isinstance(ancestor, Tag)]
    path = []
    for ancestor in reversed(ancestors[:ancestors.index(section)]):
        if any(re.fullmatch(r'sect\d', cls) for cls in ancestor.get('class', [])):
            label = _heading(ancestor)
            if label:
                path.append(label)
    if not path:
        path = ['兼容性' if compatibility else '变更']
    section_label = ' / '.join(path)
    first = copy(item.find('p') or item)
    for link in first.find_all('a'):
        if _text(link) in {'§', '#'}:
            link.decompose()
    title = _text(first)
    # Only remove a trailing ASCII contributor list, never parenthetical SQL
    # syntax or Chinese qualifiers. The full attribution remains in html.
    title = re.sub(r'\s*[（(][A-Za-zÀ-ž][A-Za-zÀ-ž\s.,，、\-\x27]+[）)]\s*$', '', title).strip()
    text = _text(item)
    cves = sorted(set(cve.upper() for cve in _CVES.findall(text)))
    commits = _commits(item)
    native_id = item.get('id', '')
    stable_key = native_id if native_id and not native_id.startswith('id-') else ((commits[0] if commits else title) + '|' + section_label)
    entry_id = release['version'] + '-' + hashlib.sha256(stable_key.encode()).hexdigest()[:16]
    anchor = native_id or next((a.get('id') for a in ancestors if a.get('id')), '')
    return {
        'id': entry_id,
        'title': title,
        'html': safe_html(item.decode_contents(), release['manual_url']),
        'text': text,
        'category': classify(title, section_label, cves, release['minor'], compatibility),
        'section': section_label,
        'section_path': path,
        'cves': cves,
        'commits': commits,
        'source_url': release['source_url'] + ('#' + anchor if anchor else ''),
    }


def parse_release(content, version, manual, status='stable', *, build='', supported=False):
    """Parse one native release note into the versioned snapshot contract."""
    match = _RELEASE_VERSION.fullmatch(version)
    if not match or int(match.group(1)) < 10:
        raise ValueError('Comparison requires a PostgreSQL version >= 10 as major.minor')
    if status not in {'stable', 'preview', 'devel'}:
        raise ValueError('Unknown release status: ' + status)
    major, minor = match.group(1), int(match.group(2))
    filename = 'release-{}{}.html'.format(major, '-' + str(minor) if minor else '')
    manual_url = '/docs/{}/{}'.format(manual, filename)
    release = {
        'version': version, 'major': major, 'minor': minor, 'status': status,
        'build': build or version, 'supported': bool(supported),
        'source_url': manual_url if manual == 'devel' else '/docs/release/{}/'.format(version),
        'manual': str(manual), 'manual_url': manual_url,
    }
    soup = BeautifulSoup(content or '', 'html.parser')
    for excluded in soup.select('.toc, .navheader, .navfooter'):
        excluded.decompose()
    root = soup.find(id='RELEASE-' + major + ('-' + str(minor) if minor else '')) or soup
    release['date'], release['source_as_of'], release['date_text'] = _date_info(root)
    changes = _section(root, 'CHANGES', r'^(?:变更|更改|变化|Changes)$')
    migration = _section(root, 'MIGRATION', r'迁移|Migration')
    incompatible = _section(root, 'INCOMPATIBILITIES', r'不兼容|Incompatibilit')
    entries = []
    # Migration paragraphs are presented separately, while their incompatibility
    # list entries also participate in search, filters and exports.
    compatibility_sections = [s for s in [migration, incompatible] if s is not None]
    seen_nodes = set()
    for section in compatibility_sections:
        for item in top_level_items(section):
            if id(item) not in seen_nodes:
                entries.append(_entry(item, release, section, compatibility=True))
                seen_nodes.add(id(item))
    if changes:
        for item in top_level_items(changes):
            if id(item) not in seen_nodes:
                entries.append(_entry(item, release, changes))
                seen_nodes.add(id(item))
    ids = Counter(entry['id'] for entry in entries)
    positions = Counter()
    for entry in entries:
        if ids[entry['id']] > 1:
            positions[entry['id']] += 1
            entry['id'] += '-' + str(positions[entry['id']])
    migration_parts = []
    for section in compatibility_sections:
        if any(parent in compatibility_sections for parent in section.parents):
            continue
        fragment = copy(section)
        for node in fragment.select('.titlepage, ul, ol'):
            node.decompose()
        migration_parts.append(safe_html(fragment.decode_contents(), manual_url))
    release.update({
        'entries': entries,
        'migration_html': '\n'.join(migration_parts),
        'placeholder': not bool(changes),
        'entry_count': len(entries),
        'changes_count': len(top_level_items(changes)),
        'compatibility_count': len(seen_nodes) - len(top_level_items(changes)),
    })
    if not changes:
        summary = copy(root)
        for node in summary.select('.titlepage, .toc'):
            node.decompose()
        release['summary_html'] = safe_html(summary.decode_contents(), manual_url)
    release['content_hash'] = hashlib.sha256(json.dumps(release, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return release
