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
    ('lock', '锁模式'),
    ('hook', '扩展钩子'),
    ('relopt', '存储参数'),
    ('role', '预定义角色'),
    ('psql', 'psql 命令'),
    ('tool', '命令行工具'),
    ('option', '选项与变量'),
    ('extension', '扩展与模块'),
    ('am', '访问方法'),
    ('language', '过程语言'),
    ('guide', '章节正文'),
)
from pgweb.wiki.topic_registry import DOMAINS
KINDS += (('version', '版本百科'),)
KINDS += tuple((row[4], row[3]) for row in DOMAINS if row[4] not in dict(KINDS))
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
    ('lock', '锁模式', ('lock',), 'ACCESS EXCLUSIVE、FOR UPDATE、锁冲突'),
    ('hook', '扩展钩子', ('hook',), 'planner_hook、ExecutorStart_hook'),
    ('relopt', '存储参数', ('relopt',), 'fillfactor、表级 autovacuum、索引选项'),
    ('role', '预定义角色', ('role',), 'pg_monitor、pg_read_all_data'),
    ('tool', '命令行工具', ('tool', 'option', 'conn'), 'pg_dump、pg_basebackup、sslmode、PGHOST'),
    ('psql', 'psql 命令', ('psql',), '\\d+、\\copy、\\watch'),
    ('extension', '扩展与模块', ('extension',), 'postgis、pg_trgm、PL/pgSQL'),
    ('guide', '章节正文', ('guide',), '概念、教程与完整正文'),
)
GROUPS += (('am', 'Index AM', ('am',), 'btree、hash、GiST、GIN'),
           ('version', '版本百科', ('version',), 'PostgreSQL 18、9.6、安全修复与升级'))
GROUPS += tuple((kind, label, (kind,), '名称或用途')
                for key, model, table, label, kind, tone, unit, lead in DOMAINS
                if kind not in {group[0] for group in GROUPS} and kind != 'operator')
GROUP_META = {key: {'key': key, 'label': label, 'kinds': list(kinds), 'hint': hint} for key, label, kinds, hint in GROUPS}
GROUP_OF = {kind: key for key, _, kinds, _ in GROUPS for kind in kinds}
KIND_ALIASES = {'param': 'guc', 'setting': 'guc', 'settings': 'guc', 'func': 'function', 'functions': 'function',
                'op': 'operator', 'operators': 'operator', 'view': 'relation', 'catalog': 'relation',
                'command': 'sql', 'commands': 'sql', 'err': 'error', 'errors': 'error', 'types': 'type',
                'ext': 'extension', 'extensions': 'extension', 'module': 'extension', 'tools': 'tool',
                'cli': 'tool', 'meta': 'psql', 'backslash': 'psql', 'chapter': 'guide', 'doc': 'guide',
                'wait': 'waitevent', 'waits': 'waitevent', 'waitevents': 'waitevent',
                'wait_event': 'waitevent', 'locks': 'lock', 'hooks': 'hook',
                'relopts': 'relopt', 'roles': 'role', 'oid': 'type', 'indexam': 'am', 'versions': 'version', 'release': 'version'}


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
