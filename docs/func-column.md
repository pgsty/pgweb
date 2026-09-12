# 函数百科 `/docs/func/`

百科第六个栏目：PostgreSQL 内置函数的跨大版本百科。数据源不是某个 pg.center 仓库，
而是**本站手册第 9 章「函数和操作符」**（`functions-*.html`），10 – 19 与 devel 用本站译文，
9.0 – 9.6 可选地从 postgresql.org 抓英文原页补齐。页面骨架沿用系统目录栏目
（`docs/catalog-column.md`）：导览索引页 + 逐函数详情页 + 按版本看变更页。

本文是设计契约（后端与前端按同一份上下文形状分头实现），也是日后的维护入口。
本文没写的细节，一律照系统目录与配置参数两个栏目已经定型的做法办。

## 1. 数据来源与范围

| 项 | 值 |
| --- | --- |
| 事实（哪些函数、什么签名、什么示例） | **postgresql.org 的英文原页**：`https://www.postgresql.org/docs/<major>/functions-*.html`，9.0 – 19 与 devel（= 20），缓存到 `tmp/func-sources/<major>/`，同名文件在就不再联网 |
| 中文 | 本站手册 `DocPage` 里 `file LIKE 'functions-%'` 的页面，版本 10 – 19 与 0（devel）。只取译文，不取事实 |
| 规模 | 2026-09-12 实测：上游 18 与 devel 各 600 余个具名函数，全部版本并集 700 上下（以导入报告为准） |
| 分组 | 手册页即分组，中文名取本站手册该页 `h1/h2.title`（去掉章节号），如 `functions-info.html` →「系统信息函数和操作符」 |

**为什么事实不取本站手册**：本站的中文手册不是忠实的逐版本快照——2026-09-12 核验发现
14 版的页面里有 PG 17 才引入的 `JSON_TABLE` 系列、PG 18 才有的 `uuidv7`，
15 版的页面里有 `gamma` / `pg_numa_available`，而自称 20devel 的 devel 手册反而没有
PG 16 的 `any_value`、PG 17 的 `to_bin`、PG 18 的 `crc32`。译文仓库是按新版为基底回填的，
用它判断「哪一版引入」会得出错误结论。上游英文页逐版本忠实（同日核验：上游 14 没有
`JSON_TABLE`、上游 devel 有 `any_value`），因此**存在性、签名、示例、分组一律以上游为准**，
本站手册只负责中文描述。这与系统目录、配置参数两个栏目「事实来自实测、中文来自手册」的
分工是同一套。

中文的对齐与回退：按函数名（`name_key`）在同版本的本站手册里找描述；该版没有译文时，
按版本距离就近借用另一版的中文，快照里记 `zh_from`（`'doc'` 本版译文 / `'inherited'` 借用 / `''` 无），
借用只在**英文描述完全相同**时才做，否则留空显示英文。9.0 – 9.6 本站没有手册，只有英文。

四种抽取形态，同一份导入器里并存：

1. **签名表（13 起）**：`div.table table.table` 里 `td.func_table_entry`，每格一条或多条 `p.func_signature`
   （`code.function` 是函数名，`code.type` 是参数类型，`code.returnvalue` 是返回类型），后面第一个 `<p>` 是描述，
   再后面带 `→` 的 `<p>` 是示例。18 有 1106 条签名段，其中 772 条带 `code.function`（其余是纯操作符，见 §1.1）。
2. **五列表（9.0 – 12）**：`div.table table.table`，表头为「函数 | 返回类型 | 描述 | 示例 | 结果」
   （英文 `Function | Return Type | Description | Example | Result`）。函数名在首格的 `code.function` 里，
   文本形如 `ascii(string)`，取第一个 `(` 之前的部分。上游偶尔把标记写坏
   （`pg_replication_origin_advance` 的名字留在外层 `code.literal` 里、内层 `code.function`
   从左括号才开始），所以判据是「标记有没有取出合法的函数名」，取不出才退回按整格文本认；
   有些页（≤12 的枚举与 JSON）整页没有 `code.function`，同样走这条兜底。
