"""Editorial labels and command variants for the reproducible lock atlas.

Conflict edges are deliberately absent: build_locks.py extracts and checks them
against each pinned PostgreSQL revision.  Command notes describe the named
object/stage, rather than claiming a statement only ever obtains one lock.
"""

MODE_DEFINITIONS = [
    ('access-share', 'ACCESS SHARE', '访问共享锁', 'AS', 'table', '普通读取取得的表级锁；只与访问排他锁冲突。'),
    ('row-share', 'ROW SHARE', '行共享锁', 'RS', 'table', '带行锁子句的查询在目标表上取得的表级锁；名字中的 ROW 不表示行级锁。'),
    ('row-exclusive', 'ROW EXCLUSIVE', '行排他锁', 'RX', 'table', '插入、更新和删除在目标表上取得的表级锁；多个事务可以同时持有。'),
    ('share-update-exclusive', 'SHARE UPDATE EXCLUSIVE', '共享更新排他锁', 'SUE', 'table', '用于维护及部分结构变更；允许普通读写，但同一表上不能同时执行另一项持有此模式的操作。'),
    ('share', 'SHARE', '共享锁', 'S', 'table', '允许读取和另一项共享锁操作，阻止对目标表的数据修改。'),
    ('share-row-exclusive', 'SHARE ROW EXCLUSIVE', '共享行排他锁', 'SRX', 'table', '阻止普通数据修改，并与自身冲突；常见于创建触发器与增加外键。'),
    ('exclusive', 'EXCLUSIVE', '排他锁', 'X', 'table', '只允许并发取得访问共享锁；普通读取仍可继续，带行锁的查询与写入需要等待。'),
    ('access-exclusive', 'ACCESS EXCLUSIVE', '访问排他锁', 'AX', 'table', '与全部表级锁模式冲突；也是唯一会阻塞普通 SELECT 的表级锁。'),
    ('for-key-share', 'FOR KEY SHARE', '键共享锁', 'FKS', 'row', '保护同一行的键值；阻止删除和修改键值，允许不修改键值的更新。'),
    ('for-share', 'FOR SHARE', '行共享锁', 'FS', 'row', '阻止同一行的更新、删除及排他行锁；允许其他事务共享锁定这一行。'),
    ('for-no-key-update', 'FOR NO KEY UPDATE', '非键更新锁', 'FNKU', 'row', '用于不修改键值的更新；与键共享锁兼容，与其余行锁模式冲突。'),
    ('for-update', 'FOR UPDATE', '行更新锁', 'FU', 'row', '最强的行锁模式；与同一行的全部行锁模式冲突，用于删除和可能修改键值的更新。'),
]

# Fixed upstream commits, not moving branch URLs.  19 is explicitly beta4.
REVISIONS = {
    '10': ('REL_10_STABLE', 'f4e8f137bfb08a664c8288824c1e36b5143ac875'),
    '11': ('REL_11_STABLE', '170e416034ec0231d9e9238f2577eeb76ca8d181'),
    '12': ('REL_12_STABLE', '3f302f0ed06f69c5ebd33d4df95895323a3cbef6'),
    '13': ('REL_13_STABLE', '05f6c9ec2c475fae8fdd56ae40bd01afcf70d1f2'),
    '14': ('REL_14_STABLE', 'fba35c7c28a567839faba867db0808564c0a66db'),
    '15': ('REL_15_STABLE', '0351991b8e7c7b64382e2f30ce581a8f276590a6'),
    '16': ('REL_16_STABLE', 'dcc37b7099a9f3cf2c75167d8dc92e75f96bc1fa'),
    '17': ('REL_17_STABLE', '163288afd32a448244c8df75b3c33181aadd7f20'),
    '18': ('REL_18_STABLE', '753057e340da8f22e57c9a409ea7a235fd6a46bd'),
    '19': ('REL_19_BETA4', 'b73d13c32c834a2c8e1c60cb92f79530376cedf1'),
    '20': ('master', '1a846a555afb0e5f2008f3aefe8f77acbe6ffba6'),
}


