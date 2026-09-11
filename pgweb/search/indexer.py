"""Explicit, transactional indexing, keyed by source hashes.

Two sources feed the same table: the locally served PostgreSQL manuals
(one row per definition or text fragment, rebuilt per major version when
the page content changes) and the PGEXT extension catalogue (one row per
extension, replaced wholesale, which is cheap at a few thousand rows).
"""
import math
import re
from collections import Counter

from django.db import connection, transaction
from django.contrib.postgres.search import SearchVector
from django.db.models import Value
from django.utils.html import escape

from pgweb.docs.models import DocPage
from pgweb.docs.versions import manual_major, manual_tree
from pgweb.ext.catalog import catalog as extension_catalog, category_label, detail_url, pg_range, value_label
from .extract import digest, extract_page, source_hash
from .lexicon import index_text
from .models import IndexedPage, SearchEntry
from .taxonomy import normalize_name
from . import service

LOCK_NAMESPACE = 734021


def eligible_page(page):
    if not page.file.endswith('.html') or page.file in ('bookindex.html', 'index.html'):
        return False
    # Older release notes are copied into newer manuals but their reader routes redirect.
    release = re.match(r'release-(\d+)(?:-|\.)', page.file)
    return not release or int(release.group(1)) == manual_major(page.version_id)


def entry_object(document_id, version, entry):
    title = index_text(' '.join([entry['name'], *entry['aliases'], entry['signature'], entry['heading']]))
    body = index_text(entry['body'])
    vector = (SearchVector(Value(title), config='simple', weight='A') +
              SearchVector(Value(body), config='simple', weight='D'))
    return SearchEntry(source='pg', document_id=document_id, version=version, vector=vector, **entry)


def rebuild_version(version, force=False, dry_run=False, progress=None):
    version = manual_major(version)
    report = Counter()
    tree = manual_tree(version)
    pages = list(DocPage.objects.filter(version=tree).order_by('file'))
    hashes = dict(IndexedPage.objects.filter(page__version=tree).values_list('page_id', 'source_hash'))
    changed, eligible = [], []
    for page in pages:
        if not eligible_page(page):
            continue
        eligible.append(page.pk)
        fingerprint = source_hash(page.title, page.content)
        if not force and hashes.get(page.pk) == fingerprint:
            report['unchanged'] += 1
            continue
        entries = extract_page(page.file, page.title, page.content, 'devel' if tree == 0 else str(int(version)))
        changed.append((page, fingerprint, entries))
        report['pages'] += 1
        report['entries'] += len(entries)
        report.update({'kind:' + k: n for k, n in Counter(e['kind'] for e in entries).items()})
        if progress and report['pages'] % 100 == 0:
            progress('{} pages extracted'.format(report['pages']))
    if dry_run:
        return dict(report)
    with transaction.atomic():
        # Serialize publication per version; lock changed source rows while publishing.
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LOCK_NAMESPACE, int(version)])
        for page, fingerprint, entries in changed:
            # Reject a changed source rather than publishing results for the wrong text.
            current = DocPage.objects.select_for_update().get(pk=page.pk)
            if (current.file != page.file or current.version_id != page.version_id
                    or source_hash(current.title, current.content) != fingerprint):
                raise ValueError('Source changed while indexing: ' + page.file)
            document, _ = IndexedPage.objects.update_or_create(page_id=page.pk, defaults={'source_hash': fingerprint})
            objects = [entry_object(document.pk, version, entry) for entry in entries]
            SearchEntry.objects.bulk_create(objects, batch_size=100, update_conflicts=True,
                                            unique_fields=['document', 'key'],
                                            update_fields=['entity_key', 'kind', 'subtype', 'name', 'name_key', 'aliases',
                                                           'anchor', 'heading', 'signature', 'body', 'preview', 'vector', 'version'])
            document.entries.exclude(key__in=[entry['key'] for entry in entries]).delete()
        IndexedPage.objects.filter(page__version=tree).exclude(page_id__in=eligible).delete()
    service.forget_catalog()
    return dict(report)


