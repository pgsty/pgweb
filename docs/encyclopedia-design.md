# PostgreSQL 参考资料模型

PGSQL.CC 在 `/docs/` 下提供 SQL 命令、SQLSTATE、系统目录、配置参数、等待事件和函数六类参考资料。模型按领域保存实体，每个实体一行；公开 URL、Python 模型和 `wiki` 应用标签保留，数据库表使用领域名称。

2026-09-25 的模型整理将原 20 张业务表收敛为 12 张，检索另有两张派生表。实施范围见 [整理计划](reference-model-plan.md)，备份、执行证据与回退见 [实施记录](reference-model-rollout.md)。本文件描述当前实现，不再沿用早期抽象基类、独立正文表及报文反查的设想。

## 表与边界

| 领域 | 实体表 | 公共资料 | 主键 / 详情地址 |
| --- | --- | --- | --- |
| SQLSTATE | `sqlstate` | `sqlstate_class`、`sqlstate_version` | 五字符大写代码；`/docs/sqlstate/<CODE>/` |
| 系统目录 | `catalog` | `catalog_version` | 关系名；`/docs/catalog/<name>/` |
| GUC | `guc` | `guc_version` | 参数规范名；`/docs/guc/<name>/` |
| 等待事件 | `waitevent` | `waitevent_version` | 归一化身份 key；`/docs/waitevent/<type>/<name>/` |
| SQL 命令 | `sqlcmd` | 从快照与 `core.Version` 组装 | slug；`/docs/sql/<slug>/` |
| 函数 | `func` | `func_version` | 函数名归一化 slug；`/docs/func/<slug>/` |

版本资料描述实际采样构建及汇总，不是每实体每版本一行的快照表。实体自己的 `versions`、`changes` 等 JSON 保存完整版本记录。各领域保持自己的身份与比较规则，未引入通用节点、边或图查询框架。

`search_indexedpage` 记录手册索引指纹，`search_searchentry` 保存统一检索投影。它们可以重建，不是正文的第二份权威副本。实体表名、检索 `source`、实体折叠键和公开 URL 是不同契约，不随表改名一起更换。

## SQLSTATE 文档

`sqlstate` 的普通列保存代码、类别外键（列名 `class_code`）、条件名、宏、严重程度、状态、版本存在性、可信度、中文摘要及计数。大块内容分别放在三个 JSONB 对象中：

| JSON | 结构与用途 |
| --- | --- |
| `facts` | 源事实、历史边界、快照身份、`presence_intervals`、`pre9_presence_intervals`；每个区间保留端点、tag、major、`position`、`evidence_count` 和原有额外字段 |
| `texts` | 按语言键保存正文对象，含 `title/name/description/summary/body_md/sections/translation_source_rev/is_stale`；中文优先，缺失时回退英文，其他已有语言也保留 |
| `evidence` | `sources/claims/messages/runtimes/cases` 五个数组；保留各自业务 ID、顺序、限制及原始 JSON。每条报文内嵌 `templates` 数组，覆盖 primary/detail/hint/context、单复数及变体 |

`name_zh`、`summary_zh` 来自 `texts.zh`，`case_count`、`snippet_count` 来自案例；由 `documents.derive()` 统一派生。主键使用格式检查，类别前缀必须匹配，三个 JSON 顶层必须为对象。导入器校验内部数组、业务 ID 和引用结构。目前没有为这些 JSON 建全量 GIN 索引；列表使用普通列并延迟加载三块大 JSON。

旧 `facts` 不是完整证据副本：旧导入器裁剪过逐补丁审计数组与作者证据。迁移必须合并八张旧子表，不能只删表保留 `facts`。已存在的 Markdown、清洗后 HTML、翻译状态和本站摘要直接迁移，不重新抓取或渲染。

源码/断言/运行/案例引用使用本条 SQLSTATE 内的业务 ID。`sources` 数组的目标实际上可能是来源、运行记录或另一条断言；页面为所有匹配目标提供类型明确的链接，只展开一层。无法解析的 ID 原样保留并显示缺失状态。当前既有四处缺口是 `22001/22003/22004/22007` 的 `manifest.<CODE>`，源证据文件也未定义相应来源记录。

## 事实与版本语义

