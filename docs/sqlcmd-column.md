# SQL 命令 `/docs/sql/`

百科第五个栏目：PostgreSQL SQL 命令（手册第 VI 部分「SQL 命令」的每一条参考页）的跨大版本百科。
和前四个栏目不同，这一栏**没有 pg.center 上游仓库**：权威源就是本站手册的 `sql-*.html` 参考页（10 – 19 与 devel），
可选地从 postgresql.org 抓 9.0 – 9.6 的英文参考页补齐老版本。页面骨架沿用配置参数栏目（`docs/guc-column.md`）：
导览索引页 + 逐命令详情页 + 按版本看变更页。本文是设计契约，也是日后维护入口；本文没写的细节照配置参数栏目办。

分两期：**一期**只用本地手册（10 – 20）把索引页与详情页的架子搭起来，内容全部来自手册；
**二期**补 9.x 英文层与编辑分析（用法要点、常见问题、示例精选）。二期的字段一期就预留（JSON 列），到时不改表。

## 1. 数据来源与范围

| 项 | 值 |
| --- | --- |
| 权威源 | 本站 `docs` 表（`DocPage`）的 `sql-*.html`，只认页里有 `div.refentry` 的（`sql-commands.html`、`sql-syntax*.html`、`sql-expressions.html`、`sql-keywords-appendix.html` 不是命令） |
| 版本 | 10 – 19（`DocPage.version`）与 devel（`version=0` → 20）；二期加 9.0 – 9.6（联网抓英文页，缓存到 `tmp/sqlcmd-sources/<major>/`） |
| 规模 | 10：176 条，18：183 条，19：188 条（含 3 条 `PROPERTY GRAPH` 与 `WAIT FOR`），devel：185 条（无 `PROPERTY GRAPH`，`sql-wait-for.html` 改名 `sql-waitfor.html`）。2026-09-11 核验 |
| 一句话 | `sql-commands.html` 目录里每条的 `span.refpurpose`（"— 定义一个新表"）；参考页 `div.refnamediv` 的 `<p>` 同样有 |
| 语法概要 | `div.refsynopsisdiv pre.synopsis`（占位符 `em.replaceable code`，译文里仍是英文，可逐版本比较） |
| 正文小节 | `div.refsect1`：描述 / 参数 / 注解（少数写「注意」）/ 示例 / 兼容性 / 另见（少数写「参见」「又见」）/ 输出（11 条 DML）/ 个别「重载」「文件格式」 |

每条命令的身份是**命令名**（`CREATE TABLE`），不是文件名：`WAIT FOR` 在 19 是 `sql-wait-for.html`、devel 是 `sql-waitfor.html`，是同一条命令。
本站地址段 `slug` 取命令名小写、空格换连字符（`create-table`）；手册文件名去掉 `sql-` 与 `.html` 的形式（`createtable`）作为别名，命中就 301。

## 2. 数据建模：一张表

一个大版本才变一次，读多写少，逐版本快照整份放 JSON；版本条不建表，从 `pgweb.core.models.Version`
与 `DocPage` 的收录情况现算并缓存（形状与 `guc.versions()` 一致）。

