"""Validate and import the complete, versioned lock reference snapshot.

One row per lock mode is sufficient: the eight table modes and four row modes
have fixed identities. Version metadata is embedded with each snapshot, so a
deployed site needs neither the harvesting checkout nor the JSON input file.
"""

from copy import deepcopy
import re
from urllib.parse import urlsplit

from django.db import transaction

from pgweb.docs.versions import DEVEL_MAJOR_VERSION

from .models import LockMode
from .snapshot import content_hash

FORMAT = 1
TABLE_MODES = ('access-share', 'row-share', 'row-exclusive', 'share-update-exclusive',
               'share', 'share-row-exclusive', 'exclusive', 'access-exclusive')
ROW_MODES = ('for-key-share', 'for-share', 'for-no-key-update', 'for-update')
MODE_SCOPES = {**dict.fromkeys(TABLE_MODES, 'table'), **dict.fromkeys(ROW_MODES, 'row')}
MODE_FIELDS = ('name', 'name_zh', 'abbrev', 'scope', 'summary', 'position', 'versions')
SLUG_RE = re.compile(r'^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')
REVISION_RE = re.compile(r'^[0-9a-f]{40}$')
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
PROVENANCE_FIELDS = {'provenance', 'sources', 'source', 'source_url', 'source_rev', 'revision',
                     'sha256', 'fetched_at', 'generated_at', 'imported_at', 'content_hash'}
SOURCE_HOSTS = {'www.postgresql.org', 'postgresql.org', 'git.postgresql.org',
                'raw.githubusercontent.com', 'github.com'}


def require(item, fields, label):
    if not isinstance(item, dict):
        raise ValueError('{} 必须是对象'.format(label))
    missing = set(fields) - set(item)
    if missing:
        raise ValueError('{} 缺少字段：{}'.format(label, ', '.join(sorted(missing))))


def text(value, label, limit=None, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or (limit and len(value) > limit):
        raise ValueError('{} 文本无效'.format(label))


def source_url(value, label):
    text(value, label)
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.hostname not in SOURCE_HOSTS or
            parsed.username or parsed.password or not parsed.path):
        raise ValueError('{} 必须指向 PostgreSQL 上游文档或源码'.format(label))
    if parsed.hostname in {'github.com', 'raw.githubusercontent.com'} and not parsed.path.startswith('/postgres/postgres/'):
        raise ValueError('{} 必须指向 postgres/postgres 源码'.format(label))


def sources(items, label, revision):
    if not isinstance(items, list) or not items:
        raise ValueError('{} 缺少采集出处'.format(label))
    for item in items:
        require(item, ('kind', 'url'), label)
        text(item['kind'], label + ' kind')
        source_url(item['url'], label + ' URL')
        if 'official_url' in item:
            source_url(item['official_url'], label + ' official URL')
        if item.get('sha256') is not None and (not isinstance(item['sha256'], str) or
                                              not SHA256_RE.fullmatch(item['sha256'])):
            raise ValueError('{} sha256 无效'.format(label))
        if item.get('revision') is not None and item['revision'] != revision:
            raise ValueError('{} revision 与版本来源不一致'.format(label))
        if item['url'].startswith('https://raw.githubusercontent.com/') and '/{}/'.format(revision) not in item['url']:
            raise ValueError('{} 源码 URL 未固定到采集提交'.format(label))


