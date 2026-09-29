# 锁百科 `/wiki/lock/`

锁百科描述 PostgreSQL 10–20 的 8 种表级锁模式、4 种行级锁模式、冲突关系和取得它们的 SQL 命令。默认版本与本站 `core.Version.current` 一致，测试版、开发快照和停止维护的版本明确标注。PG10 是采样基线，不代表锁模式的引入时间。

## 一张实体表

新增 `lock_mode`，每种锁模式一行，共 12 行。普通列保存 `slug/name/name_zh/abbrev/scope/summary/position`，`versions[major]` 保存该版本的冲突模式 slug、命令变体、适用条件、来源及构建证据。`content_hash/source_rev/imported_at` 遵循其他百科的幂等导入约定。

不建冲突边表、命令表或版本表：同作用域的冲突集合在版本 JSON 中；兼容集合、矩阵和反向命令映射由它派生。命令 slug 直接链接现有 `/wiki/sql/<slug>/?v=<major>`，版本显示复用 `core.Version`。每份快照保留实际采样构建，不能把数据库中的新 beta 标签当成来源已经刷新。来源提交或抓取时间变化而业务内容不变时，不重写实体和 `imported_at`。

## 来源与更新

`pglocks.org` 用于发现命令变体和交互设计；规则的权威来源是各版本 PostgreSQL 官方手册与源码。生成器 `tools/wiki/build_locks.py` 逐版解析官方的 8×8、4×4 冲突矩阵，并交叉核查源码冲突定义。命令说明按版本采集与编辑；尤其注意 `MERGE` 15+、`REINDEX CONCURRENTLY` 12+、不同 `ALTER TABLE` 子命令，以及表锁与索引锁的不同作用对象。

固定快照在 `data/wiki/locks.json`；包括每版来源 URL、SHA-256、固定源码 revision、采样时间和覆盖报告。重新采集时先阅读生成器的 `--help`，审核快照差异，再导入；不能用单版矩阵复制后声称核验了所有版本。

```bash
.venv/bin/python manage.py migrate wiki
.venv/bin/python manage.py wiki_import_locks --input data/wiki/locks.json --check
.venv/bin/python manage.py wiki_import_locks --input data/wiki/locks.json
.venv/bin/python manage.py index_docs --locks
```

生产按相同次序在 `/data/app/pgsql.cc` 操作，使用同一固定快照；代码发布后重启 `pgsql.cc`。导入器拒绝不完整版本、缺失模式、跨作用域冲突、非对称矩阵和缺失来源。导入在事务中进行，重复导入不重写。新表初次迁移没有历史数据转换；回退前如已有编辑，应先导出保存。

## 矩阵的含义

纵轴是请求的锁，横轴是另一事务已持有的锁，只在同一对象上判断：表锁比较同一张表，行锁比较同一行。先显示原始 8×8 表锁矩阵；下方是按表锁分组的 14×14 常见组合矩阵，不把裸行锁另放在右下角。

组合矩阵保留 8 个“仅表锁”项，在 `ROW SHARE` 下展开 4 种 `SELECT FOR …` 组合，在 `ROW EXCLUSIVE` 下展开非键更新与键更新/删除的 2 种组合。14 是显示组合数，基础模式仍为 12 种，不新增实体、表或冲突数据。保留纯 `ROW SHARE` / `ROW EXCLUSIVE` 是为了准确表达显式 `LOCK` 和普通 `INSERT` 等没有对应既有行锁的情形。

格子按所选版本的原始冲突集合派生：先比较表锁，冲突显示红色 `×`（即使命中不同行也冲突）；表锁兼容但两个行锁互斥时显示琥珀色 `●`（只在同一行时冲突）；其余显示绿色 `·`。悬浮、点击或键盘聚焦说明冲突的层级及条件。命令高亮要求组合的所有模式都匹配，不能仅因命令取得 `ROW SHARE` 就高亮它的四个子项。

分组不是从弱到强的总排序：`SHARE UPDATE EXCLUSIVE` 与 `SHARE` 的冲突集合互不包含；表锁与行锁也是两个独立层级。`SHARE UPDATE EXCLUSIVE` 主要用于维护与部分 DDL，不是更新行锁的归属。

行级锁命令也需要表锁。例如 `SELECT FOR UPDATE` 取得 `ROW SHARE` 表锁与 `FOR UPDATE` 行锁，因而会被表上的 `EXCLUSIVE` 或 `ACCESS EXCLUSIVE` 阻塞。`UPDATE` 与 `DELETE` 取得 `ROW EXCLUSIVE` 表锁；具体行锁取决于是否修改键。矩阵不等同于完整命令执行模拟器，不能据此排除锁队列、其他对象、触发器、外键、执行阶段造成的等待。

`pg_locks.locktype` 描述锁定的对象类别，与这 12 个模式不是同一个分类。咨询锁、SSI 谓词锁和内部页级/LWLock 的边界在页面说明并链接手册，不塞入表/行冲突矩阵。

## 页面与集成

- 索引 `/wiki/lock/?v=18`，详情 `/wiki/lock/access-share/?v=18`；不支持的版本或未知模式返回 404，避免悄悄展示另一版本。
- 版本下拉是普通 GET 表单，无 JavaScript 仍可切换。矩阵、模式和命令在服务端完整渲染；JavaScript 只增强单元格说明、模式高亮和命令筛选。
- 百科导航与 sitemap 从 `wiki.columns` 生成；SQL 命令详情显示所选版本的反向锁模式链接。
- 统一检索新增 `source='lock'`、`kind='lock'`、`entity_key='lock:<slug>'`，仍复用两张派生检索表，不新增索引业务表。运行 `index_docs --locks`，搜索预览按请求版本读事实。
- 样式复用百科壳和等待事件的色调，增强样式与脚本分别为 `media/css/lock.css`、`media/js/lock.js`，遵守 CSP，无内联脚本或样式。

验收包括导入幂等与拒绝坏数据、11 个版本的 12 模式覆盖、原始与展开矩阵、命令版本门槛、全部命令链接、搜索/导航/详情及桌面和窄屏浏览器检查。用真实 PostgreSQL 两会话验证原始 80 对锁模式，以及展开矩阵在同行/不同行两种条件下的 392 对组合。测试使用独立 `PGWEB_TEST_DB`，不覆盖现有业务数据。
