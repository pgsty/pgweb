# 扩展钩子、存储参数、预定义角色与对象标识符类型

PGSQL.CC 原生参考栏目，覆盖 PostgreSQL 10–20，每个实体一行、各版资料保存在 `versions` JSON 中。复用百科导航、版本方格、中文检索和手册链接，不复制 PGpedia 正文。

| 栏目 | 地址 | 实体表 | 固定快照 |
| --- | --- | --- | --- |
| 扩展钩子 | `/wiki/hook/` | `hook` | `data/wiki/hooks.json` |
| 存储参数 | `/wiki/relopts/` | `relopt` | `data/wiki/relopts.json` |
| 预定义角色 | `/wiki/role/` | `predefined_role` | `data/wiki/roles.json` |
| 对象标识符类型 | `/wiki/oid/` | `oid_type` | `data/wiki/oid_types.json` |

四张独立实体表通过抽象 Python 基类复用字段，不新增公共实体表、版本表或关系表。迁移 `wiki.0012_reference_topics` 依赖当前的 `0011_lockmode`，只建四张新表。栏目规格在 `topic_specs.py`；导入、版本选择和页面分别在 `topic_importer.py`、`topics.py`、`topic_views.py`。

## 来源与覆盖

- **扩展钩子**：逐版扫描固定 SHA 的 PostgreSQL `src/include`，收录由核心导出、使用含 hook 的函数指针类型声明的全局变量。首批 39 个实体、339 份快照，逐版完整扫描 649–838 个头文件。保留 typedef、声明、定义与调用坐标及默认指针值，中文解释独立编写。逐对象回调、GUC 回调、前端接口和过程语言插件不在这一集合内。生成器不以中文编辑清单发现接口；缺少说明或定义时失败。
- **存储参数**：从本站每版手册的 `CREATE TABLE`、`CREATE INDEX`、`CREATE VIEW` 中抽取，包括表/物化视图参数、TOAST 参数、按访问方法区分的索引参数、视图选项与历史 OIDS。当前固定快照为 60 个实体、562 份快照，包含 PG20 的 `toast_value_type`。相同名字在不同对象类型下保持独立身份，如五个 `fillfactor` 条目。
- **预定义角色**：从本站每版 `default-roles.html` 或 `predefined-roles.html` 抽取，展开合并在同一术语组中的多个角色名。首批 16 个实体、129 份快照；保存原版权限说明及手册来源。
- **对象标识符类型**：从本站每版 `datatype-oid.html` 抽取，共 18 个实体、174 份快照，含 `oid`、各类 `reg*`、`oid8`、`xid/xid8`、`cid` 与 `tid`。保留名称解析、早绑定/后绑定、依赖关系等段落和 SQL 示例的原始顺序。`regdatabase` 与 `oid8` 只在 19、20 有记录，不借用相邻版本。

版本标签显示实际采样构建；历史版本与预览状态复用 `core.Version`。最早方格仅表示本次采样首次出现，不代表真实引入版本。指定 `?v=18` 而该项只存在于 19 时，页面明确显示该版未收录，允许选择已收录版本；不自动替换正文。

手册证据保留本地 URL、原页 SHA-256 与构建身份；源码链接保留不可变 commit SHA、路径及行号。PG20 是开发快照，不代表正式发布。生成过程不写内容库，只有导入命令写库。

## 生成与导入

在项目根目录运行：

```bash
# 钩子：固定版本源码缓存放 tmp/hooks-sources，可复用现有源码仓库的 Git blobs
.venv/bin/python tools/wiki/build_hooks.py --fetch --source-repo /path/to/postgres
.venv/bin/python tools/wiki/build_hooks.py --check

# 存储参数：可固定手册输入，离线复现；省略 input 时读取本地手册
.venv/bin/python tools/wiki/build_relopts.py --export-sources tmp/relopts-sources.json
.venv/bin/python tools/wiki/build_relopts.py --input-sources tmp/relopts-sources.json --check

# 角色与标识符类型：从本地手册生成，在只读一致性事务中读取
.venv/bin/python tools/wiki/build_role_oid.py
.venv/bin/python tools/wiki/build_role_oid.py --check

.venv/bin/python manage.py migrate wiki
.venv/bin/python manage.py wiki_import_topics data/wiki/hooks.json data/wiki/relopts.json data/wiki/roles.json data/wiki/oid_types.json --check
.venv/bin/python manage.py wiki_import_topics data/wiki/hooks.json data/wiki/relopts.json data/wiki/roles.json data/wiki/oid_types.json
.venv/bin/python manage.py index_docs --topics
psql -X -d pgweb -f tools/wiki/check_data.sql
```

快照为 `format=1`，顶层 `kind/releases/items`；每条含 `slug/name/name_zh/category/summary/aliases/versions`。版本内容含 `description/facts/sections/sources/related/release`，钩子另有 `signature`。段落与代码混排用 `section.blocks` 保存顺序，模板统一转义纯文本。

