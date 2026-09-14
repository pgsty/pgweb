# Codex 任务书：SQL 命令栏目 `/docs/sql/`（一期）

你在 Django 项目 `/Users/vonng/pgsty/pgweb`（PostgreSQL 中文站 pgsql.cc）里实现百科的第五个栏目「SQL 命令」的一期：
一张表、导入链路、索引页、逐命令详情页、按版本看变更页、检索集成与测试。Python 一律用 `.venv/bin/python`。
临时文件放 `tmp/`（已在 .gitignore），不要用 `/tmp`。

## 先读什么（按顺序，读完再动手）

1. `docs/sqlcmd-column.md` —— 设计契约。表结构、快照形状、分组表、页面上下文的键名与措辞都在里面，逐键照做，不要改契约；
   发现契约有矛盾或做不到的地方，按配置参数栏目的做法办，并在汇报里写明。
2. 配置参数栏目是你的范本，整份读完：`docs/guc-column.md`、`pgweb/wiki/models.py` 末尾「配置参数」一节、`pgweb/wiki/guc_common.py`、
   `pgweb/wiki/guc_importer.py`、`pgweb/wiki/guc.py`、`pgweb/wiki/views.py` 的「配置参数」一节、`urls.py`、`struct.py`、`columns.py`、
   `pgweb/wiki/management/commands/wiki_import_guc.py`、`tools/wiki/sync_guc.py`、`templates/wiki/guc_*.html`、`media/css/wiki.css` 的「配置参数」一节、
   `media/js/wiki.js`、`pgweb/search/indexer.py` 的 `guc_entry / rebuild_guc`、`pgweb/search/service.py`、`pgweb/search/taxonomy.py`（`normalize_name`）、
   `media/js/search-ui.js`、`pgweb/wiki/test_guc.py`、`pgweb/wiki/test_guc_importer.py`。
3. 手册参考页长什么样：用 `manage.py shell` 取 `DocPage(file='sql-createtable.html', version=18).content` 与 `DocPage(file='sql-commands.html', version=18).content`，
   看 `div.refentry / refnamediv / refsynopsisdiv pre.synopsis / refsect1` 的结构；再看一条 DML（`sql-insert.html`，有「输出」小节）和 devel（`version=0`）的 `sql-waitfor.html`。

## 约定（务必遵守）

- 共享文件只做追加式修改：先读再用精确字符串替换，不整文件重写，不改别人的段落，不 reformat。共享文件指
  `models.py / views.py / urls.py / struct.py / columns.py / pgweb/util/contexts.py / pgweb/search/{indexer,service}.py / index_docs.py / media/css/wiki.css / media/js/wiki.js / media/js/search-ui.js / docs/document-search.md`。
- 迁移手写为 `pgweb/wiki/migrations/0005_sqlcmd.py`，依赖 `('wiki', '0004_waitevent')`，只含 `SqlCommand` 一个模型；写完跑
  `manage.py makemigrations --check --dry-run wiki` 确认无差异。不要对整个项目跑 `makemigrations` 后直接采用生成结果。
- CSP 禁止内联样式与内联脚本：模板里不能有 `style=`、`on*=`、内联 `<script>`；颜色、宽度、状态一律走 class。
- 站内 legacy CSS 会干扰：`base.css` 里 `.btn` 有固定宽度与自动外边距、`code` 的字号与颜色带 `!important`、`#pgContentWrap h2` 后面画一条横线、`table` 有默认样式；新组件要显式抵消（照 wiki.css 里 `guc-` 段的做法）。
- 测试库名走环境变量：`PGWEB_TEST_DB=test_pgweb_sql .venv/bin/python manage.py test … --noinput`。测试写在新文件 `pgweb/wiki/test_sqlcmd.py`（页面与取数）与 `pgweb/wiki/test_sqlcmd_importer.py`（导入），不要动 `tests.py`。
- 本地起服务只用 `127.0.0.1:8779`，无头 Chrome 只用调试端口 `9380–9385`。跑完把进程停掉。
- 不要 `git commit`，不要 ssh 生产，不要改 `CLAUDE.md`。

## 任务

### 1. 模型与迁移

按契约 §2 在 `pgweb/wiki/models.py` 末尾追加「SQL 命令」一节：`SqlCommand` 模型，以及常量 `SQLCMD_GROUPS`（十七个分组，slug / 中文 / 英文眉题，按契约顺序）、
`SQLCMD_GROUP_LABEL / SQLCMD_GROUP_ORDER / SQLCMD_GROUP_BY_SLUG`、`NAME_GROUP`（按命令全称归组）、`OBJECT_GROUP`（按对象名归组）、
`SECTION_KEYS`（中英小节标题 → key）、`sqlcmd_group_of(name)`、`sqlcmd_split(name) -> (verb, object)`、`sqlcmd_slug(name)`。
模型属性：`url`、`group_label`、`eyebrow`（'SQL COMMAND'）。写 `0005_sqlcmd.py`。

### 2. 导入链路

