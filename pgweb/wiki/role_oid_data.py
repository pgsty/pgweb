"""Chinese catalogue labels for roles and identifier types.

These labels do not define availability.  The builder derives each version's
complete set and description from that version's loaded Chinese manual.
"""

ROLE_LABELS = {
    'pg_checkpoint': ('执行检查点', '数据库维护', '允许执行 CHECKPOINT 命令。'),
    'pg_create_subscription': ('创建订阅', '数据库管理', '允许在具有 CREATE 权限的数据库中创建订阅。'),
    'pg_database_owner': ('当前数据库拥有者', '数据库管理', '以当前数据库拥有者作为唯一隐式成员，用于承载随数据库拥有者生效的权限。'),
    'pg_maintain': ('关系维护', '数据库维护', '允许对所有关系执行 MAINTAIN 权限涵盖的维护操作。'),
    'pg_monitor': ('数据库监控', '监控与统计', '读取或执行监控视图和函数，并包含三个监控子角色的权限。'),
    'pg_read_all_settings': ('读取全部配置', '监控与统计', '允许读取所有配置变量，包括通常仅对超级用户可见的变量。'),
    'pg_read_all_stats': ('读取全部统计', '监控与统计', '允许读取所有 pg_stat_* 视图及通常受限的统计信息。'),
    'pg_stat_scan_tables': ('扫描表的监控', '监控与统计', '允许执行可能长时间持有 ACCESS SHARE 锁的监控函数。'),
    'pg_read_all_data': ('读取全部数据', '数据访问', '提供所有表、视图和序列的读取权限以及模式使用权限，但不绕过行级安全策略。'),
    'pg_write_all_data': ('写入全部数据', '数据访问', '提供全部数据的写入权限以及模式使用权限，但不绕过行级安全策略。'),
    'pg_read_server_files': ('读取服务器文件', '服务器文件与程序', '允许读取数据库服务器进程可访问的文件。'),
    'pg_write_server_files': ('写入服务器文件', '服务器文件与程序', '允许向数据库服务器进程可访问的位置写入文件。'),
    'pg_execute_server_program': ('执行服务器程序', '服务器文件与程序', '允许以数据库进程所用操作系统用户的身份执行服务器端程序。'),
    'pg_signal_autovacuum_worker': ('通知自动清理进程', '进程与连接', '允许向自动清理工作进程发送信号，取消当前表的清理操作或终止其会话。'),
    'pg_signal_backend': ('通知后端进程', '进程与连接', '允许取消其他后端的查询或终止其会话，但不能向超级用户拥有的后端发送信号。'),
    'pg_use_reserved_connections': ('使用预留连接', '进程与连接', '允许使用 reserved_connections 所保留的连接槽。'),
}

OID_LABELS = {
    'oid': ('对象标识符', '对象标识符', '以无符号四字节整数表示系统对象标识符；数值不保证全库唯一。'),
    'oid8': ('64 位对象标识符', '对象标识符', '在部分上下文中使用的无符号八字节对象标识符。'),
    'regclass': ('关系名称别名', '对象名称别名', '通过关系名称输入和显示 pg_class 中对象的 OID。'),
    'regcollation': ('排序规则名称别名', '对象名称别名', '通过排序规则名称输入和显示 pg_collation 中对象的 OID。'),
    'regconfig': ('文本检索配置别名', '对象名称别名', '通过文本检索配置名称输入和显示 pg_ts_config 中对象的 OID。'),
    'regdatabase': ('数据库名称别名', '对象名称别名', '通过数据库名称输入和显示 pg_database 中对象的 OID。'),
    'regdictionary': ('文本检索词典别名', '对象名称别名', '通过文本检索词典名称输入和显示 pg_ts_dict 中对象的 OID。'),
    'regnamespace': ('命名空间名称别名', '对象名称别名', '通过模式名称输入和显示 pg_namespace 中对象的 OID。'),
    'regoper': ('操作符名称别名', '对象名称别名', '通过无歧义的操作符名称输入和显示 OID，不带参数类型。'),
    'regoperator': ('操作符签名别名', '对象名称别名', '通过操作符名称和参数类型输入和显示 OID，可以区分重载。'),
    'regproc': ('函数名称别名', '对象名称别名', '通过无歧义的函数名称输入和显示 OID，不带参数类型。'),
    'regprocedure': ('函数签名别名', '对象名称别名', '通过函数名称和参数类型输入和显示 OID，可以区分重载。'),
    'regrole': ('角色名称别名', '对象名称别名', '通过角色名称输入和显示 pg_authid 中对象的 OID。'),
    'regtype': ('数据类型名称别名', '对象名称别名', '通过数据类型名称输入和显示 pg_type 中对象的 OID。'),
    'xid': ('事务标识符', '事务与行标识符', '32 位事务标识符，用于系统列 xmin 和 xmax。'),
    'xid8': ('64 位事务标识符', '事务与行标识符', '64 位事务标识符，在数据库集簇生命周期内严格递增且不重复使用。'),
    'cid': ('命令标识符', '事务与行标识符', '32 位命令标识符，用于系统列 cmin 和 cmax。'),
    'tid': ('元组位置标识符', '事务与行标识符', '以块号和块内元组索引标识行的物理位置，是系统列 ctid 的类型。'),
}
