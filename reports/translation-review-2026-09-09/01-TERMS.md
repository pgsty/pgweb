# 术语校准

本文件仅供 Review，所有条目均待确认；页面源文件和数据库均未改动。

返回 [总览](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/REVIEW.md)。

| 编号 | 候选项目 | 判断 |
| --- | --- | --- |
| T01 | Full-Text Search：全文检索 | 建议修改 |
| T02 | Failover：故障切换 | 建议修改 |
| T03 | B-tree：B-树 | 建议修改 |
| T04 | Exclusion Constraints：排他约束 | 建议修改 |
| T05 | Operator：操作符 | 建议修改 |
| T06 | Most Common Values / MCV：高频值 | 建议修改 |
| T07 | HOT：堆内元组 | 建议修改 |
| T08 | Merge Join：归并连接 | 建议修改 |
| T09 | Partition pruning：分区剪枝 | 建议修改 |
| T10 | Identity column：标识列 | 建议修改 |
| T11 | WAL 与 full-page write：预写式日志、整页写入 | 建议修改 |
| T12 | Visibility map：可见性映射 | 建议修改 |
| T13 | Autovacuum：自动清理 | 建议修改 |
| T14 | Serializable snapshot isolation：可串行化快照隔离 | 建议修改 |
| T15 | 逻辑复制说明中的 publication / schema：发布／模式 | 建议修改 |
| T16 | 复制语境：主库、备库、从库 | 建议修改 |
| T17 | 数据库集簇与高可用集群分开使用 | 建议修改 |
| T18 | 规划器 Cost：代价 | 建议修改 |
| T19 | 后端概述：词元与聚合 | 建议修改 |
| T20 | 可伸缩性与可扩展性按语义区分 | 建议修改 |
| T21 | Trusted extension：受信任的扩展 | 建议修改 |
| T22 | 最近邻索引用词 | 建议修改 |
| T23 | 生成列的复合名称 | 建议修改 |
| T24 | Index-only scan：仅索引扫描 | 建议修改 |
| T25 | Foreign key：外键 | 建议修改 |
| T26 | 事务 ID 回卷 | 建议修改 |

原文与建议以可见文字为主；模板变量、链接和源字符串的完整记录保存在 review.json。行号以本次审阅基线为准。

## T01 · Full-Text Search：全文检索

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 202 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:202)。

**1. 原文**：`全文搜索`

**建议**：`全文检索`

落点：

- [templates/core/about.html:90](/Users/vonng/pgsty/pgweb/templates/core/about.html:90) — `全文搜索`
- [data/featurematrix_zh.yaml:108](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:108) — `description: 全文搜索支持短语和词语邻近度搜索。`
- [data/featurematrix_zh.yaml:390](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:390) — `name: 全文搜索`
- [data/featurematrix_zh.yaml:1274](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:1274) — `description: 用于从 contrib/tsearch2 迁移到 8.3 集成全文搜索的兼容性包装器`

## T02 · Failover：故障切换

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 167 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:167)。

说明：9.3 新闻资料包中的引语仅统一术语，不改人物原意；相应落点在明细中单列。

**1. 原文**：`故障转移`

**建议**：`故障切换`

落点：

- [pgweb/docs/ecosystem.py:18](/Users/vonng/pgsty/pgweb/pgweb/docs/ecosystem.py:18) — `'patroni': {'name': 'Patroni', 'icon': 'fa-heartbeat', 'description': 'PostgreSQL 高可用与自动故障转移'},`

**2. 原文**：`失效转移`

**建议**：`故障切换`

落点：

- [templates/pages/about/press/presskit93/zh_CN.html:46](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:46) — `众所周知的稳定性、强壮性、数据一致性、安全性、ACID 事务性和 SQL 标准规范性一直就是我的最喜欢的选择”，Gandi.net 网站的研发经理 Pascal Bouchareine 说道，“我对 9.3 版本中快速的失效转移功能尤其感到兴奋”。`
- [templates/pages/about/press/presskit93/zh_CN.html:55](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:55) — `快速失效转移：可以实现亚秒级的从主库向副本的切换，支持“电信级”高可用性`
- [templates/pages/about/press/presskit93/zh_CN.html:163](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:163) — `"我们需要使用复制技术，对最近这项特性的改进非常感兴趣，我对 9.3 版本中的快速失效转移功能尤其兴奋。我们在 Gandi IAAS/PAAS 平台上已经使用 PostgreSQL 很长时间，最近我们也使用它创建我们的在线系统每天来存储、计算、输出数百万条记录，真的是很简单"。`

