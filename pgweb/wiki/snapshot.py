"""Stable fingerprints of stored business content, independent of export time."""

import hashlib
import json


METADATA_FIELDS = {'source_rev', 'imported_at', 'content_hash'}


def content_hash(values):
    values = {k: v for k, v in values.items() if k not in METADATA_FIELDS}
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def model_hash(instance):
    return content_hash({f.attname: getattr(instance, f.attname)
                         for f in instance._meta.concrete_fields
                         if f.attname not in METADATA_FIELDS})


def item_hash(model, item, fields):
    values = {field: item[field] for field in fields}
    values[model._meta.pk.attname] = item[model._meta.pk.attname]
    calculated = model_hash(model(**values))
    if item.get('content_hash') and item['content_hash'] != calculated:
        raise ValueError('{} content_hash 不匹配'.format(values[model._meta.pk.attname]))
    return calculated


def hashed_defaults(model, item, fields):
    guard_calibration(model, item)
    return {**{field: item[field] for field in fields},
            'content_hash': item_hash(model, item, fields)}


def guard_calibration(model, item):
    """Reject legacy snapshots that would discard a newer release calibration.

    Release updates use a reviewed field delta. Ordinary full-snapshot imports
    must carry the existing calibration proof, including source and runtime pins.
    """
    field = 'evidence' if model._meta.db_table == 'sqlstate' else 'versions'
    if field not in item:
        return
    pk = model._meta.pk.attname
    current = model.objects.filter(pk=item[pk]).values_list(field, flat=True).first() or {}
    if field == 'evidence':
        old = current.get('release_calibrations', {})
        new = item[field].get('release_calibrations', {})
    else:
        old = {m: s['calibration'] for m, s in current.items() if s.get('calibration')}
        new = {m: s.get('calibration') for m, s in item[field].items()}
    for major, proof in old.items():
        if new.get(major) != proof:
            raise ValueError(f'{model._meta.db_table}/{item[pk]}/PG{major}: '
                             'snapshot would replace a pinned release calibration; use a reviewed guarded delta')
