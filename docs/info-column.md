# 博览（/info）实施方案

状态：2026-09-10 定稿，据此实施。本文取代 [digest-prd.md](digest-prd.md) 中与之冲突的决定；PRD 里未被本文提到的机制（每日额度校验、封面制作流水线、撤下/恢复状态机、主站 SQL 级搜索隔离、独立 sitemap 策略）首版不做。

## 1. 定义

「博览」是 pgsql.cc 自己编辑的中文资讯栏目：每天 10–30 条，以 PostgreSQL 为主，兼顾数据库与云计算。地址 `/info/`。它有独立的全文检索，不进入文档检索和搜索弹窗。

三档条目：

| 档 | 名称 | 内容 | 展示 |
| --- | --- | --- | --- |
| 1 | 大新闻 | 中文标题、一段摘要（一个完整自然段，80–300 字）、原文链接、作者、发布方、原文日期、可选配图 | 标题直接外链原文；右侧 5:3 小图；下方作者 · 发布方 · 日期 |
| 2 | 小新闻 | 中文标题、一句话说明（≤ 80 字）、原文链接 | 标题外链，后随一句说明；不配图 |
| 3 | 迷你 | 仅标题，可带链接 | 一行一条的紧凑列表，不带作者与说明 |

排序：栏目按日期倒序；同一天内按档位（1 → 2 → 3）再按编辑给定的 `position`。每一天是一个自然的阅读单元。

## 2. 数据：一张表

应用 `pgweb/info`，模型 `InfoItem`，表 `info_item`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `key` | char(16) unique | 稳定标识：`sha1(date + "|" + url 或 title)[:16]`，导入器计算；两端一致 |
| `date` | date | 归档日（Asia/Shanghai），来自批次文件 |
| `tier` | smallint | 1 / 2 / 3 |
| `position` | smallint | 当日内顺序 |
| `title` | text | 中文标题 |
| `summary` | text | 一档为一段，二档为一句，三档为空 |
| `url` | text | 原文链接；一、二档必填 |
| `author`, `source` | text | 作者、发布方；一档必填，其余可空 |
| `source_date` | date null | 原文日期 |
| `image` | text | 一档可选配图地址（外链，不落盘） |
| `domain` | char(8) | `pg` / `db` / `cloud` / `infra` / `ai` |
| `tags` | text[] | 少量主题词 |
| `status` | char(10) | `published` / `hidden`；只有 published 对外可见 |
| `origin` | jsonb | 批次文件名、来源报告等后台信息 |
| `published_at`, `updated_at` | timestamptz | 首次导入时间、最近更新时间 |
| `search_vector` | tsvector | 标题 A、摘要 B、作者/发布方/标签 C，用 `pgweb.search.lexicon.index_text` 预分词 |

索引：`key` 唯一；`(status, date DESC, tier, position)`；`search_vector` GIN。不再有第二张表。

## 3. 页面与地址

| 地址 | 页面 |
| --- | --- |
| `/info/` | 最新收录：按日倒序的信息流，每页 7 天，`?page=N` |
| `/info/YYYY-MM-DD/` | 每日更新：当天全部条目，三档分组；上一天 / 下一天（跳过无内容日） |
| `/info/daily/` | 302 到最近有内容的一天 |
| `/info/archive/` | 归档：按月列出有内容的日期与条数 |
| `/info/search/?q=` | 博览检索，每页 20 条 |
| `/info/rss/` | 最近 50 条一、二档条目 |

布局沿用站内内页：`container-fluid margin pg-page` 两栏，左侧 `.pg-sidecard`（搜索框 + 最近 30 天日期与条数 + 归档入口），右侧 `#pgContentWrap`。条目样式在 `media/css/info.css`，只用 `--pg-*` 令牌与现有排版规则（`.pg-prose` 的字号行高、酒红内容链接、外链图标）。三档的区别靠密度和字号，不用彩色卡片。

