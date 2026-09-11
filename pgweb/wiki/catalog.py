"""系统目录栏目的取数与组装。视图只负责拼上下文，这里负责形状。

前端模板按本文件给出的键名渲染，改键名等于改契约（`docs/catalog-column.md` §4）。
版本次序一律取 `CatalogVersion.position`：'9.0' 与 '10' 字符串比不出先后。
"""

from django.core.cache import cache

from .catalog_importer import compare_snapshots
from .models import (CATALOG_KINDS, CATALOG_KIND_EYEBROW, CATALOG_KIND_LABEL, CatalogRelation,
                     CatalogVersion, RELKIND_LABEL)


CACHE_KEY = 'pgweb:wiki:catalog-index'
VERSION_CACHE_KEY = 'pgweb:wiki:catalog-versions'
DOC_CACHE_KEY = 'pgweb:wiki:catalog-docpages'
CHANGES_CACHE_KEY = 'pgweb:wiki:catalog-changes:{}'
CACHE_SECONDS = 300

KINDS = [kind for kind, _, _ in CATALOG_KINDS]
KIND_LABEL = CATALOG_KIND_LABEL
EYEBROW = CATALOG_KIND_EYEBROW

# 最早收录的版本是基线，不代表这些关系首次于那一版引入。所有「引入」字样照此措辞。
BASELINE_TEMPLATE = '{0} 是本数据集的收录基线，不代表该关系首次于 {0} 引入。'
PREVIEW_NOTICE = '19 beta 3 为预发行快照，正式发布前仍可能变化。'
DEVEL_NOTICE = '20 开发版快照来自本站 devel 手册，只比较字段名与类型，描述与属性变化不作比较。'


# ---------------------------------------------------------------- 版本

def baseline_note(order=None):
    order = order if order is not None else versions()
    return BASELINE_TEMPLATE.format(order[0]['major']) if order else ''


def version_data(version, is_default=False):
    return {
        'major': version.major, 'label': version.label or version.major,
        'status': version.status, 'support_status': version.support_status,
        'status_label': version.status_label,
        'relation_count': version.relation_count, 'column_count': version.column_count,
        'url': version.changes_url, 'preview': version.is_preview, 'devel': version.is_devel,
        'doc_slug': version.doc_slug, 'release': version.release,
        'source_tag': version.source_tag, 'documentation_version': version.documentation_version,
        'runtime_verified': version.runtime_verified, 'schema_source': version.schema_source,
        'kinds': version.kinds or {}, 'position': version.position,
        'is_default': is_default,
    }


def versions():
    """全部版本，按 position。第一项是最早的 9.0，最后一项是 20 devel。"""
    rows = cache.get(VERSION_CACHE_KEY)
    if rows is None:
        stored = list(CatalogVersion.objects.all())
        default = stable_major(stored)
        rows = [version_data(version, version.major == default) for version in stored]
        cache.set(VERSION_CACHE_KEY, rows, CACHE_SECONDS)
    return rows


def stable_major(stored):
    """默认版本是 status='stable' 的那一版（当前 18），没有就取最后一个正式版。

    只有 `versions()` 建缓存时算一次，算完就记在版本条的 `is_default` 上。
    """
    for version in stored:
        if version.status == 'stable':
            return version.major
    formal = [v for v in stored if v.status not in ('preview', 'devel')]
    return (formal or stored)[-1].major if stored else ''


def default_major():
    """默认版本。取版本条上已经标好的 `is_default`，不再查库。"""
    order = versions()
    return next((v['major'] for v in order if v['is_default']),
                order[-1]['major'] if order else '')


def version_map():
    return {version['major']: version for version in versions()}


def pick_major(wanted, present, order=None):
    """无效或缺席的 ?v= 落回默认版本；默认版本这个关系也没有时取它最后存在的版本。"""
    if wanted and wanted in present:
        return wanted
    order = order if order is not None else versions()
    default = next((v['major'] for v in order if v['is_default']), '')
    if default in present:
        return default
    return present[-1] if present else ''


# ---------------------------------------------------------------- 手册链接