```python
class SqlCommand(models.Model):             # db_table = 'wiki_sqlcmd'，约 190 行
    slug = CharField(max_length=64, primary_key=True)   # 'create-table'
    name = TextField()                        # 'CREATE TABLE'（最新存在版本的写法）
    aliases = ArrayField(TextField())         # 手册文件名形式与曾用 slug：['createtable', 'wait-for']
    verb = CharField(max_length=16)           # CREATE / ALTER / DROP / SELECT / …（名字第一个词）
    object = TextField(blank=True)            # 'TABLE' / 'MATERIALIZED VIEW' / ''（去掉动词后的对象名，见 §2.1）
    group = CharField(max_length=24)          # 十七个分组之一的 slug，见 §2.1
    purpose = TextField(blank=True)           # 英文一句话，二期从上游取；一期为 ''
    purpose_zh = TextField(blank=True)        # '定义一个新表'
    first_version = CharField(max_length=8)
    last_version = CharField(max_length=8)
    present_in = ArrayField(TextField())      # 按版本顺序
    changed_in = ArrayField(TextField())      # 语法概要有变的版本
    synopsis = TextField(blank=True)          # 最新存在版本的语法概要纯文本（供索引页搜索与检索正文）
    related = ArrayField(TextField())         # 「另见」里链到的其它命令 slug（最新版）
    versions = JSONField(default=dict)        # {major: snapshot}
    changes = JSONField(default=list)         # 相邻版本变化记录
    editorial = JSONField(default=dict)       # 二期：{'summary_zh', 'usage_zh': [], 'pitfalls_zh': [], 'examples': [{title, sql, note}]}；一期 {}
    position = IntegerField()                 # 分组序 × 1000 + 组内序（见 §2.1）
    source_rev = TextField(blank=True)        # '<导出时间>@<本站 HEAD 短哈希>'
    imported_at = DateTimeField(auto_now=True)
    class Meta: ordering = ('position',)；索引 (group, slug)
```

快照 `versions[major]`：

```
{name, file: 'sql-createtable.html', anchor: 'SQL-CREATETABLE', slug: '18'（本站手册地址段，20 为 'devel'）,
 lang: 'zh' | 'en',                        # 9.x 英文层为 'en'
 purpose_zh, purpose,
 synopsis_text,                             # pre.synopsis 的纯文本，多段用空行连接；逐行折叠行内空白，供比较
 synopsis_html,                             # 清洗后的 HTML（保留 em.replaceable/code），链接已改写
 sections: [{key, title, html}],           # 顺序照手册；key ∈ description | parameters | notes | examples | compatibility | see_also | outputs | other
 sections_same_as: '',                      # 各小节 HTML 与更早某版逐字节一致时只记那一版，sections 留 []（去重，同 GUC 的 doc_same_as）
 related: [slug…]}                          # 本版「另见」里的命令
```

小节标题到 key 的映射：描述 → `description`；参数 → `parameters`；注解、注意 → `notes`；示例 → `examples`；兼容性 → `compatibility`；
另见、参见、又见 → `see_also`；输出 → `outputs`；其余 → `other`（保留 `title`）。英文页对应 Description / Parameters / Notes / Examples / Compatibility / See Also / Outputs。

HTML 清洗与链接改写照 GUC §3.1：bleach 白名单同一份再加 `pre, em, var, dl, dt, dd, h3, h4, table…`；去掉所有 `id`、`a.indexterm`、`a.id_link`；
`x.html#Y` → `/docs/<slug>/x.html#Y`、`#Y` → `/docs/<slug>/<file>#Y`；折叠空白（`pre` 内除外，`pre` 里的内容原样保留换行）。
「另见」里指向 `sql-*.html` 的链接同时记进 `related`（转成本站 slug），页面上改链到本站的命令页。

变化记录 `changes[]`（相邻两版都存在才比；新的在后）：

```
{from, to, status: 'added' | 'removed' | 'changed',
 renamed: {from_file, to_file} | null,      # 文件名变了但命令同名（sql-wait-for → sql-waitfor）
 synopsis: {added: [行…], removed: [行…]} | null,   # 语法概要逐行 diff（difflib，行先折叠空白）；没变为 null
 sections: {added: [key…], removed: [key…], changed: [key…]}   # 小节增删与正文变化（按纯文本比）
 purpose_changed: bool}
```

`changed_in` = `synopsis` 非空的 `to`；`sections` 只改正文不算「语法变化」，索引的版本变动上算 `present`，详情时间线上标「正文更新」。
`added` 只记非首个收录版本的首次出现；`removed` 记在 `last_version` 的下一版。

### 2.1 分组、动词与排序

十七个分组固定在代码里（`pgweb/wiki/sqlcmd.py` 的 `SQLCMD_GROUPS`，形状同 `GUC_GROUPS`：slug / 中文 / 英文眉题），按下面顺序：