def validate(snapshot):
    """Reject incomplete matrices and malformed links before any database writes."""
    require(snapshot, ('format', 'versions', 'modes', 'default_major'), '快照')
    if snapshot['format'] != FORMAT:
        raise ValueError('不支持的锁百科快照格式')
    if not isinstance(snapshot['versions'], list) or not snapshot['versions']:
        raise ValueError('版本列表为空')
    metadata = {}
    for item in snapshot['versions']:
        require(item, ('major', 'label', 'status', 'doc_slug', 'revision', 'sources'), '版本')
        major = item['major']
        if not isinstance(major, str) or not re.fullmatch(r'[1-9][0-9]+', major) or major in metadata:
            raise ValueError('版本标识无效或重复')
        for field in ('label', 'doc_slug', 'revision'):
            text(item[field], major + ' ' + field)
        if item['status'] not in ('historical', 'stable', 'preview', 'devel'):
            raise ValueError('{} 版本状态无效'.format(major))
        if item['doc_slug'] not in (major, 'devel') or (item['doc_slug'] == 'devel') != (item['status'] == 'devel'):
            raise ValueError('{} 文档版本标识无效'.format(major))
        if not REVISION_RE.fullmatch(item['revision']):
            raise ValueError('{} 缺少固定源码提交'.format(major))
        sources(item['sources'], major + ' 来源', item['revision'])
        if not any(source['kind'] == 'source' for source in item['sources']):
            raise ValueError('{} 缺少源码出处'.format(major))
        metadata[major] = item
    expected = {str(major) for major in range(10, DEVEL_MAJOR_VERSION + 1)}
    if set(metadata) != expected:
        raise ValueError('必须完整覆盖 PostgreSQL 10–{} 的版本'.format(DEVEL_MAJOR_VERSION))
    if not isinstance(snapshot['default_major'], str) or snapshot['default_major'] not in metadata:
        raise ValueError('默认版本不在快照中')
    if not isinstance(snapshot['modes'], list) or len(snapshot['modes']) != 12:
        raise ValueError('必须包含八种表级锁与四种行级锁')
    modes, positions = {}, set()
    for item in snapshot['modes']:
        require(item, ('slug', *MODE_FIELDS), '锁模式')
        slug = item['slug']
        if not isinstance(slug, str) or slug not in MODE_SCOPES or slug in modes:
            raise ValueError('锁模式 slug 无效或重复：{}'.format(slug))
        if item['scope'] != MODE_SCOPES[slug]:
            raise ValueError('{} 锁作用域不一致'.format(slug))
        for field in ('name', 'name_zh', 'summary'):
            text(item[field], slug + ' ' + field)
        text(item['abbrev'], slug + ' abbrev', limit=8)
        if (type(item['position']) is not int or not 0 <= item['position'] <= 32767 or
                item['position'] in positions):
            raise ValueError('{} 排序值无效或重复'.format(slug))
        positions.add(item['position'])
        if not isinstance(item['versions'], dict) or set(item['versions']) != expected:
            raise ValueError('{} 版本覆盖不完整'.format(slug))
        for major, version in item['versions'].items():
            label = '{} @ {}'.format(slug, major)
            require(version, ('conflicts', 'commands', 'sources'), label)
            conflicts = version['conflicts']
            if not isinstance(conflicts, list) or any(not isinstance(other, str) for other in conflicts):
                raise ValueError('{} 冲突列表无效'.format(label))
            if len(set(conflicts)) != len(conflicts) or any(
                    other not in MODE_SCOPES or MODE_SCOPES[other] != item['scope'] for other in conflicts):
                raise ValueError('{} 存在未知、重复或跨作用域的冲突边'.format(label))
            if not conflicts:
                raise ValueError('{} 缺少冲突矩阵'.format(label))
            if not isinstance(version['commands'], list) or not version['commands']:
                raise ValueError('{} 缺少命令映射'.format(label))
            seen_commands = set()
            for command in version['commands']:
                require(command, ('slug', 'label', 'note', 'source_url'), label + ' 命令')
                text(command['slug'], label + ' command slug', limit=64)
                if not SLUG_RE.fullmatch(command['slug']):
                    raise ValueError('{} 命令 slug 无效'.format(label))
                text(command['label'], label + ' command label')
                text(command['note'], label + ' command note', empty=True)
                if 'variant' in command:
                    text(command['variant'], label + ' command variant', empty=True)
                key = (command['slug'], command['label'], command.get('variant', ''))
                if key in seen_commands:
                    raise ValueError('{} 命令映射重复'.format(label))
                seen_commands.add(key)
                source_url(command['source_url'], label + ' command source URL')
                if 'source' in command:
                    sources([command['source']], label + ' command source', metadata[major]['revision'])
            sources(version['sources'], label + ' 来源', metadata[major]['revision'])
        modes[slug] = item
    if set(modes) != set(MODE_SCOPES):
        raise ValueError('锁模式集合不完整')
    for slug, item in modes.items():
        for major, version in item['versions'].items():
            for other in version['conflicts']:
                if slug not in modes[other]['versions'][major]['conflicts']:
                    raise ValueError('{} @ {} 与 {} 的冲突不对称'.format(slug, major, other))
    return True


def business_content(value):
    """Sources identify evidence; they are not changes to the lock's behavior."""
    if isinstance(value, dict):
        return {key: business_content(item) for key, item in value.items()
                if key not in PROVENANCE_FIELDS}
    if isinstance(value, list):
        return [business_content(item) for item in value]
    return value


def prepared_modes(snapshot):
    metadata = {item['major']: item for item in snapshot['versions']}
    source_rev = ';'.join('{}:{}'.format(major, metadata[major]['revision'])
                          for major in sorted(metadata, key=int))
    for item in snapshot['modes']:
        values = {field: deepcopy(item[field]) for field in ('slug', *MODE_FIELDS)}
        for major, version in values['versions'].items():
            version['provenance'] = deepcopy(metadata[major])
        values['source_rev'] = source_rev
        values['content_hash'] = content_hash(business_content(values))
        if item.get('content_hash') and item['content_hash'] != values['content_hash']:
            raise ValueError('{} content_hash 不匹配'.format(item['slug']))
        yield values


def changes(snapshot):
    validate(snapshot)
    prepared = list(prepared_modes(snapshot))
    stored = dict(LockMode.objects.values_list('slug', 'content_hash'))
    added, updated, unchanged = [], [], []
    for item in prepared:
        bucket = (added if item['slug'] not in stored else updated
                  if stored[item['slug']] != item['content_hash'] else unchanged)
        bucket.append(item['slug'])
    missing = sorted(set(stored) - {item['slug'] for item in prepared})
    report = {'versions': len(snapshot['versions']), 'modes': len(prepared),
              'added': len(added), 'updated': len(updated), 'unchanged': len(unchanged),
              'missing': missing, 'removed': 0}
    return prepared, set(added + updated), report


def preview(snapshot):
    return changes(snapshot)[2]


def forget():
    from . import lock
    lock.forget()


@transaction.atomic
def import_snapshot(snapshot, prune=False):
    prepared, write, report = changes(snapshot)
    for item in prepared:
        if item['slug'] in write:
            LockMode.objects.update_or_create(slug=item['slug'], defaults={
                key: value for key, value in item.items() if key != 'slug'})
    if prune:
        report['removed'] = len(report['missing'])
        LockMode.objects.filter(slug__in=report['missing']).delete()
    if write or report['removed']:
        transaction.on_commit(forget)
    report['pruned'] = bool(prune)
    return report