def doc_pages():
    """本站手册里已收录的 (版本段, 文件名)。缓存 5 分钟，够一屏渲染用。"""
    pairs = cache.get(DOC_CACHE_KEY)
    if pairs is None:
        from pgweb.docs.models import DocPage
        pairs = set()
        for tree, filename in DocPage.objects.values_list('version', 'file'):
            slug = 'devel' if int(tree) == 0 else str(int(tree))
            pairs.add((slug, filename))
        cache.set(DOC_CACHE_KEY, pairs, CACHE_SECONDS)
    return pairs


def doc_url(snapshot, pages=None):
    """本站手册该版该页的地址；没收录就留空，不给死链。

    `pages` 是 `doc_pages()` 的结果。一个详情页要问几十次，调用方读一次传进来，
    不要每次都从缓存里把上万条记录再取一遍。
    """
    doc = (snapshot or {}).get('doc') or {}
    slug, filename, anchor = doc.get('slug', ''), doc.get('file', ''), doc.get('anchor', '')
    pages = doc_pages() if pages is None else pages
    if not slug or not filename or (slug, filename) not in pages:
        return ''
    return '/docs/{}/{}{}'.format(slug, filename, '#' + anchor if anchor else '')


def forget():
    cache.delete(CACHE_KEY)
    cache.delete(VERSION_CACHE_KEY)
    cache.delete(DOC_CACHE_KEY)
    # 变更页按版本各缓存一份；版本表刚写过，照库里现有的版本清。
    cache.delete_many([CHANGES_CACHE_KEY.format(major) for major
                       in CatalogVersion.objects.values_list('major', flat=True)])


# ---------------------------------------------------------------- 索引页

def strip_of(relation, order, changed, removed_in):
    """版本轨迹：一排方格，每格一个版本。"""
    present = set(relation.present_in)
    cells = []
    for version in order:
        major = version['major']
        if major == removed_in:
            state = 'removed'
        elif major not in present:
            state = 'absent'
        elif major == relation.first_version and major != order[0]['major']:
            state = 'added'
        elif major in changed:
            state = 'changed'
        else:
            state = 'present'
        cells.append({
            'major': major, 'label': version['label'], 'state': state,
            'url': '{}?v={}'.format(relation.url, major) if state not in ('absent', 'removed') else '',
            'preview': version['preview'], 'devel': version['devel'],
        })
    return cells


def removed_after(relation, order):
    """移除标在 last_version 的下一版；还在最后一版里就没有移除版本。"""
    majors = [version['major'] for version in order]
    if not relation.last_version or relation.last_version not in majors:
        return ''
    index = majors.index(relation.last_version)
    return majors[index + 1] if index + 1 < len(majors) else ''


def row_of(relation, order):
    changed = set(relation.changed_in)
    removed_in = removed_after(relation, order)
    latest = relation.versions.get(relation.last_version) or {}
    columns = [column['name'] for column in latest.get('columns') or ()]
    return {
        'name': relation.name, 'url': relation.url, 'kind': relation.kind,
        'kind_label': relation.kind_label, 'summary': relation.summary,
        'summary_zh': relation.summary_zh,
        'first': relation.first_version, 'last': relation.last_version,
        'removed': bool(removed_in), 'removed_in': removed_in,
        'column_count': relation.column_count, 'changed_in': list(relation.changed_in),
        'change_count': len(relation.changed_in),
        'strip': strip_of(relation, order, changed, removed_in),
        'present_tokens': ' '.join(relation.present_in),
        'text': ' '.join([relation.name, relation.summary_zh, relation.summary] + columns),
    }


def groups_of(rows):
    groups = []
    for kind in KINDS:
        members = [row for row in rows if row['kind'] == kind]
        if not members:
            continue
        groups.append({'kind': kind, 'label': KIND_LABEL[kind], 'eyebrow': EYEBROW[kind],
                       'anchor': 'kind-' + kind, 'count': len(members), 'rows': members})
    return groups


