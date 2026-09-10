# tools/info — 博览候选抽取

把每天的中文技术日报、pgnexus 每日更新、postgresql.org 新闻和 Planet PostgreSQL 拆成
结构化候选，供编辑模型按 [CURATION.md](CURATION.md) 产出 `data/info/YYYY-MM-DD.json`；
批次文件写完再用 `enrich.py` 补最终链接与配图。栏目设计见
[docs/info-column.md](../../docs/info-column.md)。

| 脚本 | 作用 | 依赖 |
| --- | --- | --- |
| [`extract_daily.py`](extract_daily.py) | 解析当天日报，产出候选 | 标准库 |
| [`fetch_pgnexus.py`](fetch_pgnexus.py) | 取 pgnexus 某一期并解析 | 标准库（`--source cdp` 另需 Chrome） |
| [`chronicle.py`](chronicle.py) | 一段日期内四路来源合并去重、解析链接，逐日写候选 | 标准库 + Django（只读本地库） |
| [`enrich.py`](enrich.py) | 批次文件的链接解析与一档配图补全 | 标准库 |
| [`publish.py`](publish.py) | 校验并导入批次文件到本地或生产 | 标准库 |

只有 `chronicle.py` 读数据库（`news_newsarticle`、`core_importedrssitem`、
`pgext.universe`），而且只读不写；其余脚本都不碰数据库。

## 用法

```bash
# 解析日报，写默认候选文件
tools/info/extract_daily.py 2026-09-10

# 指定输出，并附上 pgnexus 第 264 期
tools/info/extract_daily.py 2026-09-10 --pgnexus 264 --out /tmp/c-2026-09-10.json

# 让工具按日期自己查 pgnexus 任务号（先试当天，再试前一天）
tools/info/extract_daily.py 2026-09-10 --pgnexus auto

# 单独取 pgnexus
tools/info/fetch_pgnexus.py --list             # 最近 30 期的日期与任务号
tools/info/fetch_pgnexus.py 264 --date 2026-09-09
tools/info/fetch_pgnexus.py 264 --source cdp   # 强制走 headless Chrome

# 回填：一段日期内四路来源合并去重，逐日写候选
.venv/bin/python tools/info/chronicle.py 2026-03-01 2026-09-10 --stats

# 批次文件写完之后：解析链接、补一档配图
.venv/bin/python tools/info/enrich.py data/info/2026-09-10.json
```

`extract_daily.py` 参数：

| 参数 | 说明 |
| --- | --- |
| `DATE` | `YYYY-MM-DD`，对应 `~/pgsty/daily/DATE.md` |
| `--daily-dir DIR` | 日报目录，默认 `~/pgsty/daily` |
| `--file PATH` | 直接指定日报文件 |
| `--out FILE` | 输出路径。默认目录取 `$INFO_CANDIDATES_DIR`，未设置时用会话 scratchpad 的 `info/`，再退回系统临时目录；文件名 `candidates-DATE.json`，目录会自动创建 |
| `--pgnexus JOBID` | pgnexus 任务号，或 `auto` |
| `--pgnexus-lang zh\|en` | pgnexus 语言，默认 `zh` |
| `--pgnexus-source auto\|api\|cdp` | 默认 `auto`：先试内容 API，失败退回 headless Chrome |
| `--quiet` | 不打印统计行 |

运行完会打印一行统计，例如：

```
2026-09-10  highlight=0 brief=10 feature=9 pgnexus=28  total=19  (raw 9/19/9)  -> …/candidates-2026-09-10.json
```

`raw` 是去重前的三段条数；去重后一条事件只留一条候选（见下）。

## 输出结构

```jsonc
{
  "meta": {
    "date": "2026-09-10",
    "window": "截稿：… 覆盖 2026-09-08 20:39 至 2026-09-10 08:38 CST：…",
    "counts":     { "highlight": 0, "brief": 10, "feature": 9, "pgnexus": 28, "total": 19 },
    "raw_counts": { "highlight": 9, "brief": 19, "feature": 9 },
    "source_file": "/Users/vonng/pgsty/daily/2026-09-10.md",
    "pgnexus": { "jobid": "264", "source": "api", "page_date": "2026-09-09", "groups": {…}, "warnings": [] }
  },
  "candidates": [ … ],
  "pgnexus":    [ … ]     // 只有传了 --pgnexus 才有
}
```