3. **散文页的 synopsis 块**：`functions-xml.html`、`functions-statistics.html` 这类页面没有函数表，
   每个函数占一个 `div.sect2`，标题即函数名，`pre.synopsis` 是签名（同样是 `name ( args ) → return` 的写法），
   其后的 `<p>` 是描述。这一形态与第 1 种共用签名解析。
4. **只在正文里提到的函数**：上游 ≤12 的 `functions-trigger.html` 整页零表格零 synopsis，
   `suppress_redundant_updates_trigger` 只出现在一句正文里；事件触发器与统计信息两页同理。
   这类条目**只收存在性**：快照 `signatures` 为空、`prose_only` 为真，页面上如实说明
   「PostgreSQL {major} 的手册只在正文里提到此函数，未给出签名。」（同一句用于 `change_note` 与 `signature_note`）。不借邻版签名——借用等于替上游编内容，
   而且那几版的签名未必相同。判据收紧到「段落里带 `code.function` 标记」且该名字在
   **别的版本有过真正的签名条目**（比按 `code.function` 标记的确认集更严：上游把 `LIKE` / `SIMILAR TO` 也标成了 `code.function`）：那几页同时有「该函数返回哪些列」的输出表（表头
   `Name | Type | Description`），其中一列就叫 `user`，按纯文本比对会凭空造出函数条目，
   而列名不带这个标记，因此收紧后不会误收。

9.x 上游页面是老式 DocBook：class 全大写（`CALSTABLE` / `FUNCTION` / `TYPE`），
解析前把整棵树的 class 统一小写一次，就能复用第 2 种形态的解析器（2026-09-12 对 9.0 与 9.6 实测可行）。
10 – 12 的上游页面是第 2 种形态，13 起是第 1 种。

### 1.1 收录边界

- 只收**具名函数**：签名里必须有 `code.function`，且名字匹配 `^[A-Za-z_][A-Za-z0-9_]*$`。
  纯操作符行（`text || text`）、纯语法形式（`IS DOCUMENT`、`LIKE`）不单独立条目，
  但它们所在的表仍然要解析——同一格里可能既有操作符签名又有具名函数签名。
- `COALESCE`、`GROUPING`、`XMLELEMENT` 这类全大写的语法型函数，手册把它们标成 `code.function` 时照收，
  名字原样保留，slug 走小写。
- 一个函数可能出现在多页（`rank` 在聚合与窗口两页，`unnest` 在数组、范围、文本搜索三页，`bit_length` 在三页）：
  主分组取**最新存在版本里页面序最靠前**的那一页，其余页面记进快照的 `pages`。
- 扩展与 contrib 提供的函数不在范围内（不读 `contrib-*.html`、`pgstatstatements.html` 等）。

## 2. 数据建模：两张表

与系统目录一个形状：版本一张表、函数一张表，逐版本快照与变化记录整份放 JSON 列。
一个大版本才变一次，读多写少，不拆字段表、不拆签名表。

```python
class FuncVersion(models.Model):            # db_table = 'wiki_func_version'，最多 18 行
    major = CharField(max_length=8, primary_key=True)   # '9.0' … '19', '20'
    label = TextField()                     # '18' / '19 beta 3' / '20 devel'
    status = TextField()                    # historical | stable | preview | devel
    support_status = TextField()            # end-of-life | supported | preview | devel
    doc_slug = TextField()                  # 本站手册地址段：'10' … '19'，20 为 'devel'；9.x 为 ''
    source = TextField()                    # 恒为 'upstream'：事实一律取自上游英文页
    zh_coverage = IntegerField(default=0)   # 该版有中文描述的函数数
    layout = TextField()                    # 'table-new'（13+）| 'table-old'（≤12）
    function_count = IntegerField(default=0)
    signature_count = IntegerField(default=0)
    added_count = IntegerField(default=0)
    removed_count = IntegerField(default=0)
    changed_count = IntegerField(default=0)
    transition = JSONField(default=dict)    # 与上一版的汇总，见 §2.1；首个收录版本为 {}
    position = IntegerField(default=0)
    class Meta: ordering = ('position',)

class PgFunction(models.Model):             # db_table = 'wiki_func'
    slug = CharField(max_length=80, primary_key=True)   # 'to-char'、'pg-relation-size'
    name = TextField()                      # 'to_char'（手册里的写法，大小写原样）
    name_key = CharField(max_length=80, db_index=True)  # 小写，跨版本对齐用
    group = CharField(max_length=32)        # 主分组 slug：'info' / 'string' / 'admin' …
    group_label = TextField()               # 「系统信息函数和操作符」
    groups = ArrayField(TextField())        # 出现过的全部分组 slug，按页面序
    summary = TextField(blank=True)         # 英文一句话（9.x 或上游层才有，否则空）
    summary_zh = TextField(blank=True)      # 中文一句话：最新版首条签名描述的第一句
    signature = TextField(blank=True)       # 最新版首条签名的纯文本
    first_version = CharField(max_length=8)
    last_version = CharField(max_length=8)
    present_in = ArrayField(TextField())    # 按版本顺序
    changed_in = ArrayField(TextField())    # 签名有增删改的版本
    signature_count = IntegerField(default=0)   # 最新版签名数
    versions = JSONField(default=dict)      # {major: snapshot}
    changes = JSONField(default=list)       # 相邻版本变化记录
    position = IntegerField(default=0)      # 分组序 × 1000 + 组内按 name_key 排序
    source_rev = TextField(blank=True)      # '<导出时间>@<本站 HEAD 短哈希>'
    imported_at = DateTimeField(auto_now=True)
    class Meta: ordering = ('position',)；索引 (group, name_key)
```