| slug | 中文 | 成员（按对象名或命令名） |
| --- | --- | --- |
| table | 表与视图 | TABLE、TABLE AS、VIEW、MATERIALIZED VIEW（含 REFRESH）、SEQUENCE、TRUNCATE |
| index | 索引与统计 | INDEX、STATISTICS、REINDEX |
| routine | 函数与过程 | FUNCTION、PROCEDURE、ROUTINE、AGGREGATE、LANGUAGE、TRANSFORM、CALL、DO |
| type | 类型与运算符 | TYPE、DOMAIN、CAST、OPERATOR、OPERATOR CLASS、OPERATOR FAMILY、COLLATION、CONVERSION |
| schema | 数据库、模式与表空间 | DATABASE、SCHEMA、TABLESPACE |
| role | 角色与权限 | ROLE、USER、GROUP、GRANT、REVOKE、DEFAULT PRIVILEGES、SET ROLE、SET SESSION AUTHORIZATION、REASSIGN OWNED、DROP OWNED、POLICY、SECURITY LABEL |
| trigger | 触发器与规则 | TRIGGER、EVENT TRIGGER、RULE |
| extension | 扩展与访问方法 | EXTENSION、ACCESS METHOD、LOAD |
| textsearch | 全文检索 | TEXT SEARCH CONFIGURATION / DICTIONARY / PARSER / TEMPLATE |
| foreign | 外部数据 | FOREIGN DATA WRAPPER、SERVER、USER MAPPING、FOREIGN TABLE、IMPORT FOREIGN SCHEMA |
| replication | 逻辑复制 | PUBLICATION、SUBSCRIPTION |
| query | 查询与数据操作 | SELECT、SELECT INTO、VALUES、INSERT、UPDATE、DELETE、MERGE、COPY、EXPLAIN、LOCK |
| cursor | 游标与预备语句 | DECLARE、FETCH、MOVE、CLOSE、PREPARE、EXECUTE、DEALLOCATE |
| transaction | 事务控制 | BEGIN、START TRANSACTION、COMMIT、END、ROLLBACK、ABORT、SAVEPOINT、RELEASE SAVEPOINT、ROLLBACK TO SAVEPOINT、SET TRANSACTION、SET CONSTRAINTS、PREPARE TRANSACTION、COMMIT PREPARED、ROLLBACK PREPARED、WAIT FOR |
| session | 会话与参数 | SET、RESET、SHOW、ALTER SYSTEM、DISCARD、LISTEN、NOTIFY、UNLISTEN |
| maintenance | 维护 | VACUUM、ANALYZE、CLUSTER、CHECKPOINT |
| misc | 其它对象 | COMMENT、LARGE OBJECT、PROPERTY GRAPH，以及任何没对上的命令（导入报告里列出来） |

`verb` 是命令名的第一个词；`object` 是去掉动词后的剩余部分（`CREATE TABLE AS` → `TABLE AS`；`SELECT INTO` → `INTO`；单词命令为 `''`）。
归组先查命令名全称（`NAME_GROUP`），再查 `object`（`OBJECT_GROUP`），都没有就 `misc`。
组内顺序：先按对象名，再按动词 CREATE → ALTER → DROP → 其它（这样 `CREATE TABLE / ALTER TABLE / DROP TABLE` 挨在一起），`position = 组序 × 1000 + 组内序`。

## 3. 导入：只读本站手册，快照两步

`pgweb/wiki/sqlcmd_importer.py` 提供 `export_snapshot(fetch=False, cache_dir='tmp/sqlcmd-sources')`、`validate()`、`preview()`、`import_snapshot(snapshot, prune=False)`、`digest()`；
管理命令 `manage.py wiki_import_sqlcmd`（`--input / --export / --check / --prune / --fetch`）；工具 `tools/wiki/sync_sqlcmd.py` 与 `sync_guc.py` 同形。
导出在本地做（读本地手册），导入不读手册，生产机上不需要任何源仓库。快照顶层
`{format, generated_at, source_rev, default_major, stats, harvest, versions: [...], commands: [...]}`，`versions[]` 每项
`{major, label, status, support_status, doc_slug, command_count, added_count, removed_count, changed_count, position}`。