def extension_entry(row):
    """One catalogue row as a search entry: name, descriptions, tags and a small fact card."""
    name = row['name']
    name_key = normalize_name(name)
    aliases = {name_key}
    if row.get('pkg') and row['pkg'] != name:
        aliases.add(normalize_name(row['pkg']))
    if '_' in name_key:
        aliases.add(name_key.replace('_', ''))
    category = category_label(row.get('category') or '') if row.get('category') else ''
    zh = ' '.join((row.get('zh_desc') or '').split())
    en = ' '.join((row.get('en_desc') or '').split())
    tags = [t for t in (row.get('tags') or []) if t]
    facts = [('版本', row.get('version')), ('分类', category), ('语言', row.get('lang')),
             ('许可证', row.get('license')), ('PostgreSQL', pg_range(row.get('pg_ver'))),
             ('来源', value_label('repo', row.get('repository') or 'Unknown'))]
    parts = []
    if zh or en:
        parts.append('<p class="ds-ext-desc">' + escape(zh or en) + '</p>')
    if zh and en:
        parts.append('<p class="ds-ext-desc-en">' + escape(en) + '</p>')
    parts.append('<dl class="ds-ext-facts">' + ''.join(
        '<div><dt>{}</dt><dd>{}</dd></div>'.format(escape(label), escape(str(value))) for label, value in facts if value) + '</dl>')
    if row.get('need_ddl') and re.fullmatch(r'[A-Za-z0-9_]+', name):
        parts.append('<pre data-lang="sql">CREATE EXTENSION ' + name + ';</pre>')
    if tags:
        parts.append('<p class="ds-ext-tags">' + ' '.join('<code>' + escape(t) + '</code>' for t in tags) + '</p>')
    signature = ' · '.join(v for v in ('v' + row['version'] if row.get('version') else '', row.get('lang') or '',
                                       (row.get('license') or '') if row.get('license') != 'Unknown' else '') if v)
    return {
        'key': digest('ext\0' + name), 'entity_key': 'extension:' + name_key, 'kind': 'extension',
        'subtype': 'contrib' if row.get('contrib') else 'catalog', 'name': name, 'name_key': name_key,
        'aliases': sorted(aliases), 'anchor': '', 'heading': (category + ' · ' if category else '') + '扩展目录',
        'signature': signature, 'body': '\n'.join(v for v in (zh, en, ' '.join(tags), row.get('pkg') or '', category) if v),
        'preview': ''.join(parts), 'url': detail_url(name), '_desc': zh + ' ' + en,
    }


def rebuild_extensions(dry_run=False):
    rows = [row for row in extension_catalog() if row.get('name')]
    entries = [extension_entry(row) for row in rows]
    if dry_run:
        return {'extensions': len(entries)}
    top = max((math.log1p(row.get('stars') or 0) for row in rows), default=0) or 1
    objects = []
    for row, entry in zip(rows, entries):
        desc = entry.pop('_desc')
        entry['weight'] = round(math.log1p(row.get('stars') or 0) / top, 4)
        title = index_text(' '.join([entry['name'], *entry['aliases']]))
        vector = (SearchVector(Value(title), config='simple', weight='A') +
                  SearchVector(Value(index_text(desc)), config='simple', weight='B') +
                  SearchVector(Value(index_text(entry['body'])), config='simple', weight='D'))
        objects.append(SearchEntry(source='ext', document=None, version=None, vector=vector, **entry))
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LOCK_NAMESPACE, 0])
        SearchEntry.objects.filter(source='ext').delete()
        SearchEntry.objects.bulk_create(objects, batch_size=200)
    service.forget_catalog()
    return {'extensions': len(objects)}


# ---------------------------------------------------------------- 错误代码

