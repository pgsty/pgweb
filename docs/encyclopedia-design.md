# 百科

百科是站点第三个内容栏目，与文档、博览并列，收纳"逐条查得到、每条有出处"的 PostgreSQL 参考资料。
首期做错误码大全，其后依次是配置参数、等待事件、系统目录。本文是设计方案，实施后改写为运维文档。

数据来自 `pgsty` 组织下四个独立仓库，由 Codex 会话按"造工具书"的标准产出：
每条事实锁定到具体 release tag、commit SHA 与文件行号，查不到就如实留空，不补齐、不推测。
这个诚实边界是这批数据最贵的部分，站点呈现必须原样保留，不能被漂亮的 UI 抹平。

## 1. 四个栏目的家底

上游是四个独立的双语站点，由 Pigsty 维护，本站的百科是它们的中文渲染。

| 栏目 | 上游站点 | 仓库 | 本地目录 | 条目 | 正文 |
| --- | --- | --- | --- | --- | --- |
| 错误码大全 | [err.pg.center](https://err.pg.center) | `pgsty/err.pg.center` | `~/pg.center/err` | 263 个 SQLSTATE，44 个类 | 82 full / 181 reference / 0 stub，双语配对 |
| 配置参数大全 | [guc.pg.center](https://guc.pg.center) | `pgsty/guc.pg.center` | `~/pg.center/guc` | 447 个参数 | 447 篇，9 节骨架零变体，双语配对 |
| 等待事件大全 | [wait.pg.center](https://wait.pg.center) | `pgsty/wait.pg.center` | `~/pg.center/wait` | 281 个事件 | 281 篇，7+1 节骨架，双语配对 |
| 系统目录大全 | [cat.pg.center](https://cat.pg.center) | `pgsty/cat.pg.center` | `~/pg.center/cat` | 157 个关系 × 17 个版本快照，19171 条字段记录 | **无人工正文**，页面由模板渲染数据 |

四个站都是英文默认、中文在 `/zh/`。前三个是同一套管线的三次运行（证据 → 规范化 → 人工分析 → 成文），
正文骨架高度模板化。cat 是异类：没有叙事正文，且 157 个关系的字段描述直接取自上游英文文档，没有中文译文。

## 2. 数据来源与权威归属

错误码仓库是三层结构，边界由作者划清，站点直接沿用，不重新设计：

```
evidence/<CODE>.json        人工核验的证据：源码位置、断言、报文模板、运行记录
      ↓ 机器合成
data/errcodes/<CODE>.json   规范事实：身份、版本存在性、变更、来源（83 MB，含逐补丁版审计数组）
      ↓ 裁剪
static/data/*.json          公开投影（23 MB）：catalogue / evidence / cases / 版本矩阵 / 中文检索索引
      ↓
content/docs/<CODE>.md      人写正文 + <CODE>.zh.md 译文（2.5 MB，front matter 极简）
```

**PGWeb 不夺取权威**。`pgsty/err.pg.center` 仍是唯一真源，站点表是它的投影，可随时由导入工具整体重建。

导入读的是权威三层：`data/errcodes/*.json` + `evidence/<CODE>.json` + `content/docs/*.md`。
`static/data/` 不是导入源，它本身就是作者从这三层生成的对外发布视图；
站点表建好之后能生成同样的东西，没必要把一份派生视图当成第二个真源搬进来。
`verify/results/`、`raw/`、`.cache/`、`public*/` 是构建期痕迹，其中含本机绝对路径，一律不进库——
真正被人工筛选固化下来的运行记录已经在 `evidence/<CODE>.json` 的 `runtime[]` 里。

### "不丢数据"的三道保证

1. **源头受控**：四个仓库各自提交 git，站点表任何时候都能重建。
2. **导入可逆**：`tools/wiki/sync_errcode.py --export` 固定快照，`--input` 用同一份快照分别加载本地与生产，两端逐字节一致。
3. **原样留底**：热字段提成真列供查询筛选，**整份原始 JSON 同时存进 `facts` JSONB 列**。结构化是增量，不是替换。

### 一处需要你知情的取舍

`data/errcodes/` 的 83 MB 里，绝大部分是逐补丁版审计数组：`observed_rows` 合计 84849 行、
`pre9_observed_rows` 27985 行、`evidence_refs` 中位数 505 条/码。内容是"9.0.7 里仍然存在"这类逐版本重复记录。

作者自己已经把它们压成了区间表示：`presence_intervals` 4156 组 + `pre9_presence_intervals` 1102 组。
**站点表存区间，不存逐补丁版行**。区间加 `present_in_snapshots`（16 个展示快照）足够支撑版本页与版本切换器；
逐补丁版行留在受控的源仓库里，导入工具保留一个开关，将来真需要"9.0.7 当时有哪些码"这种粒度时再物化。

这是本方案里唯一一处没有把源数据整条搬进库的地方，所以单独写出来：
严格说区间比逐行少一点信息（若某码在区间内途中改过 `condition_names` 或 `macros`，区间会掩盖这个瞬间），
代价换来的是表从 11 万行降到 5 千行。若你要求一行不落，导入工具加一张 `presence_row` 表即可，不影响其余设计。

## 3. 数据建模

### 3.1 抽象基类 + 每栏目一张表

不用单表加大 JSONB。四类条目的主键形状（单值代码 / 参数名 / `(type,name)` 复合键 / 关系名）、
版本粒度（存在区间 / 逐版本身份对象 / 布尔矩阵 / 逐版本完整字段列表）、
有无人工正文，三点差异都太大；硬塞一张表会让筛选和索引全部退化成 JSONB 表达式，且大量列对某几类永远为 NULL。

共用的只是外壳，用 Django 抽象基类表达：

```python
class WikiEntry(models.Model):          # abstract
    slug            = models.TextField()          # URL 主键
    title           = models.TextField()          # 中文标题
    description     = models.TextField()          # 一句话摘要
    status          = models.TextField()          # active / removed / preview
    present_in      = ArrayField(models.TextField(), default=list)   # 存在于哪些大版本
    depth           = models.TextField()          # reference / full
    editorial_review     = models.TextField()     # pending / reviewed
    runtime_verification = models.TextField()     # passed / failed / not_run / not_applicable
    evidence_tier   = models.TextField()          # observed_runtime / source_path_confirmed / definition_only / unknown
    facts           = models.JSONField(default=dict)    # 原样留底
    source_rev      = models.TextField()          # 源内容哈希，用于判断是否需要重导
    imported_at / updated_at
    class Meta: abstract = True


class WikiText(models.Model):           # abstract：正文，每语言一行
    lang            = models.CharField(max_length=5)    # zh / en
    title           = models.TextField()
    description     = models.TextField()
    body_md         = models.TextField()          # 可编辑真身
    body_html       = models.TextField()          # 导入期渲染，Markdown 3.10.3 + bleach（依赖已在）
    sections        = models.JSONField(default=list)    # [{anchor, heading, html}]，供 TOC 与锚点检索
    translation_source_rev = models.TextField()   # 对应英文正文哈希
    is_stale        = models.BooleanField(default=False)
    search_vector   = SearchVectorField(null=True)
    class Meta: abstract = True
```

`depth` / `runtime_verification` / `evidence_tier` 必须原样保留成枚举列——
这是整批数据的可信度分级语义，拍平成普通文本就等于把项目最看重的东西丢了。
`editorial_review` 一并存下，但它在错误码里恒为 `reviewed`，不要做成筛选项。

`evidence_tier` 不是源数据里的字段，是导入期从该码全部证据条目里取最高档算出来的，
因为源数据的证据状态是挂在"证据条目"上而不是"码"上，一个码可以同时有好几档。

### 3.2 错误码的表

**`wiki_errcode`** — 条目，语言无关。热字段提列，其余进 `facts`：

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `sqlstate` | `char(5)` unique | 五位大写，保留前导零 |
| `class_code` / `class_name` | `char(2)` idx / text | 44 个类 |
| `condition_name` | text idx | 条件名，如 `unique_violation` |
| `condition_names` / `aliases` / `macros` | text[] | 别名 6 个码有；宏 6 个码有多个 |
| `primary_macro` | text | `ERRCODE_UNIQUE_VIOLATION` |
| `severity_classes` | text[] | E 252 / W 10 / S 1 |
| `status` | text | active 262 / removed 1（`72000 snapshot_too_old`） |
| `introduced` / `removed` | jsonb null | **极稀疏**：全库只有 `57P04` 有精确引入边界，`removed` 263 个全为 null |
| `known_present_by` | text | 版本下界，20 种取值，170/263 是 `7.4`——这是历史扫描能力的上限，不是真实引入版本 |
| `present_in` / `preview_in` | text[] | 16 个正式快照 + 19beta3 |
| `evidence_tier` | text idx | 导入期算出的最高证据档，见下 |
| `facts` | jsonb | 完整留底 |

几个字段的真实取值范围值得先知道，免得照着想象建模：`condition_names` 长度恒为 1（没有多条件名并入同码的情况），
`macros` 最多 2 个（只有 6 个码带别名），`editorial_review` 526 篇**恒为 `reviewed`**——
它不是一个有区分度的字段，存下来即可，不要做成筛选项或徽章。
schema 里声明过的 `status: preview` 与 `pre9_status: source_unavailable` 实测从未出现。

**`wiki_errcode_presence`** — 存在性区间，`presence_intervals` 4156 组 + `pre9_presence_intervals` 1102 组：
`(sqlstate, era, start, end, start_tag, end_tag, start_major, end_major, evidence_refs)`。
版本页和版本间增删由它一条 SQL 算出来，不用在应用层展开 JSON。

**`wiki_errcode_message`** — **报文模板，565 条**，整个数据集里最实用的一张表。
不能只提 `primary_template` 一列就算完：565 条里只有 539 条有 `primary_template`，
其余走单复数分支（`primary_template_singular` / `_plural` 各 7）、变体数组（`primary_variants[]`）、
角色映射（`roles[].role` + `roles[].template`，116 对）等十余种形态，
另有 `detail_template` 52 / `detail_templates[]` 18 / `hint_template` 58 / `hint_templates[]` 17 / `context_template` 6。

所以这张表是 `(sqlstate, message_id, severity, limits, sources jsonb, raw jsonb, search_vector)`
加一张 `wiki_errcode_template`：把上面所有形态摊平成 `(message_id, role, kind, template)` 行，
`kind` 区分 primary / detail / hint / context。**报文反查检索这张摊平表，而不是 `primary_template` 单列**，
否则那 26 条非常规形态的码永远查不到。

**`wiki_errcode_claim`（964 条）/ `wiki_errcode_runtime`（169 条）** — 来自 `evidence/<CODE>.json`。
断言是"一句可核实的论断 + 佐证来源 + 限制条件"，直接就是详情页证据面板的行。
运行记录里的 `assertions[]`、`observed`、`environment` 是自由形状（`expected` / `observed` 有 60 余种子键），
整块存 JSONB，不要拆列。

**`wiki_errcode_text`** — 正文，263 × 2 = 526 行。
263 篇全部含 `at-a-glance` / `meaning` / `diagnosis` / `response` / `related` / `versions` / `sources` 七个锚点，
另有 `messages` 223 篇、`case` 64 篇、`observed` 5 篇。

值得注意的是：**页面有几节由证据可得性决定，不由 `content_depth` 决定**。
`messages` / `case` / `observed` 出现与否，取决于该码有没有对应证据，与 full/reference 只是弱相关。
所以建模上这两件事要分开——章节骨架从 `sections` 读，详略程度看 `depth`，不要用 depth 去推断版面。

导入时不要依赖 front matter 的 `lang` 字段：526 篇正文里有 24 篇没有这个键，语言以文件名 `.zh.md` 后缀为准。

**`wiki_errcode_class`（44 行）**与**`wiki_release`（17 行快照，带 commit SHA）**。
后者是版本切换器的基础：每个快照都有 commit，因此详情页切到 PG 16 时，文档链接和源码链接可以一起切过去。

### 3.3 导入期要做的链接改写

正文里的链接量比想象中大，必须在导入时统一重写，否则站上全是死链：

| 形态 | 条数 | 处理 |
| --- | --- | --- |
| `../25p02/` 站内码链接 | 1400 | → `/docs/errcode/25P02/`，slug 在源里是小写，站内统一大写 |
| `github.com/postgres/postgres/blob/<40位commit>/…` | 1462（其中 1084 带 `#L` 行号） | 原样保留，这正是要的效果 |
| `postgresql.org/docs/…` | 147 | → 本站中文译文 `/docs/<版本>/…`（页面存在时），原文降为次要入口 |
| `../data/evidence/<CODE>.json` | 263 | → 页内"来源与证据"区块，不再是外部 JSON 文件 |

URL 大小写要定死一个方向：错误码里有字母（`0100C`、`HV00J`、`22P02`），
报错信息里 PostgreSQL 输出的是大写，所以站内规范形式用**大写**，小写地址 301 到大写。

## 4. 页面规划

### 4.1 地址

```
（2026-09-11 起没有独立首页：四个栏目挂在「文档」菜单末尾，未上线的三个直接指向原站。）
/docs/errcode/                  错误码大全索引
/docs/errcode/23505/            详情页
/docs/errcode/class/23/         Class 23 及其全部成员
/docs/errcode/version/18/       PG 18 的全部错误码，含与 17 的增删对比
/docs/errcode/message/          报文反查
```

后续三个栏目同构：`/docs/guc/`、`/docs/waitevent/`、`/docs/catalog/`，
分别对应 guc.pg.center、wait.pg.center、cat.pg.center。

导航改两处即可，桌面与移动共用一份：`pgweb/util/contexts.py` 的 `sitenav` 加 `'wiki'` 键，
`templates/base/navitems.html` 在"文档"与"社区"之间插一行。
注意站内已有一个指向 `wiki.postgresql.org` 的"Wiki"外链挂在文档下拉里，路径若用 `/wiki/` 需把那一项改名为"PostgreSQL Wiki"。

### 4.2 错误码索引页

自上而下：

1. **报文反查框**，放最上面、给最大权重。"把报错信息粘进来"，匹配 565 条模板，直出错误码。
   这是中文用户真正的入口——他们手里有的是一条报错，不是一个五位代码。
2. **代码直达**：输入 `23505` 回车即跳转。
3. **Class 矩阵**：44 个类的色块阵列，面积按成员数（22 类 68 个、42 类 44 个、HV 类 27 个、25 类 13 个），
   悬浮显示类名与成员数。照抄 `/ext/` 的 SVG cell 做法，颜色走 `wiki-tone-*` class（CSP 禁内联样式）。
4. **筛选器 + 全表**：类 / 严重级 / 状态 / 证据等级 / 版本，当前页即时过滤，URL 用查询参数。
   表列：码 · 条件名 · 中文名 · 类 · 严重级 · 证据等级 · 版本范围。
5. **常见错误码**：手选 20 个高频码置顶（23505、23503、42P01、42601、40001、40P01、53300、57014、25P02……）。

### 4.3 详情页

```
面包屑  百科 / 错误码大全 / Class 23 完整性约束违反
H1      23505 · unique_violation · 唯一性冲突
副标题  一句话中文描述
徽章行  Class 23 · ERROR · 有效 · 深度 full · 已实测（18.6 / 10.21）
右上     版本选择器 [18 ▾]   [复制 23505]

事实卡   条件名 / 宏 / 类 / 严重级 / 状态 / 已知存在于 / 别名 / 证据等级

版本条   9.0 … 18 [19beta3] 方块，可点；缺口如实标注
        「18.5 无正式 tag — 来源缺口，不是该版本移除了这个码」

左侧 sticky 目录：速览 / 含义与触发路径 / 报文与诊断 / 诊断 / 处置 / 版本与边界 / 相关错误码 / 来源与证据

正文     七到八节，服务端渲染
  报文节 额外渲染结构化模板卡：
         ERROR   duplicate key value violates unique constraint "%s"
         DETAIL  Key %s already exists.
         来源    src/backend/access/nbtree/nbtinsert.c:640-674 @ 18.6 ↗
  处置节 SQL 片段带复制按钮与案例 ID 角标

可复现案例（87 个码有）  折叠面板：前置条件 / 触发 / 断言 / 修复 / 清理 + 运行结果

相关错误码  卡片，站内互链

来源与证据  源码表（文件 · 行号 · tag · commit 短 SHA ↗ GitHub）
           断言表（statement / method / limits / sources）
           本站中文手册 Appendix A 错误代码（18）↗   上游英文文档 ↗

页脚       数据来自 err.pg.center · 最后同步 <日期> · 纠错入口
```

站内目前没有长文 TOC 的现成样式，这部分要新写，放进 `media/css/wiki.css`。

### 4.4 版本页

`/docs/errcode/version/18/` 列出该版本全部错误码，并给出与上一版本的增删对比。
这是别处没有的东西——`presence` 表让它成为一条 SQL。同时如实标注来源缺口（18.4 与 18.6 之间没有 18.5 正式 tag）。

### 4.5 与手册双向互链

站库里有 11 个版本的中文《Appendix A 错误代码》。附录页只有表格、没有逐码锚点，所以：

- 百科 → 手册：详情页链到 `/docs/<版本>/errcodes-appendix.html`，随版本选择器切换。
- 手册 → 百科：给附录页加一个只在该页加载的外部 JS，把表格里的 `<code class="literal">23505</code>`
  变成指向 `/docs/errcode/23505/` 的链接。不改手册正文 HTML，可随时撤下。

## 5. 检索集成

站内文档检索已有 `error`（错误代码）、`guc`（配置参数）、`relation`（系统目录与视图）三个类别，
正好对应百科四栏目中的三个（缺等待事件，需新增）。`pgweb/search/extract.py` 已经在解析手册附录抽出错误码条目。
所以百科上线后必须**合并而不是并存**，否则搜 `23505` 会出两条。接法已验证：

- `SearchEntry` 加 `source='wiki'`，`document=None`、`version=None`、`url` 指百科页。表结构不用改。
- `entity_key` 用 `error:23505`，与 `extract.py:243` 生成的完全一致；
  `service.py:191` 的 `row_number() OVER (PARTITION BY entity_key …)` 会自动把手册行与百科行折叠成一条结果。
- 让百科胜出：该行排序加一项，`ORDER BY tier, (source <> 'wiki'), (source = 'ext'), relevance DESC, id`。
- `pgweb/search/indexer.py` 加 `rebuild_wiki()`，`index_docs` 加 `--wiki` 分支，仿现有 `--extensions`。

报文反查用自己的向量（`wiki_errcode_message.search_vector`），不进文档检索，避免模板碎片污染结果。
中文分词沿用 `pgweb/search/lexicon` 的 jieba + `config='simple'`，与博览一致。

sitemap 照抄 `pgweb/ext/struct.py` 写一个 `pgweb/wiki/struct.py`，百科页面应当被搜索引擎收录。
站内爬虫不必排除（`tools/search/crawler/lib/basecrawler.py:112` 的 `EXCLUDED_PREFIXES` 保持原样）。

## 6. 导入工具

数据权威源在另一个仓库、且需要跨两端加载，所以照抄 ext 范式而不是 info 范式：
`tools/wiki/sync_errcode.py`，脚本自己加载 Django 环境，支持
`--dry-run`（默认预览）、`--export FILE.json.gz`（固定快照）、`--input`（用快照加载）、
`--target production`（把快照经 stdin 传给远端同一脚本，用远端 Django 配置写库）、`--prune`。
幂等按 `sqlstate` 原位更新，无变化不重写。

发布顺序：

```
拉代码 → manage.py migrate wiki → sync_errcode.py --input <快照> → manage.py index_docs --wiki → systemctl restart pgsql.cc
```

## 7. 可信度呈现

这批数据与随便抓来的错误码列表的区别全在这里，所以要做成一等公民，而不是藏在页脚：

- 每条带一枚证据徽章，取该码所有证据条目里的**最高**档：**已实测 66** / **源码确认 127** / **仅定义 70**，合计 263。
  注意不要照抄 `coverage.json` 里的 66 / 193 / 222——那是"至少有一条该档证据"的重叠计数（三者相加超过 263），
  按互斥分区展示会算错。导入时算好存进 `evidence_tier` 列。
- 深度徽章 full（82）与 reference（181），并说明 reference 不是半成品，是"有针对性且可用"的合格线。
- 运行结果按页计 passed 132 / not_applicable 18 / not_run 376，折算到码是 66 / 9 / 188；failed 为 0。
- 案例分三个层次，不要混为一谈：87 个码有用例定义（`verify/cases/<CODE>/cases.json`），
  其中 66 个另有可执行 SQL 片段（`snippets.json`），64 个码在正文里写了 `case` 小节。
  也就是说约三分之二的码没有任何可执行用例——"是否有案例"必须是可选关联，不能假设每码都有。
- 缺口如实标注，不用漂亮 UI 抹平：PG 18.5 无正式 tag（18.4→18.6 是来源断层，不是移除）、
  PG 7.0–7.3 下界未知（170/263 个码的"已知存在于 7.4"是扫描能力的上限，不是真实引入版本）、
  中文 PO 只做了"翻译目录确认"而非中文 locale 实测运行。
- `72000 snapshot_too_old` 标着 removed 却没有任何移除证据锚点，页面上要照实说"已移除，但移除版本未取证"，
  不要显示一个编出来的移除版本。
- 百科首页放一条方法论说明，链到 `reports/ACCEPTANCE.md` 的公开版。

导入前有两个码值得人工复核一眼：`53400` 与 `54001` 标着 `content_depth: full`，
但正文长度接近 reference 中位数且 `runtime_verification: not_run`，深度标记可能偏高。

## 8. 错误码大全：已实现

应用 `pgweb/wiki`，十一张表（`wiki_errcode` 及其 `_class` / `_release` / `_text` / `_presence` /
`_source` / `_claim` / `_message` / `_template` / `_runtime` / `_case`），迁移 `wiki.0001_errcode`。

导入后的实际行数，与源仓库逐项对上：

| | 行数 | |
| --- | --- | --- |
| 错误码 | 263 | 证据档 已实测 66 / 源码确认 127 / 仅定义 70；深度 82 full / 181 reference |
| 类别 | 44 | 版本快照 17（16 正式 + 19beta3，各带 commit） |
| 正文 | 526 | 中英各 263，站点只渲染中文 |
| 存在性区间 | 5258 | 4156 现代 + 1102 pre-9 |
| 报文 / 模板 | 565 / 785 | 摊平后去重；只认 `primary_template` 会漏掉 26 条 |
| 断言 / 源码 / 运行记录 | 964 / 1294 / 169 | 来自 `evidence/<CODE>.json` |
| 案例 | 100 | 分布在 87 个码，其中 66 个另有可执行 SQL |

### 地址

```
/docs/errcode/            索引：导航索引 + 按类分组的大表格 + 即时筛选
/docs/errcode/23505/      详情，小写地址 301 到大写
/docs/errcode/23505/?v=16 切换本站手册链接的版本
```

索引页照手册附录 A 的读法：44 个类别的跳转索引在前，下面一张大表按类分组，
类标题行跨列。比附录多四列——中文一句话、严重级、证据强度、版本区间，都是能帮人做判断的。
筛选在前端即时过滤，URL 用查询参数，无脚本时降级为提交表单。

详情页从库里渲染：事实卡与版本条来自结构化列，正文按小节顺序渲染，
报文模板、可复现案例、证据链三块结构化面板插在讲同一件事的那一节后面。
正文里 `<!-- BEGIN SQLSTATE FACTS -->` 那张生成表在导入时整块摘掉，改由数据库渲染成事实卡。

### 维护

```
.venv/bin/python tools/wiki/sync_errcode.py                  # 预览，不写库
.venv/bin/python tools/wiki/sync_errcode.py --write          # 写本地
.venv/bin/python tools/wiki/sync_errcode.py --export s.json.gz
.venv/bin/python tools/wiki/sync_errcode.py --input s.json.gz --target production --write
```

按 `sqlstate` 原位更新，`source_rev` 一致就整条跳过，不重写子表。
导入后自动清索引页的 5 分钟缓存。

### 实现时发现、与原方案不同的几处

- **版本默认不落在预发行**。`present_in_snapshots` 里含 19beta3，直接取末位会让详情页默认显示 PG 19。
  正式版与预发行分开，默认取最新正式版。
- **报文模板按 `(kind, 模板文本)` 去重**，不带角色标签。同一段文本换个角色标签仍是同一条报文，
  展示两次是噪音，反查也只需要一份。
- **证据层没有中文**。正文翻译了，但 `evidence/<CODE>.json` 里的断言、核实方式、适用范围只有英文原文。
  页面照原样呈现并写明「未经翻译」，没有机翻。想要中文得另起一轮翻译。
- **上游链接对本站独有栏目会 404**。`source_url` 把任何路径前缀成 `postgresql.org/<path>`，
  而 `/docs/errcode/`、`/info/`、`/ext/`、`/e/` 上游都没有对应页。已在 `pgweb/util/contexts.py` 里按前缀抑制该链接。

## 9. 实施顺序

| 阶段 | 内容 |
| --- | --- |
| 0 | 四个源仓库各补一次 git 提交 |
| 1 | `pgweb/wiki` app 骨架、导航入口、`/wiki/` 首页（四卡片，未上线的标"筹备中"） |
| 2 | 错误码：模型与迁移、导入工具、索引页、详情页、类页、版本页 |
| 3 | 检索合并（entity_key 折叠 + wiki 优先）、`struct.py` 进 sitemap |
| 4 | 报文反查、案例折叠面板、版本切换器 |
| 5 | 手册附录页反向注入百科链接 |
| 6 | 配置参数大全（数据已受控、骨架最规整，最省事）→ 等待事件 → 系统目录 |

规模参照：`pgweb/ext` 与 `pgweb/info` 各约 600–900 行，百科 app 首期量级相当，外加导入工具约 200 行。

## 10. 已定事项

1. **路径用 `/wiki/`**。文档下拉里原有的 `wiki.postgresql.org` 外链改名为"PostgreSQL Wiki"以示区分。
2. **首期先做骨架，四个栏目都挂上**。`/wiki/` 首页四张卡片同时出现，错误码之外的三个标"筹备中"，
   之后逐个填充。用户能最早看到栏目全貌，也让抽象基类在四类数据上同时受检。
3. **英文正文只入库，暂不出页面**。`wiki_errcode_text` 存中英两行，站点只渲染中文，不开英文路由，
   不引入 i18n 框架。双语资产原样保住，以后想开随时能开。

## 维护入口

本文件是设计方案。实施后本节改为指向导入工具与运维步骤，与
[`docs/extension-catalog.md`](extension-catalog.md)、[`docs/info-column.md`](info-column.md) 保持同一形式。