导出流程：

1. 版本清单：`DocPage` 里有 `sql-commands.html` 的树（10 – 19 与 0）；`label / status / support_status` 的规则与 GUC 一致（19 是 `preview`、20 是 `devel`、最新正式版 `stable`，其余 `historical`；`support_status` 查 `Version.supported`）。
2. 每版读 `sql-commands.html` 目录：文件名、命令名、一句话；再逐页读 `sql-*.html`（只认 `div.refentry`），解析名字（`span.refentrytitle`）、`refnamediv` 的一句话、语法概要、各小节。目录里没有但页面存在的照收（报告 `harvest.orphans`）。
3. 按命令名归一身份（大小写不敏感、空白折叠）：同名跨版本合并成一条；文件名变化记 `renamed`。
4. 算 `changes`、`changed_in`、`present_in`、`first / last`、`related`、`position`；`sections_same_as` 去重；`synopsis` 取最新存在版本。
5. `--fetch`（二期）：对 9.0 – 9.6 抓 `https://www.postgresql.org/docs/<v>/sql-commands.html` 与各 `sql-*.html`，缓存到 `cache_dir`，解析成 `lang='en'` 的快照并入；`purpose` 取英文一句话。抓取失败的版本整版跳过并写报告。

`import_snapshot` 幂等：同 slug 原位更新、整条比对无变化不重写；`--prune` 才删快照里没有的命令。报告形状与 GUC 一致（`added / updated / unchanged / missing / removed / note / harvest`），
`harvest` 里给每版的命令数、小节定位统计、去重比例、`orphans`、`unmapped_groups`（落到 `misc` 的名单）、`renamed`。

## 4. 地址与页面

```
/docs/sql/                       索引：导览 + 分组入口 + 版本条 + 筛选 + 按分组的大表（含版本变动方格）
/docs/sql/<slug>/                详情，?v=<major> 切版本；默认 status='stable' 的那一版
/docs/sql/changes/               302 → /docs/sql/changes/<默认版本>/
/docs/sql/changes/<major>/       该版本相对上一版的变更；?from=<major> 改比较基准
```

`<slug>` 匹配 `^[a-z][a-z0-9-]*$`；`changes/` 排在 `<slug>/` 之前。查找顺序：`slug` → `aliases`（含大小写不敏感）→ 404；命中别名 301 到规范地址并带上 `?v=`。
`shell()` 把侧栏 `/docs/sql/` 标 active；`LOCAL_ONLY_SECTIONS` 加 `/docs/sql/`；`struct.py` 写 sitemap；
`columns.py` 加第五项 `{'slug': 'sql', 'name': 'SQL 命令', 'tone': 'sql', 'lead': '每条 SQL 命令的语法、参数与逐版本的语法演化。', 'scale': '183 条命令 · 17 组', 'coverage': 'PostgreSQL 10 – 20 devel', 'repo': '', 'origin': '', 'live': True}`；
`columns.url()` 遇到 `origin` 为空且未上线的栏目返回 `''`，`nav_items()` 跳过这种栏目（本栏目一上线就为 True，不会走到这条）。模块 docstring 里的「四个栏目」改成「五个栏目」。
三个视图挂 `@queryparams`（索引 `q / group / verb / first / present`，详情 `v`，变更页 `from`）。

### 4.1 索引页上下文（`sqlcmd.index()`，缓存 5 分钟）