每条候选：

| 字段 | 说明 |
| --- | --- |
| `section` | `highlight`（一、今日重点）/ `brief`（二、简讯）/ `feature`（三、重磅新闻）；pgnexus 条目为 `pgnexus` |
| `group` | 所属 `###` 小标题，没有则为空串 |
| `tag` | 行首方括号里的原始标签串，如 `PostgreSQL 扩展安全 / 高 / 立即行动` |
| `importance` | `高` / `中高` / `中` …；重磅取「重要性评级」 |
| `title` | 重点条目的加粗句、重磅条目的小标题、简讯条目的正文句；已去掉 markdown 标记和句末标点 |
| `text` | 该条的完整文字，链接展平成文字，无 `[]()` 语法 |
| `links` | `[{"label","url"}]`，只保留绝对 http(s) 链接，按出现顺序去重 |
| `primary_url` | 首选一手链接：跳过 HN 与搜索结果页；没有链接时为空串 |
| `publisher` | 简讯取尾部 `发布方 / 日期 / 链接` 的第一段；其余从链接标签推断（`公告`、`来源`、`讨论` 等泛称会被丢弃） |
| `date` | 原文日期 `YYYY-MM-DD`；来自尾部日期、链接 URL 里的日期或正文中的 ISO 日期，取不到为空串 |
| `hn` | `{"url","points","comments"}`，points/comments 是整数或 `null`；没有 HN 链接时为 `null` |
| `tags` | 标签串按 `/` 拆开；重磅条目取「分类标签」 |
| `in_sections` | 这条事件在日报里出现过的版块，如 `["feature","highlight","brief"]` |
| `also_in` | 去重时被折叠掉的同一事件，`[{"section","group","title","text"}]` |

重磅条目额外带：

- `fields`：`分类标签` / `来源` / `HN` / `points/comments` / `讨论焦点` / `重要性评级` / `为什么重要` / `摘要` / `对用户的潜在影响` 的原文（已清理 markdown）。
- `summary`：`fields["摘要"]` 的快捷方式。

pgnexus 条目额外带 `author`（技术博客的署名）与 `participants`（邮件线程的参与者邮箱）。

**去重**：同一 `primary_url` 如果跨版块出现（重点 + 简讯 + 重磅通常是同一件事），
只保留最丰富的一条（重磅 > 重点 > 简讯，同级取正文更长的），其余进 `also_in`，
缺失的 `date` / `publisher` / `importance` / `hn` 会从被折叠的条目补齐。
同一版块内多条引用同一公告的简讯（同一件事的不同事实）会全部保留。

## pgnexus

`https://pgnexus.ai/daily-updates?jobid=N` 是客户端渲染的 Next.js 页面，两条取数路径：

1. **api**（默认先试）：`/api/daily-updates/content?jobid=N&language=zh` 直接返回带链接的
   Markdown，最完整也最快。`/api/daily-updates/list` 提供日期↔任务号对照，`auto` 就靠它。
2. **cdp**（退路）：headless Chrome（调试端口 9343、临时 profile、导航后等 6 秒）读
   `document.body.innerText`，同时用 `document.querySelectorAll('a')` 收集 href 与标题做匹配。
   需要 `websocket-client`：脚本会把 `$PGWEB_PYLIB` 和会话 scratchpad 的 `pylib/` 加进
   `sys.path`。这条路径拿不到空标题条目的链接，条数可能比 api 少一两条。

pgnexus 第 N 期覆盖的是**前一天**，所以 `--pgnexus auto` 找不到当天就取前一天，
并在 `meta.pgnexus.warnings` 和 stderr 里说明日期不一致。

`chronicle.py` 不用这条「前一天」规则：它按每期页面 H1 里的日期归档，第 N 期属于
H1 上写的那一天。

## chronicle.py — 逐日编年候选

回填历史时日报不够用：日报只从 2026-05-06 开始，而 pgnexus、postgresql.org 新闻和
Planet PostgreSQL 覆盖得更早也更全。`chronicle.py` 把四路来源按天合并、去重，把所有
链接跟随跳转解析到最终地址，范围内**每天写一个候选文件**（当天没有候选也写空文件）。