`pgweb/wiki/sqlcmd_importer.py`：契约 §3 的全部（版本清单、目录与逐页解析、身份归一与改名、HTML 清洗与链接改写、小节 key 映射、
`sections_same_as` 去重、语法概要逐行 diff、`changes / changed_in / present_in / related / position`、`validate / preview / import_snapshot / digest`、报告）。
可以 `from .catalog_importer import Manual, text_of` 复用；bleach 与 bs4 已装。一期不做 `--fetch`，但参数与报告字段先留出来（未实现时报告 `harvest.upstream = {'fetched': False}`）。
`pgweb/wiki/management/commands/wiki_import_sqlcmd.py` 与 `tools/wiki/sync_sqlcmd.py` 与 GUC 同形（远端命令改 `tools/wiki/sync_sqlcmd.py`，提示改 `index_docs --sqlcmd`）。

### 3. 取数、视图、路由、检索

`pgweb/wiki/sqlcmd.py`：契约 §4 的 `index / detail / changes / compare / versions / default_major / pick_major / doc_pages / forget` 等，与 `guc.py` 同名同义，缓存 5 分钟（键前缀 `pgweb:wiki:sqlcmd-`）；
版本清单不建表，从 `pgweb.core.models.Version` + `DocPage` 收录情况 + 库里的 `present_in` 现算并缓存；索引页查询 defer 大 JSON 列。
`views.py` 追加「SQL 命令」一节四个视图（别名 301 带 `?v=`），`urls.py` 四条路由（`changes/` 在 `<slug>/` 之前，slug 正则 `^[a-z][a-z0-9-]*$`），`struct.py`、`columns.py`（第五项 + `url()`/`nav_items()` 对空 `origin` 的处理 + docstring）、`contexts.py` 的 `LOCAL_ONLY_SECTIONS`。
检索：`indexer.py` 加 `sqlcmd_entry / rebuild_sqlcmd`（契约 §6），`index_docs.py` 加 `--sqlcmd`（无参时也跑），`service.py` 来源元组与排序偏好加 `'sqlcmd'`，`search-ui.js` 同等对待，`docs/document-search.md` 加一句。

### 4. 前端

`templates/wiki/sqlcmd_index.html / sqlcmd_table.html / sqlcmd_detail.html / sqlcmd_changes.html`，`wiki.css` 末尾「SQL 命令」一节（前缀 `cmd-`，新增 `--c-sql` 与 `.wiki-tone-sql`），`wiki.js` 末尾一个 `wireFilter` 调用。
结构与视觉要求见契约 §5；骨架、密度、版本变动方格、版本药丸、事实卡、时间线都照配置参数栏目，重点把两样东西做好：
（a）详情页的**语法概要**：等宽、保留手册换行、占位符斜体，本版新增的行左缘带绿色标记并可展开看被移除的行；
（b）`.cmd-doc` 里手册小节（参数用 `dl.variablelist`、示例用 `pre.programlisting`、提示框）读起来要像手册页本身一样舒服，亮暗两套。

### 5. 测试

- `test_sqlcmd_importer.py`：用手工构造的 3 个版本 × 5 条命令的假 `DocPage`（含一条改名、一条新增、一条移除、一条语法概要变化、一条只改正文），测身份归一、slug 与别名、分组与 verb/object、小节 key 映射、HTML 清洗与三种链接改写、`sections_same_as` 去重、概要 diff、`changes / changed_in / related / position`、`validate` 缺字段报错、import 幂等与 prune。
- `test_sqlcmd.py`：造 18 个版本条与 5 条命令的夹具，测 index 的 groups/rows/strip（span 之和等于版本数）/filters、detail 的 facts/synopsis 行标记/sections 指针解析/ribbon/timeline/change_note 措辞/related/siblings、changes 的 summary 与基线、视图 200 / 别名 301 / changes 302 / 404、queryparams 生效、`sqlcmd_entry` 形状与 `rebuild_sqlcmd` 计数。

### 6. 真跑一遍并核验

1. `manage.py migrate wiki`。
2. `tools/wiki/sync_sqlcmd.py --export tmp/sqlcmd-snapshot.json.gz`，再 `--input tmp/sqlcmd-snapshot.json.gz --write`；第二次 `--write` 必须全部 unchanged。
3. `manage.py index_docs --sqlcmd`。
4. 起 `runserver 127.0.0.1:8779`，用 curl 核对：`/docs/sql/` 200、`/docs/sql/create-table/` 200、`/docs/sql/createtable/` 301、`/docs/sql/create-table/?v=10` 200、`/docs/sql/wait-for/` 200、`/docs/sql/nosuch/` 404、`/docs/sql/changes/` 302、`/docs/sql/changes/15/`、`/docs/sql/changes/10/`、`/docs/sql/changes/20/`、`/docs/sql/changes/18/?from=12` 200；再逐个 curl 全部命令详情页，非 200 的列出来。
5. 无头 Chrome 截图（1280 与 390 两档，亮暗两套）：索引、`create-table` 详情、`merge` 详情（15 新增）、`changes/15/`；看着截图修样式至少两轮，截图放 `tmp/sqlcmd-shots/`。
6. 全量测试：`PGWEB_TEST_DB=test_pgweb_sql .venv/bin/python manage.py test pgweb.wiki pgweb.search --noinput`。

## 汇报

用几段话写清：新建 / 修改了哪些文件（共享文件说明改了哪几处）；测试命令与结果；导出报告的 `harvest`（每版命令数、小节定位统计、去重比例、`orphans`、`unmapped_groups`、`renamed`）；
库里行数与表大小；curl 状态码表、`index_docs --sqlcmd` 计数、索引页 HTML 大小与详情页查询数；截图路径；契约上有出入的地方；遗留问题。