```
total, group_count(17), default_major, earliest_major, latest_major,
versions: [ver]                 # major, label, status, status_label, support_status, command_count, added_count, removed_count, changed_count,
                                #   position, doc_slug, url('/docs/sql/changes/<major>/'), preview, devel, is_default
groups: [{slug, label, eyebrow, anchor('group-table'), count, rows: [row]}]
row: {slug, name, url, verb, object, group, purpose_zh, purpose, first, last, baseline(bool 首个收录版本就有), removed, removed_in,
      change_count, last_change, synopsis_lines(最新概要行数),
      strip: [{state, from, to, span, label}],   # 同 GUC：absent | present | added | changed | removed，合段
      present_tokens, text(名称 + 一句话 + 别名 + 概要里的关键字，供前端搜索)}
filters: [{param:'group', label:'分组', options}, {param:'verb', label:'动词', options: CREATE / ALTER / DROP / 其它},
          {param:'first', label:'引入版本', options}, {param:'present', label:'存在于版本', options}]
stats: {commands, versions, snapshots, synopsis_changes, removed}
```

索引页查询 `defer('versions', 'changes', 'editorial')`。首个收录版本（一期是 10）是基线：措辞同前几栏「不代表首次于 10 引入」。

### 4.2 详情页上下文（`sqlcmd.detail(slug, wanted_major)`）

```
command, name, slug, group, group_label, eyebrow('SQL COMMAND'), verb, object
version: ver, previous_major, snapshot
facts: [{label, value, mono, url}]     # 动词 / 对象 / 分组（url 指索引锚点）/ 引入版本 / 状态 / 语法变更次数 / 手册小节数
synopsis: {html, text, lines: [{text, state: 'same' | 'added'}]}   # 本版语法概要；与上一存在版本比，新增行标 added（逐行按折叠后的文本比）
synopsis_diff: {added: [...], removed: [...]} | None                # 本版相对上一版的概要差异（来自 changes）
sections: [{key, title, html, anchor}]                              # 沿 sections_same_as 指针解析；「另见」的 html 里 sql-* 链接已改成本站命令页
ribbon: [{major, label, state, url, current, preview, devel, doc_url}]
change, change_note, notice
doc: {major, borrowed(bool), local_url, official_url, label('PostgreSQL 18 手册')}   # 本版没快照时借最近版并标 borrowed（二期 9.x 英文层未抓时才会发生）
timeline: [{to, from, status, url, renamed, synopsis: {added, removed} | None, sections: {...}, purpose_changed}]   # 新在前
related: [{slug, name, url, purpose_zh, exists}]
editorial: {}                                                         # 二期
links: {doc, doc_label, official}
doc_versions: [{major, label, url}]
siblings: 索引页 groups 里本组那一项（供页尾复用），current=slug
versions: [ver]
```

`change_note` 措辞：首个收录版本且存在 → 基线句；本版新增 → "PostgreSQL 15 新增此命令。"；语法有变 → "相对 PostgreSQL 17：语法概要新增 3 行，移除 1 行。"；只改正文 → "相对 PostgreSQL 17 语法未变，正文有更新。"；无变化 → "相对 PostgreSQL 17 无变化。"；改名 → 追加 "手册文件由 sql-wait-for.html 改为 sql-waitfor.html。"

### 4.3 版本变更页上下文（`sqlcmd.changes(major, from_major='')`）

```
version, previous, from_major, arbitrary, versions, notice, baseline_note
summary: {added, removed, renamed, synopsis_changed, sections_changed}
added: [card], removed: [card], renamed: [{card…, from_file, to_file}],
synopsis_changed: [{card…, added_lines: n, removed_lines: n, sample: 第一条新增行}],
sections_changed: [card]（折叠）
card: {slug, name, url, group, group_label, purpose_zh, verb, object}
baseline: bool, baseline_groups
```

## 5. 前端