## T03 · B-tree：B-树

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 28 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:28)。

说明：只改中文说明中的展示文字；英文 YAML 键、SQL、URL 与其他语言页面不替换。

**1. 原文**：`B-tree`

**建议**：`B-树`

落点：

- [templates/core/about.html:44](/Users/vonng/pgsty/pgweb/templates/core/about.html:44) — `索引：B-tree，多列，表达式，部分索引`
- [templates/core/about.html:49](/Users/vonng/pgsty/pgweb/templates/core/about.html:49) — `读查询和构建 B-tree 索引的并行化`
- [data/featurematrix_zh.yaml:127](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:127) — `name: B-tree 自底向上的索引删除`
- [data/featurematrix_zh.yaml:129](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:129) — `name: B-tree 去重`
- [data/featurematrix_zh.yaml:135](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:135) — `name: B-tree 的覆盖索引 (INCLUDE)`
- [data/featurematrix_zh.yaml:189](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:189) — `name: 并行 B-tree 索引扫描`
- [data/featurematrix_zh.yaml:190](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:190) — `description: B-tree 索引页面可以由多个并行工作进程进行搜索。`
- [data/featurematrix_zh.yaml:194](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:194) — `name: B-tree 索引的并行 CREATE INDEX`
- [data/featurematrix_zh.yaml:198](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:198) — `name: 多列 B-tree 索引上的跳跃扫描`
- [data/featurematrix_zh.yaml:199](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:199) — `description: 对于在一个或多个前导索引列上缺少 '=' 条件的查询，多列 B-tree 索引现在可以使用跳跃扫描来改善执行时间。`

## T04 · Exclusion Constraints：排他约束

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 159 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:159)。

**1. 原文**：`排除约束`

**建议**：`排他约束`

落点：

- [templates/pages/about/press/presskit17/zh.html:18](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit17/zh.html:18) — `实例的数据处理能力。PostgreSQL 17 现已支持在分区表上使用身份列与排除约束。用于在远程 PostgreSQL 实例上执行查询的 PostgreSQL 外部数据包装器</`
- [data/featurematrix_zh.yaml:150](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:150) — `name: 排除约束`

## T05 · Operator：操作符

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 349 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:349)。

**1. 原文**：`运算符`

**建议**：`操作符`

落点：

- [templates/pages/about/press/presskit12/zh.html:23](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit12/zh.html:23) — `他索引增强，进一步改善整体性能，包括降低 GiST、GIN 和 SP-GiST 索引类型生成预写式日志（WAL）的开销，支持在 GiST 索引上创建覆盖索引（INCLUDE 子句），支持使用距离运算符（<->）对 SP-GiST 索引执行 K 最近邻查询，以及让 CREATE STATISTICS 现在支持最常见值（MCV）统计，从而帮助在列分布不均匀时`
- [data/featurematrix_zh.yaml:3](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:3) — `Data Types, Functions, & Operators: 数据类型、函数和运算符`
- [data/featurematrix_zh.yaml:151](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:151) — `description: 将唯一性概念推广为支持任何可索引的交换运算符，而不仅限于等值运算符`
- [data/featurematrix_zh.yaml:184](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:184) — `description: 新增对 SP-GiST 索引上 K-最近邻 (K-NN) 搜索的支持，前提是定义了距离运算符 ''。`
- [data/featurematrix_zh.yaml:530](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:530) — `name: 改进的 JSON 函数和运算符集`
- [data/featurematrix_zh.yaml:531](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:531) — `description: 新增了从 JSON 数据字符串中提取值的运算符和函数，JSON 数据字符串现在可以转换为记录，并新增了将值、记录和 hstore 数据转换为 JSON 的函数。`
- [data/featurematrix_zh.yaml:536](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:536) — `name: JSONB 修改运算符和函数`
- [data/featurematrix_zh.yaml:537](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:537) — `description: 新增了允许删除、修改或向 JSONB 值中插入值的运算符和函数，包括在特定路径位置进行操作。`
- [data/featurematrix_zh.yaml:964](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:964) — `description: 能够在 postgres_fdw 驱动中将 JOIN、排序、UPDATE 和 DELETE 下推到远程数据库，理论上其他驱动也支持。同时支持一些通用的运算符/函数下推。`

