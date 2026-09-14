"""PG-specific categories shared by the extractor, API and interface.

Entries are stored with a fine-grained `kind` (what the extractor found:
a GUC, a psql meta-command, a libpq option...). The interface filters and
counts by a small number of groups, so rarely searched kinds do not need
a facet of their own. `kind:` in a query and the `kind` URL parameter
accept either level.
"""

KINDS = (
    ('guc', '配置参数'),
    ('sql', 'SQL 命令'),
    ('syntax', '语法与表达式'),
    ('function', '函数'),
    ('operator', '运算符'),
    ('type', '数据类型'),
    ('relation', '系统目录与视图'),
    ('error', 'SQL 状态码'),
    ('waitevent', '等待事件'),
    ('psql', 'psql 命令'),
    ('tool', '命令行工具'),
    ('option', '选项与变量'),
    ('extension', '扩展与模块'),
    ('am', '访问方法'),
    ('language', '过程语言'),
    ('guide', '章节正文'),
)
KIND_LABEL = dict(KINDS)

# key, label, kinds folded into the group, example hint
GROUPS = (
    ('guc', '配置参数', ('guc',), 'work_mem、wal_level'),
    ('sql', 'SQL 命令与语法', ('sql', 'syntax'), 'SELECT、CREATE TABLE、ON CONFLICT'),
    ('function', '函数与运算符', ('function', 'operator'), 'jsonb_set、->>、count'),
    ('type', '数据类型', ('type',), 'jsonb、integer、uuid'),
    ('relation', '系统目录与视图', ('relation',), 'pg_class、pg_stat_activity'),
    ('error', 'SQL 状态码', ('error',), 'SQLSTATE 与条件名称'),
    ('waitevent', '等待事件', ('waitevent',), 'BufferMapping、DataFileRead'),
    ('tool', '命令行工具', ('tool', 'option'), 'pg_dump、pg_basebackup、sslmode、PGHOST'),
    ('psql', 'psql 命令', ('psql',), '\\d+、\\copy、\\watch'),
    ('extension', '扩展与模块', ('extension', 'am', 'language'), 'postgis、pg_trgm、PL/pgSQL'),
    ('guide', '章节正文', ('guide',), '概念、教程与完整正文'),
)
GROUP_META = {key: {'key': key, 'label': label, 'kinds': list(kinds), 'hint': hint} for key, label, kinds, hint in GROUPS}
GROUP_OF = {kind: key for key, _, kinds, _ in GROUPS for kind in kinds}
KIND_ALIASES = {'param': 'guc', 'setting': 'guc', 'settings': 'guc', 'func': 'function', 'functions': 'function',
                'op': 'operator', 'operators': 'operator', 'view': 'relation', 'catalog': 'relation',
                'command': 'sql', 'commands': 'sql', 'err': 'error', 'errors': 'error', 'types': 'type',
                'ext': 'extension', 'extensions': 'extension', 'module': 'extension', 'tools': 'tool',
                'cli': 'tool', 'meta': 'psql', 'backslash': 'psql', 'chapter': 'guide', 'doc': 'guide',
                'wait': 'waitevent', 'waits': 'waitevent', 'waitevents': 'waitevent',
                'wait_event': 'waitevent'}


def resolve_group(value):
    """Map a user-supplied kind or group name to a group key, or '' / None."""
    value = (value or '').strip().lower()
    if not value:
        return ''
    value = KIND_ALIASES.get(value, value)
    if value in GROUP_META:
        return value
    return GROUP_OF.get(value)


def normalize_name(value):
    value = ' '.join(value.split())
    # psql commands have meaningful case, e.g. \dD and \dd.
    return value if value.startswith('\\') or '"' in value else value.casefold()
