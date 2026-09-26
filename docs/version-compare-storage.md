# 版本比较的数据库存储

版本比较运行时只读取 PostgreSQL 数据库。文件是可审核、可搬运的来源快照，不是运行时兜底；数据库未导入、激活清单缺项或内容哈希错误时，页面明确返回数据暂不可用。中文 PGSQL.CC 与英文 PG.CENTER 各自在独立数据库导入本语言，操作另一个站点必须使用它自己的项目配置。

原始抽取、分类与来源核验见 [version-compare-data.md](version-compare-data.md)，用户功能与版本区间语义见 [version-compare.md](version-compare.md)。存储实现为 `pgweb/docs/compare_store.py`，迁移为 `docs.0005_compare_storage`。

## 四张表

| 表 | 身份与用途 | 完整数据与关系 |
| --- | --- | --- |
| `release_dataset` | `releases:zh`、`releases:en` 或 `security`；当前激活清单 | 原始顶层元数据、按原始顺序排列的发布与 entry ID、计数、整份来源哈希、修订号、旧清单；security 元数据保存完整权威 CVE 矩阵 |
| `release` | 一个完整版本坐标，例如 `9.6.24`、`18.6` | 发布日期、大版本、维护小版本、状态及排序键；`payloads[language]` 保存原始发布对象（仅去掉已归属 entry 的数组），包括迁移段落、来源与所有未知字段 |
| `release_entry` | 一次发布中一个原始变更的独立 occurrence | 完整 HTML、text、英文 identity_text、作者、提交、来源坐标与未知字段保存在 `payloads[language]`；另有类别、顺序、CVE、独立 patch ID 集合、正文哈希与明确关系 |
| `release_patch` | 一个有证据支持的上游提交/回补对应组 | 提交集合、identity seed、合并/拆分证据、旧修订；组内是提交对应关系，不直接断言两个条目语义等价 |

不创建每个起止版本组合的表，不把全文再次复制到 dataset，不为条目的每个提交拆关联表。`patch_ids[]` 表达 entry 与多个独立修复组之间的多对多关联；GIN 索引支持包含与重叠查询。`relations` 的 GIN 索引支持明确关系查询，发布日期/版本/类别/正文哈希与发布内顺序另有普通索引。

PostgreSQL 9.x 的 branch 是字符串 `9.0` 至 `9.6`，版本坐标始终完整到维护小版本，例如 `9.0.0`。不能转成浮点数或把 `9.6.24` 当成“大版本 9，小版本 6”。10 起使用 `18.0`、`18.6`。状态区分 stable、preview、devel；预览构建名称保留在发布 payload 中。

## 稳定身份与可审核更新

首次出现的 entry ID 是 SHA-256 截短到 32 位十六进制：`release-occurrence + 完整版本 + 原始分区 + 英文来源 source_hash（缺失时完整英文正文哈希）+ 完全相同来源在该发布内的重复序号`。每次 occurrence 永久独立；同一发布内文字相同的条目也不合并。`source_entry_id` 的顺序坐标只是来源，不直接充当永久主键。

重导匹配限于同一发布，依次使用本语言既有展示 ID、相同来源哈希与分区、或“来源坐标与完整英文正文同时相同且提交证据没有矛盾”的注释纠错锚点。最后一种允许 SGML Author 注释校准导致 source_hash 与展示 ID 改变时保留身份；不允许仅凭位置覆盖另一个新条目。同来源重复项按原始顺序一一匹配。新增预览条目改变后续顺序时，既有来源/展示身份仍可命中。

首次出现的 patch ID 来自规范化组中最小提交的确定性哈希；之后新增 alias 保留已有 identity seed 与 ID。多个既有组被权威证据连接时，确定性选一个已有 ID，其余保存 `merged_into` 与历史。纠错拆组只根据当前有效原始 commit_groups 重建连通分量，不让历史错误边继续影响事实；包含旧 identity seed 的分量保留旧 ID，其余分量生成或复活各自 ID，所有有效 entry 的 patch_ids 与 relations 随之重算。不同导入历史之间若要求连 ID 与修订完全一致，搬运完整 storage archive；相同首次来源可以直接得到相同初始 ID。

未知 JSON 字段原样保留。正文或来源更新前，将该语言旧完整 payload、哈希、替换时间和来源追加到 `revisions`；不静默丢掉旧原文。中文和英文 payload 独立，canonical English 事实可共享，不用中文标题推断同一修复。各站只需要自己的默认语言，不会跨连接写另一站数据库。

## 明确关系规则（rule 2）

每条关系包含目标永久 entry ID、`type`、`rule` 与证据。例如：

```json
{"target":"<32 hex entry ID>","type":"equivalent","rule":2,"evidence":{"patch_ids":["<patch ID>"],"same_day":true}}
```

`equivalent` 只用于不同大版本分支、相同原始分区，并满足以下证据之一：

- 两边均有明确提交：完整独立 patch 集合完全相等。两边均为维护小版本时可成立；任意一边涉及首发版，还必须完整英文正文相同。
- 至少一边缺少提交：完整英文正文、分区与发布日期都相同。