索引页查询必须 `defer('versions', 'changes')`。

快照 `versions[major]`：

```
{'group': 'string', 'group_label': '字符串函数和操作符',
 'pages': ['functions-string.html', …],
 'doc': {'file': 'functions-string.html', 'anchor': 'FUNCTIONS-STRING-SQL', 'slug': '18'},
 'layout': 'table-new' | 'table-old', 'zh_from': 'doc' | 'inherited' | '',
 'signatures': [
   {'text': "substring ( string text [ FROM start integer ] [ FOR count integer ] ) → text",
    'html': 清洗后的签名 HTML（保留 code.function / code.type / code.returnvalue / em.parameter），
    'returns': 'text',
    'description_zh': '提取子串…', 'description': '',
    'examples': [{'expr': "substring('Thomas' from 2 for 3)", 'result': 'hom'}]}],
 'description_zh': 首条签名的描述, 'description': ''}
```

签名的 `text` 是比较用的**规范形式**：折叠空白、去掉 `indexterm` 之类空锚、统一 `→` 两侧空格、
去掉尾部句号。`html` 只用于渲染。老版面（≤12）拼成同一形状：`name ( args ) → returns`，
`args` 取首格里函数名括号内的原文，`returns` 取「返回类型」列。

变化记录 `changes[]`（相邻两版都存在才比，新的在后）：

```
{from, to, status: 'added' | 'removed' | 'changed',
 signatures: {'added': [text…], 'removed': [text…]},
 descriptions_changed: bool,          # 首条签名描述变了（同语言之间才比）
 group_changed: {'from': slug, 'to': slug} | None,
 doc_overhaul: bool}                  # 12 → 13 那一跳，见下
```

**12 → 13 是手册重排**：函数表从五列改成签名段，签名文本整体换了写法，逐条比会把几百个函数
全标成「变化」。这一跳一律 `doc_overhaul=True`，只记函数的增删（`status`），`signatures` 恒为空，
`descriptions_changed` 恒为 False。同理，中英之间（9.6 → 10）不比描述，只比签名与增删。
`changed_in` 只收 `signatures` 非空的 `to`。任一侧 `signatures` 为空（只在正文里提到的那一版）
时同样跳过签名比对，否则「12 没签名、13 有签名」会被算成「13 新增 N 条签名」，
`changed_in`、`FuncVersion.changed_count` 与索引页的版本方格都会脏。这道闸在导入器的
`compare_snapshots()` 与页面侧的 `func.compare()` **两处都要加**：前者产出的 `changes[]` 喂详情页
时间线与索引页方格，后者只喂变更页，只改一处会出现「详情页说新增了签名、变更页说没有」的矛盾。
描述比较一律比英文原文（事实层），不比译文：译文改个措辞不是 PostgreSQL 的说明变了。
`validate()` 允许个别版本没有签名，但一个函数在所有版本里都没有签名仍然报错。

