"""Versioned lock modes and conflict matrices; see docs/lock-column.md."""

from collections import OrderedDict
from copy import deepcopy
from hashlib import sha1

from django.core.cache import cache

from .models import LockMode
from .sqlcmd_common import STATUS_LABEL, version_rows

ROOT = '/wiki/lock/'
CACHE_KEY = 'pgweb:wiki:lock-modes:1'
SCOPE_LABELS = {'table': '表级锁', 'row': '行级锁'}
ABBREVIATIONS = ('AS', 'RS', 'RX', 'SUE', 'S', 'SRX', 'X', 'AX', 'FKS', 'FS', 'FNKU', 'FU')


def forget():
    cache.delete(CACHE_KEY)


def records():
    """Twelve small entities, cached together; never query once per matrix cell."""
    result = cache.get(CACHE_KEY)
    if result is None:
        result = list(LockMode.objects.order_by('position').values())
        cache.set(CACHE_KEY, result, 300)
    return deepcopy(result)


def versions(rows=None):
    rows = records() if rows is None else rows
    majors = set.intersection(*(set(row['versions']) for row in rows)) if rows else set()
    result = version_rows(majors)
    for version in result:
        status_label = ('受支持版本' if version['support_status'] == 'supported' and
                        version['status'] != 'stable' else STATUS_LABEL[version['status']])
        version.update(status_label=status_label,
                       tone={'devel': 'dev', 'preview': 'beta', 'supported': 'live',
                             'end-of-life': 'eol'}[version['support_status']],
                       url=ROOT + '?v=' + version['major'])
    return result


def matrix(modes, matrix_id, caption):
    """Cross-scope cells have no direct comparison, not a compatibility claim."""
    rows = []
    for requested in modes:
        cells = []
        for held in modes:
            if requested['scope'] != held['scope']:
                state, symbol = 'different', '—'
                reason = '作用对象不同，不直接比较；还需检查命令同时取得的表锁和行锁'
            elif held['slug'] in {mode['slug'] for mode in requested['conflicts']}:
                state, symbol = 'conflict', '×'
                reason = '冲突：不同事务在同一{}上不能同时持有'.format(
                    '表' if requested['scope'] == 'table' else '行')
            else:
                state, symbol = 'compatible', '·'
                reason = '兼容：这两种锁模式本身不冲突'
            cells.append({'row_slug': requested['slug'], 'col_slug': held['slug'],
                          'state': state, 'symbol': symbol,
                          'label': '请求 {}，已持有 {}。{}。'.format(requested['name'], held['name'], reason)})
        rows.append({'mode': requested, 'cells': cells})
    return {'id': matrix_id, 'caption': caption, 'columns': modes, 'rows': rows,
            'size': len(modes), 'expanded': False}