入口：顶部导航「博览」放在「首页」之后，下拉为 最新收录 / 每日更新 / 归档 / 搜索博览；页脚「社区」栏加「博览」；首页在「最新新闻」之前加一个「博览」区块，列出最近一天的大新闻标题（≤ 4 条，标题 + 一句摘要 + 发布方）和「更多」链接。搜索页、每日页、归档页对搜索引擎 `noindex`（信息流首页与每日页可收录）。主站爬虫（`tools/search/crawler`）跳过 `/info/` 路径。

## 4. 检索

`pgweb/info/search.py`：`plainto_tsquery('simple', query_text(q))` 对 `search_vector`，`ts_rank_cd` 加权，相关度相同按日期倒序；标题与摘要用与文档检索相同的 `highlight` 方式加 `<mark>`。结果行：档位标记、标题（外链原文）、命中片段、日期链接到 `/info/<date>/#<key>`。`manage.py info_index --rebuild` 可从正文重建全部向量。

## 5. 内容流水线

```
~/pgsty/daily/YYYY-MM-DD.md ─┐
                              ├─ tools/info/extract_daily.py ─► tmp 候选 JSON ─► 编辑（模型）─► data/info/YYYY-MM-DD.json ─► manage.py info_import ─► 本地与生产
pgnexus.ai 每日更新（可选）──┘
```

- `tools/info/extract_daily.py DATE`：确定性解析日报的「今日重点」「简讯」「重磅新闻」，输出候选（标题、链接、作者/发布方/日期、原文摘要、分类标签、HN 热度）；`--pgnexus JOBID` 用 headless Chrome 读取 pgnexus 页面文本，补充技术博客与 hackers 讨论候选。
- 编辑步骤由模型完成（Codex / Opus 均可），输入候选 JSON 与 `tools/info/CURATION.md` 的编辑规则，输出批次文件；批次文件进仓库 `data/info/`，本地和生产导入同一文件。
- `manage.py info_import data/info/2026-09-10.json`：按 `key` 幂等写入（新增 / 更新 / 不变），同时写 `search_vector`；`--hide-missing` 把该日批次里已不存在的条目置为 hidden。`--check` 只校验不写。
- `tools/info/publish.py DATE [--check] [--target production]`：包装 `info_import`；生产模式把文件经 `ssh pg` 送到远端临时目录用远端 Django 配置导入，与代码拉取无关。
- 日常：日报每天 08:30 落盘后运行一次 extract → 编辑 → publish（本地与生产），批次文件提交进仓库；操作步骤见 `tools/info/README.md`。

编辑规则（`tools/info/CURATION.md` 保存完整版）：每天 10–30 条；PostgreSQL 优先，其次数据库，再次云与基础设施；AI 内容只收开发者工具与基础设施相关；剔除营销稿、泛消费科技、无一手来源的传闻；条目不足时从 pgnexus 与日报「简讯」补数据库云与云数据库资讯，仍不足则宁少勿滥。一档摘要独立成段、不逐句翻译原文；标题 ≤ 40 字；中文与英文、数字间留空格；不写免责声明。

## 6. 实施与分工

| 阶段 | 内容 | 执行 |
| --- | --- | --- |
| A. 栏目 | `pgweb/info` 应用、迁移、视图、模板、样式、检索、`info_import` / `info_index`、导航与首页入口、爬虫排除、测试 | 代码模型 |
| B. 抽取 | `tools/info/extract_daily.py`、pgnexus 读取、`CURATION.md`、批次文件校验 | 代码模型（与 A 并行） |
| C. 回填 | 用 B 的候选为最近 30 天各生成一份批次文件；先做最近 7 天用于验收 UI | 多个编辑模型并行，按日期分片 |
| D. 验收 | 本地导入、页面与检索核验、桌面/手机/深色截图；生产 `migrate info` + 导入 + 重启 | 主会话 |
| E. 日常 | 每日流水线脚本与 crontab；AGENTS.md 记录操作 | 主会话 |

验收要点：三档展示正确；每日页与信息流顺序一致；检索能定位到当日锚点；`/info/` 不出现在文档检索和弹窗；生产与本地条目数一致。
