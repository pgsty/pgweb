# 明确误译与有限润色

本文件仅供 Review，所有条目均待确认；页面源文件和数据库均未改动。

返回 [总览](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/REVIEW.md)。

| 编号 | 候选项目 | 判断 |
| --- | --- | --- |
| C01 | 简介页：数据与工作负载的搭配 | 建议修改 |
| C02 | 媒体 FAQ：四处明确的直译或歧义 | 建议修改 |
| C03 | Linux 下载页：发行版“快照”一个版本 | 建议修改 |
| C04 | 专业服务地区页：注册地与服务地区 | 建议修改 |
| C05 | 复制槽的 WAL 限制是保留量 | 建议修改 |
| C06 | Windows Port：移植版 | 建议修改 |
| C07 | GIN：广义倒排索引 | 建议修改 |
| C08 | 分区键更新：修正主宾关系 | 建议修改 |
| C09 | COPY：输入输出方向 | 建议修改 |
| C10 | 受信任扩展：纠正函数与扩展混淆 | 建议修改 |
| C11 | 可见性映射：纠正描述方向 | 建议修改 |
| C12 | Unicode literal：字符串字面量 | 建议修改 |
| C13 | auto_explain：模块名拼写 | 建议修改 |
| C14 | PostgreSQL 12：空间优化的方向 | 建议修改 |
| C15 | PostgreSQL 11：默认分区条件 | 建议修改 |
| C16 | PostgreSQL 11：INCLUDE 与仅索引扫描 | 建议修改 |
| C17 | PostgreSQL 11：连接与 JIT 表述 | 建议修改 |
| C18 | PostgreSQL 14：拆开 postgres_fdw 的两项能力 | 建议修改 |
| C19 | PostgreSQL 15：默认权限变化 | 建议修改 |
| C20 | PostgreSQL 18：值不限定为数值 | 建议修改 |
| C21 | PostgreSQL 13：受信任扩展段的病句与引号 | 建议修改 |
| C22 | PostgreSQL 9.1：Heroku 与 salesforce.com 的归属关系 | 建议修改 |
| C23 | PostgreSQL 9.1：三处明确的误译／错字 | 建议修改 |
| C24 | PostgreSQL 10：商业伙伴错字 | 建议修改 |
| C25 | PostgreSQL 9.0：RADIUS 认证 | 建议修改 |
| C26 | 服务收录政策：word 不应换算为“字” | 建议修改 |
| C27 | 扩展属性 relocatable：说明可以迁移什么 | 建议修改 |
| C28 | 关于本站：上游入口说明 | 建议修改 |
| C29 | 提交预览：说明撤回后仍可修改 | 建议修改 |
| C30 | 账户邮箱提示：解释实际影响 | 建议修改 |
| C31 | UNLOGGED 与导入表定义的表述 | 建议修改 |
| C32 | 资金小组章程：附议主语与辩论期限 | 建议修改，政策语句请单独核对 |
| C33 | 网站团队与网络团队 | 建议修改 |

原文与建议以可见文字为主；模板变量、链接和源字符串的完整记录保存在 review.json。行号以本次审阅基线为准。

## C01 · 简介页：数据与工作负载的搭配

**待确认 · 建议修改**