模板 `templates/wiki/sqlcmd_index.html`、`sqlcmd_table.html`、`sqlcmd_detail.html`、`sqlcmd_changes.html`，都 `{% extends "wiki/base.html" %}`。
样式追加到 `media/css/wiki.css` 末尾一节 `/* ===== SQL 命令 ===== */`，类名前缀 `cmd-`（`.wiki .cmd-…`），色调 `.wiki-tone-sql`：
在 `.wiki` 里新增 `--c-sql`（亮色 `#6f42c1`，暗色 `#b08ae8`）与 `.wiki-tone-sql { --seg: var(--c-sql); }`。状态色与前几栏一致（绿增红删琥珀改灰措辞）。
`wiki.js` 末尾追加 `wireFilter({prefix: 'sqlcmd', group: '.cmd-group', row: '.cmd-row', more: 'cmd-row--more', noun: '条命令', tokens: ['present']})`。CSP 禁内联样式与脚本。

- **索引**：面包屑 → H1「PostgreSQL SQL 命令」→ 导语 → 十七个分组入口（`wiki-classnav` 网格）→ 版本条 → 搜索框 + 四个下拉 → 图例 → 分组大表（每命令两行：`命令（等宽，链接）· 动词 · 对象 · 版本变动 · 最近变更` / `一句话 · 状态`）→ 说明段。方格条与刻度用共用的 `.wiki-strip` / `.wiki-cell` / `.wiki-ruler`。版本号按支持状态着色，四档由 `pgweb/wiki/ruler.py` 的 `tone_of()` 从 `support_status` 推出：橙 = 已停止维护、绿 = 仍在支持、蓝 = 测试版、紫 = 开发版；同一套色也用在页面上方的版本导航条上（模板给药丸加 `wiki-vpill is-<tone>`）。
- **详情**：面包屑（文档 / SQL 命令 / 分组）→ 眉题 `SQL COMMAND · 表与视图` → H1（等宽命令名）→ 一句话（中文，英文灰小）→ 徽章（动词 / 分组 / 引入 / 状态 / N 次语法变更）→ 事实卡 + 两个按钮（本站手册 · 官方文档 ↗）→ 版本条 → 变化一句话 →
  **语法概要**（`pre.cmd-synopsis` 渲染 `synopsis.html`；本版新增的行左侧带绿色标记，`title` 写「PostgreSQL 15 新增」；上方一行小字写"相对 PostgreSQL 14 新增 3 行"，并可展开看被移除的行）→ 本页目录 →
  手册各小节按 `sections` 顺序渲染（`<div class="cmd-doc">`，H2 用中文标题，`id` 用 `key`）→ 「语法演化」时间线（新在前：新增 / 移除 / 改名 / 语法变化的行芯片 + / −，正文更新灰芯片）→ 「相关命令」芯片 → 「同组命令」（复用索引表）→ 页脚（数据来自本站手册译文；纠错入口：译文问题去 `pgsty/pgdoc`，本站问题去 `pgsty/pgweb`）。
  `.cmd-doc` 要把手册 HTML 排好：`pre.synopsis`/`pre.programlisting` 的等宽与换行、`em.replaceable` 斜体、`dl.variablelist` 参数表（`dt` 里 `code.parameter`）、`table`、`div.note / tip / warning / caution`，亮暗两套；`code` 的 `!important` 要抵消。
- **变更页**：H1「PostgreSQL 15 SQL 命令变更」→ 发布导航条 → 汇总五项（新增 / 移除 / 改名 / 语法变化 / 仅正文更新）→ 新增命令卡片 → 移除 → 改名 → 语法变化（表：命令 · 分组 · +n / −n · 第一条新增行）→ 仅正文更新（折叠）→ 基线名单。

## 6. 检索集成

`pgweb/search/indexer.py` 加 `sqlcmd_entry()` 与 `rebuild_sqlcmd()`：`source='sqlcmd'`（`SearchEntry.source` 是 varchar(8)）、`kind='sql'`、`subtype=group`、
`entity_key='sql:' + normalize_name(name)`（与手册 `sql-*.html` 抽出的命令条目共享实体，结果列表折叠成一条并让本站词条胜出）、
别名含 slug 与手册文件名形式、`heading='SQL 命令 · <分组>'`、`signature=一句话`、正文含一句话 + 语法概要文本 + 分组，预览含一句话 + 事实 + 语法概要前 12 行。
`service.py` 来源元组与排序偏好加 `'sqlcmd'`；`search-ui.js` 把 `sqlcmd` 与 `catalog / errcode / guc / wait` 同等对待；`index_docs --sqlcmd`。

