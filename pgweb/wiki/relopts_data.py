"""Chinese editorial labels for documented relation options.

Existence, descriptions, types and provenance come from each version's manual;
these labels do not extrapolate availability or defaults across versions.
"""

LABELS = {
    'fillfactor': ('填充因子', '控制页面的初始填充比例，为后续写入或更新预留空间。'),
    'toast_tuple_target': ('TOAST 元组目标长度', '设置触发长字段压缩或外置的元组长度，以及 TOAST 处理试图达到的目标长度。'),
    'toast_value_type': ('TOAST 值标识符类型', '指定新建 TOAST 关系的 chunk_id 类型；修改此参数不会改变已有 TOAST 关系的类型。'),
    'parallel_workers': ('并行扫描工作进程数', '为当前关系指定并行扫描工作进程数，实际数量仍受规划与资源限制。'),
    'autovacuum_enabled': ('启用自动清理', '控制当前关系的常规自动清理；关闭后仍不能阻止防止事务 ID 回卷所需的清理。'),
    'vacuum_index_cleanup': ('清理索引死元组', '控制 VACUUM 是否处理当前关系的索引死元组，取值与默认行为随版本变化。'),
    'vacuum_truncate': ('截断尾部空页', '控制 VACUUM 是否尝试将关系末尾的空页归还操作系统。'),
    'autovacuum_parallel_workers': ('自动清理并行工作进程数', '为当前表覆盖自动清理的并行工作进程上限。'),
    'autovacuum_vacuum_threshold': ('自动清理基础阈值', '为当前关系设置按更新或删除元组数触发自动清理的基础阈值。'),
    'autovacuum_vacuum_max_threshold': ('自动清理阈值上限', '为当前关系设置自动清理触发阈值的上限。'),
    'autovacuum_vacuum_scale_factor': ('自动清理比例因子', '设置按关系规模计算自动清理触发阈值时使用的比例因子。'),
    'autovacuum_vacuum_insert_threshold': ('插入触发清理基础阈值', '设置按插入元组数触发自动清理的基础阈值，或关闭这一路触发条件。'),
    'autovacuum_vacuum_insert_scale_factor': ('插入触发清理比例因子', '设置计算插入触发自动清理阈值时使用的比例因子。'),
    'autovacuum_analyze_threshold': ('自动分析基础阈值', '为当前表设置触发自动统计信息分析的基础阈值。'),
    'autovacuum_analyze_scale_factor': ('自动分析比例因子', '为当前表设置按表规模计算自动分析触发阈值时使用的比例因子。'),
    'autovacuum_vacuum_cost_delay': ('自动清理代价延迟', '覆盖当前关系自动清理时采用的代价节流延迟。'),
    'autovacuum_vacuum_cost_limit': ('自动清理代价上限', '覆盖当前关系自动清理时采用的代价节流上限。'),
    'autovacuum_freeze_min_age': ('事务 ID 最小冻结年龄', '为当前关系设置普通清理开始冻结事务 ID 的最小年龄。'),
    'autovacuum_freeze_max_age': ('事务 ID 强制冻结年龄', '为当前关系降低触发防事务 ID 回卷自动清理的年龄上限。'),
    'autovacuum_freeze_table_age': ('事务 ID 全表冻结年龄', '为当前关系设置触发积极冻结扫描的事务 ID 年龄阈值。'),
    'autovacuum_multixact_freeze_min_age': ('多事务 ID 最小冻结年龄', '为当前关系设置清理时替换多事务 ID 的最小年龄。'),
    'autovacuum_multixact_freeze_max_age': ('多事务 ID 强制冻结年龄', '为当前关系降低触发防多事务 ID 回卷自动清理的年龄上限。'),
    'autovacuum_multixact_freeze_table_age': ('多事务 ID 全表冻结年龄', '为当前关系设置触发积极冻结扫描的多事务 ID 年龄阈值。'),
    'log_autovacuum_min_duration': ('自动清理日志时长阈值', '为当前关系设置记录自动清理相关日志的最短执行时长。'),
    'log_autoanalyze_min_duration': ('自动分析日志时长阈值', '为当前表设置记录自动分析日志的最短执行时长。'),
    'vacuum_max_eager_freeze_failure_rate': ('提前冻结失败比例上限', '为当前关系覆盖 VACUUM 提前冻结扫描的失败比例上限。'),
    'user_catalog_table': ('用户目录表', '将表标记为逻辑解码使用的附加目录表。'),
    'deduplicate_items': ('B-tree 索引去重', '控制 B-tree 是否对重复键使用去重优化。'),
    'vacuum_cleanup_index_scale_factor': ('B-tree 清理比例因子', '为 B-tree 索引覆盖判断是否执行清理阶段的比例因子。'),
    'buffering': ('GiST 缓冲构建', '控制 GiST 索引构建是否使用缓冲构建技术。'),
    'fastupdate': ('GIN 快速更新', '控制 GIN 是否先将新索引项放入待处理列表，再批量合并。'),
    'gin_pending_list_limit': ('GIN 待处理列表上限', '为当前 GIN 索引覆盖待处理列表的大小上限。'),
    'pages_per_range': ('BRIN 每范围页数', '设置一个 BRIN 汇总项所覆盖的表数据块数量。'),
    'autosummarize': ('BRIN 自动汇总', '控制向新页范围插入数据时是否为前一个范围安排汇总。'),
    'check_option': ('视图检查选项', '检查通过可更新视图写入的新行是否仍符合视图条件。'),
    'security_barrier': ('视图安全屏障', '约束视图条件与外部条件的求值顺序，用于防止不可信表达式越过视图过滤条件。'),
    'security_invoker': ('以调用者权限访问视图', '访问视图的基础关系时使用调用者的权限与行安全策略。'),
    'oids': ('行 OID 兼容选项', '历史版本可为表行分配 OID；较新版本只保留 OIDS=FALSE 的兼容写法。'),
}