## T06 · Most Common Values / MCV：高频值

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 309 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:309)；[术语表第 319 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:319)。

**1. 原文**：`最常用值`

**建议**：`高频值`

落点：

- [data/featurematrix_zh.yaml:366](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:366) — `name: CREATE STATISTICS - 最常用值 (MCV) 统计信息`
- [data/featurematrix_zh.yaml:367](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:367) — `description: CREATE STATISTICS 可以收集最常用值的统计信息，从而改善对包含非均匀分布的列的优化。`

**2. 原文**：`最常见值`

**建议**：`高频值`

落点：

- [templates/pages/about/press/presskit12/zh.html:23](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit12/zh.html:23) — `UDE 子句），支持使用距离运算符（<->）对 SP-GiST 索引执行 K 最近邻查询，以及让 CREATE STATISTICS 现在支持最常见值（MCV）统计，从而帮助在列分布不均匀时生成更好的查询计划。`

## T07 · HOT：堆内元组

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 231 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:231)。

**1. 原文**：`仅堆元组`

**建议**：`堆内元组`

落点：

- [data/featurematrix_zh.yaml:410](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:410) — `name: 仅堆元组 (HOT)`

## T08 · Merge Join：归并连接

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 311 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:311)。

**1. 原文**：`合并连接`

**建议**：`归并连接`

落点：

- [templates/pages/about/press/presskit18/zh.html:20](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit18/zh.html:20) — `HERE 子句中包含 OR 条件的查询，使其更好地利用索引，从而显著缩短执行时间。PostgreSQL 18 还在表连接的规划与执行方面做出多项改进，包括提升哈希连接性能，以及允许合并连接使用增量排序等。此外，GIN 索引现在也支持并行构建，与 B-树和 <a href="https://w`
- [data/featurematrix_zh.yaml:466](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:466) — `name: 并行合并连接`
- [data/featurematrix_zh.yaml:467](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:467) — `description: 合并连接可以并行执行。`

## T09 · Partition pruning：分区剪枝

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 381 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:381)。

**1. 原文**：`分区裁剪`

**建议**：`分区剪枝`

落点：

- [data/featurematrix_zh.yaml:563](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:563) — `name: 加速分区裁剪`
- [data/featurematrix_zh.yaml:580](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:580) — `name: 查询执行期间的分区裁剪`

**2. 原文**：`分区消除`

**建议**：`分区剪枝`

落点：

- [templates/pages/about/press/presskit11/cn.html:24](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit11/cn.html:24) — `PostgreSQL 11 版本通过使用新的分区消除策略来提升查询分区表的性能。另外，PostgreSQL 11 现在在分区表上也支持流行的“UPSERT”功能，这可以帮助用户在处理应用数据时，简化应用程序的开发，减少网络负载。`

**3. 原文**：`修剪分区`

**建议**：`对分区剪枝`

落点：

- [templates/pages/about/press/presskit13/zh.html:38](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit13/zh.html:38) — `查询不必完全放在内存中。带有分区表的查询性能得到了提高，因为现在有更多情况可以修剪分区并且可以直接连接分区。`

## T10 · Identity column：标识列

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 239 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:239)。

**1. 原文**：`身份列`

**建议**：`标识列`

落点：

- [templates/pages/about/press/presskit17/zh.html:18](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit17/zh.html:18) — `SQL 实例的数据处理能力。PostgreSQL 17 现已支持在分区表上使用身份列与排除约束。用于在远程 PostgreSQL 实例上执行查询的 PostgreSQL 外部数据`

## T11 · WAL 与 full-page write：预写式日志、整页写入

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 630 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:630)；[术语表第 201 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:201)。