## 7. 维护

发布完成后执行[百科数据发布验收](wiki-data-deployment.md#发布检查)，确认 PG 10–20 数据、版本汇总和检索条目齐全。

```
.venv/bin/python manage.py migrate wiki                                            # wiki.0005_sqlcmd
.venv/bin/python tools/wiki/sync_sqlcmd.py --export /tmp/sqlcmd-YYYYMMDD.json.gz   # 本地导出（读本地手册；二期加 --fetch）
.venv/bin/python tools/wiki/sync_sqlcmd.py --input /tmp/sqlcmd-….json.gz --write   # 写本地
.venv/bin/python tools/wiki/sync_sqlcmd.py --input /tmp/sqlcmd-….json.gz --target production --write
.venv/bin/python manage.py index_docs --sqlcmd
```

发布顺序：拉代码 → `migrate wiki` → 导入快照 → `index_docs --sqlcmd` → `systemctl restart pgsql.cc`。手册重灌后重导一次。
测试：`PGWEB_TEST_DB=test_pgweb_sql .venv/bin/python manage.py test pgweb.wiki.test_sqlcmd pgweb.wiki.test_sqlcmd_importer --noinput`。

## 7.1 逐大版本的语法铁道图

每个命令的每个已收录大版本都有铁道图，直接从该快照的完整 `synopsis_html` 派生，不增加表或另一份语法数据。`pgweb/wiki/sqlcmd_railroad.py` 保留占位符、字面符号、可选分支、必选分支和重复项；命名子规则与多种命令形式分别成图，点击参数名可展开子规则。原始语法概要仍可查看。

记法遵循 [PostgreSQL Conventions](https://www.postgresql.org/docs/current/notation.html)，SVG 使用 [railroad-diagrams](https://github.com/tabatkins/railroad-diagrams) 的 Python 包（`requirements.txt` 固定 3.0.1）。绘图适配层修正该版库在折行分支高度和链接标签上的两处问题。语法树和 SVG 按语法内容缓存，HTML 锚点按命令、版本与展示位置隔离；多个大版本语法相同可以共享图形，摘要和版本状态仍各自取数。

详情页在原始语法之前显示图；检索页和全站弹窗使用相同图形，并通过 `?v=` 原地切换版本。样式和子规则交互在 `media/css/sql-railroad.css`、`media/js/sql-railroad.js`，支持亮暗主题和窄屏滚动，不使用内联 CSS、脚本或外部绘图服务。

更新手册后，完成 SQL 快照导入，再校验全部命令和版本：

```bash
.venv/bin/python manage.py wiki_check_sqlcmd_railroads --report tmp/sqlcmd-railroad-coverage.json
PGWEB_TEST_DB=test_pgweb_sql .venv/bin/python manage.py test pgweb.wiki pgweb.search --noinput
```

校验命令只读数据库，逐份生成所有主图和子规则图，检查 SVG 格式、所有字面语法 token 的覆盖、子规则锚点与无内联脚本样式。报告列出每命令、每大版本的语法摘要和图数。2026-09-12 本地数据为 188 条命令、11 个大版本、2009 份语法快照；正式发布前应在目标数据上重新运行。

## 8. 二期（先预留，不实现）

- 9.0 – 9.6 英文层（`--fetch`），索引与版本条自动延伸到 9.0，措辞上基线改为 9.0。
- 编辑分析 `editorial`：每条命令一段中文摘要、用法要点、常见问题、精选示例；由批次文件 `data/sqlcmd/<slug>.json` 导入，形状在实现时再定，表不改。
- 与 SQL 状态码、配置参数、系统目录的互链：正文里出现的 GUC 名、pg_* 关系名、SQLSTATE 自动链到对应栏目。