CATEGORIES = {
    'table': '表与物化视图', 'toast': 'TOAST 表',
    'btree': 'B-tree 索引', 'hash': 'Hash 索引', 'gist': 'GiST 索引',
    'spgist': 'SP-GiST 索引', 'gin': 'GIN 索引', 'brin': 'BRIN 索引',
    'view': '视图选项', 'compat': '表兼容选项',
}

INDEX_SCOPES = {
    'fillfactor': ('btree', 'hash', 'gist', 'spgist'),
    'vacuum_cleanup_index_scale_factor': ('btree',),
    'deduplicate_items': ('btree',), 'buffering': ('gist',),
    'fastupdate': ('gin',), 'gin_pending_list_limit': ('gin',),
    'pages_per_range': ('brin',), 'autosummarize': ('brin',),
}

# PG10–12 omit types from the index definition terms. These types are also
# explicit in later documentation; this map changes no default or range.
INDEX_TYPES = {
    'fillfactor': 'integer', 'vacuum_cleanup_index_scale_factor': 'floating point',
    'deduplicate_items': 'boolean', 'buffering': 'enum', 'fastupdate': 'boolean',
    'gin_pending_list_limit': 'integer', 'pages_per_range': 'integer',
    'autosummarize': 'boolean',
}

COVERAGE_NOTES = [
    '按 PostgreSQL 10–20 各版本中文手册逐版整理，版本格表示该版手册明确收录；起点为本栏目采样下界，不据此认定首次引入版本。',
    '覆盖 CREATE TABLE 与 CREATE INDEX 明确列出的存储参数；TOAST 参数单独列出，同名索引参数按访问方法区分。物化视图沿用表存储参数，不重复建条目。',
    '视图选项控制查询安全与可更新性，不控制物理存储；OIDS 另列为历史兼容语法。二者仍可从关系选项的同一入口查阅。',
    '参数未显式设置时的回退与默认行为见逐版说明；全局 GUC 的默认值不能直接当成关系选项的显式默认值。TOAST 对应选项未设置时，可继承主表设置。',
    '仅收录上述命令手册明确列出的关系选项，不把列统计选项、索引操作符类参数、外部表选项或扩展自定义选项混入此目录。',
]
