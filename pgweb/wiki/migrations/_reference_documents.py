"""Frozen 2026-09 document conversion. Never import runtime models/importers here."""
"""SQLSTATE document contract and lossless conversion from the first snapshot format."""

from copy import deepcopy


TEXT_DEFAULTS = dict.fromkeys(('title', 'name', 'description', 'summary', 'body_md',
                               'translation_source_rev'), '')
TEXT_DEFAULTS.update(sections=[], is_stale=False)
ROW_DEFAULTS = {
    'sources': dict.fromkeys(('source_id', 'kind', 'tag', 'commit', 'path', 'location',
                             'url', 'docs_url', 'sha256'), ''),
    'claims': dict(statement='', claim_id='', method='', limits='', sources=[], runtime=[]),
    'messages': dict(message_id='', severity='', path='', limits='', sources=[], raw={}),
    'runtimes': dict(runtime_id='', run_id='', status='', target='', server_version='',
                     cases=[], limits='', raw={}),
    'cases': dict(case_id='', versions=[], preconditions=[], trigger='', assertions=[],
                  repair='', cleanup='', has_snippet=False),
}
TEMPLATE_DEFAULTS = dict(kind='', role='', template='', literal='')
INTERVAL_KEYS = {'modern': 'presence_intervals', 'pre9': 'pre9_presence_intervals'}
PRESENCE_FIELDS = ('start', 'end', 'start_tag', 'end_tag', 'start_major', 'end_major')


def merge_presence(facts, rows):
    """Keep extra fact keys; conflicting endpoints/order are errors, never last-write-wins."""
    facts = deepcopy(facts)
    if any(row['era'] not in INTERVAL_KEYS for row in rows):
        raise ValueError('未知存在性区间 era')
    for era, key in INTERVAL_KEYS.items():
        incoming = sorted((row for row in rows if row['era'] == era), key=lambda r: r['position'])
        prior = facts.get(key, [])
        if prior and len(prior) != len(incoming):
            raise ValueError('{} 区间数不一致'.format(key))
        if len({r['position'] for r in incoming}) != len(incoming):
            raise ValueError('{} 区间 position 重复'.format(key))
        merged = []
        for index, row in enumerate(incoming):
            interval = dict(prior[index]) if prior else {}
            for field in (*PRESENCE_FIELDS, 'position', 'evidence_count'):
                value = row.get(field, 0 if field in ('position', 'evidence_count') else '')
                if field in interval and interval[field] != value:
                    raise ValueError('{}[{}].{} 冲突'.format(key, index, field))
                interval[field] = value
            merged.append(interval)
        if merged or key in facts:
            facts[key] = merged
    return facts


def expand_presence(facts):
    return [dict(era=era, position=item.get('position', index),
                 evidence_count=item.get('evidence_count', 0),
                 **{field: item.get(field, '') for field in PRESENCE_FIELDS})
            for era, key in INTERVAL_KEYS.items()
            for index, item in enumerate(facts.get(key, []))]


def pack_legacy(item):
    """No DB or Markdown rendering: preserve already stored prose, evidence and ordering."""
    out = deepcopy(item)
    texts = {}
    for text in out.pop('texts', []):
        lang = text['lang']
        if lang in texts:
            raise ValueError('重复语言 {}'.format(lang))
        texts[lang] = {**deepcopy(TEXT_DEFAULTS), **{k: v for k, v in text.items() if k != 'lang'}}
    out['texts'] = texts
    out['facts'] = merge_presence(out.get('facts', {}), out.pop('presence', []))
    evidence = {}
    for key, defaults in ROW_DEFAULTS.items():
        rows = out.pop(key, [])
        evidence[key] = []
        for position, row in enumerate(rows):
            row = {**deepcopy(defaults), 'position': position, **row}
            if key == 'messages':
                row['templates'] = [{**TEMPLATE_DEFAULTS, 'position': n, **template}
                                    for n, template in enumerate(row.get('templates', []))]
            evidence[key].append(row)
        evidence[key].sort(key=lambda r: r['position'])
    out['evidence'] = evidence
    return derive(out)


def derive(item):
    item = deepcopy(item)
    zh = item['texts'].get('zh', {})
    item['name_zh'] = zh.get('name', '')
    item['summary_zh'] = zh.get('summary', '')
    cases = item['evidence']['cases']
    item['case_count'] = len(cases)
    item['snippet_count'] = sum(bool(c.get('has_snippet')) for c in cases)
    return item


def reference_gaps(item):
    """Reference IDs are polymorphic, scoped to one SQLSTATE; preserve unresolved IDs."""
    evidence = item['evidence']
    ids = {key: {row[key[:-1] + '_id'] for row in evidence[key]}
           for key in ROW_DEFAULTS}
    all_ids = set().union(*ids.values())
    gaps = []
    for key, fields in [('claims', ('sources', 'runtime')), ('messages', ('sources',)),
                        ('runtimes', ('cases',))]:
        for row in evidence[key]:
            for field in fields:
                targets = ids['runtimes'] if field == 'runtime' else ids['cases'] if field == 'cases' else all_ids
                for ref in row[field]:
                    if ref not in targets:
                        gaps.append({'sqlstate': item['sqlstate'], 'kind': key,
                                     'id': row[key[:-1] + '_id'], 'field': field, 'ref': ref})
    return gaps