```bash
# 回填 2026-03-01 到 2026-09-10，并打印逐日、逐月统计
.venv/bin/python tools/info/chronicle.py 2026-03-01 2026-09-10 --stats

# 只重做最近十天，链接强制重新解析
.venv/bin/python tools/info/chronicle.py 2026-09-01 2026-09-10 --refresh-links
```

| 参数 | 说明 |
| --- | --- |
| `START END` | 起止日期（含两端），`YYYY-MM-DD` |
| `--out-dir DIR` | 输出目录，默认 `tmp/info/chronicle` |
| `--refresh-links` | 忽略链接缓存重新解析 |
| `--recheck-dead` | 只把缓存里疑似被限流/超时的失效链接再试一次 |
| `--refresh-pgnexus` | 重新抓取 pgnexus markdown |
| `--stats` | 打印逐日一行统计和逐月 min/median/max |
| `--quiet` | 不打印进度 |

四路来源：

| `source` | `section` | 来自 | 说明 |
| --- | --- | --- | --- |
| `daily` | `highlight` / `feature` / `brief` | `~/pgsty/daily/DATE.md` | 复用 `extract_daily.parse_daily`，保留 `importance`、`hn_points`、`tags`；`feature` 的正文只留「摘要 / 为什么重要 / 对用户的潜在影响」 |
| `news` | `news` | 本地 `news_newsarticle`（`modstate=2`） | 标题与正文已是中文，正文转纯文本截到 600 字；`url` 取正文里第一个非 postgresql.org 的链接（即发布方自己的页面），`via` 是 postgresql.org 的新闻页 |
| `pgnexus` | `blog` / `industry` / `hackers` | `tmp/info/pgnexus/<期号>.md` | 按页面 H2 分组归类：技术博客、行业新闻、hackers 邮件讨论 |
| `planet` | `planet` | 本地 `core_importedrssitem`（`planet` 源） | 标题形如 `作者：标题`，拆成 `author` 与 `title`；`postgr.es/p/xxx` 短链解析成文章原址 |

候选字段：`id`（当天序号 `d001`）、`source`、`section`、`group`、`title`、`text`
（纯文本，≤ 500 字，新闻 ≤ 600）、`url`（最终地址）、`via`（解析前或另一来源的地址，
没有就不出现）、`dead`、`publisher`、`author`、`date`、`importance`、`hn_points`、
`tags`、`pg`、`also`（合并掉的其他来源标题）。`pg` 是粗判：正文命中
PostgreSQL/Postgres/`pg_`/psql/pgsql/PGDG 等词、标签命中 `pgext.universe` 里的扩展名，
或来源本身是 pgnexus / 新闻 / Planet 时为 true。

文件按一条候选一行写出，方便扫读：

```jsonc
{
 "date": "2026-09-09",
 "sources": {"daily": true, "pgnexus": 264, "news": 2, "planet": 4},
 "candidates": [
  {"id": "d001", "source": "daily", "section": "feature", "title": "…", …},
  …
 ],
 "repeats": [
  {"title": "…", "url": "…", "first_seen": "2026-09-08"}
 ]
}
```

排序（组内保持原顺序）：日报重点与重磅 → postgresql.org 新闻 → pgnexus 技术博客与
行业新闻 → Planet 博客 → pgnexus hackers 讨论 → 日报简讯。

去重分两层：

- **同一天**：`url` 或 `via` 归一化后相同的候选合并成一条，正文取最长的一份，标签取并集，
  `importance` 和 `hn_points` 优先用日报那条，其他来源的不同标题进 `also`。
  保留的链接失效而同组里有能打开的，就换成能打开的那个。
- **跨天**：某个链接第一次出现的那天算候选，之后各天只在 `repeats` 里列出
  （标题、链接、首次出现的日期）。多日延续的邮件线程、被反复引用的公告都靠这条收敛。

两处缓存都在 `tmp/`（已被 gitignore）：

- `tmp/info/pgnexus/<期号>.md`：第 60 期到最新一期的 markdown，只抓一次。早期几期
  （`source=file`）按期号取会 404，工具会自动改用列表接口给的 `filename` 再取一次。
