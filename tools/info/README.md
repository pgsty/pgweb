# tools/info — 博览候选抽取

把每天的中文技术日报（和可选的 pgnexus 每日更新）拆成结构化候选，供编辑模型按
[CURATION.md](CURATION.md) 产出 `data/info/YYYY-MM-DD.json`。栏目设计见
[docs/info-column.md](../../docs/info-column.md)。

两个脚本都只用 Python 3 标准库，不需要 Django，也不写数据库。

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
3. **导入**：`tools/info/publish.py YYYY-MM-DD --check` 先校验（标题 ≤ 40 字、一档摘要
   80–300 字、档位与编号顺序），通过后去掉 `--check` 写本地；`--target production` 把同一
   文件经 `ssh pg` 送到生产导入，不依赖代码是否已拉取。批次文件随后提交进仓库。
   导入按 `key` 幂等，重复运行只报 `unchanged`；`--hide-missing` 撤下该日批次里已删除的条目。
   首页「博览」区块与导航缓存 5 分钟，无需重启服务。

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