def filters_of(rows, order):
    """筛选下拉。计数就地算，不再查库。"""
    def options(values):
        counts = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return counts

    kinds = options(row['kind'] for row in rows)
    present = options(major for row in rows for major in row['present_tokens'].split())
    first = options(row['first'] for row in rows if row['first'])
    labels = {version['major']: version['label'] for version in order}
    return [
        {'param': 'kind', 'label': '类别',
         'options': [{'value': kind, 'label': KIND_LABEL[kind], 'count': kinds[kind]}
                     for kind in KINDS if kinds.get(kind)]},
        {'param': 'present', 'label': '存在于版本',
         'options': [{'value': version['major'], 'label': labels[version['major']],
                      'count': present[version['major']]}
                     for version in reversed(order) if present.get(version['major'])]},
        {'param': 'first', 'label': '引入版本',
         'options': [{'value': version['major'], 'label': labels[version['major']],
                      'count': first[version['major']]}
                     for version in reversed(order) if first.get(version['major'])]},
    ]


def index_payload():
    order = versions()
    relations = list(CatalogRelation.objects.all())
    rows = [row_of(relation, order) for relation in relations]
    latest = order[-1]['major'] if order else ''
    snapshots = sum(len(relation.versions) for relation in relations)
    structural = sum(sum(1 for change in relation.changes if change.get('structural'))
                     for relation in relations)
    columns_latest = sum(len(relation.versions.get(latest, {}).get('columns') or ())
                         for relation in relations)
    groups = groups_of(rows)
    return {
        'total': len(rows), 'kind_count': len(groups),
        'default_major': default_major(), 'earliest_major': order[0]['major'] if order else '',
        'latest_major': latest,
        'versions': order, 'groups': groups, 'filters': filters_of(rows, order),
        'stats': {'relations': len(rows), 'columns': columns_latest,
                  'snapshots': snapshots, 'structural_changes': structural},
    }


def index():
    payload = cache.get(CACHE_KEY)
    if payload is None:
        payload = index_payload()
        cache.set(CACHE_KEY, payload, CACHE_SECONDS)
    return payload


def sibling_groups(kind, current=''):
    """页尾复用索引表：只留本类别那一组。"""
    groups = [dict(group, current=current) for group in index()['groups'] if group['kind'] == kind]
    return groups


def kind_nav(current=''):
    """「系统目录」下的四个类别，侧栏导航用。"""
    return [{'title': group['label'], 'link': '/docs/catalog/#' + group['anchor'],
             'active': group['kind'] == current} for group in index()['groups']]


# ---------------------------------------------------------------- 详情页

def reference_of(value, major, known):
    """字段引用：'pg_namespace.oid' → 可点的本站地址（目标关系该版存在才给）。"""
    if not value:
        return None
    name, _, column = value.partition('.')
    url = ''
    if name in known and major in known[name]:
        url = '/docs/catalog/{}/?v={}'.format(name, major)
    return {'text': value, 'name': name, 'column': column, 'url': url}


def column_data(column, major, known, added=(), types=None):
    types = types or {}
    change = types.get(column['name'])
    return {
        'name': column['name'], 'type': column.get('type', ''),
        'documented_type': column.get('documented_type', ''),
        'description': column.get('description', ''),
        'description_zh': column.get('description_zh', ''),
        'zh_from': column.get('zh_from', ''),
        'hidden': bool(column.get('hidden')), 'not_null': bool(column.get('not_null')),
        'array_dimensions': column.get('array_dimensions', 0), 'attnum': column.get('attnum'),
        'added': column['name'] in added,
        'type_change': {'from': change['from'], 'to': change['to']} if change else None,
        'references': reference_of(column.get('references', ''), major, known),
        'schema_note': column.get('schema_note', ''),
    }


def change_note(relation, major, order, change):
    """本版变化一句话。9.0 是收录基线，不说「引入」。"""
    majors = [version['major'] for version in order]
    if major == majors[0]:
        return baseline_note(order)
    if change is None:
        previous = previous_major(relation, major, order)
        return '相对 PostgreSQL {} 无变化。'.format(previous) if previous else ''
    if change['status'] == 'added':
        return 'PostgreSQL {} 新增此关系，共 {} 个字段。'.format(
            major, len(relation.versions.get(major, {}).get('columns') or ()))
    parts = [
        ('新增 {} 个字段', len(change.get('added_columns') or ())),
        ('移除 {} 个', len(change.get('removed_columns') or ())),
        ('类型变更 {} 处', len(change.get('type_changes') or ())),
        ('描述更新 {} 处', len(change.get('description_changes') or ())),
    ]
    written = [template.format(count) for template, count in parts if count]
    if not written:
        return '相对 PostgreSQL {} 无变化。'.format(change['from'])
    return '相对 PostgreSQL {}：{}。'.format(change['from'], '，'.join(written))


