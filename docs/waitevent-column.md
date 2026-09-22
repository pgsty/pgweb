# 等待事件 `/docs/waitevent/`

百科第三个上线栏目：PostgreSQL 核心等待事件（`pg_stat_activity.wait_event_type` / `wait_event`）的跨大版本百科。
权威源是 [wait.pg.center](https://wait.pg.center)（仓库 `pgsty/wait.pg.center`，本机 `~/pg.center/wait`），它覆盖 13 – 18 并带双语档案；
本站在此之上补齐 **9.6 – 12、19 与 20** 的事件清单（来自本站手册译文与上游文档/源码），并把 9.0 – 9.5 如实标为"尚无等待事件机制"。
页面骨架与系统目录栏目（`docs/catalog-column.md`）一致：导览索引页 + 逐事件详情页 + 按版本看变更页。

本文是设计契约（后端与前端按同一份上下文形状分头实现），也是日后的维护入口。

## 1. 数据来源与范围

| 层 | 版本 | 来源 | 内容 |
| --- | --- | --- | --- |
| 图谱 | 13 – 18 | `~/pg.center/wait/data/wait_events.jsonl`（282 行：281 个核心事件 + 1 个 Extension 机制页）、`facts/wait_event_matrix.json`（327 个 `(type,name)` 身份，逐版本描述与来源锚点）、`facts/wait_event_canonical_map.json` / `wait_event_aliases.json`（拼写更名与类型迁移）、`facts/translations.zh.json` | 逐版本英文官方描述、中文官方描述、触发机制 / 正常与异常 / 处置 / 事故模式（中英）、三条诊断 SQL（中文标题）、源码位置与状态、相关 GUC 与指标 |
| 手册 | 10 – 12、13 – 19、20 | 本站 `docs` 表 `monitoring-stats.html`：10 – 12 是一张带 `rowspan` 类型列的总表 `#WAIT-EVENT-TABLE`（类型 / 名称 / 描述）；13 起每类一张 `#WAIT-EVENT-<TYPE>-TABLE`（名称 / 描述）；19 与 devel 把 `BufferPin` 类改成 `Buffer`（锚点 `WAIT-EVENT-BUFFER-TABLE`） | 事件身份（类型 + 名称）与中文描述 |
| 上游 | 9.6 – 12、19、20 | 可选联网：`https://www.postgresql.org/docs/<v>/monitoring-stats.html`（9.6 – 12 英文总表；本站没有 9.6 手册，9.6 只有这一来源）；`src/backend/utils/activity/wait_event_names.txt` 在 `REL_19_BETA3` 与 `master` 的 raw 文件（19、20 的英文描述） | 英文官方描述；9.6 的事件身份 |

9.0 – 9.5 没有 `wait_event` 列（9.6 引入），这六个版本在数据里存在、事件数为 0、`has_wait_events=False`，页面上以"不适用"呈现，不当作"缺席"。
9.6 是收录起点，同时也是机制的起点，措辞可以直接写"9.6 引入"。

## 2. 身份归一：同一个事件跨版本怎么认

事件身份 `key = <规范类型小写>/<规范名>`：

- 规范类型：`LWLockNamed`、`LWLockTranche`（9.6）→ `LWLock`；`BufferPin`（≤ 18）→ `Buffer`（19 起的官方名）；其余不变。九个规范类型固定顺序（沿用手册顺序）：`Activity, Buffer, Client, Extension, IO, IPC, Lock, LWLock, Timeout`。
- 规范名：小写并去掉非字母数字；LWLock 类再去掉结尾的 `lock`（`WALWriteLock` → `walwrite`，`buffer_content` → `buffercontent`，都能对上 13 起的 `WALWrite`、`BufferContent`）。
- 再套一层图谱的 `wait_event_canonical_map.json`（如 `Client/WalReceiverWaitStart` → `IPC/WalReceiverWaitStart`）。
- 同一版本内归一后撞 key 的，保留各自原名不合并，并写进导入报告。
- `waitevent_importer.CURATED_RENAMES` 收 12 → 13 那批机械对不上的更名（39 对：`CLogControlLock` → `XactSLRU`、`clog` → `XactBuffer`、`Hash/Batch/Allocating` → `HashBatchAllocate`、`speculative token` → `spectoken` 等），依据是 PostgreSQL 13 发行说明的等待事件统一命名条目与 13 源码里的 `lwlocknames.txt`、`lwlock.c`、`nodeHash.c`；它与图谱映射合成一张表，`identity()` 沿着映射走到底（`buffer_io` → `BufferIO` → `IPC/BufferIO`）。没有证据的不猜：`RecoveryWalAll` 如实显示为"移除"（13 把它改叫 `RecoveryWalStream`，而 12 的 `RecoveryWalStream` 改成了 `Timeout/RecoveryRetrieveRetryInterval`，同名异物，全局映射表达不了）。

每个版本快照保留该版的**原始**类型标签与名称（`LWLockTranche` / `buffer_content` 照原样存），页面按版本展示原名，行首用最新版的名字。

## 3. 数据建模：两张表

```python
class WaitEventVersion(models.Model):         # db_table = 'wiki_waitevent_version'，18 行
    major = CharField(max_length=8, primary_key=True)   # '9.0' … '20'
    label = TextField()                       # '18' / '19 beta 3' / '20 devel'
    status = TextField()                      # historical | stable | preview | devel
    support_status = TextField()              # end-of-life | supported | preview | devel
    doc_slug = TextField()                    # '9.6' … '19'，20 为 'devel'
    has_wait_events = BooleanField(default=True)   # 9.0 – 9.5 为 False
    method = TextField(blank=True)            # atlas | manual | manual+upstream | upstream | none
    event_count = IntegerField(default=0)
    type_counts = JSONField(default=dict)     # 该版原始类型标签 → 数量
    transition = JSONField(default=dict)      # 与上一版的汇总，见 §4；9.0 与 9.6 为 {}（9.6 是起点）
    position = IntegerField(default=0)
    notes = JSONField(default=dict)           # 来源说明：文档版本、tag、抓取时间等
    class Meta: ordering = ('position',)

class WaitEvent(models.Model):                # db_table = 'wiki_waitevent'
    key = CharField(max_length=96, primary_key=True)    # 'lwlock/buffermapping'
    type = CharField(max_length=16)           # 规范类型标签：'LWLock' / 'Buffer' …
    type_slug = CharField(max_length=16)      # 'lwlock'
    name = TextField()                        # 最新出现版本的显示名 'BufferMapping'
    slug = TextField()                        # 图谱 slug（'buffer-mapping'），没有的按名字生成
    aliases = ArrayField(TextField())         # 其它版本用过的名字
    type_variants = ArrayField(TextField())   # 其它版本用过的类型标签（'BufferPin'、'LWLockTranche'）
    summary = TextField(blank=True)           # 最新版英文官方描述
    summary_zh = TextField(blank=True)        # 中文官方描述：图谱优先，其次最新版手册译文
    first_version = CharField(max_length=8)
    last_version = CharField(max_length=8)
    present_in = ArrayField(TextField())      # 按版本顺序
    changed_in = ArrayField(TextField())      # 更名 / 类型变动 / 描述更新落地的版本
    versions = JSONField(default=dict)        # {major: snapshot}
    changes = JSONField(default=list)         # 相邻版本变化记录
    dossier = JSONField(default=dict)         # 图谱档案，见下；不在图谱里的事件为 {}
    has_dossier = BooleanField(default=False)
    position = IntegerField(default=0)        # 类型序 × 1000 + 类型内按名
    source_rev = TextField(blank=True)
    imported_at = DateTimeField(auto_now=True)
    class Meta: ordering = ('position',)
```

快照 `versions[major]`：
`{type（该版原始标签）, name（该版原名）, description（英文，可空）, description_zh（可空）, zh_from（'atlas'|'doc'|'inherited'|''）, source（'atlas'|'manual'|'upstream'）, doc: {file: 'monitoring-stats.html', anchor: 'WAIT-EVENT-LWLOCK-TABLE' 或 'WAIT-EVENT-TABLE', slug}}`。
译文回退与系统目录同一规则：本版无译文时，只在另一版**英文描述完全相同**（忽略末尾句号与空白）的情况下借用，否则留空显示英文。

变化记录 `changes[]`：
`{from, to, status: added|removed|changed, renamed: {from, to} | null, moved: {from, to} | null, reworded: {from, to} | null}`。
`reworded` 只在两侧都有英文描述且归一（去末尾句号、折叠空白）后仍不同时记录；16 → 17 整批去句号不算措辞变化。

`dossier`（原样取自图谱，键名不变）：`mechanism{en,zh}, normal{en,zh}, trouble{en,zh}, actions{en:[],zh:[]}, incident_pattern{en,zh}, diagnostic_sql[{id,title,title_zh,min_version,sql}], gucs[], metrics[], source_locations[{major,version,tag,commit,path,line,kind,status,symbol,excerpt,url}], source_status, emission{status,verified_release}, availability{…}, record_kind, official_descriptions{major: text}`。

## 4. 导入：快照两步，两端一致

`pgweb/wiki/waitevent_importer.py` 提供 `export_snapshot(root, fetch=True, cache_dir='tmp/waitevent-sources')`、`validate()`、`preview()`、`import_snapshot(snapshot, prune=False)`；
管理命令 `manage.py wiki_import_waitevent`（`--root / --input / --export / --check / --prune / --no-fetch`）；工具 `tools/wiki/sync_waitevent.py` 与 `sync_catalog.py` 同形（`--export / --input / --target production / --write / --prune / --no-fetch`）。

导出流程：

1. 读图谱：`wait_events.jsonl` 给档案与 13 – 18 的逐版本英文描述与中文描述；`wait_event_matrix.json` 给 13 – 18 每个 `(type,name)` 的存在与来源锚点；`canonical_map` 给类型迁移。
2. 读本站手册 `monitoring-stats.html`（版本 10 – 19 与 0）：解析事件表，得到每版的 `(type, name, description_zh)`；10 – 12 处理 `rowspan` 类型列。
3. 联网（默认开，`--no-fetch` 关）：抓 9.6 – 12 英文总表得到 9.6 身份与 9.6 – 12 英文描述；抓 `wait_event_names.txt@REL_19_BETA3` 与 `@master` 得到 19、20 英文描述（格式：节标题 `Section: ClassName - "WaitEventXxx"`，行 `NAME<TAB>"description"`；名称在 17 起按驼峰规则生成，13 – 18 图谱里的名字就是它的产物；类型 `Buffer` 在 19 的分节名请以文件为准）。抓取结果缓存到 `cache_dir`，同名文件存在就不再联网。没联网时 9.6 缺席、19/20 只有中文，报告里说明。
4. 归一身份、合并各层、算变化记录与版本汇总，输出自包含快照 `{'versions': [...], 'relations' → 'events': [...], 'meta': {...}}`。

版本汇总 `WaitEventVersion.transition`：
`{from, added: [key], removed: [key], renamed: [{key, from, to}], moved: [{key, from, to}], reworded: [key], added_types: [], removed_types: [], event_count_delta}`。
`method`：13 – 18 `atlas`；10 – 12 有英文时 `manual+upstream`、否则 `manual`；9.6 `upstream`；19、20 `manual+upstream` / `manual`；9.0 – 9.5 `none`。

`import_snapshot` 幂等：同 key 原位更新、无变化不重写；`--prune` 才删除快照里没有的事件与版本；报告形状与系统目录一致（`missing: {events, versions}` 等）。

## 5. 地址与页面

```
/docs/waitevent/                          索引
/docs/waitevent/<type>/<name>/            详情，?v=<major>；type 为规范类型小写，name 为最新显示名（区分大小写）
/docs/waitevent/changes/                  302 → 默认版本（status='stable'）
/docs/waitevent/changes/<major>/          版本变更；?from=<major> 改基准
```

查找顺序：精确 `(type_slug, name)` → 不分大小写 → 图谱 `slug` → 曾用名 `aliases`；命中非规范形式时 301 到规范地址。`<type>` 不在九个规范类型里或找不到事件则 404。
`shell()` 把侧栏 `/docs/waitevent/` 标 active；`LOCAL_ONLY_SECTIONS` 加 `/docs/waitevent/`；`struct.py` 把索引、每个事件、每个变更页写入 sitemap；`columns.py` 里 `waitevent` 置 `live: True`，规模与覆盖按库里实际数量写（导入后核对）。

`TYPE_META` 放在 `pgweb/wiki/waitevent.py`：九个规范类型的中文标签与一句话（Activity 服务器进程在主循环里空闲等待；Buffer 等待访问数据缓冲区；Client 等待客户端套接字；Extension 扩展代码中的等待；IO 等待文件 I/O；IPC 等待其它进程；Lock 等待重量级锁；LWLock 等待轻量级锁；Timeout 等待超时到期），以及英文眉题（`WAIT EVENT · LWLOCK` 这种形式由模板拼）。

### 5.1 索引页上下文（`waitevent.index()`，缓存 5 分钟）

```
total, type_count, default_major, earliest_major('9.6'), latest_major('20'), na_majors(['9.0', … '9.5'])
versions: [ver]                 # major, label, status, status_label, support_status, has_wait_events, method,
                                #   event_count, url('/docs/waitevent/changes/<major>/'), preview, devel, is_default
groups: [{type, type_slug, label, eyebrow, blurb, anchor('type-lwlock'), count, rows: [row]}]
row: {key, name, url, type, type_slug, type_label, summary, summary_zh, first, last, removed(bool), removed_in,
      aliases: [...], type_variants: [...], has_dossier, change_count, last_change,
      strip: [{major, label, state, url, preview, devel}],   # state ∈ na | absent | present | added | changed | removed
      present_tokens, text}
filters: [{param:'type', …}, {param:'present', …}, {param:'first', …}]
stats: {events, types, snapshots, changes, dossiers}
```

索引表的方格条与表头刻度用共用的 `.wiki-strip` / `.wiki-cell` / `.wiki-ruler`：一版一格，刻度逐格写出版本号，版本号与版本导航条的药丸按支持状态着色（橙 = 已停止维护、绿 = 仍在支持、蓝 = 测试版、紫 = 开发版，判定在 `pgweb/wiki/ruler.py` 的 `tone_of()`）；9.0 – 9.5 没有这套机制，刻度与药丸都走「不适用」的点线灰。

`strip` 状态：`na` 9.0 – 9.5；`added` 首次出现（9.6 起点也算 added，因为机制在 9.6 引入）；`changed` 该版发生更名 / 类型变动 / 描述更新；`removed` 只标在 `last_version` 的下一版；其余 `present` / `absent`。

### 5.2 详情页上下文（`waitevent.detail(type_slug, name, wanted)`）

```
event, name, type, type_slug, type_label, eyebrow, blurb
version: ver, previous_major, snapshot, description, description_zh, zh_from
change: 落在本版的记录或 None; change_note
ribbon: [{major, label, state, url, current, preview, devel, doc_url}]
runs: [{majors: ['13','14','15','16'], first, last, type, name, description, description_zh}]   # 相邻且（类型、名称、归一后英文）都相同的版本合并成一段，旧在前
links: {doc, doc_label, official, definition}   # 本站手册该版锚点 / postgresql.org 同锚点 / 源码定义（图谱 catalog_definition 位置，17+ 才有）
facts: [{label, value, url}]    # 类型 / 引入版本 / 状态 / 覆盖版本数 / 触发路径状态（live_trigger 实测触发 · dynamic_trigger 动态触发 · catalog_only 仅定义）/ 实测发行版
dossier: 原样 + 便于模板的派生：actions_zh, sql: [{id, title_zh, title, min_version, sql}], gucs: [{name, url}], metrics: [{name}], sources: [{…, path_line: 'path:line', commit_short}]
timeline: [{to, from, status, url, renamed, moved, reworded, description_zh_to}]   # 新在前
siblings: 索引页 groups 里本类型那一组（current=key）
doc_versions: [{major, label, url}]
notice: '' | 预发行 / 开发版说明 | 9.x 说明
versions: order
```

GUC 链接：在 `SearchEntry(source='pg', kind='guc', name=<guc>, version=<默认版本>)` 里找到就用它的手册 URL，否则退到 `/search/?q=<guc>&kind=guc`；一次查完所有 GUC，缓存 5 分钟。

### 5.3 版本变更页上下文（`waitevent.changes(major, from_major='')`）

```
version, previous, from_major, arbitrary, versions: [ver + is_current]
summary: {added, removed, renamed, moved, reworded, total, types}
added: [{type_label, cards: [card]}]（按类型分组）, removed: [...], renamed: [card 含 from/to], moved: [card], reworded: [card 含 from/to 英文]
card: {key, name, url('?v=<major>'), type, type_label, summary_zh, summary, status}
baseline: bool（9.6）, na: bool（9.0 – 9.5，页面只放一段说明并链到 9.6）
```

### 5.4 措辞

- 9.0 – 9.5 详情/变更页："PostgreSQL 9.x 尚无等待事件机制；`wait_event_type` 与 `wait_event` 自 9.6 引入。"
- 9.6 起点："9.6 引入等待事件机制，此为本事件的首个版本。"
- 更名："PostgreSQL 17：由 `AutoVacuumMain` 更名为 `AutovacuumMain`。"；类型变动："PostgreSQL 19：类型由 `BufferPin` 改为 `Buffer`。"；描述更新："描述措辞更新。"；无变化："相对 PostgreSQL 17 无变化。"

## 6. 前端

模板 `templates/wiki/waitevent_index.html`、`waitevent_table.html`、`waitevent_detail.html`、`waitevent_changes.html`；样式追加到 `media/css/wiki.css` 一节 `/* ===== 等待事件 ===== */`，类名前缀 `we-`，色调 `.wiki-tone-wait`（琥珀）；脚本复用 `wiki.js` 的 `wireFilter` 与 `table[data-rowlink]`。

页面结构与系统目录同构，差异在于：

- 索引页的类别入口是九个类型卡（中文标签 + 数量 + 一句话）；版本条里 9.0 – 9.5 六个药丸用"不适用"样式（更淡、带斜线或点线），title 说明"尚无等待事件"；轨迹里 `na` 格同样淡化。
- 详情页头部：眉题 `WAIT EVENT · LWLOCK`，H1 是 `类型 / 名称` 两段（类型小、名称大、等宽），一句话是中文官方描述；徽章：类型、引入、状态、触发路径状态、有档案。
- 「各版本描述」：把 `runs` 渲染成分段列表，每段左侧一组版本药丸（如 `13 – 16`），右侧该段的名称（若与最新名不同则标"曾用名"）、中文描述、英文原文（小字）。
- 图谱档案（有 `dossier` 时）：「触发机制」「正常还是麻烦」（两块并排的绿色 / 琥珀色说明）「诊断 SQL」（每条带标题与复制按钮，代码块用站点现有代码样式）「处置步骤」（有序列表）「事故模式」「相关参数与指标」（GUC 链接、指标标签）「源码证据」（版本 · 路径:行 · 符号 · 类型 · 状态，链到 GitHub）。没有档案的事件（9.6 – 12 独有或 19/20 新增）只有描述、版本条与时间线，并提示"图谱尚未收录"。
- 时间线、同类事件表、页脚（数据来自 wait.pg.center，纠错入口）与系统目录一致。
- 变更页汇总五格：新增 / 移除 / 更名 / 类型变动 / 描述更新；卡片按类型分组。

## 7. 检索集成

`pgweb/search/taxonomy.py` 新增 kind `waitevent`（'等待事件'）与同名分组（示例 `BufferMapping、DataFileRead`），`KIND_ALIASES` 加 `wait`、`waits`；`search-ui.js` 与 `templates/search/docsearch.html` 的图标映射给它一个现有图标。
`indexer.py` 加 `waitevent_entry()` / `rebuild_waitevents()`：`source='wait'`（列宽 8 字符，写不下 waitevent）、`kind='waitevent'`、`subtype=type_slug`、`entity_key='waitevent:<key>'`、`url` 指详情页、别名含所有名字变体与 `Type/Name` 写法、正文含中英描述与触发机制中文、预览含描述 + 事实 + 首条 SQL 标题。`service.py` 的来源元组、`source_label`（本站词条）与排序偏好加 `'wait'`；`index_docs --waitevents`。

## 8. 维护

发布完成后执行[百科数据发布验收](wiki-data-deployment.md#发布检查)，确认 PG 10–20 数据、版本汇总和检索条目齐全。

```
.venv/bin/python tools/wiki/sync_waitevent.py --export /tmp/waitevent-YYYYMMDD.json.gz      # 本地导出（读图谱 + 本地手册 + 联网缓存）
.venv/bin/python tools/wiki/sync_waitevent.py --input /tmp/waitevent-….json.gz --write      # 写本地
.venv/bin/python tools/wiki/sync_waitevent.py --input /tmp/waitevent-….json.gz --target production --write
.venv/bin/python manage.py index_docs --waitevents
```

发布顺序：拉代码 → `manage.py migrate wiki` → 导入快照 → `index_docs --waitevents` → `systemctl restart pgsql.cc`。
图谱更新（覆盖新版本）或本站手册重灌后重新导出导入；19 正式发布后把 `wait_event_names.txt` 的 tag 从 `REL_19_BETA3` 改为正式 tag。测试：`manage.py test pgweb.wiki pgweb.search --noinput`。

## 9. 实施增补（2026-09-11）

§1 – §8 的形状不变，这一节写定实现时补上的细节，与 §5 冲突处以本节为准。

### 9.1 共用模块与文件归属

- `pgweb/wiki/waitevent_common.py`（已写好）：`canonical_type`、`canonical_name`、`identity(type, name, canonical_map)`、`normal_text`、`compare_snapshots(left, right, from, to)`、`position_of`。导入与页面都只从这里取归一与比较规则。
- 导入侧：`waitevent_importer.py`、`migrations/0004_waitevent.py`（依赖 `0003_guc`，手写，不跑 `makemigrations`）、`management/commands/wiki_import_waitevent.py`、`tools/wiki/sync_waitevent.py`、测试 `pgweb/wiki/tests_waitevent_import.py`。
- 页面侧：`waitevent.py`、`views.py` / `urls.py` / `struct.py` / `columns.py` / `pgweb/util/contexts.py` 的追加、检索集成、测试 `pgweb/wiki/tests_waitevent.py` 与 `pgweb/search/tests_waitevent.py`。
- 前端：`templates/wiki/waitevent_{index,table,detail,changes}.html`、`media/css/wiki.css` 追加一节、`media/js/wiki.js` 追加。
- 测试库：`PGWEB_TEST_DB=test_pgweb_wait manage.py test pgweb.wiki pgweb.search --noinput`（配置参数栏目并行开发，各用各的测试库）。本地预览端口 8767，Chrome 调试端口 9341 – 9351。

### 9.2 导入细节

- 19 / 20 的英文描述来自 `wait_event_names.txt`，带 DocBook 标记：`<xref linkend="guc-archive-command"/>` 还原成参数名 `archive_command`（`guc-` 后的段把 `-` 换成 `_`）；`<command>`、`<filename>`、`<literal>`、`<function>`、`<structname>`、`<structfield>`、`<varname>` 只留内容；`<quote>x</quote>` → `“x”`；其余标签一律只留内容。事件名由枚举名按 17 起的规则生成：按 `_` 分词，每段首字母大写其余小写（`ARCHIVER_MAIN` → `ArchiverMain`，`IO_WORKER_MAIN` → `IoWorkerMain`——以 18 图谱里的实际名字核对生成规则，若有不一致以图谱名为准并记入报告）。LWLock 与 Lock 两节的名字在文件里已是最终形式，不再转换。
- 9.6 手册总表是三列 `Wait Event Type / Wait Event Name / Description`，类型列带 `rowspan`；10 – 12 同形。13 起每类一张表。解析时以 `#WAIT-EVENT-TABLE` 或 `#WAIT-EVENT-<TYPE>-TABLE` 锚点定位，锚点找不到再按表头文字兜底。
- 快照 `versions[major].doc`：`{file: 'monitoring-stats.html', anchor, slug}`；`slug` 是本站手册地址段（'10' … '19'、'devel'），9.6 本站没有手册时 `slug` 仍写 '9.6'，页面按 `doc_pages()` 判断有没有。
- 同一版本内归一后撞 key 的事件保留各自原名不合并，key 后缀加 `~2`、`~3`，并写进报告 `collisions`。
- `WaitEventVersion.notes`：`{doc_version, doc_tag, fetched_at, sources: [...]}`；`label` 写法与系统目录一致（'18'、'19 beta 3'、'20 devel'），`status`/`support_status`/`position` 与 `wiki_catalog_version` 同一套值。
- 报告形状：`{versions, events, created, updated, unchanged, missing: {events, versions}, collisions, coverage: {zh_atlas, zh_doc, zh_inherited, zh_none, dossiers}, transitions: {major: {added, removed, renamed, moved, reworded}}}`。

### 9.3 页面侧增补

- `WaitEvent.url` 里的 `<name>` 是最新显示名；`Extension/Extension` 这类事件正常成页。
- GUC 链接：`GucParameter.objects.filter(name__in=…)` 命中的给 `/docs/guc/<name>/`（配置参数栏目并行上线），否则按 §5.2 的 SearchEntry 规则退到手册锚点或 `/search/?q=<guc>&kind=guc`。一次查完，缓存 5 分钟。
- 图谱派生字段（`dossier` 内加，不改原键）：
  - `kind_label`：`trigger` 触发点 · `resource_path` 资源定义 · `generic_reporter` 通用上报 · `catalog_definition` 目录定义。
  - `status_label`：`live_trigger` 实测触发 · `dynamic_trigger` 动态触发 · `catalog_only` 仅定义。
  - `sources_by_major`: `[{major, tag, rows: [{path, line, path_line, symbol, kind, kind_label, status, status_label, excerpt, url}]}]`，新版本在前，`catalog_definition` 排在每组最后。
  - `emission_note`：`emission.status == 'dormant'` 时的一句中文（“已编目但从未上报；PG15 移除”这类，`reason` 原文英文照抄在 `emission_reason`），`evidence` 原样带出；`active` 时为 ''。
  - `availability_note`：`availability.zh`，附 `observed_releases` / `not_observed`。
  - `wait_url`：`https://wait.pg.center/<type_slug>/<slug>/`（有档案时），否则 `https://wait.pg.center/`。
  - `sql`: `[{id, title_zh, title, min_version, sql, dom_id: 'we-sql-<id>'}]`。
- `facts`：类型（链到索引锚点）· 引入版本（9.6 写“9.6（机制起点）”）· 版本状态（链到变更页）· 覆盖版本（“N 个 · first – last”）· 触发路径（有档案时）· 实测发行版（`emission.verified_release`）· 名称变动（`aliases` 与 `type_variants` 合写，无则“无”）· 手册章节（该版本站锚点，无则不给）。
- `links.source`：图谱里 `kind == 'trigger'` 的最新一条 GitHub 地址，没有就取 `catalog_definition`。
- 变更页 `added / removed / renamed / moved / reworded` 都按类型分组：`[{type, type_label, cards: [...]}]`；`card` 加 `from_name / to_name / from_type / to_type`。9.6 基线页用 `baseline_groups`，行里加 `name_at`（9.6 的原名）与 `type_at`（原始类型标签）。`na` 页只给 `na_note` 与 `first_url`（9.6 变更页）。
- 类型卡 `groups[]` 加 `count_latest`（最新版本的数量）与 `en`（类型英文名）。

### 9.4 前端增补

- 复制按钮：`<button type="button" class="we-copy" data-copy-target="<pre 的 id>">复制</button>`，`wiki.js` 里通用处理 `[data-copy-target]`（`navigator.clipboard.writeText`，成功后按钮文字改“已复制”1.5 秒）。
- 索引页筛选：`wireFilter({prefix: 'waitevent', group: '.we-group', row: '.we-row', more: 'we-row--more', noun: '个等待事件', tokens: ['present']})`。
- 状态色约定（与系统目录一节的注释同一口径）：琥珀 = 本栏目强调 / 新增 / 首次出现，红 = 移除，蓝 = 更名或类型变动，灰 = 只改描述；9.0 – 9.5 的“不适用”用点线框加更淡的灰。

### 9.5 实施后的键名核对（以 `waitevent.py` 实际返回为准）

- 变更页 `reworded` 卡片的旧/新英文是 `card.from_text` / `card.to_text`；更名与类型变动卡片是 `from_name / to_name`、`from_type / to_type`。
- `summary.total` 是本版发生变动的事件数（新增 + 移除 + 更名 + 类型变动 + 描述更新去重），本版事件总数看 `version.event_count`。
- 档案派生字段都放在 `dossier` 顶层：`actions_zh / actions_en / emission_note / emission_reason / emission_evidence / availability_note / observed_releases / not_observed / sources_by_major / sql / gucs / metrics / wait_url / kind_label / status_label`；图谱原键（`mechanism / normal / trouble / incident_pattern / …`）原样保留，正文里的 Markdown 反引号在 `dossier_of` 里转成 `<code class="we-mono">`（已转义、`mark_safe`），模板直接输出。
- `runs[]` 没有 `current` 键，模板用 `version.major in run.majors` 判断当前段；`run.renamed / run.moved` 标出该段名称或类型与最新写法不同。
- `links` 给 `doc / doc_label / official / definition / source / atlas`，动作行优先 `source`。
- `sibling_groups` 与 `siblings` 同义。