`wiki_import_topics` 先校验整批文件，再在一个事务中导入。内容和来源身份一起参与 SHA-256；相同快照完全跳过，保留 `imported_at`。缺项默认保留，只有显式 `--prune` 删除该输入栏目的缺项。重复的栏目文件、实体身份、不明版本和不安全链接均在写库前拒绝。`--check` 只预览新增/更新/未变/删除数。

生产更新应使用已验收的同一组 JSON 快照，在生产应用目录迁移、导入、索引、重启 `pgsql.cc`。本地生成、测试和导入均不等于已发布生产；不要使用历史 `/data/app/pgweb` 或英文站数据库。

## 页面与检索

列表提供版本、分类和关键词筛选，保留完整采样版本方格。详情提供逐版说明、参数事实或 C 签名、手册示例、相关链接和可展开的来源。栏目自动进入百科菜单、侧栏和 sitemap，不伪造 postgresql.org 对应栏目地址。

检索 `source` 为 `hook/relopts/role/oid`，类别为 `hook/relopt/role/type`。对象标识符类型使用 `type:<name>` 实体键与手册类型定义折叠；其余以栏目和 slug 为身份。索引包含所有版本的说明、事实、C 签名及 SQL 示例。弹窗预览和结果 URL 保持所选版本，缺失版本同样明确提示。

## 验证

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
PGWEB_TEST_DB=test_pgweb_topics .venv/bin/python manage.py test pgweb.wiki.test_topics pgweb.wiki.test_hook_data pgweb.wiki.test_relopts_data pgweb.wiki.test_role_oid_data --noinput
```

测试覆盖真实固定快照、逐版集合与源说明、重复导入、缺项保留、版本缺失、规范地址、页面渲染、索引实体折叠及预览版本。每次刷新还应运行各生成器的 `--check`，核对来源文件哈希和页内锚点，并验收实际页面。

## 2026-09-26 本地验收

本地 `pgweb` 库已应用迁移、导入 132 个实体与 1,203 份版本快照，建立 132 个检索条目。第二次导入全部为 `unchanged`。`check_data.sql` 的十一领域检查全部通过；新增 35 项测试与既有搜索 49 项测试通过；Django 检查、迁移漂移检查与 diff 空白检查通过。

三份手册快照共 3,444 次引用，去重 1,193 个 URL。本地手册的 645 个 URL、176 页、564 项哈希声明及全部锚点通过；488 个百科 URL 全部 HTTP 200 且保持指定版本。60 个外部原文 URL 仅清点，未作在线可用性声明。钩子的 1,036 条源码引用逐一核验文件哈希与行号，固定源码离线重建一致；155 个站内关联目标均核验，其中 56 个新钩子页面另在实际导入后核验了 HTTP 200 与签名正文。

浏览器验收了列表筛选、角色详情、钩子版本签名和全站搜索预览。Sitemap 含四个入口与全部 132 个详情地址。预览运行于 `http://127.0.0.1:8013/wiki/hook/`。本轮未部署生产，未提交或推送。详细审计保存在 `tmp/reference-topics-20260926/`，测试与数据库日志为 `tmp/reference-topics-{tests,search-tests,db-check}.log`。

## 2026-09-27 固定快照刷新

依据当前已入库的最新 PGDOC 中文手册重新生成并审阅角色、OID 类型与存储参数。角色和 OID 快照逐字节不变；存储参数新增仅存在于 PG20 的 `toast_value_type`，共 60 个实体、562 份版本记录，四主题合计 133 个实体、1,204 份记录。该参数只在创建 TOAST 关系时决定 `chunk_id` 类型；不能通过后续修改参数改变已有 TOAST 关系。已有参数正文不变，相关 PG20 来源指纹随新手册刷新。

钩子与锁保留已经对固定上游构建核验的快照。源码记录和正文未变化时不为刷新日期而重抓或改写。候选导入使用独立测试库验证全部 SQL 命令与五个新领域；二次导入全部跳过且保留 `imported_at`。本次数据差异、预览及幂等验收保存在 `tmp/catalog-update-20260927/topics/`；本段仅记录固定快照与隔离验证，业务库导入和发布另行核验。


## 2026-09-30 路由与现行手册复核

四主题仍为 133 个实体、1,204 份快照。钩子和 OID 固定数据仅把关联百科链接改为 `/wiki/`；角色快照不变。存储参数同步当前 PG20 手册的三段说明：`toast_value_type` 的 `oid8` 指针代价、`REPACK` 不改变既有 TOAST 类型，以及 `CREATE VIEW CHECK OPTION` 撤回的 temporal DML 说明；同时更新原页哈希与构建身份。钩子另对当前 PG20 源归档的 838 个头文件重新扫描，38 个接口的集合、typedef 和声明均与固定快照相同，保留原有不可变源码引用。
