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
    return {**{field: item[field] for field in fields},
            'content_hash': item_hash(model, item, fields)}