- `tmp/info/links.json`：`{原链接: {"final","status","checked"}}`。HEAD 请求跟随跳转，
  405/403 之类退回 GET，超时 15 秒、16 线程；去掉 `utm_*`、`ref`、`fbclid` 参数；
  状态码 ≥ 400 或请求失败记 `dead: true`。HN 讨论页和搜索结果页不解析。
  高并发下站点会限流，所以本轮新解析的链接里状态是 0/403/408/429/5xx 的会用 1/4 并发
  再试一遍；缓存里已有的这类结果要重试得加 `--recheck-dead`。

## enrich.py — 批次文件补链接与配图

编辑写完 `data/info/DATE.json` 之后跑一遍，只改 `url` 和 `image`，绝不动
`title` / `summary` / `tier` / `position`。

```bash
.venv/bin/python tools/info/enrich.py data/info/2026-09-10.json
.venv/bin/python tools/info/enrich.py data/info/2026-09-*.json --dry-run
.venv/bin/python tools/info/enrich.py data/info/2026-09-10.json --missing-images tmp/info/need-image.jsonl
```

1. **链接**：每条 `url` 用与 `chronicle.py` 相同的缓存和规则解析到最终地址，变了就改写；
   失效链接只在报告里列出，不删条目（要不要换链接由编辑决定）。
2. **配图**：`tier: 1` 且 `image` 为空的条目，抓原文页面的 `og:image`、`twitter:image`、
   `og:image:secure_url`（按这个顺序），只接受 https、能返回 200 且 `content-type` 是
   `image/*` 的地址。[`generic-images.txt`](generic-images.txt) 里的片段按小写子串匹配，
   命中就跳过：站点通用标志、栏目默认社交图、头像都不算题图，遇到新的默认图往里加一行。

报告按文件一行：链接改写数、失效数、补图数、一档仍缺图数，末尾一行合计。
`--dry-run` 照常联网和统计，但不写回文件、不追加清单。
`--missing-images FILE` 把仍缺配图的一档条目按行追加成 JSONL（`date`、`key`、`title`、
`url`），`key` 与导入器一致（`sha1(date + "|" + url)[:16]`），供之后统一生成配图。

## 每天怎么走

```
~/pgsty/daily/YYYY-MM-DD.md ─┐
                              ├─ extract_daily.py ─► 候选 JSON ─► 编辑（模型）
pgnexus 每日更新（可选）──────┘                                    │
                                                                   ▼
                                          data/info/YYYY-MM-DD.json
                                                                   │
                                            manage.py info_import ─┴─► 本地与生产
```

1. **抽取**：日报落盘后（约 08:30）跑
   `tools/info/extract_daily.py $(date +%F) --pgnexus auto`。
2. **编辑**：把候选 JSON 和 [CURATION.md](CURATION.md) 一起交给编辑模型，产出
   `data/info/YYYY-MM-DD.json`。挑选时的经验：
   - `in_sections` 含 `highlight` 或 `feature` 的通常是一档；`feature` 条目的
     `fields["摘要"]`、`fields["为什么重要"]`、`fields["对用户的潜在影响"]` 是写一档摘要的素材，
     但要按 CURATION.md 重新组织，不逐句翻译。
   - 只在 `brief` 里出现的多半是二档；版本小更新、会议通知、单条工具发布是三档。
   - `primary_url` 直接做 `url`；`publisher` → `source`，`date` → `source_date`，
     一档的 `author` 从正文或发布机构补。没有 `primary_url` 的候选不能升为一、二档。
   - `hn.points` 只作热度参考，不写进条目文字。
   - pgnexus 的技术博客可补 PostgreSQL 条目；邮件线程与补丁讨论一般不单独成条，
     除非是已提交的重要特性或回退。
3. **补全**：`tools/info/enrich.py data/info/$(date +%F).json` 解析链接、补一档配图。
4. **导入**：`tools/info/publish.py YYYY-MM-DD --check` 先校验（标题 ≤ 40 字、一档摘要
   长度、档位与编号顺序），通过后去掉 `--check` 写本地；`--target production` 把同一
   文件经 `ssh pg` 送到生产导入，不依赖代码是否已拉取。批次文件随后提交进仓库。
   导入按 `key` 幂等，重复运行只报 `unchanged`；`--hide-missing` 撤下该日批次里已删除的条目。
   首页「博览」区块与导航缓存 5 分钟，无需重启服务。