一个独立 patch 若在同一发布、同一原始分区对应多个不同的完整英文正文，就标为全局歧义 patch；任何涉及它的等价判断都额外要求完整正文相同，证据里保留 `ambiguous_patch_ids`。例如 PostgreSQL 16.2 的大对象所有权检查与 PostAlterHook 报告修复共享提交，而旧分支仅发布了后者，不能把前者标为旧版已有的同一修复。检测按独立 patch 进行，部分重叠的多提交条目同样能触发。

部分 patch 重叠、首发版正文不同、或同一分支的关联只记 `related`。两边明确提交集合互斥时，即使同日文字相同也不建立关系。正文哈希相同本身不等于已确认重复。同分支原始记录永远保留，不因关系删减。

关系保存的是跨发布事实，和用户选的比较区间无关。运行时在跨分支比较中仍按实际源分支可见历史与目标发布日期限制进行回补排除；不能仅因存在 equivalent 就在所有报告里隐藏该条目。`load_database_snapshot()` 会把关系限制到当前语言激活清单内，返回旧 JSON 契约并为每个条目增加 `db_id`、`patch_ids`、`statement_hash`、`relations`。

## 导入、导出与恢复

先在对应站点项目根目录运行迁移，再导入本语言来源。以下中文示例全部明确语言；英文站改为 `--language en` 并使用英文快照及英文站配置。

```bash
.venv/bin/python manage.py migrate docs
.venv/bin/python manage.py import_compare data/compare/releases.json.gz --language zh --check
.venv/bin/python manage.py import_compare data/compare/releases.json.gz --language zh --complete --prune --write
.venv/bin/python manage.py import_compare data/compare/security.json --kind security --complete --prune --write
.venv/bin/python manage.py export_compare /tmp/compare-releases-zh.json.gz --language zh
.venv/bin/python manage.py export_compare /tmp/compare-security.json --kind security
.venv/bin/python manage.py export_compare /tmp/compare-storage-backup.json.gz --archive
```

`import_compare` 默认在事务中写入、核验再回滚；只有 `--write` 提交。所有写入以数据库 advisory lock 串行化。源缺项默认保留；只有显式 `--complete --prune` 才撤下该语言缺失成员，旧行和原文仍保留。撤下不是物理删除。完整快照首次导入及正式全量更换使用这两个参数，避免旧预览条目残留在激活集合。

事务内逐行哈希避免无意义更新，然后严格从数据库重建原始 JSON，验证数量、所有未知字段、完整原始对象相等及整体哈希，最后原子激活 manifest。失败整体回滚。无变化的重复导入不改数据修订、正文历史或写入时间。关系规则升级后重导原始快照会重新计算关系；即使原文完全相同，派生关系变化也会更新 manifest 修订号，使所有 worker 缓存失效。

普通 export 从数据库重建原始来源，精确保持对象内容及数组顺序，不混入运行时注解。`--archive` 导出四表全部行，包含旧原文、已撤下成员、永久 ID、patch 合并/拆分证据、关系及 manifest 修订。archive 可用同一个 `import_compare ARCHIVE --write` 恢复到四张空表；非空且不同的库会拒绝覆盖，完全相同则幂等返回。恢复后再次导出 archive 必须完全一致。输出文件原子替换、权限 0644，gzip 时间戳固定。

## 运行时与内存

运行时每次请求只读一次对应 dataset 的修订号；修订未变直接复用该 worker 当前快照。一个 dataset 只缓存最新修订，替换前移除旧缓存引用，避免更新后多份大快照长期常驻。冷读取只查询本语言 JSON 与必要投影列，迭代读取条目，不载入历史 revisions，不构造全量 ORM 对象，不复制每份正文；内容哈希按 JSON 编码块计算，避免拼接完整大字符串。

数据库读取期间若 manifest 发生变化，重新加载；同一修订缺项或哈希错误则报数据不可用。完整来源数据与安全矩阵分别激活；发布时先导入两者再重启应用。无需运行文档全文索引，比较条目当前不写入手册搜索表。

## 检验

隔离测试库，不使用本地业务库：

```bash
PGWEB_TEST_DB=test_pgweb_compare_store .venv/bin/python manage.py test pgweb.docs.test_compare_store --noinput
.venv/bin/python manage.py makemigrations docs --check --dry-run
psql service=pgweb.pg -f tools/docs/check_compare.sql
```

SQL 检查脚本只有 SELECT，直接验证发布/条目/patch/关系数量、孤立关系、激活清单成员及错误的同分支 equivalent。更深入的跨分支算法穷举使用 [数据说明](version-compare-data.md) 的 `audit_compare --database`。

353 个发布、16,113 个 entry 的中文完整来源在隔离库验收：原始 JSON 严格往返、第二次导入所有行哈希与写入时间不变；7,244 个提交组、40,634 条有向关系。测试覆盖双语独立 payload、未知字段、预览插入、注释纠错拆组、同分支不等价、明确提交互斥、部分回补、首发版完整正文限制、回滚、缺项错误、单修订缓存及完整 archive 恢复。