**1. 原文**：`预写日志`

**建议**：`预写式日志`

落点：

- [templates/pages/about/press/presskit14/zh.html:45](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit14/zh.html:45) — `ode> 命令的进度、预写日志（WAL）活动和<a href="https://www.postgresql.org/docs/14/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-S`
- [data/featurematrix_zh.yaml:211](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:211) — `description: 哈希索引具有预写日志支持，这使其既具备崩溃安全性，又可进行复制。`

**2. 原文**：`全页写`

**建议**：`整页写入`

落点：

- [data/featurematrix_zh.yaml:693](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:693) — `name: WAL 全页写的 lz4 与 Zstandard (zstd) 压缩`

## T12 · Visibility map：可见性映射

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 609 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:609)。

说明：这条描述还存在方向相反的技术表述，见 C11。若同时确认，应合并处理同一段落。

**1. 原文**：`可见性图`

**建议**：`可见性映射`

落点：

- [data/featurematrix_zh.yaml:931](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:931) — `name: 用于 Vacuuming 的可见性图`
- [data/featurematrix_zh.yaml:932](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:932) — `description: 这减少了 vacuum 的开销，因为可见性图只跟踪需要被 vacuum 的页面。`

## T13 · Autovacuum：自动清理

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 26 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:26)；[术语表第 27 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:27)。

说明：独立命令名 VACUUM、工具名 vacuumdb 和参数名均保留；不对它们做全局汉化。

**1. 原文**：`自动 vacuum`

**建议**：`自动清理`

落点：

- [data/featurematrix_zh.yaml:907](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:907) — `name: 插入的数据可触发自动 vacuum`
- [data/featurematrix_zh.yaml:910](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:910) — `name: 集成自动 vacuum 守护进程`

## T14 · Serializable snapshot isolation：可串行化快照隔离

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 488 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:488)；[术语表第 489 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:489)。

**1. 原文**：`可串行快照隔离`

**建议**：`可串行化快照隔离`

落点：

- [data/featurematrix_zh.yaml:898](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:898) — `name: 可串行快照隔离`
- [data/featurematrix_zh.yaml:899](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:899) — `description: 实现了真正的可串行快照隔离。此前，请求可串行隔离级别仅保证在整个事务中使用单个 MVCC 快照，这允许某些已知的异常现象发生。`

**2. 原文**：`可串行隔离级别`

**建议**：`可串行化隔离级别`

落点：

- [data/featurematrix_zh.yaml:899](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:899) — `description: 实现了真正的可串行快照隔离。此前，请求可串行隔离级别仅保证在整个事务中使用单个 MVCC 快照，这允许某些已知的异常现象发生。`

**3. 原文**：`可串行化的快照隔离`

**建议**：`可串行化快照隔离`

落点：

- [templates/pages/about/press/presskit91/zh_cn.html:43](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:43) — `可串行化的快照隔离: 使用”真正的可串行化“，确保并行事务的一致性。`
- [templates/pages/about/press/presskit91/zh_cn.html:82](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:82) — `可串行化的快照隔离: 通过在事务运行时自动侦测已使用的冲突条件来允许用户强制多次地执行复杂的用户自定义的商业规则而不会有阻隔。这个功能目前也是仅 PostgreSQL 具有。`

## T15 · 逻辑复制说明中的 publication / schema：发布／模式

**待确认 · 建议修改**

这里指数据库对象，而不是 SQL 命令中的关键字。 依据：[publication：发布](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:418)；[schema：模式](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:472)。

**1. 原文**：`publication`

**建议**：`发布`

落点：

- [data/featurematrix_zh.yaml:626](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:626) — `description: 逻辑复制中的 publication 现在可以指定要发布的列列表，以往必须复制整行。`
- [data/featurematrix_zh.yaml:645](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:645) — `description: 创建 publication 时，现在可以指定发布某个 schema 下的全部表。`

**2. 原文**：`schema`

**建议**：`模式`

落点：

- [data/featurematrix_zh.yaml:644](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:644) — `name: 逻辑复制发布 schema 中的全部表`
- [data/featurematrix_zh.yaml:645](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:645) — `description: 创建 publication 时，现在可以指定发布某个 schema 下的全部表。`

