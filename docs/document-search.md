# PostgreSQL 文档检索

`/search/` 提供类似 Dash 的文档检索：左侧类别、中间即时结果、右侧定义预览；全站任意页面按 `/` 或 `⌘K` 打开同一套检索的弹窗版本。数据来自本站已有的 `docs` 表（PostgreSQL 手册）和 `pgext.universe`（扩展目录），查询在本站 PostgreSQL 数据库中完成，不依赖独立搜索服务或外部 API。

## 使用

| 输入或操作 | 效果 |
| --- | --- |
| `work_mem`、`逻辑复制槽` | 在当前版本手册与扩展目录中搜索名称、别名、定义和正文 |
| `postgis`、`向量` | 扩展目录条目与手册中的同名模块一起出现；扩展条目链接到 `/e/<名称>/` |
| `pg: work_mem` | 使用 `core_version.current` 指定的版本 |
| `pg17: work_mem` | 严格限定 PG17；支持已建立索引的 PG10–20，测试版和开发版有标记 |
| `ex: hnsw` | 只搜扩展目录（名称、包名、中英文简介、标签、分类） |
| `kind:guc 内存`、左侧类别 | 按类别筛选；`kind:` 接受类别键或更细的种类名（`operator`、`psql` 等） |
| `23505`、`unique_violation`、`->>`、`\d+`、`"逻辑复制"` | 错误码与条件名、运算符、psql 命令、连续短语 |
| 清空输入，选择类别 | 像字典一样按类别浏览 |
| `/search/?q=…&site=1` | 原有站内全文检索（新闻、活动、页面），`m=1` 仍是邮件列表检索 |
| 单击 / 方向键、回车 / 双击 | 预览定义、打开正文并定位锚点 |
| 预览里的版本行 | 与手册页顶部的版本链接同一风格，点击即切换到该版本的定义 |

### 范围标签

搜索框前面的范围（`PG 18`、`PG 17`、`扩展目录`）是一个可编辑的标签：光标在最前面按退格，标签退回成纯文本 `pg18:`，可以继续删改；输入 `pg17:` 或 `ex:` 再打一个空格，又变回标签。点击标签列出全部范围。没有标签时，文本里的前缀照常生效，没有前缀则用当前版本。检索页与弹窗共用这一逻辑（`createScopeField`），无 JS 时检索页退化为下拉框。

### 全站弹窗

- 宽屏（≥ 900px）：`/`、`⌘K`、点击页头搜索框或手册页内的搜索框，都会就地打开弹窗；页头的放大镜图标直接进入 `/search/`。在手册页打开时范围预填为正在阅读的版本。
- 什么都没输入时，弹窗列出十个类别（两列五行，带条目数与示例），点击进入检索页按类别浏览。输入后显示排好序的结果，≥ 1100px 时右侧同时显示定义预览；回车打开条目，`⌘↵` 或“完整检索页”进入 `/search/`。
- 兜底：结果列表末尾始终附三个动作——在手册全文中检索（`kind=guide`，即章节正文）、在站内新闻与页面中搜索（`/search/?site=1`，走原有 `site_search` 爬虫索引，仅在配置了 `SEARCH_DSN` 时显示）、在 postgresql.org 搜索。没有任何结果时它们成为首选项。检索页的空结果状态给出同样三个入口。
- 窄屏：页头只保留一个搜索按钮，点击直接跳到 `/search/`。
- 弹窗、检索页共用 `media/js/search-ui.js` 的结果行、范围标签、类别卡片、兜底动作与预览渲染；图标是 `templates/search/icons.html` 中的 SVG 雪碧图（Lucide）。

### 类别

界面只显示十个类别：配置参数、SQL 命令与语法、函数与运算符、数据类型、系统目录与视图、错误代码、命令行工具（`pg_dump` 等程序及其选项、连接参数与环境变量）、psql 命令（`\d+` 等反斜线元命令）、扩展与模块（手册附录中的模块、访问方法、过程语言，以及扩展目录）、章节正文。数据库里的 `kind` 仍是细粒度种类，类别到种类的映射在 `pgweb/search/taxonomy.py`，调整分组不需要重建索引。

## 数据与提取

两个可重建的派生表：

| 表 | 用途 |
| --- | --- |
| `search_indexedpage` | 手册页面外键、内容及提取器版本的摘要、索引时间 |
| `search_searchentry` | `source`（`pg` 手册 / `ext` 扩展目录 / `errcode` 错误代码）、版本、实体身份、种类、名称、别名、签名、正文片段、锚点、清洗后的预览 HTML、`url`、热度 `weight` 和 `tsvector` |