“存储工作负载”搭配不当；保留原句的存储能力与扩展能力两层含义。 依据：[上游项目简介](https://www.postgresql.org/about/)。

**1. 原文**：`能够安全地存储和扩展最复杂的数据工作负载`

**建议**：`能够安全地存储数据，并灵活扩展以应对最复杂的数据工作负载`

落点：

- [templates/core/about.html:8](/Users/vonng/pgsty/pgweb/templates/core/about.html:8) — `PostgreSQL 是一个强大的开源对象关系型数据库系统。它使用并扩展了 SQL 语言，并结合了大量功能，能够安全地存储和扩展最复杂的数据工作负载。PostgreSQL 的起源可以追溯到 1986 年，当时它还是加州大学伯克利分校 POSTGRES 项目的一部分；其核心代码库至今已持`

## C02 · 媒体 FAQ：四处明确的直译或歧义

**待确认 · 建议修改**

只调整不自然的搭配与误译，不改其余已校对正文。 依据：[上游媒体 FAQ](https://www.postgresql.org/about/press/faq/)。

**1. 原文**：`以共同的礼貌和共同的利益行事`

**建议**：`以礼相待，维护共同利益`

落点：

- [templates/pages/about/press/faq.html:11](/Users/vonng/pgsty/pgweb/templates/pages/about/press/faq.html:11) — `答：PostgreSQL 项目以代码质量和工作成果以及社区的技术和专业成就为荣。我们期望每位参与者都以专业的方式行事，以共同的礼貌和共同的利益行事，尊重所有用户和开发者。为此，我们制定了行为准则，用于规范社区互动和项目工作及社区整体参与。`

**2. 原文**：`前两位小数代表主要版本`

**建议**：`版本号的前两部分代表主要版本`

落点：

- [templates/pages/about/press/faq.html:22](/Users/vonng/pgsty/pgweb/templates/pages/about/press/faq.html:22) — `答：因为我们项目历史悠久，前两位小数代表主要版本。因此 9.6、9.5 等都是主要版本。次要版本的编号类似于 9.6.6。从版本 10 开始，项目采用了两部分版本编号方案。`

**3. 原文**：`由于我们通过开源世界的广泛分发和宽松的许可证，很难准确回答这个问题。`

**建议**：`由于 PostgreSQL 通过开源渠道广泛分发，且采用宽松许可证，很难准确统计用户数量。`

落点：

- [templates/pages/about/press/faq.html:34](/Users/vonng/pgsty/pgweb/templates/pages/about/press/faq.html:34) — `答：由于我们通过开源世界的广泛分发和宽松的许可证，很难准确回答这个问题。大多数用户通过 Linux 发行版获取 PostgreSQL，或者通过包含 PostgreSQL 的许多其他产品、开源软件和硬件设备获取。许多指标，如 <a href="https://db-engines.com/en`

**4. 原文**：`功能和特性的高级概述`

**建议**：`功能和特性概览`

落点：

- [templates/pages/about/press/faq.html:49](/Users/vonng/pgsty/pgweb/templates/pages/about/press/faq.html:49) — `可证，由 Oracle 拥有。除此之外，每位数据库用户都应做出自己的评估；开源软件使得进行比较非常容易。我们建议您查看关于 PostgreSQL 页面上 PostgreSQL 功能和特性的高级概述。`

## C03 · Linux 下载页：发行版“快照”一个版本

**待确认 · 建议修改**

这里是发行版选定所提供的 PostgreSQL 版本，不是数据库快照操作。

**1. 原文**：`会“快照”一个特定版本的 PostgreSQL`

**建议**：`会选定一个 PostgreSQL 版本`

落点：

- [templates/pages/download/linux/debian.html:10](/Users/vonng/pgsty/pgweb/templates/pages/download/linux/debian.html:10) — `所有 Debian 版本默认都包含 PostgreSQL。但是，Debian 会“快照”一个特定版本的 PostgreSQL，该版本在 Debian 版本的整个生命周期内受到支持。PostgreSQL 项目维护了一个 Apt 仓库，提供所有受支持的 PostgreSQL 版本。`
- [templates/pages/download/linux/ubuntu.html:10](/Users/vonng/pgsty/pgweb/templates/pages/download/linux/ubuntu.html:10) — `所有 Ubuntu 版本默认都提供 PostgreSQL。但是，Ubuntu 会“快照”一个特定版本的 PostgreSQL，并在该 Ubuntu 版本的整个生命周期内提供支持。PostgreSQL 项目维护了一个 Apt 仓库，提供所有受支持的 PostgreSQL 版本。`
- [templates/pages/download/linux/suse.html:7](/Users/vonng/pgsty/pgweb/templates/pages/download/linux/suse.html:7) — `所有 SUSE 版本默认都提供 PostgreSQL。但是，SUSE Linux 会“快照”一个特定版本的 PostgreSQL，并在该 SUSE 版本的整个生命周期内提供支持。`

**2. 原文**：`每个版本的平台通常会“快照”一个特定版本的 PostgreSQL`

**建议**：`各发行版版本通常会选定一个 PostgreSQL 版本`

落点：

- [templates/pages/download/linux/redhat.html:22](/Users/vonng/pgsty/pgweb/templates/pages/download/linux/redhat.html:22) — `这些平台默认提供 PostgreSQL。但是，每个版本的平台通常会“快照”一个特定版本的 PostgreSQL，并在该平台的整个生命周期内提供支持。由于这通常意味着提供的版本并非用户所需，PostgreSQL`

## C04 · 专业服务地区页：注册地与服务地区

**待确认 · 建议修改**

视图按服务覆盖地区筛选，当前句子会被理解为公司法定注册地。 依据：[地区筛选来源](/Users/vonng/pgsty/pgweb/pgweb/profserv/views.py:38)。

**1. 原文**：`以下{{whatname}}在{{regionname}}注册。`

**建议**：`以下公司在{{regionname}}提供{{whatname}}。`

落点：

- [templates/profserv/list.html:5](/Users/vonng/pgsty/pgweb/templates/profserv/list.html:5) — `以下{{whatname}}在{{regionname}}注册。`

## C05 · 复制槽的 WAL 限制是保留量

**待确认 · 建议修改**

max_slot_wal_keep_size 限制的是 WAL 文件总大小，默认单位为 MB；不是时间，也不是文件个数。 依据：[复制配置参数 max_slot_wal_keep_size](https://www.postgresql.org/docs/18/runtime-config-replication.html#GUC-MAX-SLOT-WAL-KEEP-SIZE)。

**1. 原文**：`配置复制槽的最大 WAL 保持时间`

**建议**：`配置复制槽的最大 WAL 保留量`

落点：

- [data/featurematrix_zh.yaml:615](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:615) — `name: 配置复制槽的最大 WAL 保持时间`

**2. 原文**：`要保留的 WAL 文件的最大数量`

**建议**：`WAL 文件的最大保留量`

落点：

- [templates/pages/about/press/presskit13/zh.html:52](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit13/zh.html:52) — `行调整以指定要保留的 WAL 文件的最大数量，并有助于避免磁盘空间不足的错误。`

## C06 · Windows Port：移植版

**待确认 · 建议修改**

此处 port 指平台移植；该条目的现有 description 已经正确说明“原生移植到 Microsoft Windows 平台”。

**1. 原文**：`原生 Windows 端口`

**建议**：`Windows 原生移植版`

落点：

- [data/featurematrix_zh.yaml:1300](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:1300) — `name: 原生 Windows 端口`

## C07 · GIN：广义倒排索引

**待确认 · 建议修改**

Inverted Index 在该索引技术语境中是倒排索引，“反向索引”容易产生歧义。 依据：[GIN 索引原理](https://www.postgresql.org/docs/18/gin.html)。

**1. 原文**：`GIN (广义反向索引) 索引`

**建议**：`GIN（广义倒排索引）`

落点：

- [data/featurematrix_zh.yaml:153](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:153) — `name: GIN (广义反向索引) 索引`

## C08 · 分区键更新：修正主宾关系

**待确认 · 建议修改**

被更新的是行的分区键，“分区键上的行”关系颠倒。

**1. 原文**：`当分区键上的行被更新时`

**建议**：`当行的分区键被更新时`

落点：

- [data/featurematrix_zh.yaml:589](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:589) — `description: 当分区键上的行被更新时，该行会被移动到相应的分区。`

## C09 · COPY：输入输出方向

**待确认 · 建议修改**

英文条目是 from/to STDIN/STDOUT，现有中文标题把方向反过来了。现有 description 的方向是正确的。

**1. 原文**：`COPY 到/从 STDIN/STDOUT`

**建议**：`COPY 从 STDIN 导入／向 STDOUT 导出`

落点：

- [data/featurematrix_zh.yaml:754](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:754) — `name: COPY 到/从 STDIN/STDOUT`

## C10 · 受信任扩展：纠正函数与扩展混淆

**待确认 · 建议修改**

当前说明误将部分内置扩展写成“某些函数”；同时说明安装者仍需当前数据库的 CREATE 权限。这是对技术含义的订正。 依据：[PostgreSQL 扩展打包与 trusted 属性](https://www.postgresql.org/docs/18/extend-extensions.html)。

**1. 原文**：`被超级用户标记为"受信任"的扩展随后可以由非特权用户通过 'CREATE EXTENSION' 安装。某些函数默认标记为"受信任"。 更多信息请参阅 ['CREATE EXTENSION'](https://www.postgresql.org/docs/current/sql-createextension.html) 文档。`

**建议**：`标记为“受信任”的扩展可由对当前数据库具有 CREATE 权限的非超级用户通过 'CREATE EXTENSION' 安装。某些内置扩展默认标记为“受信任”。 更多信息请参阅 ['CREATE EXTENSION'](https://www.postgresql.org/docs/current/sql-createextension.html) 文档。`

落点：

- [data/featurematrix_zh.yaml:1099](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:1099) — `Trusted Extensions / description`

## C11 · 可见性映射：纠正描述方向

**待确认 · 建议修改**

可见性映射记录全可见／全冻结状态，清理可据此跳过不必扫描的页面。原句把记录方向反过来了；英文特性矩阵本身也有该问题，属于继承的技术内容问题。 依据：[Visibility Map](https://www.postgresql.org/docs/18/storage-vm.html)；[英文特性矩阵](/Users/vonng/pgsty/pgweb/data/featurematrix.yaml:1411)。

说明：若确认 T12 与本条，直接采用本条完整描述；不在同一字符串上重复替换。

**1. 原文**：`用于 Vacuuming 的可见性图`

**建议**：`清理使用的可见性映射`

落点：

- [data/featurematrix_zh.yaml:931](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:931) — `Visibility Map for Vacuuming / name`

**2. 原文**：`这减少了 vacuum 的开销，因为可见性图只跟踪需要被 vacuum 的页面。`

**建议**：`可见性映射记录页面的全可见状态，使 VACUUM 能够跳过无需扫描的页面，从而减少清理开销。`

落点：

- [data/featurematrix_zh.yaml:932](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:932) — `Visibility Map for Vacuuming / description`

## C12 · Unicode literal：字符串字面量

**待确认 · 建议修改**

literal 不是“文字”，同一矩阵其他条目已使用“字面量”。

**1. 原文**：`字符串文字`

**建议**：`字符串字面量`

落点：

- [data/featurematrix_zh.yaml:1133](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:1133) — `name: Unicode 字符串文字和标识符`
- [data/featurematrix_zh.yaml:1134](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:1134) — `description: 允许使用代码点指定 Unicode 字符串文字和标识符`

## C13 · auto_explain：模块名拼写

**待确认 · 建议修改**

模块键和文档中都是 auto_explain；显示名漏掉了下划线。

**1. 原文**：`contrib/autoexplain`

**建议**：`contrib/auto_explain`

落点：

- [data/featurematrix_zh.yaml:1185](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:1185) — `name: contrib/autoexplain`

## C14 · PostgreSQL 12：空间优化的方向

**待确认 · 建议修改**

原文是减少空间占用，译作“空间利用率降低”容易被理解为退步。保留原来的约 40% 数字与历史时间语境。 依据：[PostgreSQL 12 英文新闻资料包](https://www.postgresql.org/about/press/presskit12/)。

**1. 原文**：`平均将空间利用率降低了约 40%`

**建议**：`平均减少约 40% 的空间占用`

落点：

- [templates/pages/about/press/presskit12/zh.html:19](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit12/zh.html:19) — `B-树索引，PostgreSQL 中的标准索引类型，在 PostgreSQL 12 中得到优化，以更好地处理索引经常被修改的工作负载。使用 TPC-C 基准测试，PostgreSQL 12 平均将空间利用率降低了约 40%，并整体提升了查询性能。`

## C15 · PostgreSQL 11：默认分区条件

**待确认 · 建议修改**

默认分区接收的是不匹配任何已有分区的行，并非没有分区键值的行。 依据：[PostgreSQL 11 英文新闻资料包](https://www.postgresql.org/about/press/presskit11/)。

**1. 原文**：`将不含有分区键值的记录自动转入缺省分区`

**建议**：`将不匹配任何现有分区的记录自动放入默认分区`

落点：

- [templates/pages/about/press/presskit11/cn.html:22](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit11/cn.html:22) — `为了帮助管理分区，PostgreSQL 11 引入了将不含有分区键值的记录自动转入缺省分区的功能，并增加了在（主表）执行创建主键、外键、索引和触发器时，会将这些操作全部自动复制给所有分区表的功能。另外 PostgreSQL 11 现在也支持当记录中的分区键值字段被更新后，会自动将该记录移至新的正确的分区表中的`

## C16 · PostgreSQL 11：INCLUDE 与仅索引扫描

**待确认 · 建议修改**

原句很难读懂，也没有准确说明非键列可以存入覆盖索引的意义。 依据：[PostgreSQL 11 英文新闻资料包](https://www.postgresql.org/about/press/presskit11/)。

**1. 原文**：`“覆盖索引”操作，允许用户在创建一个索引通过使用 INCLUDE 选项来增加额外字段，这样会对无 B-树索引列的查询来使用 Index-Only 的扫描有很大好处；`

**建议**：`“覆盖索引”允许通过 INCLUDE 子句将非键列存入索引，从而让更多查询使用仅索引扫描；这些附加列甚至可以使用 B-树不支持索引的数据类型；`

落点：

- [templates/pages/about/press/presskit11/cn.html:51](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit11/cn.html:51) — `“覆盖索引”操作，允许用户在创建一个索引通过使用 INCLUDE 选项来增加额外字段，这样会对无 B-树索引列的查询来使用 Index-Only 的扫描有很大好处；`

## C17 · PostgreSQL 11：连接与 JIT 表述

**待确认 · 建议修改**

这几处能与原文逐一对应：hash joins 不是哈希聚合，target lists 不是指定列表，data definition commands 不是数据集的定义指令。 依据：[PostgreSQL 11 英文新闻资料包](https://www.postgresql.org/about/press/presskit11/)。

**1. 原文**：`在并行顺序扫描和哈希聚合方面`

**建议**：`在并行顺序扫描和哈希连接方面`

落点：

- [templates/pages/about/press/presskit11/cn.html:34](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit11/cn.html:34) — `PostgreSQL 11 提升了并行查询的性能，通过更加有效的分区数据扫描，在并行顺序扫描和哈希聚合方面性能有了更大的改进。即使是组成 UNION 的查询子句不能并行处理时，PostgreSQL 现在也可以对使用 UNION 的 SELECT 查询并行处理。`

**2. 原文**：`指定列表`

**建议**：`目标列表`

落点：

- [templates/pages/about/press/presskit11/cn.html:40](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit11/cn.html:40) — `PostgreSQL 11 版本引入了 JIT 编译来加速查询中的表达式的计算和执行。JIT 表达式的编译使用 LLVM 项目编译器的架构来提升在 WHERE 条件、指定列表、聚合、投影以及一些内部操作的表达式的编译执行。`

**3. 原文**：`几种数据集的定义指令`

**建议**：`几种数据定义命令`

落点：

- [templates/pages/about/press/presskit11/cn.html:36](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit11/cn.html:36) — `PostgreSQL 11 也对几种数据集的定义指令增加了并行处理功能，最显著的就是通过 CREATE INDEX 指令创建的 B-树索引。其他几种支持并行化操作的还有 CREATE TABLE .. AS、`

## C18 · PostgreSQL 14：拆开 postgres_fdw 的两项能力

**待确认 · 建议修改**

批量插入数据与 IMPORT FOREIGN SCHEMA 导入分区定义是两个功能；当前句子错误地把两者都归给 IMPORT FOREIGN SCHEMA。 依据：[PostgreSQL 14 英文新闻资料包](https://www.postgresql.org/about/press/presskit14/)。

**1. 原文**：`除了支持并行查询之外，postgres_fdw 现在还可以使用 IMPORT FOREIGN SCHEMA 指令在外部表上批量插入数据并导入表分区。`

**建议**：`除了支持并行查询之外，postgres_fdw 现在还支持向外部表批量插入数据，并可通过 IMPORT FOREIGN SCHEMA 命令导入分区表的定义。`

落点：

- [templates/pages/about/press/presskit14/zh.html:35](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit14/zh.html:35) — `除了支持并行查询之外，postgres_fdw 现在还可以使用 IMPORT FOREIGN SCHEMA 指令在外部表上批量插入数据并导入表分区。`

## C19 · PostgreSQL 15：默认权限变化

**待确认 · 建议修改**

该版本改变的是新数据库的默认权限，“现在允许撤销”会误导读者以为以前无法执行 REVOKE。保留已有数据库权限不会被升级自动修改的边界。 依据：[PostgreSQL 15 发行说明：迁移兼容性](https://www.postgresql.org/docs/15/release-15.html)。

**1. 原文**：`PostgreSQL 15 还允许从 public（即默认）模式中撤销除数据库所有者之外所有用户的 CREATE 权限。`

**建议**：`PostgreSQL 15 调整了新建数据库的默认权限：不再向 PUBLIC 授予 public 模式的 CREATE 权限。升级现有数据库时，其原有权限设置保持不变。`

落点：

- [templates/pages/about/press/presskit15/zh.html:31](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit15/zh.html:31) — `PostgreSQL 15 还允许从 public（即默认）模式中撤销除数据库所有者之外所有用户的 CREATE 权限。`

## C20 · PostgreSQL 18：值不限定为数值

**待确认 · 建议修改**

生成列及 OLD / NEW 都可处理非数值类型；这里的 values 应译为“值”。

**1. 原文**：`数值`

**建议**：`值`

落点：

- [templates/pages/about/press/presskit18/zh.html:6](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit18/zh.html:6) — `最高可达 3 倍，同时还扩大了能够利用索引的查询范围。此版本降低了主版本升级带来的扰动，加快了升级速度，并缩短了升级完成后恢复到预期性能所需的时间。开发者也能从 PostgreSQL 18 中直接受益，例如可在查询时计算数值的虚拟生成列，以及能够为 UUID 带来更佳索引与读取性能的 uuidv7() 函数。借助对 OAuth 2.0 身份验证的支持，PostgreSQL 18 也更易于与单点登录（SSO）系统集成`
- [templates/pages/about/press/presskit18/zh.html:24](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit18/zh.html:24) — `ps://www.postgresql.org/docs/18/sql-createtable.html#SQL-CREATETABLE-PARMS-GENERATED-STORED">虚拟生成列，它在查询时计算数值而不是直接存储，并已成为生成列的默认选项。此外，存储型生成列现在也可以参与逻辑复制。`
- [templates/pages/about/press/presskit18/zh.html:25](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit18/zh.html:25) — `l.org/docs/18/dml-returning.html">RETURNING 子句中同时访问修改前（OLD）与当前（NEW）数值的能力，适用于 INSERT、UPDATE、DELETE 和 MERGE 命令。PostgreSQL 18 还通过`

## C21 · PostgreSQL 13：受信任扩展段的病句与引号

**待确认 · 建议修改**

“使用安装”明显不通，引号方向也混乱。改动限于引入概念的这句话，并明确安装权限。 依据：[PostgreSQL 扩展 trusted 属性](https://www.postgresql.org/docs/18/extend-extensions.html)。

**1. 原文**：`PostgreSQL 13 添加了"可信扩展“的概念，该概念允许数据库用户使用安装超级用户标记为”受信任"的扩展。`

**建议**：`PostgreSQL 13 引入了“受信任的扩展”概念，允许对当前数据库具有 CREATE 权限的非超级用户安装被标记为“受信任”的扩展。`

落点：

- [templates/pages/about/press/presskit13/zh.html:73](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit13/zh.html:73) — `PostgreSQL 的扩展系统是其强大功能的关键组成部分，因为它允许开发人员扩展其功能。在以前的版本中，新的扩展只能由数据库超级用户安装。为了更轻松地利用 PostgreSQL 的可扩展性，PostgreSQL 13 添加了"可信扩展“的概念，该概念允许数据库用户使用安装超级用户标记为”受信任"的扩展。某些内置扩展默认情况下标记为受信任，包括 pgcrypto, <a`

## C22 · PostgreSQL 9.1：Heroku 与 salesforce.com 的归属关系

**待确认 · 建议修改**

译文把母公司与子公司关系写反了。按当年英文资料订正，不延伸为对当前公司关系的声明。 依据：[PostgreSQL 9.1 英文新闻资料包](https://www.postgresql.org/about/press/presskit91/)。

**1. 原文**：`Heroku 公司完全拥有 salesforce.com 网站`

**建议**：`Heroku 是 salesforce.com 的全资子公司`

落点：

- [templates/pages/about/press/presskit91/zh_cn.html:174](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:174) — `.heroku.com">网站和博客或是 Twitter。Heroku 公司完全拥有 salesforce.com 网站，联系方式：Jill Ratkevic`

## C23 · PostgreSQL 9.1：三处明确的误译／错字

**待确认 · 建议修改**

state of the art 指前沿水平；integrity 指完整性；下载链接的“原代码”应为“源代码”。 依据：[PostgreSQL 9.1 英文新闻资料包](https://www.postgresql.org/about/press/presskit91/)。

**1. 原文**：`（艺术级）的高级功能`

**建议**：`前沿特性`

落点：

- [templates/pages/about/press/presskit91/zh_cn.html:38](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:38) — `（艺术级）的高级功能`
- [templates/pages/about/press/presskit91/zh_cn.html:77](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:77) — `（艺术级）的高级功能`

**2. 原文**：`原代码`

**建议**：`源代码`

落点：

- [templates/pages/about/press/presskit91/zh_cn.html:116](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:116) — `原代码`

**3. 原文**：`数据集成性`

**建议**：`数据完整性`

落点：

- [templates/pages/about/press/presskit91/zh_cn.html:47](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:47) — `”OpenERP 软件依赖于具有企业级特性的 PostgreSQL，来为我们用户的每天操作实现快速、安全和可伸缩性的商业应用。在高并发和复杂事务条件下的数据集成性对我们来说是关键，我们对新的 PostgreSQL 9.1 版本中可串行化快照隔离技术非常感兴趣！“OpenERP 社区经理 Olivier Dony 说道。`
- [templates/pages/about/press/presskit91/zh_cn.html:177](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:177) — `”OpenERP 软件依赖于具有企业级特性的 PostgreSQL，来为我们用户的每天操作实现快速、安全和可伸缩性的商业应用。在高并发和复杂事务条件下的数据集成性对我们来说是关键，我们对新的 PostgreSQL 9.1 版本中可串行化快照隔离技术非常感兴趣！同步复制技术和性能优化是两个我们期待新版本 PostgreSQL 的主要原因，PostgreSQL 是开源软件的典型代表。`

## C24 · PostgreSQL 10：商业伙伴错字

**待确认 · 建议修改**

确定的错别字，不涉及重译。

**1. 原文**：`商业伙们`

**建议**：`商业伙伴`

落点：

- [templates/pages/about/press/presskit10/cn.html:164](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:164) — `ttps://yandex.com/" target="_blank" rel="noopener">Yandex 公司是一家使用机器学习技术提供人工智能产品和服务的技术公司。Yandex 公司的目标是帮助客户和商业伙们更好地探索在线和离线业务。从 1997 年起，Yandex 公司已交付了世界级的、本地业务相关的搜索和信息服务。另外，Yandex 公司也为全球上百万的用户开发了市场领先的按需乘车服务、导航产品以及其他移动应用。可以通过`

## C25 · PostgreSQL 9.0：RADIUS 认证

**待确认 · 建议修改**

此处对应 authentication，不是 authorization。 依据：[特性条目 Native RADIUS authentication](/Users/vonng/pgsty/pgweb/data/featurematrix.yaml:2111)。

**1. 原文**：`RADIUS 授权`

**建议**：`RADIUS 认证`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:59](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:59) — `RADIUS 授权`

## C26 · 服务收录政策：word 不应换算为“字”

**待确认 · 建议修改**

上游要求 15–50 words；当前中文改变了字数限制的计量单位。只校正单位，不修改政策。 依据：[服务与托管收录政策](https://www.postgresql.org/about/policies/services-and-hosting/)。

**1. 原文**：`15 至 50 字`

**建议**：`15 至 50 个词`

落点：

- [templates/pages/about/policies/services-and-hosting.html:23](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/services-and-hosting.html:23) — `一段 15 至 50 字的公司服务摘要，详细说明公司为 PostgreSQL 提供的具体服务。`

## C27 · 扩展属性 relocatable：说明可以迁移什么

**待确认 · 建议修改**

“可迁移模式”看不出布尔值表示什么。此属性决定扩展对象能否通过 ALTER EXTENSION SET SCHEMA 更换目标模式。 依据：[扩展的 relocatable 属性](https://www.postgresql.org/docs/18/extend-extensions.html)。

**1. 原文**：`可迁移模式`

**建议**：`可更改目标模式`

落点：

- [pgweb/ext/views.py:188](/Users/vonng/pgsty/pgweb/pgweb/ext/views.py:188) — `(('need_load', ('需要显式加载', 'Requires loading')), ('trusted', ('可信扩展', 'Trusted extension')), ('relocatable', ('可迁移模式', 'Relocatable'))):`

## C28 · 关于本站：上游入口说明

**待确认 · 建议修改**

生态文档和扩展详情的右上角链接可以指向各自项目的上游，不一定都是 postgresql.org。 依据：[公共页头中的上游链接逻辑](/Users/vonng/pgsty/pgweb/templates/base/header.html:1)。

**1. 原文**：`每个页面右上角的外链图标可以直接跳转到 postgresql.org 上的对应英文页面。`

**建议**：`页面右上角的外链图标可前往对应的上游原文。`

落点：

- [templates/pages/about/pgcenter.html:15](/Users/vonng/pgsty/pgweb/templates/pages/about/pgcenter.html:15) — `译文力求忠实原文，但翻译难免存在疏漏。凡译文与英文原文有出入之处，均以原文为准。每个页面右上角的外链图标可以直接跳转到 postgresql.org 上的对应英文页面。`

## C29 · 提交预览：说明撤回后仍可修改

**待确认 · 建议修改**

新闻提交后不能直接修改，但待审核时可以撤回；当前绝对化表述与列表页的撤回说明不一致。 依据：[等待审核时可以撤回](/Users/vonng/pgsty/pgweb/templates/account/objectlist.html:44)；[撤回流程](/Users/vonng/pgsty/pgweb/pgweb/account/views.py:351)。

**1. 原文**：`您即将提交以下{{objtype}}进行审核。请注意，一旦提交，内容将无法再修改。`

**建议**：`您即将提交以下{{objtype}}进行审核。提交后如需修改，请先在待审核列表中撤回提交。`

落点：

- [templates/account/submit_preview.html:7](/Users/vonng/pgsty/pgweb/templates/account/submit_preview.html:7) — `您即将提交以下{{objtype}}进行审核。请注意，一旦提交，内容将无法再修改。`

## C30 · 账户邮箱提示：解释实际影响

**待确认 · 建议修改**

“级联到关联系统”是实现用语，替换为用户能够直接理解的后果。

**1. 原文**：`删除此处的任何地址将级联到关联系统`

**建议**：`删除这里的邮箱地址也会影响关联系统`

落点：

- [templates/account/userprofileform.html:60](/Users/vonng/pgsty/pgweb/templates/account/userprofileform.html:60) — `请注意，删除此处的任何地址将级联到关联系统，例如可能导致自动取消邮件列表订阅。`

## C31 · UNLOGGED 与导入表定义的表述

**待确认 · 建议修改**

不记录 WAL 的表不是尚未创建记录的表；IMPORT FOREIGN SCHEMA 里的后一个 schema 指表定义，而不是要导入一个命名模式。

**1. 原文**：`未记录表`

**建议**：`不记录 WAL 的表（UNLOGGED）`

落点：

- [data/featurematrix_zh.yaml:524](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:524) — `name: 未记录表`

**2. 原文**：`已记录日志和未记录日志状态`

**建议**：`记录 WAL 和不记录 WAL 两种状态`

落点：

- [data/featurematrix_zh.yaml:315](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:315) — `description: 允许表在已记录日志和未记录日志状态之间切换。`

**3. 原文**：`导入分区表的 schema`

**建议**：`导入分区表的定义`

落点：

- [data/featurematrix_zh.yaml:956](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:956) — `description: ''IMPORT FOREIGN SCHEMA' 现在可以导入分区表的 schema。'`

## C32 · 资金小组章程：附议主语与辩论期限

**待确认 · 建议修改，政策语句请单独核对**

现有主语容易读成所有其他成员都必须附议，且“自动议……不得少于……结束”不通顺。以每项动议为主语，并明确不得提前结束的时间起点。 依据：[Funds Group 章程](https://www.postgresql.org/about/policies/funds-group/)。

**1. 原文**：`任何其他现任成员必须对所有动议进行附议`

**建议**：`每项动议都必须由另一位现任成员附议`

落点：

- [templates/pages/about/policies/funds-group.html:141](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/funds-group.html:141) — `任何其他现任成员必须对所有动议进行附议`

**2. 原文**：`自动议获得附议后不得少于 72 小时结束`

**建议**：`不得早于动议获得附议后的 72 小时结束`

落点：

- [templates/pages/about/policies/funds-group.html:149](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/funds-group.html:149) — `自动议获得附议后不得少于 72 小时结束，除非动议中特别要求了更长的辩论期（任何情况下辩论不得少于 72 小时）`

## C33 · 网站团队与网络团队

**待确认 · 建议修改**

新闻与活动政策中的 web / WWW team 管理网站内容；“网络团队”容易被理解为网络运维团队。

**1. 原文**：`网络团队`

**建议**：`网站团队`

落点：

- [templates/pages/about/policies/news-and-events.html:34](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/news-and-events.html:34) — `PostgreSQL 项目的网络团队可以永久禁止任何因社区成员对准确性、道德或合法性提出实质性投诉的组织。`
- [templates/pages/about/policies/news-and-events.html:36](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/news-and-events.html:36) — `网络团队不承诺及时审批公告。如果在特定日期发布对您至关重要，您需要在提交之前联系 pgsql-www 邮件列表或核心团队成员。`
- [templates/pages/about/policies/news-and-events.html:38](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/news-and-events.html:38) — `赞助商页面上列出的公司可以在网络团队的自行决定下，获得新闻和活动的任何限制（如允许的发布频率）的豁免。`
- [templates/pages/about/policies/news-and-events.html:40](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/news-and-events.html:40) — `网络团队保留部分或全部重写新闻或活动帖子以提高清晰度的权利。`
- [templates/pages/about/policies/news-and-events.html:125](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/news-and-events.html:125) — `更常规的活动，如每月的本地聚会或小型会议，将不会被列出。会议必须包含重要的 PostgreSQL 内容才值得列出，相对重要性的决定由网络团队作出。`
