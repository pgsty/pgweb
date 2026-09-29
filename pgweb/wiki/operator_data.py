"""Identities and presentation labels for core operator catalogs.

An operator is identified by namespace, symbol and both operand types. OIDs
belong to one source build and are deliberately absent from stable URLs.
"""
from urllib.parse import quote

METHOD_NAMES = {'btree': 'B-tree', 'hash': 'Hash', 'gist': 'GiST',
                'spgist': 'SP-GiST', 'gin': 'GIN', 'brin': 'BRIN'}
OPERATOR_COVERAGE = [
    'Every explicitly bootstrapped pg_operator overload in the verified PostgreSQL 10–20 source archives is included. Prefix, postfix and binary operators keep distinct operand signatures.',
    'Declared pg_amop membership is evidence of a specific operator-family strategy or ordering purpose, not a general promise that any query can use an index.',
    'Operator descriptions come from the same source catalog and matching English manual. Missing manual matches remain explicit; no performance or runtime claim is inferred.',
    'Source OIDs, generated OIDs and extension objects are not global identities. PostgreSQL 6.3–9.6 manuals remain available but are not sampled by this inventory.',
]
OPCLASS_COVERAGE = [
    'Classes and families are separate entities, identified by kind, index access method and catalog name. The inventory covers all pg_opclass and pg_opfamily bootstrap rows in the verified PostgreSQL 10–20 source archives.',
    'Operators and support functions belong to the operator family. A class page shows its complete family, marking members whose declared left/right types both match the class input type; cross-type members remain visible.',
    'An operator strategy number and support-function number have meanings defined by the index access method. They are not interchangeable across methods.',
    'Core bootstrap membership is not an inventory of extension classes or runtime-created objects. Binary compatibility, expression indexes and polymorphic resolution are not guessed.',
]


def operator_slug(symbol, left, right):
    """Hex encodes only the symbol; type names stay readable and collision-free."""
    return 'op-' + symbol.encode().hex() + '-' + left + '-' + right


def operator_signature(symbol, left, right, result=None):
    signature = symbol + '(' + left + ',' + right + ')'
    return signature + (' → ' + result if result else '')


def catalog_slug(kind, method, name):
    return kind + '-' + method + '-' + name


def type_url(name, major):
    if name in {'none', '0', '-'}:
        return ''
    target = 'arrays' if name.startswith('_') or name.endswith('[]') else name
    return '/wiki/type/' + quote(target) + '/?v=' + major


def cell(text, url=''):
    return {'text': str(text), 'url': url} if url else str(text)


def table(key, title, columns, rows):
    return {'key': key, 'title': title,
            'columns': [{'key': k, 'label': label} for k, label in columns],
            'rows': [{key: row[key] for key, _ in columns} for row in rows]}