### 2.1 版本汇总 `FuncVersion.transition`

```
{'from': '17',
 'added': [slug…], 'removed': [slug…],
 'changed': [{'slug': 'to-char', 'added': n, 'removed': m}],   # 签名增删的函数
 'moved': [{'slug': …, 'from': group, 'to': group}],
 'doc_overhaul': bool}
```

## 3. 导入：快照两步，两端一致

`pgweb/wiki/func_importer.py` 提供 `export_snapshot(cache_dir='tmp/func-sources', offline=False)`、
`validate()`、`preview()`、`import_snapshot(snapshot, prune=False)`、`digest()`；
管理命令 `manage.py wiki_import_func`（`--input / --export / --check / --prune / --offline`）；
工具 `tools/wiki/sync_func.py` 与 `sync_catalog.py` 同形（`--export / --input / --target production / --write / --prune / --offline`）。
导出在本地做（联网抓上游 + 读本地手册取中文；`--offline` 只用缓存，缓存缺的版本跳过并写进报告），
导入不读手册也不联网，生产机上不需要任何源。

快照顶层 `{format, generated_at, source_rev, default_major, stats, harvest, versions: [...], functions: [...]}`。
`import_snapshot` 幂等：同 slug 原位更新、整条比对无变化不重写；`--prune` 才删快照里没有的函数与版本。
报告形状与系统目录一致，另加 `harvest`：

```
{'versions': {major: {'functions': n, 'signatures': n, 'pages': n, 'layout': …, 'zh': n}},
 'pages_without_functions': [(major, file)…],     # 解析不出函数的页面，用来发现漏网的形态
 'multi_group': [(slug, [group…])…],
 'upstream': {'majors': […], 'failures': […], 'downloads': n},
 'zh': {'doc': n, 'inherited': n, 'none': n},
 'doc_overhaul_at': ['13']}
```

版本行的 `label / status / support_status` 规则与前几个栏目一致（查 `pgweb.core.models.Version.supported`，
19 为 `preview`、20 为 `devel`、最新正式版为 `stable`）；开发版号取 `pgweb.docs.versions.DEVEL_MAJOR_VERSION`。

## 4. 地址与页面

```
/docs/func/                      索引：导览 + 分组入口 + 版本条 + 筛选 + 按分组的大表（含版本变动方格）
/docs/func/<slug>/               详情，?v=<major> 切版本；默认 status='stable' 的那一版
/docs/func/changes/              302 → /docs/func/changes/<默认版本>/
/docs/func/changes/<major>/      该版相对上一版的变更；?from=<major> 改比较基准
```

`<slug>` 匹配 `^[a-z][a-z0-9-]*$`；`changes/` 排在 `<slug>/` 之前。查找顺序：`slug` → `name_key`
（`to_char`、`TO_CHAR` 都能进）→ 404，命中非规范形式时 301 到规范地址并带上 `?v=`。
`shell()` 把侧栏 `/docs/func/` 标 active；`LOCAL_ONLY_SECTIONS` 加 `/docs/func/`；
`struct.py` 把索引、每个函数、每个版本变更页写进 sitemap；三个视图都挂 `@queryparams`
（索引 `q / group / first / present`，详情 `v`，变更页 `from`）。
`columns.py` 加第六项：`slug='func'`、`name='函数百科'`、`tone='func'`、
`lead='每个内置函数的签名、说明、示例与逐版本的签名演化。'`、`scale`/`coverage` 按导入后实际数字写、`live=True`。

### 4.1 索引页上下文（`func.index()`，缓存 5 分钟）

```
total, group_count, default_major, earliest_major, latest_major,
versions: [ver]      # major, label, status, status_label, support_status, function_count, signature_count,
                     #   added_count, removed_count, changed_count, position, doc_slug, lang, source,
                     #   url('/docs/func/changes/<major>/'), preview, devel, is_default,
                     #   tick_head/tick_tail/tone/tone_label（由 pgweb/wiki/ruler.py 的 mark_ticks 补）
groups: [{slug, label, eyebrow, anchor('group-string'), count, rows: [row]}]
row: {slug, name, url, group, group_label, summary_zh, summary, signature, signature_count,
      first, last, baseline(bool 首个收录版本就有), removed(bool), removed_in,
      change_count, last_change, present_tokens, text(名称 + 两种一句话 + 签名 + 分组，供前端搜索),
      strip: [{major, state, label}]}      # state ∈ absent | present | added | changed | removed，一版一格
filters: [{param:'group'…}, {param:'first'…}, {param:'present'…}]
stats: {functions, versions, snapshots, signatures, changes, removed}
```