def previous_major(relation, major, order):
    """按 present_in 顺序的上一版；9.0 或首版返回 ''。"""
    present = relation.present_in
    if major not in present:
        return ''
    index = present.index(major)
    return present[index - 1] if index else ''


def ribbon_of(relation, major, order, changed, removed_in, pages=None):
    cells = strip_of(relation, order, changed, removed_in)
    by_major = {version['major']: version for version in order}
    for cell in cells:
        snapshot = relation.versions.get(cell['major'])
        cell['current'] = cell['major'] == major
        cell['doc_url'] = doc_url(snapshot, pages) if snapshot else ''
        cell['status'] = by_major[cell['major']]['status']
    return cells


def facts_of(relation, major, snapshot, order):
    rows = [('类别', relation.kind_label, '/docs/catalog/#kind-' + relation.kind)]
    if snapshot.get('relation_oid'):
        rows.append(('关系 OID', str(snapshot['relation_oid']), ''))
    relkind = snapshot.get('relkind', '') or relation.relkind
    if relkind:
        label = RELKIND_LABEL.get(relkind, relkind)
        value = '{}（{}）'.format(relkind, label) if label != relkind else relkind
        if snapshot.get('shared'):
            value += ' · 全局共享'
        rows.append(('关系类型', value, ''))
    rows.append(('字段数', str(len(snapshot.get('columns') or ())), ''))
    first = relation.first_version
    baseline = order[0]['major'] if order else ''
    rows.append(('引入版本', '{}（收录基线）'.format(first) if first == baseline else first, ''))
    version = version_map().get(major)
    if version:
        rows.append(('版本状态', version['status_label'], version['url']))
    rows.append(('结构变更', '{} 次'.format(len(relation.changed_in)), ''))
    if snapshot.get('carried_from'):
        reason = snapshot.get('carry_reason') or '手册没有这张表'
        rows.append(('字段来源', '沿用 {}（{}）'.format(snapshot['carried_from'], reason), ''))
    return [{'label': label, 'value': value, 'url': url} for label, value, url in rows if value]


def timeline_of(relation, order):
    """演化历史，新的在前。"""
    rows = []
    for change in reversed(relation.changes):
        rows.append({
            'to': change['to'], 'from': change['from'], 'status': change['status'],
            'url': '{}?v={}'.format(relation.url, change['to'])
            if change['to'] in relation.present_in else '',
            'structural': bool(change.get('structural')),
            'added': [column['name'] for column in change.get('added_columns') or ()],
            'removed': [column['name'] for column in change.get('removed_columns') or ()],
            'types': [{'name': item['name'], 'from': item['from'], 'to': item['to']}
                      for item in change.get('type_changes') or ()],
            'attrs': [{'name': item['name'], 'attribute': item['attribute'],
                       'from': item['from'], 'to': item['to']}
                      for item in change.get('attribute_changes') or ()],
            'order_changed': bool(change.get('column_order_changed')),
            'descriptions': [{'name': item['name'], 'from': item['from'], 'to': item['to']}
                             for item in change.get('description_changes') or ()],
            'relation_description_changed': bool(change.get('relation_description_changed')),
            'references': [{'name': item['name'], 'from': item['from'], 'to': item['to']}
                           for item in change.get('reference_changes') or ()],
            'carried': bool(change.get('carried')),
        })
    return rows


def signature_of(column):
    """判断字段「有变」看这几项：类型、是否隐式、可空、数组维数。"""
    return (column.get('type', ''), bool(column.get('hidden')),
            bool(column.get('not_null')), column.get('array_dimensions', 0))


