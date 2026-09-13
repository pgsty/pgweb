"""SQL 命令导入与页面共用的版本、正文解析和比较规则。"""

from collections import defaultdict
from difflib import SequenceMatcher
from functools import lru_cache

from bs4 import BeautifulSoup

from pgweb.core.models import TESTING_SHORTSTRING, Version
from pgweb.docs.versions import DEVEL_MAJOR_VERSION

DEVEL_MAJOR = str(DEVEL_MAJOR_VERSION)
STATUS_LABEL = {'stable': '当前稳定版', 'historical': '历史版本',
                'preview': '预发行', 'devel': '开发版'}


def major_of(tree):
    return DEVEL_MAJOR if tree == 0 else str(int(tree)) if tree >= 10 else str(tree)


def version_key(major):
    return tuple(int(part) for part in major.split('.'))


def version_rows(majors):
    """不建版本表；标签与支持状态始终取本站 Version。"""
    majors = sorted(set(majors), key=version_key)
    stored = {major_of(row.tree): row for row in Version.objects.all()}
    formal = [major for major in majors if major != DEVEL_MAJOR and
              not (stored.get(major) and stored[major].testing)]
    default = next((major for major in reversed(formal) if stored.get(major) and
                    stored[major].current), (formal or majors or [''])[-1])
    out = []
    for position, major in enumerate(majors):
        row = stored.get(major)
        status = ('devel' if major == DEVEL_MAJOR else 'preview' if row and row.testing
                  else 'stable' if major == default else 'historical')
        label = major
        if status == 'devel':
            label += ' devel'
        elif status == 'preview':
            label += ' {} {}'.format(TESTING_SHORTSTRING[row.testing], row.latestminor)
        out.append({
            'major': major, 'label': label, 'status': status,
            'support_status': status if status in ('preview', 'devel') else
                              'supported' if row and row.supported else 'end-of-life',
            'doc_slug': 'devel' if major == DEVEL_MAJOR else major,
            'command_count': 0, 'added_count': 0, 'removed_count': 0, 'changed_count': 0,
            'position': position,
        })
    return out


def normalized_lines(text):
    return [' '.join(line.split()) for line in (text or '').strip('\n').splitlines()]


def line_changes(left, right):
    """逐行比较；保留重复行的位置，避免把同名占位符的所有行都涂绿。"""
    a, b = normalized_lines(left), normalized_lines(right)
    added, removed, positions = [], [], set()
    for tag, i, j, k, l in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ('replace', 'delete'):
            removed.extend(a[i:j])
        if tag in ('replace', 'insert'):
            added.extend(b[k:l])
            positions.update(range(k, l))
    return ({'added': added, 'removed': removed} if added or removed else None), positions


def sections_at(snapshots, major):
    """解析 sections_same_as；循环或断链不继续跳转，validate 会拒绝这种快照。"""
    seen = set()
    while major and major not in seen:
        seen.add(major)
        snapshot = snapshots.get(major) or {}
        if snapshot.get('sections'):
            return snapshot['sections']
        major = snapshot.get('sections_same_as', '')
    return []


@lru_cache(maxsize=4096)
def section_text(html):
    soup = BeautifulSoup(html, 'html.parser')
    return ' '.join(soup.get_text().split())


def section_map(sections):
    parts = defaultdict(list)
    for section in sections or ():
        parts[section['key']].append(section_text(section['html']))
    return {key: '\n'.join(value) for key, value in parts.items()}


def compare(left, right, from_major='', to_major=''):
    """两份已解析小节的快照现算差异；导出与任意两版比较共用。"""
    if not left and not right:
        return None
    record = {'from': from_major, 'to': to_major, 'status': 'changed', 'renamed': None,
              'synopsis': None, 'sections': {'added': [], 'removed': [], 'changed': []},
              'purpose_changed': False}
    if not left or not right:
        record['status'] = 'added' if right else 'removed'
        return record
    if left['file'] != right['file']:
        record['renamed'] = {'from_file': left['file'], 'to_file': right['file']}
    record['synopsis'], _ = line_changes(left['synopsis_text'], right['synopsis_text'])
    a, b = section_map(left['sections']), section_map(right['sections'])
    record['sections'] = {
        'added': [key for key in b if key not in a],
        'removed': [key for key in a if key not in b],
        'changed': [key for key in b if key in a and a[key] != b[key]],
    }
    record['purpose_changed'] = any(' '.join((left.get(key) or '').split()) !=
                                    ' '.join((right.get(key) or '').split())
                                    for key in ('purpose', 'purpose_zh'))
    return record if (record['renamed'] or record['synopsis'] or record['purpose_changed'] or
                      any(record['sections'].values())) else None