`strip` 与刻度用共用的 `.wiki-strip` / `.wiki-cell` / `.wiki-ruler`，写法照 `templates/wiki/catalog_table.html`。

### 4.2 详情页上下文（`func.detail(slug, wanted_major)`）

```
function, name, slug, group, group_slug, group_label, eyebrow('FUNCTION')
version: ver, previous_major, snapshot
facts: [{label, value, mono, url}]      # 分组（链索引锚点）/ 签名数 / 引入版本 / 状态 / 签名变更次数 / 本版来源（本站译文 / 上游英文）
signatures: [{text, html, returns, description_zh, description, examples: [{expr, result}],
              added(bool 本版新增的签名)}]
removed_signatures: [{text, …}]         # 本版相对上一版移除的签名（取上一版快照）
ribbon: [{major, label, state, url, current, preview, devel, doc_url}]
change, change_note, notice
doc: {file, anchor, local_url, official_url, label('PostgreSQL 18 手册 · 9.4 字符串函数和操作符'), borrowed(bool), major}
timeline: [{to, from, status, url, added: [text], removed: [text], doc_overhaul, group_changed, descriptions_changed}]
matrix: {versions: [ver], rows: [{text, cells: [{major, state, url}]}]}   # 签名 × 版本；state ∈ exists | absent
related: [{slug, name, url, summary_zh}]   # 同页相邻的几个函数（同分组，按 position 取前后各 N 个）
siblings: 索引页 groups 里本分组那一项（复用索引表），current=slug
doc_versions: [{major, label, url}]
versions: [ver]
```

`change_note` 措辞（照配置参数栏目的语气）：

- 首个收录版本且存在：「{major} 是本数据集的收录基线，不代表该函数首次于 {major} 引入。」
- 本版新增：「PostgreSQL 16 新增此函数，共 N 条签名。」
- 签名有变：「相对 PostgreSQL 17：新增 2 条签名，移除 1 条。」
- 手册重排那一跳：「PostgreSQL 13 重排了函数表的写法，签名文本整体改变，此处不逐条比较。」
- 无变化：「相对 PostgreSQL 17 无变化。」
- 无中文译文时：句末追加「本站手册未收录该版的这条译文，说明按英文原文显示。」

### 4.3 版本变更页上下文（`func.changes(major, from_major='')`）

```
version, previous, from_major, arbitrary, versions, notice, baseline_note
summary: {added, removed, changed, moved}
added: [card], removed: [card], changed: [{card…, added: n, removed: n, sample: 第一条新增签名}],
moved: [{card…, from_group, to_group}]
card: {slug, name, url, group, group_label, summary_zh, summary, signature, signature_count}
baseline: bool, baseline_groups          # 首个收录版本：列出当时的全部函数
```

## 5. 前端

模板 `templates/wiki/func_index.html`、`func_table.html`（可复用分组表，参数 `groups / table_id / top_link / current`）、
`func_detail.html`、`func_changes.html`，都 `{% extends "wiki/base.html" %}`。
样式追加到 `media/css/wiki.css` 末尾一节 `/* ===== 函数百科 ===== */`，类名前缀 `fn-`（`.wiki .fn-…`）；
在 `.wiki` 的色板里加 `--c-func`（亮 `#0f766e` 青绿，暗 `#4fd1c5`）与 `.wiki-tone-func { --seg: var(--c-func); }`。
版本方格、刻度尺、版本药丸一律复用共用的 `.wiki-strip` / `.wiki-cell` / `.wiki-ruler` / `.wiki-vpill`，
**不要再造一套**；`wiki.js` 末尾追加一个 `wireFilter({prefix:'func', group:'.fn-group', row:'.fn-row', more:'fn-row--more', noun:'个函数', tokens:['present']})`。
CSP 禁内联样式与脚本；站内 legacy CSS（`.btn` 宽度、`code` 的 `!important`、`#pgContentWrap h2` 的横线）要显式抵消。

