# 第三方文档外链

第三方组件只提供外部 URL 入口，不在 pgsql.cc 导入、保存或渲染文档正文，也不纳入本站文档检索。文档页面左侧的“三方文档”默认收起；顶部“文档”下拉菜单与移动端文档导航的最下面也提供“三方文档”入口，链接到 `/docs/third-party/`，不在菜单中展开组件子项。`/docs/` 首页正文不重复展示。

点击左侧“三方文档”进入 `/docs/third-party/`，左侧展开九个组件的外链，右侧按相同顺序展示组件简介，点击组件名称直接前往外部文档。名称、链接、简介与顺序共用 `pgweb/util/contexts.py` 的 `THIRD_PARTY_DOCS`。离开介绍页后，其他文档页面的三方文档分组仍保持收起。`/docs/#ecosystem-docs` 仍可定位到左侧入口。

| 名称 | 目标地址 |
| --- | --- |
| Patroni | https://pigsty.cc/docs/patroni |
| PgBouncer | https://pigsty.cc/docs/pgbouncer |
| pgBackRest | https://pigsty.cc/docs/pgbackrest |
| pg_exporter | https://pigsty.cc/docs/pg_exporter |
| Pigsty | https://pigsty.cc/docs |
| pig | https://pigsty.cc/docs/pig |
| PostGIS | https://postgis.net/docs/manual-dev/zh_Hans/ |
| TimescaleDB | https://docs.timescaledb.cn/ |
| Citus | https://learn.microsoft.com/zh-cn/postgresql/citus/?view=citus-14 |

链接直接指向外站。旧 `/docs/patroni/`、`/docs/pgbouncer/`、`/docs/pgbackrest/` 及其版本、语言、章节地址统一 301 到各自外部文档首页；不保留本站正文，也不把旧版本号和章节路径拼到外站地址。旧 pgBadger 阅读入口返回 404。sitemap 收录组件介绍页，不收录三方正文或这些兼容跳转地址。

## 2026-09-09 撤回与归档

本次撤回 `doc_project`、`doc_revision`、`doc_page` 三张独立表及其 identity 序列、模型、导入工具、阅读页、专用静态资源和附件。两端均通过 Django 反向执行 `docs.0005_ecosystem_documentation`，再移除其迁移定义，docs 的迁移终点回到 `0004_docpageredirect`。没有使用 `DROP ... CASCADE`。PostgreSQL 核心手册与 `pgext` 扩展目录继续使用原有表。

归档位置：

- 本地：`tmp/ecosystem-rollback-20260909T014349Z/`，包含 `local/` 与取回的 `production/`。
- 生产：`/data/app/pgweb/tmp/ecosystem-rollback-20260909T014349Z/production/`。

每端均包含：

- `ecosystem.dump`：三表完整数据与结构的 PostgreSQL 自定义格式备份。
- `schema.sql`：从备份提取的 DDL，包括索引、约束及序列。
- `files/`：撤回前的模型、迁移、SQL 定义与该端实际存在的实现文件和附件。
- `database-before.json`：撤回前各表行数与逐行内容摘要；两端均为 6 个项目、12 个版本/语言记录、424 篇文档。
- `django-metadata.json`：三种已撤回模型对应的 ContentType 与权限。
- `sha256.json`、`archive-list.txt`：备份文件校验值与归档目录。
- `preexisting.patch`：开始操作时的修改快照；不应整体覆盖回当前工作区。

两份 `ecosystem.dump` 已分别恢复到一次性本地数据库，逐表行数和内容 SHA-256 均与原库一致，恢复结果在 `restore-verification.json`。其他表的前后内容摘要另行核验。

## 如需恢复旧实现

1. 从所需端的 `files/` 选择恢复迁移 `0005`、三种模型和相应实现，合并期间新增的修改。生产端原先只加载过数据，尚未部署阅读页；完整阅读实现位于本地归档。
2. 使用该端 Django 配置运行 `manage.py migrate docs 0005` 创建空表。再以同一数据库身份运行 `pg_restore --data-only --single-transaction --exit-on-error --no-owner --no-privileges --dbname=pgweb ecosystem.dump`；单个事务使可延迟外键在三表全部加载后校验。不要向非空表重复加载。
3. Django 会重新创建 ContentType 和权限；如需保留旧 ID，先检查有无 ID 冲突，再使用归档的元数据，避免覆盖后续新增模型。
4. 对照 `database-before.json` 核验数据，按需恢复附件，并检查迁移、页面和索引入口后重启应用。

在尚未执行撤回的其他环境中，先导出并恢复校验三表备份，再运行 `manage.py migrate docs 0004`，最后部署删除 `0005` 的代码。不要先删迁移文件再尝试反向迁移。