## T16 · 复制语境：主库、备库、从库

**待确认 · 建议修改**

按 primary / standby / slave 的原文区别统一，不把副本或多节点系统一律替换成备库。 依据：[primary：主库](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:410)；[standby：备库](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:523)；[slave：从库](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:507)。

**1. 原文**：`备用服务器`

**建议**：`备库`

落点：

- [data/featurematrix_zh.yaml:613](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:613) — `description: 备用服务器现在可以向其他备用服务器进行流式传输，减少主服务器的复制负载。`
- [data/featurematrix_zh.yaml:662](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:662) — `description: 使用 synchronous_standby_names 配置参数，可以设置同步复制以允许任意数量的备用服务器确认写入已提交，而不考虑其顺序。这也被称为“仲裁提交”。`
- [data/featurematrix_zh.yaml:668](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:668) — `description: 级联复制以前要求 xlog 归档可用，以便新主服务器的备用服务器正确切换到新时间线。此更改移除了这一依赖。`
- [data/featurematrix_zh.yaml:674](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:674) — `description: 允许主服务器在确认提交之前等待备用服务器将事务信息写入磁盘。通过 synchronous_standby_names 设置控制，一次可以有一个备用服务器担任同步备用服务器的角色。可以使用 synchronous_commit 设置按事务启用或禁用同步复制。`
- [data/featurematrix_zh.yaml:701](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:701) — `name: 多个同步备用服务器`
- [data/featurematrix_zh.yaml:702](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:702) — `description: 在提交同步事务时，能够要求多个优先级备用服务器确认同步消息。`
- [data/featurematrix_zh.yaml:739](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:739) — `name: 延迟备用服务器`
- [data/featurematrix_zh.yaml:740](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:740) — `description: 一个名为 recovery_min_apply_delay 的新设置允许备用服务器按指定的时间量落后于主服务器。`

**2. 原文**：`主服务器`

**建议**：`主库`

落点：

- [data/featurematrix_zh.yaml:613](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:613) — `description: 备用服务器现在可以向其他备用服务器进行流式传输，减少主服务器的复制负载。`
- [data/featurematrix_zh.yaml:668](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:668) — `description: 级联复制以前要求 xlog 归档可用，以便新主服务器的备用服务器正确切换到新时间线。此更改移除了这一依赖。`
- [data/featurematrix_zh.yaml:674](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:674) — `description: 允许主服务器在确认提交之前等待备用服务器将事务信息写入磁盘。通过 synchronous_standby_names 设置控制，一次可以有一个备用服务器担任同步备用服务器的角色。可以使用 synchronous_commit 设置按`
- [data/featurematrix_zh.yaml:737](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:737) — `description: 能够要求同步副本在提交之前与主服务器保持应用变更的同步。支持“一致性集群”。`
- [data/featurematrix_zh.yaml:740](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:740) — `description: 一个名为 recovery_min_apply_delay 的新设置允许备用服务器按指定的时间量落后于主服务器。`

**3. 原文**：`复制从属服务器`

**建议**：`从库`

落点：

- [data/featurematrix_zh.yaml:525](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:525) — `description: 此类表比普通表提供更好的更新性能，但不具有崩溃安全性：在服务器崩溃时其内容会自动清除。其内容也不会传播到复制从属服务器。`

**4. 原文**：`备节点`

**建议**：`备库`

落点：