def errcode_entry(code, text, card):
    """One SQLSTATE as a search entry, sharing the manual rows' entity so the
    result list shows the 百科 entry once and the preview still lists the
    manual versions."""
    name_key = normalize_name(code.sqlstate)
    aliases = {name_key, normalize_name(code.condition_name)}
    for macro in code.macros:
        aliases.add(normalize_name(macro))
    if '_' in code.condition_name:
        aliases.add(normalize_name(code.condition_name).replace('_', ''))
    zh_name = text.name if text else ''
    summary = (text.summary if text else '') or ''
    klass = '{} {}'.format(code.klass.code, code.klass.label)
    names = [('条件名', code.condition_name), ('宏名称', card['macro'])]
    facts = [('类别', klass), ('严重等级', code.severity_label), ('启用版本', card['since']), ('状态', card['status_text'])]

    def dl(rows, extra=''):
        return '<dl class="ds-ext-facts{}">'.format(extra) + ''.join(
            '<div><dt>{}</dt><dd>{}</dd></div>'.format(escape(label), escape(str(value)))
            for label, value in rows if value) + '</dl>'
    parts = []
    if summary:
        parts.append('<p class="ds-ext-desc">' + escape(summary) + '</p>')
    # Identifiers get a full row each (macros run to 60 characters); the rest share a grid.
    parts.append(dl(names, ' ds-ext-facts--stack ds-ext-facts--mono') + dl(facts))
    glance = next((sec.get('html', '') for sec in (text.sections if text else []) if sec.get('anchor') == 'at-a-glance'), '')
    if glance:
        parts.append('<h3>速览</h3>' + glance)
    body = '\n'.join(v for v in (summary, zh_name, text.description if text else '', klass, code.severity_label) if v)
    return {
        'key': digest('errcode\0' + code.sqlstate), 'entity_key': 'error:' + name_key, 'kind': 'error',
        'subtype': code.klass.code, 'name': code.sqlstate, 'name_key': name_key,
        'aliases': sorted(aliases), 'anchor': '', 'heading': 'Class ' + klass + ' · SQL 状态码',
        'signature': code.condition_name + ('（' + zh_name + '）' if zh_name else ''),
        'body': body, 'preview': ''.join(parts), 'url': code.url, 'weight': 0.5,
    }


def rebuild_errcodes(dry_run=False):
    """Replace the search entries of the SQL 状态码 column (source 'errcode')."""
    from pgweb.wiki import errcode as errcode_payload
    from pgweb.wiki.models import ErrorCode, ErrorCodeText
    texts = {t.errcode_id: t for t in ErrorCodeText.objects.filter(lang='zh')}
    codes = list(ErrorCode.objects.select_related('klass').all())
    entries = [errcode_entry(code, texts.get(code.sqlstate), errcode_payload.card(code)) for code in codes]
    if dry_run:
        return {'errcodes': len(entries)}
    objects = []
    for entry in entries:
        title = index_text(' '.join([entry['name'], *entry['aliases']]))
        vector = (SearchVector(Value(title), config='simple', weight='A') +
                  SearchVector(Value(index_text(entry['body'])), config='simple', weight='B'))
        objects.append(SearchEntry(source='errcode', document=None, version=None, vector=vector, **entry))
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LOCK_NAMESPACE, 0])
        SearchEntry.objects.filter(source='errcode').delete()
        SearchEntry.objects.bulk_create(objects, batch_size=200)
    service.forget_catalog()
    return {'errcodes': len(objects)}


# ---------------------------------------------------------------- 系统目录

