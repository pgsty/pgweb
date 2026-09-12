# 配置参数 `/docs/guc/`

百科第三个上线栏目：PostgreSQL 配置参数（GUC，`pg_settings` 的每一行）的跨大版本百科。
数据来自 [guc.pg.center](https://guc.pg.center)（仓库 `pgsty/guc.pg.center`，本机 `~/pg.center/guc`），
本站在此之上叠加两层：**手册译文**（每个参数、每个版本的说明段落，取自本站手册）与 **PostgreSQL 20 开发版快照**（从本站 devel 手册推导）。
页面骨架沿用系统目录栏目（`docs/catalog-column.md`）：导览索引页 + 逐参数详情页 + 按版本看变更页。

本文既是设计契约（后端与前端按同一份上下文形状分头实现），也是日后维护入口。
凡本文没写的细节，照系统目录栏目的做法办。

## 1. 数据来源与范围

| 项 | 值 |
| --- | --- |
| 权威源 | `~/pg.center/guc/data/guc.json`（447 个参数的完整记录）、`data/diffs.json`（相邻版本差异）、`data/catalog.json`（规模）、`raw/manifest.json`（每版实测的服务器版本） |
| 版本 | 9.0 – 9.6、10 – 18、19 beta 3（guc，键为 `19beta3`）+ 20 devel（本站推导） |
| 参数 | guc 447 个（19 beta 3 在档 419 个，期间移除 28 个）；本站再加 20 devel 手册新出现的参数（2026-09-11 核验为 `enable_groupagg`、`log_statement_max_length` 两个） |
| 事实 | 每版 `pg_settings` 的 `setting / unit / category / short_desc / extra_desc / context / vartype / min_val / max_val / enumvals / boot_val`；引入提交（240 个参数有）；官方文档锚点 |
| 编辑分析 | guc 的 `editorial.zh / en`：机制、按负载的建议、常见问题、关联参数、参考资料 |
| 中文 | 本站手册 10 – 19 与 devel 的 `runtime-config-*.html`：每个参数 `<dt id="GUC-…">` 后的 `<dd>` 说明段落 |

guc.json 每项：`name / slug / identity（最新快照）/ lifecycle{first_seen, first_seen_is_scope_boundary, last_seen, removed_in, present_in[], gaps[]} /
default_history[{from, to, boot_val, unit, human}] / changed_fields{字段: [{from, to, value}]} / official_docs{版本: {status, anchor, url}} /
introduction_commit{status, hash, authored_at, subject, url, discussion[]} 或 null / pigsty{…} / editorial{en, zh} / versions{版本: 快照} / provenance`。

**Pigsty 相关内容一律不进本站**：`pigsty` 块、`editorial.*.pigsty_rationale_pending_review` 整个丢掉；
其余编辑文字里提到 Pigsty 的句子也要清掉（§3.3），本站页面上不出现 Pigsty 取值。

9.0 是收录基线：`lifecycle.first_seen_is_scope_boundary` 为真的参数不能说"首次于 9.0 引入"，页面措辞与系统目录一致。

## 2. 数据建模：两张表，非规范化

模型已写在 `pgweb/wiki/models.py`（`GucVersion`、`GucParameter`），迁移 `wiki.0003_guc`。同文件还定义了
`GUC_CONTEXTS / GUC_CONTEXT_LABEL / GUC_CONTEXT_NOTE`、`GUC_VARTYPES / GUC_VARTYPE_LABEL`、
`GUC_FIELDS / GUC_FIELD_LABEL / GUC_SUBSTANTIVE_FIELDS / GUC_DEFAULT_FIELDS`、
`GUC_GROUPS`（16 个一级分类：英文 / 中文 / slug，按手册第 19 章顺序）、`GUC_CATEGORY_ZH`（58 个 `pg_settings.category` 的中文，
字典顺序即子分类显示顺序）、`GUC_CATEGORY_ORDER`、`guc_group_of(category)`。这些表是唯一定义，页面与导入都从这里取。

```python
class GucVersion:                 # db_table 'wiki_guc_version'，18 行
    major                         # '9.0' … '18', '19', '20'（guc 的 '19beta3' 归一成 '19'）
    label                         # '18' / '19 beta 3' / '20 devel'
    status                        # historical(≤17) | stable(18) | preview(19) | devel(20)
    support_status                # end-of-life | supported | preview | devel（查 pgweb.core.models.Version 的 supported，查不到按 end-of-life）
    source_key                    # guc 的版本键：'19beta3'；20 为 ''
    server_version                # 实测服务器版本，去掉括号：'18.6'、'19beta3'；20 为 ''
    doc_slug                      # '9.0' … '19'，20 为 'devel'
    parameter_count, added_count, removed_count, default_changed_count, changed_count, reworded_count
    schema_source                 # 'runtime' | 'documentation'(20)
    transition                    # 见下；9.0 为 {}
    position                      # 9.0 → 0 … 20 → 17

class GucParameter:               # db_table 'wiki_guc'，447 + 20 新增
    name (pk, 规范大小写), key (小写, unique)
    group, group_slug, category, category_zh          # 按最新存在版本的 category
    vartype, context, unit, boot_val(可 NULL), boot_human, short_desc, short_desc_zh, enumvals[], min_val, max_val   # 最新存在版本
    first_version, last_version, present_in[], changed_in[], default_changed_in[], baseline(bool)
    versions {major: 快照}, changes [...], default_history [...], docs {major: …}, editorial {...}, intro_commit {...}
    position, source_rev, imported_at
```

- 热字段取**最新存在版本**的快照（现存参数是 20，20 沿用 19 的事实）。`short_desc_zh` 取 guc `editorial.zh.official_short_desc_translation`；20 新增参数取 devel 手册说明的第一句。
- `position = 一级分类序 × 10000 + 子分类序（GUC_CATEGORY_ORDER）× 100 + 子分类内按 name 小写排序的序号`。
- `changed_in`：落地了实质变化（`GUC_SUBSTANTIVE_FIELDS` 任一）的版本；`default_changed_in`：其中 `boot_val` 或 `unit` 变了的版本，与 guc `diffs.json` 的 `default_changed` 同口径。
- 索引页查询必须 `defer('versions', 'changes', 'default_history', 'docs', 'editorial', 'intro_commit')`：447 行乘上逐版本手册译文不小。

快照 `versions[major]`：

```
{setting, boot_val, unit, human, category, category_zh, short_desc, extra_desc, context, vartype, min_val, max_val, enumvals,
 doc: {file: 'runtime-config-wal.html', anchor: 'GUC-WAL-LEVEL', slug: '18', url: 官方文档 URL},
 doc_html: '<p>…</p>',            # 本站手册译文（10 – 20），已清洗、链接已改写；9.x 为 ''
 doc_same_as: '',                 # 译文与更早某版完全一致时只记那一版的 major，doc_html 留空（去重）
 carried_from: '', carry_reason: ''}   # 20 沿用 19 的事实时：'19' / '手册不含 pg_settings 事实，沿用 19'
```

`human` 用 guc `scripts/build_catalog.py::human_value(raw, unit)` 的同一规则算（移植过来，别 import 那边的脚本）：
无单位原样，内存单位换算成 MB/GB 并附 `(raw × unit)`，时间单位换算成秒/分/时。`boot_human` 同此。
`doc` 的 `file / anchor` 来自 guc `official_docs[版本]`（`status == 'verified'` 才算）；没有的按 `'GUC-' + name.upper().replace('_', '-')`
在该版全部 `runtime-config-*.html` 里找一次，找到就用。`slug` 与 `GucVersion.doc_slug` 相同。

变化记录 `changes[]`（相邻两版都存在才比；新的在后）：

```
{from, to, status: 'added' | 'removed' | 'changed',
 fields: {字段: {from, to}},      # 只含变了的字段，字段限 GUC_FIELDS；enumvals 存列表
 substantive: bool,               # 任一 GUC_SUBSTANTIVE_FIELDS 变了
 default_changed: bool,           # boot_val 或 unit 变了
 carried: bool}                   # 19 → 20 沿用（fields 恒为 {}）
```

`added` 只记非 9.0 的首次出现；`removed` 记在 `last_version` 的下一版（`fields` 为空）。`changed` 只在 `fields` 非空时记录。
比较时把 `None`、`''` 与 `[]` 视为同一个"空"（guc 的老版本把无单位存成 `''`，新版本存 `null`）。
`setting`（容器里的运行值）不参与比较，只在快照里保留。

`default_history`：guc 的 `default_history[]` 原样，末段若延伸到 19 且参数被沿用到 20，则 `to` 改成 `'20'`。

`docs`：`{major: {status, anchor, url}}`，guc `official_docs` 归一版本键后原样；20 加 `{'status': 'derived', 'anchor', 'url': 'https://www.postgresql.org/docs/devel/<file>#<anchor>'}`。

`editorial`（去掉 Pigsty，中英各留一份）：

```
{'summary_zh', 'summary', 'mechanism_zh': [], 'mechanism': [], 'advice_zh': {oltp, olap, small}, 'advice': {…},
 'pitfalls_zh': [], 'pitfalls': [], 'related': [name…], 'references_zh': [{title, url}], 'references': [{title, url}]}
```

`intro_commit`：guc `introduction_commit` 里 `status == 'verified'` 的 `{hash, authored_at, subject, url, discussion: []}`；其它状态（`predates_history_boundary`、`downstream_only`）只保留 `{status}`；null 为 `{}`。

`GucVersion.transition`：

```
{from, added: [name…], removed: [name…],
 default_changed: [{name, from: {boot_val, unit, human}, to: {…}}],
 changed: [{name, fields: [字段…]}],          # 实质变化但默认值没变的
 reworded: [name…]}                           # 只有 category / short_desc / extra_desc 变了的
```

与 guc `diffs.json` 逐版核对：`added / removed / default_changed` 三项必须一致（导出时 assert，报告里写核对结果）。

## 3. 导入：快照两步，两端一致

照抄系统目录：`pgweb/wiki/guc_importer.py` 提供 `export_snapshot(root)`、`validate()`、`preview()`、`import_snapshot(snapshot, prune=False)`、`digest()`；
管理命令 `manage.py wiki_import_guc`（`--root / --input / --export / --check / --prune`）；工具 `tools/wiki/sync_guc.py` 与 `sync_catalog.py` 同形。
快照顶层：`{format, generated_at, root, source_rev('<guc HEAD 日期>@<HEAD>'), default_major('18'), stats, harvest, versions: [...], parameters: [...]}`。
导出在本地做（读本地手册），导入不读手册。`import_snapshot` 幂等：同名原位更新、整条比对无变化不重写；`--prune` 才删快照里没有的参数与版本。
报告形状与系统目录一致（`versions / added / updated / unchanged / missing / removed / note / coverage / harvest`）。

### 3.1 手册译文采集

版本 10 – 19 与 0（devel）。定位：`DocPage(file=doc.file, version=树)` → `dt#<anchor>` → 紧随的 `dd`。取 `dd` 的内部 HTML，清洗后存 `doc_html`：

- bleach 白名单：`p, br, code, a, em, strong, b, i, ul, ol, li, dl, dt, dd, table, thead, tbody, tr, td, th, pre, span, div, sub, sup, kbd, samp, blockquote, h4, h5`；
  属性：`a[href, title]`、`code / span / div / table / p[class]`、`td / th[colspan, rowspan]`。所有 `id` 去掉（同一页面渲染多版会撞）。
- 删除 `a.indexterm`、`a.id_link`、`a.indexterm` 之类空锚。
- 链接改写：`x.html#Y` → `/docs/<slug>/x.html#Y`，`x.html` → `/docs/<slug>/x.html`，`#Y` → `/docs/<slug>/<file>#Y`；`http(s)://` 原样。
- 折叠空白（`\s+` → 单空格），去掉标签间的纯空白文本，保证同一段译文在不同版本里比得出"完全一致"。
- 与更早的某个已存 `doc_html` 逐字节一致时，本版只记 `doc_same_as: '<那一版>'`，`doc_html` 留空；渲染时沿指针取。
- 同时记 `dd` 首段的纯文本第一句，供 20 新增参数的 `short_desc_zh`。

采不到的「参数 @ 版本」进报告 `harvest.unlocated`。

### 3.2 PostgreSQL 20 开发版推导

guc 到 19 beta 3 为止；20 由本站 devel 手册（`DocPage.version=0`）推出：

- 遍历 devel 的全部 `runtime-config-*.html`，收集 `dt[id^=GUC-]`：参数名（`code.varname`）、类型（`code.type`：`boolean → bool`、`floating point → real`、`integer / string / enum` 照旧；其它如 `pg_lsn / timestamp` 归 `string`）、所在页与 `sect2` 锚点、说明 HTML。
- 19 存在且 devel 手册有：20 快照 = 19 快照的事实 + devel 的 `doc / doc_html`，`carried_from='19'`、`carry_reason='手册不含 pg_settings 事实，沿用 19'`。
- 19 存在、devel 手册没有、但 19 手册也没有（未文档化的 7 个 `debug_print_* / log_*_stats / trace_connection_negotiation`）：同样沿用，`carry_reason='手册从未收录此参数，沿用 19'`。
- 19 存在、19 手册有、devel 手册没有：视为 20 移除（2026-09-11 核验为 0 个）。
- devel 手册有、19 没有：20 新增。`category` 用同页同 `sect2` 里 19 参数的 category 推（建 `(file, sect2 锚点) → category` 映射；推不出用一级分类页名映射，如 `runtime-config-wal.html → 'Write-Ahead Log'`）；`context / boot_val / unit / min_val / max_val / enumvals` 为空，`setting` 为空；`short_desc` 为 `''`，`short_desc_zh` 取说明第一句；`editorial={}`、`intro_commit={}`；`docs['20']` 的 url 指 devel。
- `GucVersion('20')`：`label='20 devel'`、`status='devel'`、`support_status='devel'`、`schema_source='documentation'`、`doc_slug='devel'`。
- 本地没有 devel 手册时跳过 20，报告 `harvest.devel = {'derived': False, 'reason': …}`。开发版号取 `pgweb.docs.versions.DEVEL_MAJOR_VERSION`，推导基准是 guc 的最后一版，不写死 `'19'`。

### 3.3 编辑文字去 Pigsty

`editorial.zh / en` 的 `summary / mechanism[] / advice{} / pitfalls[]`：先用正则删掉 `或(实测 )?Pigsty (矩阵|模板)?值` 这类短语（英文对应 `or the measured Pigsty value` 等），
仍含 `Pigsty` 的句子按 `。；.;` 拆句后整句丢掉；处理后仍含 `Pigsty` 的进报告 `harvest.pigsty_left`。`related` 只保留快照里确实存在的参数名。

## 4. 地址与页面

```
/docs/guc/                       索引：导览 + 分类入口 + 版本条 + 筛选 + 按分类分组的大表（含生命线）
/docs/guc/<name>/                详情，?v=<major> 切版本；默认 status='stable' 的那一版（当前 18）
/docs/guc/changes/               302 → /docs/guc/changes/<默认版本>/
/docs/guc/changes/<major>/       该版本相对上一版的变更；?from=<major> 改比较基准
```

`<name>` 匹配 `^[A-Za-z][A-Za-z0-9_]*$`；`changes/` 路由排在 `<name>/` 之前。查找用 `key=name.lower()`，命中但大小写与规范名不同时 301 到规范地址（`/docs/guc/datestyle/` → `/docs/guc/DateStyle/`）。
无效 `?v=` 落回默认版本（默认版本该参数不存在时取它最后存在的版本）；找不到 404。
`shell()` 给侧栏把 `/docs/guc/` 标 active；`LOCAL_ONLY_SECTIONS` 加 `/docs/guc/`；`struct.py` 把索引、每个参数、每个版本变更页写进 sitemap；
`columns.py` 里 `guc` 置 `live: True`，规模写"449 个参数 · 16 类"（按导入后实际数改），覆盖写"PostgreSQL 9.0 – 20 devel"。
三个视图都挂 `@queryparams`（索引 `q / group / context / first / present`，详情 `v`，变更页 `from`）。

### 4.1 索引页上下文（`guc.index()`，缓存 5 分钟）

```
total, group_count(16), default_major, earliest_major('9.0'), latest_major('20'),
versions: [ver]                 # major, label, status, status_label, support_status, parameter_count, added_count,
                                #   removed_count, default_changed_count, position, doc_slug, server_version, schema_source,
                                #   url('/docs/guc/changes/<major>/'), preview, devel, is_default
groups: [{slug, group, label, anchor('group-wal'), count,
          subgroups: [{category, label(中文子分类名，去掉一级分类前缀；一级分类本身就是子分类时留空), anchor('cat-wal-settings'), count, rows: [row]}]}]
row: {name, url, group_slug, category, category_zh, vartype, vartype_label, context, context_label, context_note,
      boot_human, boot_val, unit, short_desc, short_desc_zh, first, last, baseline(bool), removed(bool), removed_in,
      change_count, default_change_count, last_change('' 或 major),
      strip: [{state, from, to, span, label}],   # 生命线：同状态的连续版本合成一段；state ∈ absent | present | added | changed | removed
      present_tokens('9.0 9.1 … 20'), text(名称 + 两种简述 + 分类，供前端搜索)}
filters: [{param:'group', label:'分类', options:[{value: slug, label, count}]},
          {param:'context', label:'上下文', options:[...]},
          {param:'first', label:'引入版本', options:[...]},
          {param:'present', label:'存在于版本', options:[...]}]
stats: {parameters, versions, snapshots, default_changes, changes, removed}
```

行上显示的 `vartype / context / boot_human` 取**默认版本**的快照，默认版本没有该参数时取最后存在的版本。
生命线状态：`added` 首次出现（9.0 基线除外）；`changed` 该版落地实质变化；`removed` 只标在 `last_version` 的下一版；其余 `present` / `absent`。
`span` 是该段覆盖的版本数，`label` 形如 `'9.0 – 9.6 · 存在'`、`'10 · 默认值变更'`。18 个版本合计每行 `span` 之和恒为 18（含 absent 段），
前端按 `span` 给每段 `flex-grow`，与表头刻度对齐。

`versions()`、`doc_pages()`、`default_major()`、`pick_major()`、`forget()` 与系统目录同名同义，各自缓存 5 分钟。

### 4.2 详情页上下文（`guc.detail(name, wanted_major)`）

```
parameter, name, group, group_slug, group_label, category, category_zh, eyebrow
version: ver, previous_major(按 present_in 顺序的上一版，9.0 为 '')
snapshot                        # 该版快照
facts: [{label, value, mono(bool), note, url}]
                                # 类型（布尔 / 整数 …，mono 写原词）/ 上下文（中文标签，note 为说明）/ 默认值（human，note 写原始 boot_val 与 unit）
                                # / 取值范围（min – max，无则不出）/ 枚举值（无则不出）/ 分类（category_zh，url 指索引锚点）
                                # / 引入版本（'9.0（基线）' 或 '13'，有引入提交时 url 指提交）/ 状态（现存 / 于 16 移除）
context_label, context_note, vartype_label
default_track: [{from, to, span, boot_val, unit, human, current(bool)}]   # 默认值变迁条，按 default_history；20 新增参数为 []
ribbon: [{major, label, state, url, current, preview, devel, doc_url, status}]   # state 同 strip（逐版本，不合段）
change, change_note, notice     # 落在本版的记录 / 一句话 / 预发行与开发版提示
doc: {html, major(译文实际来自哪一版), borrowed(bool 本站没有该版手册时借最近的可用版), local_url, official_url, label('PostgreSQL 18 手册 · 19.5.1 设置')}
                                # 9.x：borrowed=True，取 10 的译文；官方链接仍指该版
editorial: {mechanism: [], advice: {oltp, olap, small}, pitfalls: [],
            related: [{name, url, short_desc_zh, exists(bool)}], references: [{title, url}]}   # 均取 zh，无则空
timeline: [{to, from, status, url('?v=<to>'), substantive, default_changed, carried,
            fields: [{field, label, from, to, from_human, to_human}]}]   # 新的在前；默认值项带 human
matrix: {versions: [ver], fields: [{field, label}],           # 逐版本快照矩阵：行 = 版本，列 = boot_val(human) / unit / context / vartype / min_val / max_val / enumvals
         rows: [{major, label, url('?v=<major>'), current, carried, cells: [{field, value, changed(bool 与上一存在版本不同)}]}]}
intro_commit: {hash, short(前 10 位), date('2024-03-29'), subject, url, discussion: [url]} 或 None
links: {doc: 本站手册 URL 或 '', doc_label: 'PostgreSQL 18 手册', official: 该版官方文档 URL, commit: 提交 URL 或 ''}
doc_versions: [{major, label, url}]   # 本站手册收录了该参数的版本
siblings: 索引页 groups 里本参数所在子分类那一组（同形，供页尾复用索引表），current=name
versions: [ver]
```

`change_note` 措辞：

- 9.0 且存在："9.0 是本数据集的收录基线，不代表该参数首次于 9.0 引入。"
- 本版新增："PostgreSQL 13 新增此参数。"
- 有实质变化："相对 PostgreSQL 9.6：默认值由 minimal 改为 replica，枚举值由 minimal, archive, hot_standby, logical 改为 minimal, replica, logical。"（逐字段列，措辞项不列）
- 只有措辞变化："相对 PostgreSQL 17 仅简述或分类有更新。"
- 无变化："相对 PostgreSQL 17 无变化。"
- 20 沿用："PostgreSQL 20 开发版沿用 19 的 pg_settings 事实，说明取自 devel 手册。"
- 预发行 / 开发版在句末追加 `notice`。

### 4.3 版本变更页上下文（`guc.changes(major, from_major='')`）

```
version, previous(ver 或 None), from_major, arbitrary(bool 非相邻比较), versions, notice, baseline_note
summary: {added, removed, default_changed, changed, reworded}
added: [card], removed: [card],
default_changed: [{name, url, category_zh, from: {boot_val, unit, human}, to: {…}}],
changed: [{name, url, category_zh, fields: [{field, label, from, to}]}],
reworded: [card]
card: {name, url, group_slug, category, category_zh, short_desc_zh, short_desc, vartype, vartype_label, context, context_label, boot_human, unit}
baseline: bool                  # 9.0：列出当时全部 207 个参数
baseline_groups: 索引页 groups 形状，只含 9.0 存在的参数
```

相邻比较直接用库里的 `transition` 与 `changes`，按版本各缓存 5 分钟；`?from=` 非相邻比较现算不缓存，`guc.compare(left, right)` 按快照逐字段比。

## 5. 前端

模板 `templates/wiki/guc_index.html`、`guc_table.html`（可复用的分组表，参数 `groups / table_id / top_link / current`）、
`guc_detail.html`、`guc_changes.html`，都 `{% extends "wiki/base.html" %}`。
样式追加到 `media/css/wiki.css` 末尾一节 `/* ===== 配置参数 ===== */`，类名前缀 `guc-`（`.wiki .guc-…`），色调 `.wiki-tone-guc`（蓝 `--c-guc`）；
状态色与系统目录一致：绿 = 新增，红 = 移除，琥珀 = 默认值或属性变化，灰 = 只改措辞。CSP 禁内联样式，状态与段宽一律走 class（`guc-seg--n1` … `guc-seg--n18` 给 `flex-grow`）。亮暗两套。
脚本追加到 `media/js/wiki.js`：一个 `wireFilter` 调用（`prefix: 'guc'`，`group: '.guc-group'`，`row: '.guc-row'`，`more: 'guc-row--more'`，`noun: '个参数'`，`tokens: ['present']`），
并让 `wireFilter` 支持可选的 `sub`（子分类分隔行选择器）：一个子分类下没有可见行时把它的分隔行也收起。

页面结构：

- **索引**：面包屑 → H1「PostgreSQL 配置参数」→ 导语 → 十六个分类入口（`wiki-classnav` 形，紧凑网格，中文名 + 数量 + 英文眉题）→ 版本条（18 个药丸链到变更页，实心 = 默认版本，虚线 = 未发布）→ 搜索框 + 四个下拉 → 图例 → 分组大表 → 说明段。
  表：每个一级分类一个 `tbody`（组标题行），子分类一行浅色分隔行，每个参数两行：
  第一行 `名称 · 类型 · 上下文 · 默认值 · 生命线 · 变更`，第二行 `中文简述（无则英文并 lang="en"）· 状态（现存 / 于 16 移除）`。
  生命线是一条分段的细条（每段按 `span` 伸展，颜色按 state，`title` 写 label），表头上方一排 18 个刻度与之对齐。
- **详情**：面包屑（文档 / 配置参数 / 一级分类）→ 眉题 `CONFIGURATION PARAMETER · 预写式日志 / 设置` → H1（等宽参数名）→ 中文简述 + 英文简述（灰、小）→ 徽章（类型 / 上下文 / 引入 / 状态 / N 次默认值变更 / 未发布提示）→ 事实卡（三栏）与三个按钮（本站手册 · 官方文档 ↗ · 引入提交 ↗）→ 版本条（当前高亮，变化版本带角标，缺席灰）→ 本版变化一句话 → **默认值变迁条**（横向分段条，每段标 human 值与版本区间，当前版本所在段高亮；只有一段时也画，表明"自 9.0 起未变"）→ 本页目录 →
  「手册说明」（`<div class="guc-doc">` 渲染 `doc.html`，顶部一行写来源与链接，借用时加提示）→「机制详解」（段落）→「调优建议」（OLTP / OLAP / 小规格三张卡）→「常见问题」（列表）→「演化历史」（时间线，新在前，每项一组字段变化芯片：`默认值 minimal → replica`、`上下文 …`、新增 / 移除 / 沿用）→「逐版本快照」（矩阵：行 = 版本，列 = 七个字段；有变的格高亮，当前版本行高亮，版本号链到该版）→「关联参数」（芯片链接，不在本站的只显示名字）→「参考资料」→「同类参数」（复用索引表，只含本子分类）→ 页脚（数据来源 guc.pg.center、手册译文、纠错入口）。
  `.guc-doc` 要给手册 HTML 配样式：段落间距、`code.varname / literal / type`、`table.simplelist`、`div.note / tip / warning / caution` 提示框，亮暗两套。
- **变更页**：面包屑 → H1「PostgreSQL 18 配置参数变更」→ 发布导航条 → 汇总数字五项（新增 / 移除 / 默认值变更 / 属性变更 / 仅描述更新）→ 新增参数（卡片：名称、分类、中文简述、类型 · 上下文 · 默认值）→ 移除参数 → 默认值变更（表：参数 · 分类 · 旧默认 → 新默认）→ 属性变更（表：参数 · 变化芯片）→ 仅描述更新（折叠）→ 9.0 显示基线名单。

## 6. 检索集成

`pgweb/search/indexer.py` 加 `guc_entry()` 与 `rebuild_guc()`，`source='guc'`、`kind='guc'`、`subtype=group_slug`、
`entity_key='guc:' + normalize_name(name)`（与手册页抽出的 `GUC-*` 条目一致，结果列表折叠成一条并让本站词条胜出）、
别名含小写与去下划线形式、`url='/docs/guc/<name>/'`、正文含两种简述、机制段落、分类；预览含简述 + 事实（类型 / 上下文 / 默认值 / 引入）+ 默认值变迁。
`service.py` 的来源元组加 `'guc'`，`source_label` 为「本站词条」；`search-ui.js` 把 `guc` 与 `catalog`、`errcode` 同等对待。
`index_docs --guc` 只重建这批条目。

## 7. 维护

```
.venv/bin/python manage.py migrate wiki
.venv/bin/python tools/wiki/sync_guc.py --export /tmp/guc-YYYYMMDD.json.gz      # 本地导出（读 guc 仓库 + 本地手册）
.venv/bin/python tools/wiki/sync_guc.py --input /tmp/guc-….json.gz --write      # 写本地
.venv/bin/python tools/wiki/sync_guc.py --input /tmp/guc-….json.gz --target production --write
.venv/bin/python manage.py index_docs --guc
```

不给 `--write` 就只预览。发布顺序：拉代码 → `manage.py migrate wiki` → `sync_guc.py --input … --write` → `index_docs --guc` → `systemctl restart pgsql.cc`。
页面缓存 5 分钟，导入后命令主动清缓存（`guc.forget()`）。guc 出新版本时更新 `~/pg.center/guc`，重新导出导入；20 推导层跟着本站 devel 手册走，手册重灌后重导一次。

测试：`PGWEB_TEST_DB=test_pgweb_guc .venv/bin/python manage.py test pgweb.wiki pgweb.search --noinput`（测试库名走环境变量，避免与并行会话相撞）。