- [templates/pages/about/press/presskit16/zh.html:13](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit16/zh.html:13) — `g/docs/16/logical-replication.html">逻辑复制允许用户将数据流复制到其他可以解析 PostgreSQL 逻辑复制协议的节点或订阅者。在 PostgreSQL 16 中，用户可以从备节点（standby）执行逻辑复制，这意味着备节点可以将逻辑变更发布到其他服务器。这为开发者提供了新的工作负载分布选项——例如，使用备节点而不是更繁忙的主节点通过逻辑复制将更改应用到下级订阅端。`
- [templates/pages/about/press/presskit16/zh.html:13](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit16/zh.html:13) — `cation.html">逻辑复制允许用户将数据流复制到其他可以解析 PostgreSQL 逻辑复制协议的节点或订阅者。在 PostgreSQL 16 中，用户可以从备节点（standby）执行逻辑复制，这意味着备节点可以将逻辑变更发布到其他服务器。这为开发者提供了新的工作负载分布选项——例如，使用备节点而不是更繁忙的主节点通过逻辑复制将更改应用到下级订阅端。`
- [templates/pages/about/press/presskit16/zh.html:13](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit16/zh.html:13) — `reSQL 逻辑复制协议的节点或订阅者。在 PostgreSQL 16 中，用户可以从备节点（standby）执行逻辑复制，这意味着备节点可以将逻辑变更发布到其他服务器。这为开发者提供了新的工作负载分布选项——例如，使用备节点而不是更繁忙的主节点通过逻辑复制将更改应用到下级订阅端。`

**5. 原文**：`主节点`

**建议**：`主库`

落点：

- [templates/pages/about/press/presskit16/zh.html:13](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit16/zh.html:13) — `协议的节点或订阅者。在 PostgreSQL 16 中，用户可以从备节点（standby）执行逻辑复制，这意味着备节点可以将逻辑变更发布到其他服务器。这为开发者提供了新的工作负载分布选项——例如，使用备节点而不是更繁忙的主节点通过逻辑复制将更改应用到下级订阅端。`

## T17 · 数据库集簇与高可用集群分开使用

**待确认 · 建议修改**

仅列出对应单个 PostgreSQL 安装、数据目录或升级对象的 cluster；多节点集群保留原词。 依据：[database cluster：数据库集簇](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:122)。

**1. 原文**：`集群`

**建议**：`集簇`

落点：

- [data/featurematrix_zh.yaml:679](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:679) — `description: 现在可以在创建集群时对页面启用校验和，以检测和报告页面损坏。`
- [data/featurematrix_zh.yaml:681](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:681) — `name: 在离线集群中启用/禁用页面校验和`
- [data/featurematrix_zh.yaml:682](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:682) — `description: '可以通过 pg_checksums 命令在离线 PostgreSQL 集群中启用或禁用页面校验和：`
- [data/featurematrix_zh.yaml:723](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:723) — `description: pg_basebackup 是一个用于对 PostgreSQL 集群进行基础备份的工具`
- [data/featurematrix_zh.yaml:749](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:749) — `description: ''--swap' 选项会把旧集群的数据目录直接交换到新集群，并用新版本生成的目录元数据替换之。'`
- [data/featurematrix_zh.yaml:752](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:752) — `description: 主版本升级后会保留规划器统计信息，使集群在升级完成后更快恢复预期性能。`
- [data/featurematrix_zh.yaml:1112](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:1112) — `name: 集群/数据库的默认 ICU 排序规则`
- [data/featurematrix_zh.yaml:1113](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:1113) — `description: ICU 排序规则现在可以作为整个 PostgreSQL 集群或单个数据库的默认排序规则类型。`
- [data/featurematrix_zh.yaml:1163](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:1163) — `description: 以人类可读的格式显示 PostgreSQL 数据库集群的预写式日志。`

**2. 原文**：`数据库集群（database clusters）`

**建议**：`数据库集簇（database clusters）`

落点：

- [templates/pages/about/press/presskit10/cn.html:53](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:53) — `有的 PostgreSQL 复制特性进行了扩展，新版本的逻辑复制可以将单个数据库级别或者表级别的改动（modifications）发送至不同的 PostgreSQL 数据库。这意味着用户可以细粒度地将数据变化发送到不同的数据库集群（database clusters），甚至在大版本升级期间，实现零停机（zero-downtime）。`

## T18 · 规划器 Cost：代价

**待确认 · 建议修改**

这两处指规划器参数含义；普通性能开销与商业成本不做替换。 依据：[Cost：代价](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:111)。

**1. 原文**：`为 TABLESPACE 设置特定成本`

**建议**：`为表空间设置特定代价`

落点：

- [data/featurematrix_zh.yaml:500](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:500) — `name: 为 TABLESPACE 设置特定成本`

**2. 原文**：`CPU 成本`