def catalog_entry(relation):
    """One catalog relation as a search entry, sharing the manual rows' entity so the
    result list shows the 百科 entry once and the preview still lists the manual
    versions."""
    name = relation.name
    name_key = normalize_name(name)
    aliases = {name_key, name_key.replace('_', '')}
    # Drop the pg_ prefix only when what is left is still a compound name:
    # "stat_activity" points at one relation, "class" or "index" is a word that
    # belongs to the manual, not to pg_class.
    stem = name_key[3:] if name_key.startswith('pg_') else ''
    if '_' in stem:
        aliases.update((stem, stem.replace('_', '')))
    zh = ' '.join((relation.summary_zh or '').split())
    en = ' '.join((relation.summary or '').split())
    latest = relation.versions.get(relation.last_version) or {}
    columns = [column['name'] for column in latest.get('columns') or ()]
    description = ' '.join((latest.get('description_zh') or latest.get('description') or '').split())
    facts = [('类别', relation.kind_label), ('字段数', relation.column_count),
             ('引入版本', relation.first_version),
             ('版本覆盖', '{} – {}'.format(relation.first_version, relation.last_version)),
             ('结构变更', '{} 次'.format(len(relation.changed_in)) if relation.changed_in else ''),
             ('关系 OID', relation.relation_oid or '')]
    parts = []
    if zh or en:
        parts.append('<p class="ds-ext-desc">' + escape(zh or en) + '</p>')
    if zh and en:
        parts.append('<p class="ds-ext-desc-en">' + escape(en) + '</p>')
    parts.append('<dl class="ds-ext-facts">' + ''.join(
        '<div><dt>{}</dt><dd>{}</dd></div>'.format(escape(label), escape(str(value)))
        for label, value in facts if value) + '</dl>')
    if columns:
        parts.append('<p class="ds-ext-tags">' + ' '.join(
            '<code>' + escape(column) + '</code>' for column in columns) + '</p>')
    return {
        'key': digest('catalog\0' + name), 'entity_key': 'relation:' + name_key,
        'kind': 'relation', 'subtype': relation.kind, 'name': name, 'name_key': name_key,
        'aliases': sorted(aliases), 'anchor': '',
        'heading': relation.kind_label + ' · 系统目录',
        'signature': ' · '.join(v for v in (
            relation.kind_label, '{} 个字段'.format(relation.column_count),
            '{} – {}'.format(relation.first_version, relation.last_version)) if v),
        'body': '\n'.join(v for v in (zh, en, description, ' '.join(columns),
                                      relation.kind_label) if v),
        'preview': ''.join(parts), 'url': relation.url, 'weight': 0.5,
        '_title': ' '.join([name, *sorted(aliases)]), '_lead': zh + ' ' + en,
    }


def rebuild_catalog(dry_run=False):
    """Replace the search entries of the 系统目录 column (source 'catalog')."""
    from pgweb.wiki.models import CatalogRelation
    relations = list(CatalogRelation.objects.all())
    entries = [catalog_entry(relation) for relation in relations]
    if dry_run:
        return {'catalog': len(entries)}
    objects = []
    for entry in entries:
        title = index_text(entry.pop('_title'))
        lead = index_text(entry.pop('_lead'))
        vector = (SearchVector(Value(title), config='simple', weight='A') +
                  SearchVector(Value(lead), config='simple', weight='B') +
                  SearchVector(Value(index_text(entry['body'])), config='simple', weight='D'))
        objects.append(SearchEntry(source='catalog', document=None, version=None, vector=vector,
                                   **entry))
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LOCK_NAMESPACE, 0])
        SearchEntry.objects.filter(source='catalog').delete()
        SearchEntry.objects.bulk_create(objects, batch_size=200)
    service.forget_catalog()
    return {'catalog': len(objects)}


# ---------------------------------------------------------------- 配置参数