页面结构：

- **索引**：面包屑 → H1「PostgreSQL 函数百科」→ 导语 → 分组入口（`wiki-classnav` 网格，中文名 + 数量 + 英文眉题）→
  版本条（共用药丸 + 支持状态色标）→ 搜索框 + 三个下拉 → 图例 → 分组大表 → 说明段。
  表每个函数两行：第一行 `函数名（等宽，链接）· 签名数 · 主签名（等宽，截断）· 版本变动 · 最近变更`，
  第二行 `中文一句话（无则英文并 lang="en"）· 状态（现存 / 于 16 移除）`。
- **详情**：面包屑（文档 / 函数百科 / 分组）→ 眉题 `FUNCTION · 字符串函数和操作符` → H1（等宽函数名）→
  中文一句话 + 英文一句话（灰、小）→ 徽章（分组 / 引入 / 状态 / N 条签名 / N 次签名变更 / 未发布提示）→
  事实卡（三栏）+ 两个按钮（本站手册 · 官方文档 ↗）→ 版本条 → 本版变化一句话 → 本页目录 →
  **「签名」**（每条签名一张卡：等宽签名行，`→ 返回类型` 用强调色；本版新增的签名左缘带绿色标记与「新」角标；
  描述；示例按 `expr → result` 排成等宽两列，示例多时折叠）→ 本版移除的签名（若有，灰底列出）→
  「演化历史」时间线（新在前，每项列出新增 / 移除的签名芯片；手册重排那一跳给一句灰色说明）→
  「签名矩阵」（签名 × 版本，首列吸附，横向滚动，格子复用 `.wiki-cell`）→ 「相关函数」芯片 →
  「同组函数」（复用索引表）→ 页脚（数据来自本站手册译文 / 上游英文原页，纠错入口：译文问题去 `pgsty/pgdoc`，本站问题去 `pgsty/pgweb`）。
- **变更页**：面包屑 → H1「PostgreSQL 18 函数变更」→ 发布导航条 → 汇总四项（新增 / 移除 / 签名变化 / 换了分组）→
  新增函数卡片 → 移除函数 → 签名变化（表：函数 · 分组 · +n / −n · 第一条新增签名）→ 换了分组（折叠）→
  首个收录版本显示基线名单。

签名是这个栏目的主角，排版要讲究：等宽、`→` 前后留空、参数名用斜体、类型用弱化色，长签名折行时保持缩进对齐。

## 6. 检索集成

`pgweb/search/indexer.py` 加 `func_entry()` 与 `rebuild_func()`：`source='func'`、`kind='function'`、
`subtype=group`、`entity_key='function:' + normalize_name(name)`（与手册页抽出的函数条目共用实体，
结果列表折叠成一条并让本站词条胜出）、别名含去下划线形式、`heading='函数 · <分组中文名>'`、
`signature` 为主签名、正文含两种一句话 + 全部签名文本 + 分组、预览含一句话 + 事实 + 前几条签名。
`service.py` 的来源元组与排序偏好加 `'func'`；`search-ui.js` 把 `func` 与 `catalog`/`errcode`/`guc` 同等对待；
`index_docs --func` 只重建这批条目。

## 7. 维护

```
.venv/bin/python manage.py migrate wiki                                   # wiki.0006_func
.venv/bin/python tools/wiki/sync_func.py --export /tmp/func-YYYYMMDD.json.gz        # 本地导出（读本地手册；加 --fetch 抓 9.x）
.venv/bin/python tools/wiki/sync_func.py --input /tmp/func-….json.gz --write        # 写本地
.venv/bin/python tools/wiki/sync_func.py --input /tmp/func-….json.gz --target production --write
.venv/bin/python manage.py index_docs --func
```

发布顺序：拉代码 → `migrate wiki` → 导入快照 → `index_docs --func` → `systemctl restart pgsql.cc`。
手册重灌后重导一次。测试：`PGWEB_TEST_DB=test_pgweb_func manage.py test pgweb.wiki.test_func pgweb.wiki.test_func_importer`。