# Frozen business fingerprint; keep in step only with this migration's contract.
import hashlib
import json


ENTITY_MODELS = ('ErrorCode', 'CatalogRelation', 'GucParameter', 'WaitEvent', 'SqlCommand', 'PgFunction')
CHILD_MODELS = dict(texts='ErrorCodeText', presence='ErrorCodePresence',
                    sources='ErrorCodeSource', claims='ErrorCodeClaim', messages='ErrorCodeMessage',
                    runtimes='ErrorCodeRuntime', cases='ErrorCodeCase')


def fingerprint(row):
    data = {f.attname: getattr(row, f.attname) for f in row._meta.concrete_fields
            if f.attname not in ('content_hash', 'source_rev', 'imported_at')}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def legacy_document(apps, alias, code):
    item = {'sqlstate': code.pk, 'facts': code.facts}
    for key, name in CHILD_MODELS.items():
        model = apps.get_model('wiki', name)
        fields = [f.attname for f in model._meta.concrete_fields
                  if f.attname not in ('id', 'errcode_id', 'search_vector')]
        item[key] = list(model.objects.using(alias).filter(errcode_id=code.pk)
                         .order_by('lang' if key == 'texts' else 'position', 'pk').values(*fields))
        if key == 'messages':
            for message in item[key]:
                parent = model.objects.using(alias).get(errcode_id=code.pk, message_id=message['message_id'])
                templates = apps.get_model('wiki', 'ErrorCodeTemplate').objects.using(alias).filter(message_id=parent.pk)
                if templates.exclude(errcode_id=code.pk).exists():
                    raise ValueError('Template SQLSTATE/parent mismatch: ' + code.pk)
                message['templates'] = list(templates.order_by('position', 'pk').values(
                    'kind', 'role', 'template', 'literal', 'position'))
    return pack_legacy(item)


def backfill(apps, schema_editor):
    alias = schema_editor.connection.alias
    for code in apps.get_model('wiki', 'ErrorCode').objects.using(alias).iterator():
        document = legacy_document(apps, alias, code)
        for field in ('facts', 'texts', 'evidence', 'name_zh', 'summary_zh', 'case_count', 'snippet_count'):
            if field in ('case_count', 'snippet_count') and getattr(code, field) != document[field]:
                raise ValueError('{} {} inconsistent'.format(code.pk, field))
            setattr(code, field, document[field])
        # QuerySet.update deliberately preserves imported_at and source_rev.
        apps.get_model('wiki', 'ErrorCode').objects.using(alias).filter(pk=code.pk).update(
            **{field: getattr(code, field) for field in ('facts', 'texts', 'evidence', 'name_zh', 'summary_zh')})
    for name in ENTITY_MODELS:
        model = apps.get_model('wiki', name)
        for row in model.objects.using(alias).iterator():
            model.objects.using(alias).filter(pk=row.pk).update(content_hash=fingerprint(row))


def verify(apps, schema_editor):
    alias = schema_editor.connection.alias
    for code in apps.get_model('wiki', 'ErrorCode').objects.using(alias).iterator():
        expected = legacy_document(apps, alias, code)
        for field in ('facts', 'texts', 'evidence', 'name_zh', 'summary_zh', 'case_count', 'snippet_count'):
            if getattr(code, field) != expected[field]:
                raise ValueError('SQLSTATE {} {} differs from legacy rows'.format(code.pk, field))
        if code.content_hash != fingerprint(code):
            raise ValueError('SQLSTATE {} content_hash mismatch'.format(code.pk))


def restore_children(apps, schema_editor):
    """Reverse of contraction: old tables already exist; restore business IDs and all fields."""
    alias = schema_editor.connection.alias
    template_model = apps.get_model('wiki', 'ErrorCodeTemplate')
    for code in apps.get_model('wiki', 'ErrorCode').objects.using(alias).iterator():
        data = {**code.evidence,
                'texts': [dict(lang=lang, **text) for lang, text in code.texts.items()],
                'presence': expand_presence(code.facts)}
        for key, name in CHILD_MODELS.items():
            model = apps.get_model('wiki', name)
            model.objects.using(alias).filter(errcode_id=code.pk).delete()
            for item in data[key]:
                values = dict(item)
                templates = values.pop('templates', []) if key == 'messages' else []
                row = model.objects.using(alias).create(errcode_id=code.pk, **values)
                if templates:
                    template_model.objects.using(alias).bulk_create([
                        template_model(errcode_id=code.pk, message_id=row.pk, **template)
                        for template in templates])
