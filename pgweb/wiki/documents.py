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