def matrix_of(relation, order):
    """字段 × 版本。`changed` 指与上一版相比类型、隐式、可空或数组维数有变。"""
    present = [version for version in order if version['major'] in relation.present_in]
    columns, names = {}, []
    for version in present:
        major = version['major']
        columns[major] = {column['name']: column
                          for column in relation.versions[major].get('columns') or ()}
        for name in columns[major]:
            if name not in names:
                names.append(name)
    rows = []
    for name in names:
        cells, previous = [], None
        for version in present:
            major = version['major']
            column = columns[major].get(name)
            if column is None:
                # 移除只标在最后存在版本的下一版。
                cells.append({'major': major, 'state': 'removed' if previous else 'absent',
                              'type': '', 'url': ''})
                previous = None
                continue
            signature = signature_of(column)
            cells.append({'major': major,
                          'state': 'changed' if previous and previous != signature else 'exists',
                          'type': column.get('type', ''),
                          'url': '{}?v={}'.format(relation.url, major)})
            previous = signature
        rows.append({'name': name, 'cells': cells})
    return {'versions': present, 'rows': rows}


def notice_of(version):
    if version and version['preview']:
        return PREVIEW_NOTICE
    if version and version['devel']:
        return DEVEL_NOTICE
    return ''


def detail(name, wanted=''):
    """一个关系的详情页上下文。找不到关系抛 CatalogRelation.DoesNotExist。"""
    relation = CatalogRelation.objects.get(name=name)
    order = versions()
    major = pick_major(wanted, relation.present_in, order)
    if not major:
        raise CatalogRelation.DoesNotExist(name)
    snapshot = relation.versions[major]
    # 手册页清单一次读到底：下面的版本条与链接要问它几十次。
    pages = doc_pages()
    known = {row.name: set(row.present_in)
             for row in CatalogRelation.objects.all().only('name', 'present_in')}

    change = next((c for c in relation.changes
                   if c['to'] == major and c['status'] != 'removed'), None)
    added = {column['name'] for column in (change or {}).get('added_columns') or ()}
    types = {item['name']: item for item in (change or {}).get('type_changes') or ()}
    previous = previous_major(relation, major, order)
    removed_columns = []
    if change and previous:
        base = relation.versions.get(previous) or {}
        gone = {column['name'] for column in (change or {}).get('removed_columns') or ()}
        removed_columns = [column_data(column, previous, known)
                           for column in base.get('columns') or () if column['name'] in gone]

    version = version_map().get(major)
    doc_versions = []
    for item in order:
        if item['major'] not in relation.present_in:
            continue
        url = doc_url(relation.versions.get(item['major']), pages)
        if url:
            doc_versions.append({'major': item['major'], 'label': item['label'], 'url': url})
    local_doc = doc_url(snapshot, pages)
    return {
        'relation': relation, 'name': relation.name, 'kind_label': relation.kind_label,
        'eyebrow': relation.eyebrow,
        'version': version, 'previous_major': previous, 'snapshot': snapshot,
        'description': snapshot.get('description', ''),
        'description_zh': snapshot.get('description_zh', ''),
        'columns': [column_data(column, major, known, added, types)
                    for column in snapshot.get('columns') or ()],
        'removed_columns': removed_columns,
        'change': change, 'change_note': change_note(relation, major, order, change),
        'ribbon': ribbon_of(relation, major, order, set(relation.changed_in),
                            removed_after(relation, order), pages),
        'links': {
            'doc': local_doc,
            'doc_label': 'PostgreSQL {} 手册'.format(
                '20 devel' if (version or {}).get('devel') else major) if local_doc else '',
            'official': snapshot.get('source_url', ''),
            'definition': snapshot.get('definition_source_url', ''),
        },
        'facts': facts_of(relation, major, snapshot, order),
        'timeline': timeline_of(relation, order),
        'matrix': matrix_of(relation, order),
        'system_columns': [{'name': column['name'], 'type': column.get('type', ''),
                            'attnum': column.get('attnum')}
                           for column in snapshot.get('system_columns') or ()],
        'doc_versions': doc_versions,
        'sibling_groups': sibling_groups(relation.kind, relation.name),
        'notice': notice_of(version),
        'versions': order,
    }


# ---------------------------------------------------------------- 变更页

def compare(left, right):
    """两份快照现算一条变化记录，供非相邻比较用。"""
    return compare_snapshots(left or {}, right or {}, '', '')