手册条目按结构提取：GUC 定义列表、函数与运算符表、类型表、错误码表、SQL reference、文档化的系统关系与章节标题；正文中偶然出现的函数名不会成为定义。长章节按结构拆分并保留标题路径。已有锚点优先，缺少锚点的定义用内容摘要生成 `SEARCH-*` 标识，阅读页使用同一生成函数，不改写 `docs.content`。

错误代码条目来自百科的 `wiki_errcode` 表（`source = 'errcode'`），与手册附录 A 的同一 SQLSTATE 共享实体：结果列表里只出现百科条目（链接到 `/docs/errcode/<代码>/`），预览是一句话说明、事实卡与「速览」，版本行仍列出各版手册的附录行。

扩展条目直接来自 `pgext.universe` 当前快照：名称与包名为别名，中英文简介、标签、分类和包名进入正文，预览是一张事实卡（版本、分类、语言、许可证、PG 版本范围、来源、`CREATE EXTENSION`），链接到本站扩展页。同名的手册模块与目录条目共享实体身份：结果列表里折叠为一条，手册定义优先，预览底部给出目录卡片。`weight` 取 `log1p(stars)` 归一化到 0–1，只在有搜索词时参与排序。

后续加入错误码补充数据、GUC 档案等来源时，沿用同一张表：新增一个 `source` 值、一段提取函数和对应的 `url`，不需要新表。

## 检索与排序

1. 解析前缀得到范围与类别；手册范围同时包含扩展目录，`ex:` 只含扩展目录。
2. 名称精确匹配、别名匹配、名称前缀、正文匹配四个层级依次排列。名称前缀层内短名称优先（`jsonb_set` 在 `jsonb_set_lax` 之前）；正文层按 `ts_rank_cd` 加扩展热度排序。
3. 同一实体的重载、多处定义与目录条目折叠为一条，预览提供其他签名、其他版本与目录卡片。
4. 没有结果时用 `pg_trgm` 在同一范围内给出名称相近的条目；纯符号与错误码不做模糊纠错。

中文用 jieba 加 PG 术语词典分词，英文与标识符用 `simple` 配置；名称、别名、签名与标题为高权重，简介为中权重，正文为低权重。

## 建立与更新索引

```bash
.venv/bin/python manage.py migrate search
.venv/bin/python manage.py index_docs                       # 全部已加载的 PG10+ 手册与开发快照 + 扩展目录
.venv/bin/python manage.py index_docs --versions 18         # 某个大版本，增量：未变化的页面跳过
.venv/bin/python manage.py index_docs --versions 18 --force # 提取规则变化后重建
.venv/bin/python manage.py index_docs --extensions          # 只重建扩展目录条目
.venv/bin/python manage.py index_docs --errcodes            # 只重建错误代码条目（tools/wiki/sync_errcode.py 之后）
.venv/bin/python manage.py index_docs --dry-run             # 只提取统计，不写入
```

- 手册：`tools/docs/docload.py` 导入有变化时会打印重建命令；数据库触发器在页面内容、标题、路径或版本变化时立即撤下旧索引，重建前该页面暂不出现在结果中。
- 扩展目录：`tools/ext/sync_catalog.py` 写入后会提示运行 `index_docs --extensions`；扩展条目整体替换，几千行在一个事务内完成。
- 修改分词或提取规则时递增 `extract.PIPELINE_VERSION` 再运行增量索引。迁移 0004 用 `ALTER COLUMN` 放开 `document_id`/`version` 的非空约束，保留 0002 设置的级联删除；回滚到 `search zero` 会删除派生索引，保留原手册与 `pg_trgm`。

## 验证

```bash
.venv/bin/python manage.py test pgweb.search pgweb.ext pgweb.docs --noinput
.venv/bin/python manage.py makemigrations --check --dry-run
node --check media/js/search-ui.js media/js/docsearch.js media/js/palette.js
```

已加载的版本自动进入范围列表；PG20 开发快照沿用 `docs.version = 0` 和 `/docs/devel/`，检索前缀为 `pg20:`，开发版本号集中维护于 `pgweb/docs/versions.py`。`/docs/20/` 跳转到开发快照。生产发布时先安装依赖、应用迁移并建立索引，再切换应用代码；若代理缓存了旧阅读页面，需刷新对应 `pgdocs_<版本>` 缓存以使生成的锚点生效。
