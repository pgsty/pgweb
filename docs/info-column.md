# 博览（/info）实施方案

状态：2026-09-10 定稿，据此实施。本文取代 [digest-prd.md](digest-prd.md) 中与之冲突的决定；PRD 里未被本文提到的机制（每日额度校验、封面制作流水线、撤下/恢复状态机、主站 SQL 级搜索隔离、独立 sitemap 策略）首版不做。

## 1. 定义

「博览」是 pgsql.cc 自己编辑的中文资讯栏目：每天 20–40 条（一档 5–12 条），按与 PostgreSQL 的相关度排序，兼顾数据库与云计算。地址 `/info/`。它有独立的全文检索，不进入文档检索和搜索弹窗。

三档条目：

| 档 | 名称 | 内容 | 展示 |
| --- | --- | --- | --- |
| 1 | 大新闻 | 中文标题、一段摘要（150–220 字，约四行）、原文链接、作者、发布方、原文日期、5:3 配图（必有；暂缺的显示空位，待生成批次补齐） | 标题直接外链原文；下一行日期 · 作者 · 发布方；再下一行左侧固定位置放 5:3 配图，右侧摘要，无图时摘要占满整行 |
| 2 | 小新闻 | 中文标题、一句话说明（≤ 80 字）、原文链接 | 标题外链，说明另起一行；不配图 |
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
| `/info/rss/` | 每天一期：最近 30 天，每天一个条目，正文是当天三档全文（`content:encoded`），链接与 guid 指向当天页面；页面标题右侧有「RSS 订阅」按钮 |

布局沿用站内内页：`container-fluid margin pg-page` 两栏，左侧 `.pg-sidecard`（搜索框 + 「新闻博览」入口 + 最近 30 天日期与条数 + 归档入口），右侧 `#pgContentWrap`。条目样式在 `media/css/info.css`，只用 `--pg-*` 令牌与现有排版规则（`.pg-prose` 的字号行高、酒红内容链接、外链图标）。三档的区别靠密度和字号，不用彩色卡片。

入口：顶部导航「博览」放在最后（「支持」之后），下拉为 新闻博览 / PG 日报（下级列出最近 7 天与「日报归档」）/ 社区新闻 / 近期活动，日期由 `info_nav()` 按 5 分钟缓存生成；在博览页面按 `/` 聚焦博览搜索框而不是文档检索弹窗（⌘K 仍打开弹窗）；页脚不放「博览」；首页在「遇到异常行为」区块之后放一个「博览」区块：最近一天的全部条目按阅读顺序排成两栏紧凑列表（不分档、无配图、无摘要），标题外链原文，有摘要的条目带「详情」锚点链接到当天页面，下方是「查看当天详情」与「更多博览」。搜索页、每日页、归档页对搜索引擎 `noindex`（信息流首页与每日页可收录）。主站爬虫（`tools/search/crawler`）跳过 `/info/` 路径。

## 4. 检索

`pgweb/info/search.py`：`plainto_tsquery('simple', query_text(q))` 对 `search_vector`，`ts_rank_cd` 加权，相关度相同按日期倒序；标题与摘要用与文档检索相同的 `highlight` 方式加 `<mark>`。结果行：档位标记、标题（外链原文）、命中片段、日期链接到 `/info/<date>/#<key>`。`manage.py info_index --rebuild` 可从正文重建全部向量。

## 5. 内容流水线

```
~/pgsty/daily/YYYY-MM-DD.md ─┐
postgresql.org 新闻（本地库）─┤
Planet PostgreSQL（本地库）───┼─ tools/info/chronicle.py ─► tmp/info/chronicle/DATE.json ─► 编辑（模型）─► data/info/DATE.json ─► enrich.py ─► publish.py ─► 本地与生产
pgnexus.ai 每日更新 ──────────┘
```

- `tools/info/chronicle.py FROM TO`：把四类来源按天合并、去重（同一链接只归首次出现的那天，之后的天列入 `repeats`）、把链接解析到最终页面并标出失效链接，输出紧凑候选文件；`--stats` 打印每天各来源条数。来源覆盖：postgresql.org 新闻长期有；pgnexus 自 2026-03-04（#71，早期有缺号）；Planet 自 2026-03-14；本地日报自 2026-05-06。因此栏目从 2026-03-01 起回补，之前的日子只有零星新闻，不单独成天。
- `tools/info/enrich.py data/info/DATE.json`：把条目链接解析到最终地址、标出失效链接、为一档补 og:image（排除 `tools/info/generic-images.txt` 里的站点通用图）；`--missing-images 清单.jsonl` 列出仍无配图的一档条目。