def card_of(relation, major, change):
    tags = []
    for kind, template, count in (
            ('added', '新增 {} 个字段', len(change.get('added_columns') or ())),
            ('removed', '移除 {} 个字段', len(change.get('removed_columns') or ())),
            ('type', '类型变更 {} 处', len(change.get('type_changes') or ())),
            ('attr', '属性变更 {} 处', len(change.get('attribute_changes') or ())),
            ('desc', '描述更新 {} 处', len(change.get('description_changes') or ())),
            ('ref', '引用更新 {} 处', len(change.get('reference_changes') or ()))):
        if count:
            tags.append({'kind': kind, 'text': template.format(count)})
    if change.get('column_order_changed'):
        tags.append({'kind': 'order', 'text': '字段顺序调整'})
    if change.get('relation_description_changed'):
        tags.append({'kind': 'desc', 'text': '关系说明更新'})
    return {
        'name': relation.name,
        'url': '{}?v={}'.format(relation.url, major) if major in relation.present_in
        else relation.url,
        'kind': relation.kind, 'kind_label': relation.kind_label,
        'summary_zh': relation.summary_zh, 'summary': relation.summary,
        'status': change['status'], 'tags': tags,
        'column_count': len(relation.versions.get(major, {}).get('columns')
                            or relation.versions.get(change['from'], {}).get('columns') or ()),
    }


def changes(major, from_major=''):
    """一个版本相对上一版（或 ?from= 指定的基准）的变更页上下文。

    相邻比较是默认入口，和索引页一样缓存 5 分钟；`?from=` 的非相邻比较现算不缓存。
    """
    if not from_major:
        payload = cache.get(CHANGES_CACHE_KEY.format(major))
        if payload is None:
            payload = changes_payload(major)
            cache.set(CHANGES_CACHE_KEY.format(major), payload, CACHE_SECONDS)
        return payload
    return changes_payload(major, from_major)


def changes_payload(major, from_major=''):
    order = versions()
    by_major = {version['major']: version for version in order}
    if major not in by_major:
        raise CatalogVersion.DoesNotExist(major)
    majors = [version['major'] for version in order]
    index = majors.index(major)
    natural = majors[index - 1] if index else ''
    if from_major not in majors or from_major == major:
        from_major = ''
    base = from_major or natural
    arbitrary = bool(from_major) and from_major != natural

    version = by_major[major]
    previous = by_major.get(base)
    relations = list(CatalogRelation.objects.all())

    added, removed, changed, wording = [], [], [], []
    counts = {'added_relations': 0, 'removed_relations': 0, 'changed_relations': 0,
              'structurally_changed': 0, 'added_columns': 0, 'removed_columns': 0,
              'type_changes': 0, 'description_changes': 0}
    for relation in relations:
        if arbitrary:
            left = relation.versions.get(base) or {}
            right = relation.versions.get(major) or {}
            if not left and not right:
                continue
            change = compare_snapshots(left, right, base, major)
        else:
            change = next((c for c in relation.changes
                           if c['to'] == major and c['from'] == base), None)
        if change is None:
            continue
        card = card_of(relation, major, change)
        if change['status'] == 'added':
            added.append(card)
            counts['added_relations'] += 1
            # 字段计数只统计既存关系的增减，和 cat transitions 的口径一致：
            # 新增关系的字段已经由「新增的关系」那一段说清楚了。
        elif change['status'] == 'removed':
            removed.append(card)
            counts['removed_relations'] += 1
        else:
            counts['changed_relations'] += 1
            counts['added_columns'] += len(change.get('added_columns') or ())
            counts['removed_columns'] += len(change.get('removed_columns') or ())
            if change.get('structural'):
                counts['structurally_changed'] += 1
                changed.append(card)
            else:
                wording.append(card)
        counts['type_changes'] += len(change.get('type_changes') or ())
        counts['description_changes'] += len(change.get('description_changes') or ())

    baseline = not base
    baseline_groups = []
    if baseline:
        rows = [row_of(relation, order) for relation in relations
                if major in relation.present_in]
        baseline_groups = groups_of(rows)

    return {
        'version': version, 'previous': previous, 'from_major': from_major,
        'arbitrary': arbitrary, 'versions': [dict(item, is_current=item['major'] == major)
                                             for item in order],
        'summary': counts, 'added': added, 'removed': removed, 'changed': changed,
        'wording': wording, 'baseline': baseline, 'baseline_groups': baseline_groups,
        'notice': notice_of(version), 'baseline_note': baseline_note(order) if baseline else '',
    }
