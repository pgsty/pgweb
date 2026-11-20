"""Project release lifecycle onto pinned Wiki samples without changing evidence."""
import re

from pgweb.core.models import Version
from .manuals import manual_slug


def release_versions(rows):
    """Use the site's current release for navigation; retain every source field."""
    releases = {manual_slug(v.tree): v for v in Version.objects.all() if v.tree}
    current = next((major for major, v in releases.items() if v.current), '')
    has_current = any(row['major'] == current for row in rows)
    result = []
    for original in rows:
        row = dict(original)
        version = releases.get(row['major'])
        if version is not None:
            row['sample_label'] = row['label']
            row['sample_status'] = row['status']
            if has_current:
                row['is_default'] = row['major'] == current
            row['status'] = ('preview' if version.testing else
                             'stable' if version.current else 'historical')
            row['support_status'] = ('preview' if version.testing else
                                     'supported' if version.supported else 'end-of-life')
            row['preview'] = bool(version.testing)
            row['devel'] = False
            row['label'] = version.versionstring_spaced if version.testing else row['major']
            row['latest_release'] = version.versionstring
            row['status_label'] = ('预发行' if version.testing else '当前稳定版' if version.current
                                   else '受支持版本' if version.supported else '历史版本')
            sample = (row.get('release') or row.get('server_version') or
                      row.get('source_release') or row['sample_label'])
            # Major-only labels do not establish a particular patch build.
            if sample and sample != row['major'] and not version.testing:
                normalized = re.sub(r'\s+', '', sample).lower().removeprefix('rel_')
                normalized = re.sub(r'_?(alpha|beta|rc)_?', r'\1', normalized).replace('_', '.')
                preview = bool(re.fullmatch(re.escape(row['major']) + r'(?:alpha|beta|rc)\d+', normalized))
                older = (bool(re.fullmatch(r'\d+(?:\.\d+)+', normalized)) and
                         tuple(map(int, normalized.split('.'))) <
                         tuple(map(int, version.versionstring.split('.'))))
                if preview or older:
                    row['source_notice'] = ('PostgreSQL {} 已正式发布；本栏采样构建为 {}，'
                                            '尚未完成 {} 校准。').format(
                                                row['major'], sample, version.versionstring)
        result.append(row)
    return result