- `tools/info/extract_daily.py DATE`：确定性解析日报的「今日重点」「简讯」「重磅新闻」，输出候选（标题、链接、作者/发布方/日期、原文摘要、分类标签、HN 热度）；`--pgnexus JOBID` 读取 pgnexus 每日更新，补充技术博客与 hackers 讨论候选。chronicle.py 内部复用这两个解析器。
- 编辑步骤由模型完成（Codex / Opus 均可），输入候选 JSON 与 `tools/info/CURATION.md` 的编辑规则，输出批次文件；批次文件进仓库 `data/info/`，本地和生产导入同一文件。
- `manage.py info_import data/info/2026-09-10.json`：按 `key` 幂等写入（新增 / 更新 / 不变），同时写 `search_vector`；`--hide-missing` 把该日批次里已不存在的条目置为 hidden。`--check` 只校验不写。
- `tools/info/publish.py DATE [--check] [--target production]`：包装 `info_import`；生产模式把文件经 `ssh pg` 送到远端临时目录用远端 Django 配置导入，与代码拉取无关。
- 日常：日报每天 08:30 落盘后运行一次 extract → 编辑 → publish（本地与生产），批次文件提交进仓库；操作步骤见 `tools/info/README.md`。

编辑规则（`tools/info/CURATION.md` 保存完整版）：每天 20–40 条、一档 5–12 条；按与 PostgreSQL 的相关度排序，PostgreSQL 优先，其次数据库，再次云与基础设施；AI 内容只收开发者工具与基础设施相关；剔除营销稿、泛消费科技、无一手来源的传闻；枯水期先放宽标准，再把前一两天没用上的候选匀过来，仍不足则宁少勿滥。链接直指最终内容页；一档摘要 150–220 字独立成段、不逐句翻译原文；标题 ≤ 40 字；中文与英文、数字间留空格；不写免责声明。导入器把一档 > 12 条、全日 > 45 条、摘要超长当作错误，把条数不足与缺配图当作警告。

## 6. 实施与分工

| 阶段 | 内容 | 执行 |
| --- | --- | --- |
| A. 栏目 | `pgweb/info` 应用、迁移、视图、模板、样式、检索、`info_import` / `info_index`、导航与首页入口、爬虫排除、测试 | 代码模型 |
| B. 抽取 | `tools/info/extract_daily.py`、pgnexus 读取、`CURATION.md`、批次文件校验 | 代码模型（与 A 并行） |
| C. 回填 | 用 B 的候选为最近 30 天各生成一份批次文件；先做最近 7 天用于验收 UI | 多个编辑模型并行，按日期分片 |
| D. 验收 | 本地导入、页面与检索核验、桌面/手机/深色截图；生产 `migrate info` + 导入 + 重启 | 主会话 |
| E. 日常 | 每日流水线脚本与 crontab；AGENTS.md 记录操作 | 主会话 |

验收要点：三档展示正确；每日页与信息流顺序一致；检索能定位到当日锚点；`/info/` 不出现在文档检索和弹窗；生产与本地条目数一致。

## 7. 缩略图

每条一档都有一张 500 × 300 的 WebP 缩略图，存在 `info_item.thumb`（bytea），由 `/info/img/<key>.webp` 提供（`Cache-Control: public, max-age=604800`）。源文件是 `data/info/img/<key>.webp`，随批次文件进仓库；导入器在写行时读取同名文件，文件变化算一次更新。批次文件的 `image` 字段只记录来源图地址，页面优先用本地缩略图，没有缩略图时退回 `image`，两者都没有时显示空位。

- `tools/info/thumbs.py fetch DATE…`：下载一档的 `image`，居中裁成 5:3、缩到 500 × 300、转 WebP；`missing … --out 清单.jsonl` 列出仍没有缩略图的一档；`convert 图片…` 把任意图片按文件名（= key）转成缩略图；`orphans [--delete]` 清理已无条目的缩略图。需要 ImageMagick。
- `tools/info/gen_thumbs.py 清单.jsonl [--batch 8 --parallel 4]`：把清单分批交给 `codex exec`，用 Codex 的图像工具（GPT Image）按统一风格（扁平矢量、大象蓝配色、无文字无标志）为每条生成 1536 × 1024 图，再裁成缩略图。每张约一分钟；失败的留到下次运行。
- `tools/info/relink.py`：把第三方公告从 postgresql.org 新闻页改到本站译文页（PostgreSQL 自身发布与安全公告保留）；`tools/info/dedupe.py`：跨天重复链接只留档位更高、日期更早的一条。回补后先 relink、dedupe，再 thumbs、gen_thumbs，最后 publish。
