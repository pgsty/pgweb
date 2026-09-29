"""Stable presentation choices for the source-backed Data Types collection.

These are names and categories, not measured capabilities or version facts.
Catalog records and documented aliases are always collected per source build.
"""
SQL_NAMES = {
    'bool': 'boolean', 'int2': 'smallint', 'int4': 'integer', 'int8': 'bigint',
    'float4': 'real', 'float8': 'double precision', 'bpchar': 'character',
    'varchar': 'character varying', 'varbit': 'bit varying',
    'time': 'time without time zone', 'timetz': 'time with time zone',
    'timestamp': 'timestamp without time zone', 'timestamptz': 'timestamp with time zone',
    'char': '"char"',
}
SQL_TO_INTERNAL = {v: k for k, v in SQL_NAMES.items()}
SQL_TO_INTERNAL.update({'int': 'int4', 'decimal': 'numeric', 'float': 'float8',
                        'char': 'bpchar', 'timestamp': 'timestamp', 'time': 'time'})
FAMILIES = {
    'arrays': ('Arrays', 'arrays.html'),
    'composite': ('Composite types', 'rowtypes.html'),
    'domains': ('Domains', 'domains.html'),
    'enums': ('Enumerated types', 'datatype-enum.html'),
}
CATEGORIES = {
    'B': 'Boolean', 'N': 'Numeric', 'S': 'Character strings', 'D': 'Date and time',
    'T': 'Date and time', 'G': 'Geometric', 'I': 'Network addresses',
    'V': 'Bit strings', 'X': 'Internal and special-purpose',
    'Z': 'Internal and special-purpose', 'A': 'Internal and special-purpose',
    'U': 'Other built-in types',
}
FILE_TYPES = {
    'datatype-numeric.html': 'int2 int4 int8 float4 float8 numeric smallserial serial bigserial',
    'datatype-money.html': 'money',
    'datatype-character.html': 'bpchar varchar text char name',
    'datatype-binary.html': 'bytea',
    'datatype-datetime.html': 'date time timetz timestamp timestamptz interval abstime reltime tinterval',
    'datatype-boolean.html': 'bool',
    'datatype-geometric.html': 'point line lseg box path polygon circle',
    'datatype-net-types.html': 'inet cidr macaddr macaddr8',
    'datatype-bit.html': 'bit varbit',
    'datatype-textsearch.html': 'tsvector tsquery',
    'datatype-uuid.html': 'uuid',
    'datatype-xml.html': 'xml',
    'datatype-json.html': 'json jsonb jsonpath',
    'datatype-pg-lsn.html': 'pg_lsn',
    'datatype-oid.html': 'oid oid8 xid xid8 cid tid regproc regprocedure regoper regoperator regclass regcollation regdatabase regtype regconfig regdictionary regnamespace regrole',
    'functions-info.html': 'txid_snapshot pg_snapshot',
}
TYPE_FILES = {name: file for file, names in FILE_TYPES.items() for name in names.split()}
COVERAGE_NOTES = [
    'The inventory includes every explicitly bootstrapped, non-array, non-composite pg_type row in the sampled PostgreSQL 10–20 source archives, plus the three documented serial conveniences and four user-defined type families.',
    'Array companions are recorded on their element type and have a shared Arrays page. Automatically generated catalog composite row types, extension types and user-created types are outside the finite inventory.',
    'A pg_type source row is a source declaration, not a measurement of a running server. Build-dependent values such as NAMEDATALEN and FLOAT8PASSBYVAL remain symbolic.',
    'Operator overloads retain both operand types and their return type. Listed operator classes match their declared input type exactly; absence does not mean that a type cannot be indexed, since binary coercion and polymorphic classes can apply.',
    'Cast rows cover only explicitly bootstrapped pg_cast entries. Automatic array, domain, polymorphic and I/O coercions are not a complete pg_cast enumeration.',
    'PostgreSQL 6.3–9.6 manuals remain available; this collection does not claim a source inventory for those unsampled versions.',
]


def canonical_name(value):
    """Normalize documented type spellings without conflating SQL char and \"char\"."""
    import re
    value = ' '.join(value.split()).strip()
    value = re.sub(r'\s*\([^)]*\)', '', value)
    value = re.sub(r'\s*\[[^]]*\]', '', value)
    value = ' '.join(value.split())
    return SQL_TO_INTERNAL.get(value, value)


def category(record):
    kind = record.get('typtype', 'b')
    if kind == 'p':
        return 'Pseudo-types'
    if kind in {'r', 'm'}:
        return 'Multiranges' if kind == 'm' else 'Ranges'
    name = record['typname']
    if name in FILE_TYPES['datatype-oid.html'].split():
        return 'Object and transaction identifiers'
    if name in {'json', 'jsonb', 'jsonpath'}:
        return 'JSON'
    if name in {'tsvector', 'tsquery'}:
        return 'Text search'
    return CATEGORIES.get(record.get('typcategory'), 'Other built-in types')