def expanded_matrix(modes):
    """Expand common row-lock operations inside their accompanying table mode.

    These are display profiles, not new lock modes or a total strength order.
    Keep each table-only profile: explicit LOCK and ordinary INSERT must not
    inherit a row lock merely because SELECT/UPDATE use the same table mode.
    """
    by_slug = {mode['slug']: mode for mode in modes}
    expansions = {
        'row-share': [(mode['slug'], 'SELECT ' + mode['name'])
                      for mode in modes if mode['scope'] == 'row'],
        'row-exclusive': [('for-no-key-update', 'UPDATE（不修改键值）'),
                          ('for-update', 'UPDATE（修改键值） / DELETE')],
    }
    axes, groups = [], []
    for table in (mode for mode in modes if mode['scope'] == 'table'):
        children = expansions.get(table['slug'], [])
        groups.append({key: table[key] for key in ('slug', 'name', 'abbrev', 'url')})
        groups[-1]['span'] = 1 + len(children)
        axes.append(dict(table, display_name=table['name'], is_child=False,
                         group_start=bool(axes), table_slug=table['slug'], row_slug='',
                         mode_slugs=table['slug'], parent_name=table['name'], operation='仅表锁'))
        for row_slug, operation in children:
            row = by_slug[row_slug]
            axes.append(dict(row, slug=table['slug'] + '--' + row_slug,
                             name=table['name'] + ' + ' + row['name'], display_name=row['name'],
                             scope='combined', is_child=True, group_start=False,
                             table_slug=table['slug'], row_slug=row_slug,
                             mode_slugs=table['slug'] + ' ' + row_slug,
                             parent_name=table['name'], operation=operation))
    conflicts = {mode['slug']: {other['slug'] for other in mode['conflicts']} for mode in modes}
    rows = []
    for requested in axes:
        cells = []
        for held in axes:
            if held['table_slug'] in conflicts[requested['table_slug']]:
                state, symbol = 'conflict', '×'
                reason = '表锁冲突：{} 与 {} 冲突，即使操作不同的行也不能共存'.format(
                    by_slug[requested['table_slug']]['name'], by_slug[held['table_slug']]['name'])
            elif (requested['row_slug'] and held['row_slug'] and
                  held['row_slug'] in conflicts[requested['row_slug']]):
                state, symbol = 'row-conflict', '●'
                reason = '表锁兼容；仅命中同一行时，{} 与 {} 冲突。命中不同行时这组锁模式兼容'.format(
                    by_slug[requested['row_slug']]['name'], by_slug[held['row_slug']]['name'])
            else:
                state, symbol = 'compatible', '·'
                reason = '所列组合的表锁兼容，行锁也不冲突；其他对象与等待队列仍可能造成等待'
            cells.append({'row_slug': requested['slug'], 'col_slug': held['slug'],
                          'col_group_start': held['group_start'], 'state': state, 'symbol': symbol,
                          'label': '请求 {}，已持有 {}。{}。'.format(requested['name'], held['name'], reason)})
        rows.append({'mode': requested, 'cells': cells})
    return {'id': 'lock-full-matrix', 'caption': '按表锁展开的组合冲突矩阵',
            'columns': axes, 'rows': rows, 'groups': groups, 'size': len(axes), 'expanded': True}


