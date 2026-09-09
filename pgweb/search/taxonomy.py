"""PG-specific categories shared by the extractor, API and interface."""

KINDS = (
    ('guc', '配置参数', 'G', 'work_mem、wal_level'),
    ('sql', 'SQL 命令', 'SQL', 'SELECT、CREATE TABLE'),
    ('function', '函数与例程', 'ƒ', '函数、聚合、窗口函数'),
    ('operator', '运算符', '⊕', '->>、@>、&&'),
    ('type', '数据类型', 'T', 'jsonb、integer、uuid'),
    ('relation', '系统目录与视图', '▤', 'pg_class、pg_stat_activity'),
    ('error', '错误代码', '!', 'SQLSTATE 与条件名称'),
    ('psql', 'psql 命令', '\\', '\\d+、\\copy、\\watch'),
    ('tool', '命令行工具', '>_', 'pg_dump、pg_basebackup'),
    ('option', '选项与环境变量', '⚙', 'sslmode、PGHOST、工具选项'),
    ('extension', '模块与扩展', '◇', '官方手册收录的模块'),
    ('am', '访问方法', 'AM', 'B-tree、GIN、BRIN'),
    ('language', '过程语言', 'PL', 'PL/pgSQL、PL/Python'),
    ('syntax', '语法与表达式', '()', 'COALESCE、ON CONFLICT'),
    ('guide', '章节与指南', '§', '概念、教程与完整正文'),
)
KIND_META = {key: {'key': key, 'label': label, 'icon': icon, 'hint': hint} for key, label, icon, hint in KINDS}
KIND_ALIASES = {'param': 'guc', 'setting': 'guc', 'func': 'function', 'op': 'operator', 'view': 'relation',
                'catalog': 'relation', 'command': 'sql', 'err': 'error', 'types': 'type'}


def normalize_name(value):
    value = ' '.join(value.split())
    # psql commands have meaningful case, e.g. \dD and \dd.
    return value if value.startswith('\\') or '"' in value else value.casefold()