**建议**：`CPU 代价`

落点：

- [data/featurematrix_zh.yaml:1076](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:1076) — `description: 现在可以为过程函数指定 CPU 成本和预期行数，以向规划器提供更好的提示`

## T19 · 后端概述：词元与聚合

**待确认 · 建议修改**

语法分析中的 token 与 SQL aggregate 有固定译名。 依据：[Token：词元](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:563)；[aggregate：聚合](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:12)。

**1. 原文**：`记号`

**建议**：`词元`

落点：

- [templates/pages/developer/backend.html:47](/Users/vonng/pgsty/pgweb/templates/pages/developer/backend.html:47) — `将查询分解为记号（token）。解析器使用 <a`
- [templates/pages/developer/backend.html:49](/Users/vonng/pgsty/pgweb/templates/pages/developer/backend.html:49) — `和这些记号来识别查询类型，并加载相应的查询特定结构，如 <a`

**2. 原文**：`聚集`

**建议**：`聚合`

落点：

- [templates/pages/developer/backend.html:72](/Users/vonng/pgsty/pgweb/templates/pages/developer/backend.html:72) — `其他查询元素，如聚集（SUM()）、GROUP`

## T20 · 可伸缩性与可扩展性按语义区分

**待确认 · 建议修改**

9.2 的性能段与 17 的开篇对应 scalability；扩展框架、用户定义类型等 extensibility 语境保留“可扩展性”。 依据：[scalability：可伸缩性](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:471)；[PostgreSQL 9.2 英文新闻资料包](https://www.postgresql.org/about/press/presskit92/)；[PostgreSQL 17 英文新闻资料包](https://www.postgresql.org/about/press/presskit17/)。

**1. 原文**：`可扩展性`

**建议**：`可伸缩性`

落点：

- [templates/pages/about/press/presskit92/zh_CN.html:23](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:23) — `2012/09/10: PostgreSQL 全球开发组宣布业界领先的开源关系数据库 PostgreSQL 9.2 版发布，由于 Beta 测试版本在 5 月即已发布，开发人员和软件厂商称赞该版本在性能、可扩展性和灵活性方面得到大的提升。大量的用户期待切换至新的版本。`
- [templates/pages/about/press/presskit92/zh_CN.html:30](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:30) — `性能提升和可扩展性`
- [templates/pages/about/press/presskit92/zh_CN.html:33](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:33) — `垂直可扩展性的提升增加了 PostgreSQL 在大型服务器上有效利用硬件资源的能力，高级锁的管理、写性能、索引扫描以及其他对硬件的底层操作允许 PostgreSQL 处理海量负载，从数据上与 PostgreSQL 9.1 版本对比`
- [data/page_metadata.yaml:3507](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:3507) — `/about/press/presskit92/zh_CN/ / description: 2012/09/10: PostgreSQL 全球开发组宣布业界领先的开源关系数据库 PostgreSQL 9.2 版发布，由于 Beta 测试版本在 5 月即已发布，开发人员和软件厂商称赞该版本在性能、可扩展性和灵活性方面得到大的提升。大量的用户期待切换至新的版本。`

**2. 原文**：`进一步提升了性能与可扩展性`

**建议**：`进一步提升了性能与可伸缩性`

落点：

- [templates/pages/about/press/presskit17/zh.html:6](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit17/zh.html:6) — `PostgreSQL 17 建立在数十年的开源开发积累之上，在继续适应新兴数据访问与存储模式的同时，进一步提升了性能与可扩展性。这个版本的 PostgreSQL 带来了显著的整体性能提升，包括重构后的 vacuum 内存管理实现、面向高并发工作负载的存储访问优化、`

## T21 · Trusted extension：受信任的扩展

**待确认 · 建议修改**

扩展详情与特性矩阵统一。PG13 历史资料包中的病句单列在 C21，避免重叠修改。 依据：[trusted：受信任的](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:578)。

**1. 原文**：`可信扩展`

**建议**：`受信任的扩展`

落点：

- [pgweb/ext/views.py:188](/Users/vonng/pgsty/pgweb/pgweb/ext/views.py:188) — `for field, label in (('need_load', ('需要显式加载', 'Requires loading')), ('trusted', ('可信扩展', 'Trusted extension')), ('relocatable', ('可迁移模式', 'Relocatable'))):`

## T22 · 最近邻索引用词

**待确认 · 建议修改**

术语表使用“最近邻搜索”；同一技术在新闻资料包中写为“最近相邻”，建议派生用语统一为“最近邻索引”。 依据：[Nearest Neighbor Search：最近邻搜索](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:329)；[Foreign Data Wrapper：外部数据包装器](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:186)。

**1. 原文**：`最近相邻索引`

**建议**：`最近邻索引`

落点：

- [templates/pages/about/press/presskit91/zh_cn.html:23](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:23) — `2011/09/12: PostgreSQL 全球开发组宣布业界领先的开源关系数据库 PostgreSQL 9.1 版发布，该版本增加了很多创新性的技术、强大的可扩展性以及类似同步复制、最近相邻索引和外部数据封装等功能。`
- [templates/pages/about/press/presskit91/zh_cn.html:42](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:42) — `最近相邻索引技术: 索引是按照”距离“来达到在查询中快速定位和文字搜索。`
- [data/page_metadata.yaml:3210](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:3210) — `/about/press/presskit91/zh_cn/ / description: 2011/09/12: PostgreSQL 全球开发组宣布业界领先的开源关系数据库 PostgreSQL 9.1 版发布，该版本增加了很多创新性的技术、强大的可扩展性以及类似同步复制、最近相邻索引和外部数据封装等功能。`

**2. 原文**：`外部数据封装`

**建议**：`外部数据包装器`

落点：

- [templates/pages/about/press/presskit91/zh_cn.html:23](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:23) — `2011/09/12: PostgreSQL 全球开发组宣布业界领先的开源关系数据库 PostgreSQL 9.1 版发布，该版本增加了很多创新性的技术、强大的可扩展性以及类似同步复制、最近相邻索引和外部数据封装等功能。`
- [data/page_metadata.yaml:3210](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:3210) — `/about/press/presskit91/zh_cn/ / description: 2011/09/12: PostgreSQL 全球开发组宣布业界领先的开源关系数据库 PostgreSQL 9.1 版发布，该版本增加了很多创新性的技术、强大的可扩展性以及类似同步复制、最近相邻索引和外部数据封装等功能。`

## T23 · 生成列的复合名称

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 206 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:206)。