def guc_entry(parameter):
    """One configuration parameter as a search entry, sharing the entity of the
    manual's own GUC definition rows so the result list shows the 百科 entry once
    and the preview still lists the manual versions."""
    from pgweb.wiki.models import GUC_CONTEXT_LABEL, GUC_VARTYPE_LABEL
    name = parameter.name
    name_key = normalize_name(name)
    aliases = {name_key}
    if '_' in name_key:
        aliases.add(name_key.replace('_', ''))
    zh = ' '.join((parameter.short_desc_zh or '').split())
    en = ' '.join((parameter.short_desc or '').split())
    editorial = parameter.editorial or {}
    summary = ' '.join((editorial.get('summary_zh') or '').split())
    mechanism = [' '.join(str(part).split()) for part in (editorial.get('mechanism_zh') or ()) if part]
    vartype = GUC_VARTYPE_LABEL.get(parameter.vartype, parameter.vartype)
    context = GUC_CONTEXT_LABEL.get(parameter.context, parameter.context)
    first = parameter.first_version + ('（基线）' if parameter.baseline else '')
    facts = [('类型', vartype), ('上下文', context), ('默认值', parameter.boot_human),
             ('引入版本', first), ('分类', parameter.category_zh),
             ('版本覆盖', '{} – {}'.format(parameter.first_version, parameter.last_version)
              if parameter.first_version else '')]
    parts = []
    if zh or en:
        parts.append('<p class="ds-ext-desc">' + escape(zh or en) + '</p>')
    if zh and en:
        parts.append('<p class="ds-ext-desc-en">' + escape(en) + '</p>')
    parts.append('<dl class="ds-ext-facts">' + ''.join(
        '<div><dt>{}</dt><dd>{}</dd></div>'.format(escape(label), escape(str(value)))
        for label, value in facts if value) + '</dl>')
    track = [item for item in (parameter.default_history or ()) if item.get('from')]
    if len(track) > 1:
        parts.append('<h3>默认值变迁</h3><dl class="ds-ext-facts ds-ext-facts--stack">' + ''.join(
            '<div><dt>{}</dt><dd>{}</dd></div>'.format(
                escape('{} – {}'.format(item.get('from', ''), item.get('to', ''))),
                escape(str(item.get('human') or item.get('boot_val') or '')))
            for item in track) + '</dl>')
    return {
        'key': digest('guc\0' + name), 'entity_key': 'guc:' + name_key, 'kind': 'guc',
        'subtype': parameter.group_slug, 'name': name, 'name_key': name_key,
        'aliases': sorted(aliases), 'anchor': '',
        'heading': '配置参数' + (' · ' + parameter.category_zh if parameter.category_zh else ''),
        'signature': ' · '.join(v for v in (
            vartype, context, '默认 ' + parameter.boot_human if parameter.boot_human else '') if v),
        'body': '\n'.join(v for v in (zh, en, summary, ' '.join(mechanism),
                                      parameter.category_zh, parameter.category) if v),
        'preview': ''.join(parts), 'url': parameter.url, 'weight': 0.5,
        '_title': ' '.join([name, *sorted(aliases)]), '_lead': ' '.join(v for v in (zh, en, summary) if v),
    }


def rebuild_guc(dry_run=False):
    """Replace the search entries of the 配置参数 column (source 'guc')."""
    from pgweb.wiki.models import GucParameter
    # The per-version snapshots carry the translated manual text; the entry needs none of it.
    parameters = list(GucParameter.objects.defer('versions', 'changes', 'docs', 'intro_commit'))
    entries = [guc_entry(parameter) for parameter in parameters]
    if dry_run:
        return {'guc': len(entries)}
    objects = []
    for entry in entries:
        title = index_text(entry.pop('_title'))
        lead = index_text(entry.pop('_lead'))
        vector = (SearchVector(Value(title), config='simple', weight='A') +
                  SearchVector(Value(lead), config='simple', weight='B') +
                  SearchVector(Value(index_text(entry['body'])), config='simple', weight='D'))
        objects.append(SearchEntry(source='guc', document=None, version=None, vector=vector,
                                   **entry))
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LOCK_NAMESPACE, 0])
        SearchEntry.objects.filter(source='guc').delete()
        SearchEntry.objects.bulk_create(objects, batch_size=200)
    service.forget_catalog()
    return {'guc': len(objects)}


# ---------------------------------------------------------------- 等待事件