def command_specs():
    """Return curated command associations; source evidence is attached at build."""
    result = []

    def add(mode, slug, label, note, minimum=10, maximum=20, source=None, enum=None):
        result.append(dict(mode=mode, slug=slug, label=label, note=note,
                           minimum=minimum, maximum=maximum,
                           source=source or slug.replace('-', '_'), enum=enum))

    add('access-share', 'select', 'SELECT', '读取所引用的表；未使用 FOR … 行锁子句的表取得此模式。', source='mvcc')
    add('access-share', 'copy', 'COPY … TO', '从源表读取；COPY (query) TO 则取决于该查询。', source='copy-source')
    add('row-exclusive', 'insert', 'INSERT', '在写入的目标表上加锁；新插入行不能简单等同于对已有行取得 FOR UPDATE。', source='mvcc')
    add('row-exclusive', 'update', 'UPDATE', '目标表取得此模式；受影响的已有行另有行锁。', source='mvcc')
    add('row-exclusive', 'delete', 'DELETE', '目标表取得此模式；删除的已有行另有 FOR UPDATE 行锁。', source='mvcc')
    add('row-exclusive', 'copy', 'COPY … FROM', '在目标表上加锁并插入新行；不笼统列为对已有行取得 FOR UPDATE。', source='copy-source')
    add('row-exclusive', 'merge', 'MERGE', '目标表取得此模式；每个匹配分支是否加行锁以及锁强度由实际 INSERT / UPDATE / DELETE 动作决定。', 15, source='mvcc')
    for rowmode in ('for-key-share', 'for-share', 'for-no-key-update', 'for-update'):
        label = 'SELECT ' + rowmode.upper().replace('-', ' ')
        add('row-share', 'select', label, '此模式锁住指定的表；同时在选中的行上取得对应的行锁。', source='mvcc')
        add(rowmode, 'select', label, '作用于实际选中的行；目标表同时取得 ROW SHARE。NOWAIT / SKIP LOCKED 改变等待行为，不改变锁冲突规则。', source='mvcc')
    add('for-no-key-update', 'update', 'UPDATE（不修改键值）', '没有取得 FOR UPDATE 的 UPDATE 使用此模式。此处的键列是可供外键引用的唯一索引列，不包括部分索引与表达式索引。', source='mvcc')
    add('for-update', 'update', 'UPDATE（修改键值）', '修改可供外键引用的唯一索引列时使用；部分索引和表达式索引不算在内。', source='mvcc')
    add('for-update', 'delete', 'DELETE', '在被删除的已有行上取得此模式；目标表同时取得 ROW EXCLUSIVE。', source='mvcc')
    add('for-no-key-update', 'merge', 'MERGE … WHEN MATCHED THEN UPDATE（非键）', '实际执行 UPDATE 分支且不需 FOR UPDATE 时；不能给所有 MERGE 分支统一套用一种行锁。', 15, source='mvcc')
    add('for-update', 'merge', 'MERGE … WHEN MATCHED THEN DELETE / UPDATE（键）', '实际删除或更新键列的匹配行；纯插入分支不适用。', 15, source='mvcc')
    add('for-no-key-update', 'insert', 'INSERT … ON CONFLICT DO UPDATE（非键）', '冲突路径锁住要更新的已有行；锁强度按 UPDATE 的键列规则确定，即使 DO UPDATE WHERE 排除更新也会锁行。', source='insert')
    add('for-update', 'insert', 'INSERT … ON CONFLICT DO UPDATE（键）', '冲突路径修改键列时，锁住冲突的已有行；不是普通 INSERT 的固定行锁。', source='insert')
    for slug, minimum in (('insert', 10), ('update', 10), ('copy', 10), ('merge', 15)):
        label = ('COPY … FROM' if slug == 'copy' else slug.upper()) + '（外键检查）'
        add('for-key-share', slug, label, '实际检查非空外键引用时，在被引用表的匹配行上取得 FOR KEY SHARE；可能在语句内或延迟约束检查时执行。级联动作还会取得相应 UPDATE / DELETE 的锁。', minimum, source='ri-source')
        add('row-share', slug, label, '外键检查的内部 SELECT … FOR KEY SHARE 在被引用表上取得 ROW SHARE；写入目标表上的模式仍是 ROW EXCLUSIVE。', minimum, source='ri-source')
    for rowmode in ('for-key-share', 'for-share', 'for-no-key-update', 'for-update'):
        add(rowmode, 'insert', 'INSERT … ON CONFLICT DO SELECT ' + rowmode.upper().replace('-', ' '), 'PostgreSQL 19 起，DO SELECT 可通过对应 FOR 子句锁住冲突的已有行。', 19, source='insert')

    for mode, slug, label, note, minimum, source in [
        ('share-update-exclusive','vacuum','VACUUM（不含 FULL）','常规清理持有此锁；尝试截断表尾空页时还可能短暂取得 ACCESS EXCLUSIVE。',10,'vacuum'),
        ('share-update-exclusive','analyze','ANALYZE','在被分析的目标表上取得此模式。',10,'mvcc'),
        ('share-update-exclusive','create-index','CREATE INDEX CONCURRENTLY','作用于被索引的表；多个事务阶段构建并等待旧事务，不表示无等待。',10,'create_index'),
        ('share-update-exclusive','create-statistics','CREATE STATISTICS','在被收集统计信息的表上加锁。',10,'mvcc'),
        ('share-update-exclusive','comment','COMMENT ON（关系对象）','COMMENT 在所注释对象上取得此模式；不同对象上的同名锁不会互相冲突。',10,'comment'),
        ('share-update-exclusive','drop-index','DROP INDEX CONCURRENTLY','在所属表上取得此模式，分阶段等待并移除索引；不在表上持有普通 DROP INDEX 的 ACCESS EXCLUSIVE。',10,'index-source'),
        ('share-update-exclusive','reindex','REINDEX … CONCURRENTLY','PostgreSQL 12 起；会话级 SHARE UPDATE EXCLUSIVE 锁覆盖被重建的索引及所属表，分多个事务完成构建、验证、切换与清理。',12,'reindex'),
        ('share','create-index','CREATE INDEX（不含 CONCURRENTLY）','作用于被索引的表，阻止表上并发写入。',10,'mvcc'),
        ('share','reindex','REINDEX（所属表）','非并发重建在所属表上取得 SHARE；被重建的索引另取 ACCESS EXCLUSIVE，不能把索引锁误写成整个表的 ACCESS EXCLUSIVE。',10,'index-source'),
        ('share-row-exclusive','create-trigger','CREATE TRIGGER','在触发器所属表上加锁。',10,'mvcc'),
        ('exclusive','refresh-materialized-view','REFRESH MATERIALIZED VIEW CONCURRENTLY','作用于被刷新的物化视图；普通读取可继续，同一个物化视图同时只允许一个刷新。',10,'mvcc'),
        ('access-exclusive','refresh-materialized-view','REFRESH MATERIALIZED VIEW（不含 CONCURRENTLY）','作用于被刷新的物化视图，同时阻止普通读取。',10,'mvcc'),
        ('access-exclusive','drop-table','DROP TABLE','作用于被删除的表；依赖对象及 CASCADE 还可能取得额外锁。',10,'mvcc'),
        ('access-exclusive','drop-index','DROP INDEX（不含 CONCURRENTLY）','在所属表上加 ACCESS EXCLUSIVE，阻塞读写；被删除的索引也需要锁定。',10,'reindex'),
        ('access-exclusive','truncate','TRUNCATE','在被截断的各表上加锁；包含的表和依赖对象依命令选项而定。',10,'mvcc'),
        ('access-exclusive','cluster','CLUSTER','重写目标表期间阻止并发读写。',10,'mvcc'),
        ('access-exclusive','vacuum','VACUUM FULL','重写目标表期间阻止并发读写。',10,'mvcc'),
        ('access-exclusive','vacuum','VACUUM（截断表尾阶段）','常规 VACUUM 尝试将末尾空页归还操作系统时，短暂尝试 ACCESS EXCLUSIVE；可用相应版本支持的截断选项避免该阶段。',10,'vacuum-source'),
        ('access-exclusive','reindex','REINDEX（被重建索引）','此锁作用于索引本身，而非所属表；查询规划也会访问索引，所以非并发 REINDEX 仍可能阻塞查询。',10,'reindex'),
        ('access-exclusive','repack','REPACK（不含 CONCURRENTLY）','PostgreSQL 19 起；整个重写期间在目标表上取得 ACCESS EXCLUSIVE。',19,'repack'),
        ('share-update-exclusive','repack','REPACK (CONCURRENTLY)（复制与追赶阶段）','PostgreSQL 19 起；主体阶段在目标表上持有 SHARE UPDATE EXCLUSIVE，切换文件阶段再升级为 ACCESS EXCLUSIVE。',19,'repack-source'),
        ('access-exclusive','repack','REPACK (CONCURRENTLY)（切换文件阶段）','PostgreSQL 19 起；主体复制允许并发读写，最终切换表与索引文件时取得 ACCESS EXCLUSIVE；等待后补放的变更可能延长该阶段。',19,'repack'),
    ]:
        add(mode,slug,label,note,minimum,source=source)

    # LOCK supports all eight table-level modes, including the default AX.
    for slug, name, *_ in MODE_DEFINITIONS[:8]:
        add(slug, 'lock', 'LOCK TABLE … IN ' + name + ' MODE',
            '显式请求此表级模式；省略 IN … MODE 时默认为 ACCESS EXCLUSIVE。', source='mvcc')

    # Simple ALTER TABLE cases: mode and availability are extracted separately
    # from AlterTableGetLockLevel in *each* pinned version, not copied forward.
    for enum, label, note in [
        ('AT_AddColumn','ADD COLUMN','是否需要重写取决于版本与默认表达式；避免重写并不降低这里的锁级别。'),
        ('AT_DropColumn','DROP COLUMN','删除列并改变表结构。'),
        ('AT_ColumnDefault','ALTER COLUMN … SET / DROP DEFAULT','修改列默认值。'),
        ('AT_AlterColumnType','ALTER COLUMN … TYPE','改变列类型；是否重写不改变这里列出的锁要求。'),
        ('AT_SetStorage','ALTER COLUMN … SET STORAGE','修改列存储策略。'),
        ('AT_SetCompression','ALTER COLUMN … SET COMPRESSION','修改列压缩方法。'),
        ('AT_SetStatistics','ALTER COLUMN … SET STATISTICS','修改列统计目标。'),
        ('AT_SetOptions','ALTER COLUMN … SET (n_distinct = …)','修改列统计选项；RESET 同样适用。'),
        ('AT_ClusterOn','CLUSTER ON','设置后续聚簇使用的索引；此命令本身不重写表。'),
        ('AT_DropCluster','SET WITHOUT CLUSTER','清除聚簇索引标记。'),
        ('AT_SetTableSpace','SET TABLESPACE','移动表的表空间。'),
        ('AT_SetLogged','SET LOGGED / UNLOGGED','切换日志持久性。'),
        ('AT_SetAccessMethod','SET ACCESS METHOD','修改表访问方法。'),
        ('AT_ValidateConstraint','VALIDATE CONSTRAINT','在当前表上验证约束；外键验证还需要访问被引用表。'),
        ('AT_DropConstraint','DROP CONSTRAINT','删除约束及可能依赖的索引。'),
        ('AT_AlterConstraint','ALTER CONSTRAINT','修改约束属性。'),
        ('AT_SetNotNull','ALTER COLUMN … SET NOT NULL','设置非空约束。'),
        ('AT_DropNotNull','ALTER COLUMN … DROP NOT NULL','移除非空约束。'),
        ('AT_EnableTrig','ENABLE / DISABLE TRIGGER','启停触发器，包括 USER / ALL / REPLICA / ALWAYS 相应形式。'),
        ('AT_EnableRule','ENABLE / DISABLE RULE','启停规则。'),
        ('AT_EnableRowSecurity','ENABLE / DISABLE ROW LEVEL SECURITY','启停行级安全策略。'),
        ('AT_ForceRowSecurity','FORCE / NO FORCE ROW LEVEL SECURITY','改变表所有者是否受行级安全策略约束。'),
        ('AT_DropExpression','ALTER COLUMN … DROP EXPRESSION','移除生成列表达式。'),
        ('AT_SetExpression','ALTER COLUMN … SET EXPRESSION','设置生成列表达式。'),
        ('AT_SetIdentity','ALTER COLUMN … SET GENERATED / RESTART / SET sequence_option','修改标识列属性或其隐式序列选项；不是名为 SET SEQUENCE 的独立子命令。'),
        ('AT_AddIdentity','ALTER COLUMN … ADD GENERATED … AS IDENTITY','为列增加标识属性。'),
        ('AT_DropIdentity','ALTER COLUMN … DROP IDENTITY','移除标识属性。'),
        ('AT_AddInherit','INHERIT / NO INHERIT（子表）','此处列出被修改的子表；父表另按继承处理锁定。'),
        ('AT_ChangeOwner','OWNER TO','修改表所有者。'),
        ('AT_ReplicaIdentity','REPLICA IDENTITY','修改复制标识。'),
        ('AT_AttachPartition','ATTACH PARTITION（父表）','父表锁级别逐版本解析；待挂载分区另取 ACCESS EXCLUSIVE。PostgreSQL 11 起如有默认分区，也需锁定默认分区。'),
        ('AT_DetachPartitionFinalize','DETACH PARTITION … FINALIZE（父表）','完成中断的并发分离；被分离分区另取 ACCESS EXCLUSIVE。'),
    ]:
        add('from-source', 'alter-table', 'ALTER TABLE … ' + label, note,
            source='table-source', enum=enum)
    for mode, label, note, minimum in [
        ('access-exclusive','RENAME','重命名表、列或约束。',10),
        ('access-exclusive','ADD CONSTRAINT（CHECK / UNIQUE / PRIMARY KEY / EXCLUDE）','普通添加约束；ADD FOREIGN KEY 使用较弱的 SHARE ROW EXCLUSIVE。',10),
        ('share-row-exclusive','ADD FOREIGN KEY [NOT VALID]（引用表）','引用方与被引用方都取得 SHARE ROW EXCLUSIVE；NOT VALID 只省略已有数据的初始验证，不免除这个锁。',10),
        ('share-row-exclusive','ADD FOREIGN KEY [NOT VALID]（被引用表）','与引用方同样取得 SHARE ROW EXCLUSIVE，不能把被引用表记为只有 ACCESS SHARE。',10),
        ('row-share','VALIDATE CONSTRAINT（外键被引用表）','验证外键时，被引用表另取 ROW SHARE；正在验证约束的表取 SHARE UPDATE EXCLUSIVE。',10),
        ('share-update-exclusive','SET / RESET (fillfactor = …)','表存储参数按参数定义选择锁；fillfactor 可用 SHARE UPDATE EXCLUSIVE。',10),
        ('share-update-exclusive','SET / RESET (autovacuum_* = …)','表的自动清理存储参数使用 SHARE UPDATE EXCLUSIVE。',10),
        ('share-update-exclusive','SET / RESET (toast.autovacuum_* = …)','这里给出 TOAST 自动清理参数；不存在笼统的 SET TOAST 子命令，其他参数按具体定义选择锁。',10),
        ('access-exclusive','ATTACH PARTITION（待挂载分区）','待挂载表需 ACCESS EXCLUSIVE；合适的 CHECK 约束可以免除验证扫描，但不免除对这张表的锁。',10),
        ('access-exclusive','ATTACH PARTITION（默认分区）','PostgreSQL 11 起如有默认分区，对其取得 ACCESS EXCLUSIVE；合适 CHECK 约束可免扫描，不能免除默认分区本身的锁。递归子分区另按验证需要处理。',11),
        ('access-exclusive','DETACH PARTITION（父表）','未使用 CONCURRENTLY 的常规分离。',10),
        ('access-exclusive','DETACH PARTITION（被分离分区）','常规分离在被分离分区上取得 ACCESS EXCLUSIVE。',10),
        ('share-update-exclusive','DETACH PARTITION … CONCURRENTLY（父表）','PostgreSQL 14 起，分两个事务进行；父表使用 SHARE UPDATE EXCLUSIVE，等待使用分区的事务结束后进入完成阶段。',14),
        ('share-update-exclusive','DETACH PARTITION … CONCURRENTLY（分区，第一阶段）','第一阶段父表与分区使用 SHARE UPDATE EXCLUSIVE；提交并等待后再升级分区锁。',14),
        ('access-exclusive','DETACH PARTITION … CONCURRENTLY（分区，完成阶段）','第二阶段在被分离分区取得 ACCESS EXCLUSIVE；不允许存在默认分区时使用 CONCURRENTLY。',14),
    ]:
        add(mode,'alter-table','ALTER TABLE … '+label,note,minimum,source='alter_table')
    for mode, label, note, minimum in [
        ('share-update-exclusive','RENAME','作用于被重命名的索引本身。',10),
        ('access-exclusive','SET TABLESPACE','作用于被移动的索引；不要把索引上的锁当作同名表上的锁。',10),
        ('access-exclusive','SET / RESET (fillfactor = …)','作用于被修改的索引本身。',10),
        ('access-exclusive','ATTACH PARTITION','PostgreSQL 11 起；修改父分区索引与被附加的子索引。',11),
    ]:
        add(mode,'alter-index','ALTER INDEX … '+label,note,minimum,source='alter_index')
    add('share-update-exclusive', 'alter-table', 'ALTER TABLE … INHERIT（父表）',
        '在新指定的继承父表上取得 SHARE UPDATE EXCLUSIVE；被修改的子表另取 ACCESS EXCLUSIVE。', source='table-source')
    add('access-share', 'alter-table', 'ALTER TABLE … NO INHERIT（父表）',
        '检查并解除继承关系时，在父表上取得 ACCESS SHARE；被修改的子表另取 ACCESS EXCLUSIVE。', source='table-source')

    # The selector groups by (slug, label). Every DML row-lock variant must
    # therefore carry its own mandatory target-table lock as well. This is a
    # narrowly defined DML rule, not a union of all locks sharing a command slug.
    # In particular, foreign-key checks lock a *different*, referenced object.
    existing = {(s['mode'], s['slug'], s['label'], s['minimum'], s['maximum'])
                for s in result}
    for spec in tuple(result):
        if spec['slug'] not in {'insert', 'update', 'delete', 'merge', 'copy'}:
            continue
        if spec['slug'] == 'copy' and not spec['label'].startswith('COPY … FROM'):
            continue
        if not spec['mode'].startswith('for-'):
            continue
        identity = ('row-exclusive', spec['slug'], spec['label'],
                    spec['minimum'], spec['maximum'])
        if identity in existing:
            continue
        note = '这个写入变体在目标表上取得 ROW EXCLUSIVE；对已有行的锁另按实际动作取得。'
        if '外键检查' in spec['label']:
            note = ('原始写入命令在写入目标表上取得 ROW EXCLUSIVE；'
                    '外键检查的 ROW SHARE 与 FOR KEY SHARE 则作用于被引用的表和行，不能混为同一对象。')
        add('row-exclusive', spec['slug'], spec['label'], note,
            spec['minimum'], spec['maximum'],
            source='copy-source' if spec['slug'] == 'copy' else 'mvcc')
        existing.add(identity)
    return result


COVERAGE_NOTES = [
    '12 种模式是 8 种表级锁与 4 种行级锁，不是 PostgreSQL 所有锁机制的穷举；咨询锁、页锁、谓词锁及内部轻量锁不套用此矩阵。',
    '冲突判断要求不同事务、同一个被锁对象、同一个锁作用域；同事务不会与自己冲突。跨表级与行级的格子不适用。',
    '矩阵说明模式兼容性，不能保证完整 SQL 语句必定不等待；外键、触发器、索引、其他关系、锁队列和事务快照都可能带来额外等待。',
    '命令关联按对象与执行阶段列出常见及文档明确的形式；一条语句可能取得多种锁，ALTER TABLE 组合子命令使用所需的最强模式。',
    'pglocks.org 用于发现命令范围；冲突及命令事实以固定 PostgreSQL 源码和官方手册为准，纠正 COPY FROM、MERGE、REINDEX、外键及分区操作的一刀切对应。',
]