def index(wanted=''):
    rows = records()
    order = versions(rows)
    if not order:
        raise LockMode.DoesNotExist('锁百科数据尚未导入')
    default = next((v['major'] for v in order if v['status'] == 'stable'), order[-1]['major'])
    wanted = str(wanted)
    if wanted == 'devel':
        wanted = next((v['major'] for v in order if v['status'] == 'devel'), wanted)
    if wanted and wanted not in {v['major'] for v in order}:
        raise LockMode.DoesNotExist('未收录此版本')
    major = wanted or default
    version = next(v for v in order if v['major'] == major)
    for item in order:
        item['is_current'] = item['major'] == major
    modes = []
    sources = OrderedDict()
    for position, row in enumerate(rows):
        snapshot = row['versions'][major]
        commands = [dict(command, url='/wiki/sql/{}/?v={}'.format(command['slug'], major))
                    for command in snapshot['commands']]
        mode = {key: row[key] for key in ('slug', 'name', 'name_zh', 'scope', 'summary')}
        mode.update(abbrev=row.get('abbrev') or ABBREVIATIONS[position],
                    summary=snapshot.get('summary') or row['summary'],
                    scope_label=SCOPE_LABELS[row['scope']], url=ROOT + row['slug'] + '/?v=' + major,
                    commands=commands, conflict_slugs=snapshot['conflicts'],
                    sources=snapshot.get('sources', []), snapshot=snapshot)
        mode['source_url'] = 'https://www.postgresql.org/docs/{}/explicit-locking.html'.format(version['doc_slug'])
        modes.append(mode)
        for source in snapshot.get('sources', []):
            if isinstance(source, dict) and source.get('url'):
                filename = source.get('path', source['url']).rsplit('/', 1)[-1]
                label = source.get('label') or {'mvcc.sgml': '手册源码：显式锁定',
                    'lock.c': '表级锁冲突定义', 'heapam.c': '行级锁模式定义'}.get(filename, filename)
                sources[source['url']] = dict(source, label=label,
                                              revision=source.get('revision', '')[:12])
    by_slug = {mode['slug']: mode for mode in modes}
    commands = OrderedDict()
    for mode in modes:
        mode['conflicts'] = [{'slug': slug, 'name': by_slug[slug]['name'], 'url': by_slug[slug]['url']}
                             for slug in mode.pop('conflict_slugs')]
        for command in mode['commands']:
            identity = (command['slug'], command['label'], command.get('note', ''))
            if identity not in commands:
                commands[identity] = dict(command, key=sha1('|'.join(identity).encode()).hexdigest()[:12], modes=[])
            commands[identity]['modes'].append({key: mode[key] for key in ('slug', 'name', 'url')})
    for command in commands.values():
        command['search_text'] = ' '.join((command['label'], command.get('note', ''),
                                          *(m['name'] for m in command['modes']))).lower()
    choices = OrderedDict()
    for command in commands.values():
        identity = (command['slug'], command['label'])
        if identity not in choices:
            choices[identity] = {'key': sha1('|'.join(identity).encode()).hexdigest()[:12],
                                 'label': command['label'], 'modes': [], 'notes': []}
        choice = choices[identity]
        command['choice_key'] = choice['key']
        for mode in command['modes']:
            if mode not in choice['modes']:
                choice['modes'].append(mode)
        if command.get('note') and command['note'] not in choice['notes']:
            choice['notes'].append(command['note'])
    for choice in choices.values():
        notes = choice.pop('notes')
        choice['note'] = '；'.join([note.rstrip('。；') for note in notes[:-1]] + notes[-1:])
    table_modes = [m for m in modes if m['scope'] == 'table']
    row_modes = [m for m in modes if m['scope'] == 'row']
    notice = ('尚未正式发布；锁规则及命令说明对应下方标注的采样构建。'
              if version['status'] in ('preview', 'devel') else
              '历史版本，已结束维护。' if version['support_status'] == 'end-of-life' else '')
    provenance = rows[0]['versions'][major].get('provenance', {})
    snapshot_label = '采样构建 {} · {}'.format(provenance.get('ref', provenance.get('label', '')),
                                               provenance.get('revision', '')[:12])
    return {
        'versions': list(reversed(order)), 'version': version, 'major': major, 'notice': notice,
        'total': len(modes), 'modes': modes, 'table_modes': table_modes, 'row_modes': row_modes,
        'table_matrix': matrix(table_modes, 'lock-table-matrix', '表级锁冲突矩阵'),
        'full_matrix': expanded_matrix(modes),
        'commands': list(commands.values()), 'command_choices': list(choices.values()),
        'sources': list(sources.values()),
        'matrix_note': '纵轴是请求的锁，横轴是另一事务已经持有的锁；只比较同一对象。',
        'snapshot_label': snapshot_label,
        'source_date': provenance.get('fetched_at', '')[:10],
        'manual_base': '/docs/{}/'.format(version['doc_slug']),
    }


def detail(slug, wanted=''):
    payload = index(wanted)
    mode = next((m for m in payload['modes'] if m['slug'] == slug), None)
    if mode is None:
        raise LockMode.DoesNotExist(slug)
    payload.update(mode=mode, conflicting_modes=mode['conflicts'],
                   compatible_modes=[m for m in payload['modes'] if m['scope'] == mode['scope']
                                     and m['slug'] not in {c['slug'] for c in mode['conflicts']}])
    for version in payload['versions']:
        version['url'] = ROOT + slug + '/?v=' + version['major']
    return payload


def for_command(slug, major):
    """Reverse links on SQL command pages, from the same versioned facts."""
    result = []
    for row in records():
        snapshot = row['versions'].get(str(major), {})
        matches = [command for command in snapshot.get('commands', []) if command['slug'] == slug]
        if matches:
            result.append({'name': row['name'], 'scope_label': SCOPE_LABELS[row['scope']],
                           'url': ROOT + row['slug'] + '/?v=' + str(major), 'commands': matches})
    return result