def waitevent_entry(event):
    """One wait event as a search entry. The manual has no per-event definition
    row, so the entity is the 百科 entry's own; `Type/Name` and every historical
    spelling are aliases, because that is how people paste them out of
    pg_stat_activity."""
    name = event.name
    name_key = normalize_name(name)
    pair = '{}/{}'.format(event.type, name)
    aliases = {name_key, normalize_name(pair)}
    for alias in event.aliases or ():
        aliases.add(normalize_name(alias))
        aliases.add(normalize_name('{}/{}'.format(event.type, alias)))
    for variant in event.type_variants or ():
        aliases.add(normalize_name('{}/{}'.format(variant, name)))
    aliases.discard('')
    zh = ' '.join((event.summary_zh or '').split())
    en = ' '.join((event.summary or '').split())
    dossier = event.dossier or {}
    mechanism = ' '.join(((dossier.get('mechanism') or {}).get('zh') or '').split())
    status = event.source_status_label
    sql = [item.get('title_zh') or item.get('title') or '' for item in dossier.get('diagnostic_sql') or ()]
    facts = [('类型', event.type_label), ('等待事件', pair),
             ('引入版本', event.first_version),
             ('版本覆盖', '{} – {}'.format(event.first_version, event.last_version)
              if event.first_version else ''),
             ('触发路径', status), ('名称变动', '、'.join(event.aliases or ()))]
    parts = []
    if zh or en:
        parts.append('<p class="ds-ext-desc">' + escape(zh or en) + '</p>')
    if zh and en:
        parts.append('<p class="ds-ext-desc-en">' + escape(en) + '</p>')
    parts.append('<dl class="ds-ext-facts">' + ''.join(
        '<div><dt>{}</dt><dd>{}</dd></div>'.format(escape(label), escape(str(value)))
        for label, value in facts if value) + '</dl>')
    if sql and sql[0]:
        parts.append('<h3>诊断 SQL</h3><p class="ds-ext-desc">' + escape(sql[0]) + '</p>')
    return {
        'key': digest('waitevent\0' + event.key), 'entity_key': 'waitevent:' + event.key,
        'kind': 'waitevent', 'subtype': event.type_slug, 'name': name, 'name_key': name_key,
        'aliases': sorted(aliases), 'anchor': '',
        'heading': event.type_label + ' · 等待事件',
        'signature': ' · '.join(v for v in (
            pair, event.type_label,
            '{} – {}'.format(event.first_version, event.last_version)
            if event.first_version else '') if v),
        'body': '\n'.join(v for v in (zh, en, mechanism, event.type_label, event.type, pair) if v),
        'preview': ''.join(parts), 'url': event.url, 'weight': 0.5,
        '_title': ' '.join([name, *sorted(aliases)]), '_lead': ' '.join(v for v in (zh, en) if v),
    }


def rebuild_waitevents(dry_run=False):
    """Replace the search entries of the 等待事件 column (source 'wait').

    'waitevent' does not fit SearchEntry.source (varchar(8)); the short source
    keeps the schema untouched and `kind` carries the full name.
    """
    from pgweb.wiki.models import WaitEvent
    events = list(WaitEvent.objects.defer('versions', 'changes'))
    entries = [waitevent_entry(event) for event in events]
    if dry_run:
        return {'waitevents': len(entries)}
    objects = []
    for entry in entries:
        title = index_text(entry.pop('_title'))
        lead = index_text(entry.pop('_lead'))
        vector = (SearchVector(Value(title), config='simple', weight='A') +
                  SearchVector(Value(lead), config='simple', weight='B') +
                  SearchVector(Value(index_text(entry['body'])), config='simple', weight='D'))
        objects.append(SearchEntry(source='wait', document=None, version=None, vector=vector,
                                   **entry))
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LOCK_NAMESPACE, 0])
        SearchEntry.objects.filter(source='wait').delete()
        SearchEntry.objects.bulk_create(objects, batch_size=200)
    service.forget_catalog()
    return {'waitevents': len(objects)}