- `introduced.release` 有明确证据时显示“引入版本”，补丁号不裁剪；`57P04` 是 `9.0.4`。
- `known_present_by` 只表示“最早已知存在”；`23505` 的 `7.4` 不能解释为真实引入时间。
- `removed` 缺失时不根据相邻版本推断精确移除边界；`72000` 保留“已移除（边界未取证）”。
- 版本条区分已收录、已采样构建未定义、尚未采样。`active` 不证明 PG20 存在性。
- SQLSTATE 的 `?v=` 选择手册链接，源码与运行证据仍锚定原 tag/commit/服务器构建。beta 3 的证据不能因当前手册已到 beta 4 而改称 beta 4。
- 其余领域的 `first_version/last_version` 是收录范围。基线、沿用事实、借用译文、散文中仅有存在性而无签名的记录，均保留原注记；专属规则见各栏目契约。

## 数据来源与导入

SQLSTATE 读取 `~/pg.center/err` 的 `data/errcodes/*.json`、`evidence/*.json`、`content/docs/*.md` 及已选定案例；不把 `static/data` 的生成投影当权威输入。原始逐补丁审计记录仍留源仓库，本网站保留压缩区间。`facts` 只承诺保留本站已有事实，不宣称是未经裁剪的整份原始资料。

其余来源和校验规则分别见 [catalog](catalog-column.md)、[GUC](guc-column.md)、[等待事件](waitevent-column.md)、[SQL 命令](sqlcmd-column.md)、[函数](func-column.md)。函数存在性以英文原页为准，本站译文用于中文叠加。每个领域仍有独立导入器，不用一个通用框架抹平来源差异。

SQLSTATE 快照格式是 `format=2`：`classes[]`、`releases[]`、`codes[]`；每条 code 包含完整三块 JSON。`importer.prepare()` 纯转换兼容 `format=1`，不修改调用者输入。本站 `data/wiki/errcode-summaries.json` 在源导出阶段覆盖正文摘要，固定快照已经自包含；`--input` 不读取另一台机器的摘要覆盖。

六张主表都有稳定 `content_hash`，按落库业务字段计算 SHA-256：对象键排序、数组顺序保留，排除 `source_rev/imported_at/content_hash`。含指纹的输入会重新计算核验。无内容变化的实体完全跳过，保留 `imported_at` 和最近一次内容写入时的来源身份；新导出的 SQL 命令和函数 `source_rev` 使用来源提交，不再拼运行时间。

导入在事务中原位更新，默认保留输入缺项，显式 `--prune` 才删除。成功提交后清理栏目缓存。所有来源都继续用原来的管理命令和 `tools/wiki/sync_*.py`；固定快照分别导入本地与生产。数据库迁移从现有库直接转换，避免用源仓库覆盖本站已有编辑。

```bash
.venv/bin/python tools/wiki/sync_errcode.py --export /tmp/sqlstate.json.gz
.venv/bin/python tools/wiki/sync_errcode.py --input /tmp/sqlstate.json.gz --write
.venv/bin/python manage.py index_docs --errcodes --catalog --guc --waitevents --sqlcmd --func
psql -X -d pgweb -f tools/wiki/check_data.sql
```

## 迁移、约束与验证

历史 `wiki.0001–0006` 和 `search.0001–0004` 保持原样。新增：

1. `wiki.0007_reference_documents`：添加文档、摘要和六主表指纹；旧正文反向访问器只在迁移状态中改名。
2. `wiki.0008_backfill_reference_documents`：以历史模型合并现有内容、核对计数、保留导入时间，填充指纹。
3. `wiki.0009_reference_table_names`：改名 12 表、显式索引及目录中真实存在的自动生成对象。
4. `search.0005_catalog_entry_identity`：非手册条目增加 `(source,key) WHERE document_id IS NULL` 唯一约束，保留原手册唯一约束与数据库级联外键。
5. `wiki.0010_retire_errcode_children`：再次比较完整 JSON 与八张旧子表，确认一致后删除，并加最终约束。逆向迁移先重建表，再从当前文档恢复子记录和报文父子关系。

数据转换逻辑冻结在迁移目录中，不导入可变的运行时模型或导入器。回退会重新分配附属行的数据库 ID，业务 ID 与内容保持一致；`facts` 保留新增的区间计数与顺序，不丢弃补充信息。生产切换须让旧代码与新结构停止交叉使用，详见实施记录。

测试入口：`PGWEB_TEST_DB=test_pgweb_reference manage.py test pgweb.wiki pgweb.search --noinput`，以及 `manage.py check`、`makemigrations --check --dry-run`。实际发布还需备份恢复、全量内容比较、固定快照重复导入、六来源索引及真实页面检查；表存在和 HTTP 200 不能代替数据验收。