说明：不强制统一“存储型生成列”与“存储生成列”两种都清楚的自然表述。

**1. 原文**：`存储生成的列`

**建议**：`存储生成列`

落点：

- [data/featurematrix_zh.yaml:334](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:334) — `name: 存储生成的列`

## T24 · Index-only scan：仅索引扫描

**待确认 · 建议修改**

9.2 历史性能列表的术语口径；不调整当年的性能数字。 依据：[index-only scan：仅索引扫描](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:254)。

**1. 原文**：`只使用索引扫描`

**建议**：`使用仅索引扫描`

落点：

- [templates/pages/about/press/presskit92/zh_CN.html:38](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:38) — `数据仓库中只使用索引扫描的查询（最高可比以前快 20 倍）`

## T25 · Foreign key：外键

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 187 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:187)。

**1. 原文**：`外部键`

**建议**：`外键`

落点：

- [data/featurematrix_zh.yaml:572](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:572) — `name: 分区表的外部键引用`
- [data/featurematrix_zh.yaml:573](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:573) — `description: 外部键可以引用分区表。`

## T26 · 事务 ID 回卷

**待确认 · 建议修改**

与指定术语表保持一致。 依据：[术语表第 571 行](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:571)。

**1. 原文**：`事务 ID 环绕`

**建议**：`事务 ID 回卷`

落点：

- [templates/pages/about/press/presskit14/zh.html:39](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit14/zh.html:39) — `//www.postgresql.org/docs/14/routine-vacuuming.html">vacuum 系统，包括减少 B-树索引开销的优化。此版本还添加了 vacuum 的“紧急模式”，用于防止事务 ID 环绕。ANALYZE 用于收集数据库统计信息，基于自身的性能改进，`