回填历史用另一条路：先 `chronicle.py START END --stats` 一次性生成整段日期的候选，
按统计把日期分片交给多个编辑模型（各自只写自己的批次文件），主会话统一 `enrich.py`
补全、`publish.py --check` 校验、导入并提交。

## 缩略图

一档条目的缩略图存在 `data/info/img/<key>.webp`（500 × 300），导入时读进 `info_item.thumb`，页面从 `/info/img/<key>.webp` 取。

```bash
tools/info/thumbs.py fetch 2026-09-10                 # 下载 image 字段的原图，裁成 5:3 转 WebP
tools/info/thumbs.py missing --out tmp/info/need-image.jsonl   # 仍缺图的一档清单
tools/info/gen_thumbs.py tmp/info/need-image.jsonl    # 用 Codex 图像工具按统一风格生成（约 1 分钟/张）
tools/info/thumbs.py orphans --delete                 # 删除已无条目的缩略图
```

`gen_thumbs.py` 依赖本机 `codex`（ChatGPT 登录、`image_generation` 功能）与 `magick`。风格约束写在脚本的 `STYLE` 里：扁平矢量、PostgreSQL 大象蓝配色、无文字、无标志、无真人。

## 已知限制

- **不做网络核实**：脚本只解析日报文本，日期、发布方、HN 热度都照抄原文；日报本身
  写错，候选就跟着错。
- **`publisher` 是启发式的**。简讯的尾部字段最准；重点和重磅从链接标签推断，
  会出现 `HN`、`GitHub Release`、`Project` 这类不适合直接写进 `source` 的值，编辑要复核。
- **`date` 可能缺**。5826 条历史候选里约 15% 没有日期（原文没写、链接里也没有日期）。
- **HN 热度经常缺**。全量 5826 条候选里 3551 条带 HN 链接，其中约一半没有
  points/comments：5–7 月缺失率 54–62%，8 月 34%，9 月已降到 10%。`hn.points` 为
  `null` 只表示日报没写，不代表没有讨论。已识别的写法：`148 / 49`、
  `（采集时约 150 / 208）`、`718 points、377 comments`、`11 points / 0 comments`、
  `在 HN 获 485/90`。
- **早期「今日重点」没有标签和加粗**（2026-07 中旬之前），此时 `tag`、`importance` 为空，
  `title` 退化为正文第一句，可能偏长；这些条目往往也没有链接，只能当线索用。
- **简讯里的元条目会被当成候选**：如「本窗口没有 PostgreSQL 核心版本」「已扫描 HN New」
  这类过滤说明也会出现在候选里，编辑直接跳过即可。
- **去重只看 `primary_url`**。同一件事若在不同版块用了不同链接（官方公告 vs. 媒体转述），
  仍会是两条候选，需要编辑合并。
- **pgnexus 需要联网**；`--source cdp` 还需要本机 Chrome 和 `websocket-client`。
- 输出默认落在临时目录，不进仓库；批次文件才进 `data/info/`。

`chronicle.py` / `enrich.py` 另有几条：

- **链接状态是抓取当时的快照**。缓存不会自动过期，`dead: true` 仍可能只是当时被限流或
  挡了 UA（openai.com、postgr.es 这类站点在高并发下尤其明显），要复核用
  `--recheck-dead`，整段重来用 `--refresh-links`。反过来，返回 200 的软 404 页面
  （站点自己渲染的「页面不存在」）识别不出来。
- **`text` 是原文素材，不是可以直接用的中文摘要**：日报条目是中文，pgnexus 是机翻中文，
  新闻是人工中文，Planet 只有标题。一档摘要仍要按 CURATION.md 重新组织。
- **跨天去重按链接**，同一件事换了链接（官方公告 vs. 媒体转述）仍是两条，需要编辑合并；
  没有链接的候选（日报里的元条目）永远不会被判为重复。
- **日报「今日重点」几乎都没有链接**（5 月 158 条里 0 条有链接，6–8 月每月只有 7–8 条），
  它们是当天的导语，内容多半在下面的「重磅新闻」里重复出现。排序时仍放在最前面，当成
  「日报编辑认为今天什么重要」的索引读，真正可引用的链接去 `feature` 和 `brief` 里找。
- **`og:image` 不一定是题图**：很多站点回落到全站默认图，`generic-images.txt` 只挡得住
  已经见过的那些，补进来的图仍需扫一眼。
