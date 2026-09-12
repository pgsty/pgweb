# 系统目录 `/docs/catalog/`

百科第二个上线栏目：PostgreSQL 系统目录表、系统视图、统计视图与进度视图的跨大版本字段百科。
数据来自 [cat.pg.center](https://cat.pg.center)（仓库 `pgsty/cat.pg.center`，本机 `~/pg.center/cat`），
本站在此之上叠加两层：**中文**（从本站手册译文里采集）与 **PostgreSQL 20 开发版快照**（从本站 devel 手册推导）。
页面设计沿用 SQL 状态码栏目（`/docs/sqlstate/`）的骨架：导览索引页 + 逐条详情页，外加一个按版本看变更的页面。

本文既是设计契约（后端与前端按同一份上下文形状分头实现），也是日后维护入口。

## 1. 数据来源与范围

| 项 | 值 |
| --- | --- |
| 权威源 | `~/pg.center/cat/data/catalog.json`（`static/data/catalog.json` 是同一份） |
| 版本 | 9.0 – 9.6、10 – 18、19 beta 3（cat）+ 20 devel（本站推导） |
| 关系 | cat 157 个：`catalog` 70、`view` 39、`statistics` 40、`progress` 8；`pg_pltemplate` 于 13 移除。本站再多一个 `pg_stat_kind_info`（20 推导层），库里共 158 个 |
| 记录 | cat 2032 份关系快照、19171 条字段记录、732 条相邻版本变化（其中 335 条结构变化）；加上 20 一层，库里 2184 份快照、20709 条字段记录 |
| 中文 | 本站手册 10 – 19 与 devel 的译文：总览表一句话、关系说明段、逐字段描述 |

cat 的 `relations[]` 每项：`name / kind / summary / first_version / last_version / versions{major: snapshot} / changes[]`。
快照：`description / columns[] / system_columns[] / source_url / definition_source_url / schema_source / relation_oid / relkind / shared / runtime_validation …`。
字段：`name / type / description / references / hidden / not_null / attnum / type_oid / type_modifier / array_dimensions / documented_type / documented_name / schema_note …`。
变化记录：`from / to / status(added|removed|changed) / added_columns[] / removed_columns[] / type_changes[] / description_changes[] / reference_changes[] / attribute_changes[] / relation_description_changed / column_order_changed / structural`。
`versions[]` 每项：`id / label / status(historical|stable|preview) / support_status / source_tag / documentation_version / relation_count / column_count / kinds{} / release / runtime_verified`。
`transitions[]`：相邻两版的汇总（新增/移除/变化的关系名单与字段计数）。

9.0 是收录基线：9.0 已有的对象不能据此说"首次于 9.0 引入"。页面上凡涉及 9.0 的"引入"字样都要照此措辞。

20 与 19 目前只差关系增删：新增 `pg_stat_kind_info`（7 个字段），移除五个 `pg_propgraph_*` 目录表；
既存关系的字段、类型、顺序一处没变。2026-09-11 对 postgresql.org/docs/devel 核验：
`catalogs-overview.html` 列 64 个目录表、不含 propgraph，`monitoring-stats.html` 的 `pg_stat_kind_info`
字段与本站推导的七个完全一致。

## 2. 数据建模：两张表，非规范化

这批数据一个大版本才变一次，读多写少，整份快照放 JSON 列即可；不拆字段表、变化表。

```python
class CatalogVersion(models.Model):            # db_table = 'wiki_catalog_version'，18 行
    major = CharField(max_length=8, primary_key=True)   # '9.0' … '19', '20'
    label = TextField()                       # '18' / '19 beta 3' / '20 devel'
    status = TextField()                      # historical | stable | preview | devel
    support_status = TextField()              # end-of-life | supported | preview | devel
    source_tag = TextField(blank=True)        # 'REL_18_6'；devel 为 'master'
    documentation_version = TextField(blank=True)   # '18.6' / '19beta3' / 'devel'
    release = TextField(blank=True)
    doc_slug = TextField()                    # 本站手册地址段：'9.0' … '19'，20 为 'devel'
    relation_count = IntegerField(default=0)
    column_count = IntegerField(default=0)
    kinds = JSONField(default=dict)           # {'catalog': 69, 'view': 39, 'statistics': 40, 'progress': 8}
    runtime_verified = BooleanField(default=False)
    schema_source = TextField(blank=True)     # 'runtime+documentation'；devel 为 'documentation'
    transition = JSONField(default=dict)      # 与上一版的汇总（cat transitions[] 的一项），9.0 为 {}
    position = IntegerField(default=0)        # 9.0 → 0 … 20 → 17
    class Meta: ordering = ('position',)

class CatalogRelation(models.Model):           # db_table = 'wiki_catalog'，158 行
    name = CharField(max_length=64, primary_key=True)
    kind = CharField(max_length=12)           # catalog | view | statistics | progress
    summary = TextField(blank=True)           # cat 的英文一句话
    summary_zh = TextField(blank=True)        # 手册总览表的中文一句话，采不到留空
    first_version = CharField(max_length=8)
    last_version = CharField(max_length=8)
    present_in = ArrayField(TextField())      # 按版本顺序
    changed_in = ArrayField(TextField())      # 结构变化落地的版本（change.status=='changed' 且 structural 的 to）
    column_count = IntegerField(default=0)    # last_version 快照的字段数
    relation_oid = IntegerField(null=True)    # 最新快照
    relkind = CharField(max_length=1, blank=True)
    shared = BooleanField(default=False)
    versions = JSONField(default=dict)        # {major: snapshot}，见下
    changes = JSONField(default=list)         # cat 的 changes[] 原样 + 19→20 一条
    position = IntegerField(default=0)        # 类别序 × 1000 + 类别内按名排序
    source_rev = TextField(blank=True)        # '<cat generated_at>@<仓库 HEAD>'，如 '2026-09-08@419045e'
    imported_at = DateTimeField(auto_now=True)
    class Meta: ordering = ('position',)       # 外加 Index(kind, name)
```

两张表都只按 `position` 排序，任何地方判先后都读它——`'9.0'` 与 `'10'` 字符串比不出大小。
`source_rev` 只记来源，不做变更检测：`import_snapshot()` 是拿库里的字段（含两个 JSON 列）整份比对，
一致就整条跳过。模型另有几个只读属性供模板取用：`CatalogVersion.status_label`（历史版本 / 当前稳定版 /
预发行 / 开发版）、`is_preview`、`is_devel`、`changes_url`，`CatalogRelation.url`、`kind_label`、
`eyebrow`、`relkind_label`（`r` → 普通表 …，表 `RELKIND_LABEL`）。

快照在 cat 原样的基础上增删这些键：

- 加 `description_zh`（关系说明段译文）、每个字段加 `description_zh`；
- 加 `doc = {'file': 'catalog-pg-class.html', 'anchor': 'PG-STAT-ACTIVITY-VIEW' 或 '', 'slug': '18'}`，由 `source_url`（缺则 `documentation_url`）推出，9.x 也照推（渲染时再查本站有没有那一版）。锚点只留全大写的语义锚点：DocBook 自动生成的 `id-1.10.4.13.4` 与整页锚点 `docContent` 换一版就变，写进链接等于埋死链，一律丢掉；
- 加 `zh_from`：`'doc'`（本版译文）、`'inherited'`（英文原文与另一版完全相同，借用那版译文）、`''`（无）。字段级同名键 `zh_from` 同义；
- 删 `runtime_validation` 里的大块原始记录，只留 `runtime_verified: bool` 与 `release`；`source_path / definition_source_path / documentary_schema_source` 不保留。

类别顺序固定：`catalog → view → statistics → progress`。中文标签：系统目录表 / 系统视图 / 统计视图 / 进度视图；眉题英文：SYSTEM CATALOG / SYSTEM VIEW / STATISTICS VIEW / PROGRESS REPORT。

## 3. 导入：快照两步，两端一致

照抄错误码：`pgweb/wiki/catalog_importer.py` 提供 `export_snapshot(root)` 与 `import_snapshot(snapshot, prune=False)`，
管理命令 `manage.py wiki_import_catalog`（`--root / --input / --export / --check / --prune`），
工具 `tools/wiki/sync_catalog.py` 与 `sync_errcode.py` 同形（`--export`、`--input`、`--target production` 经 `ssh pg` 把快照送到远端同一脚本、`--write`）。

导出在本地做，因为它要读本地手册库（`docs` 表）；导入不读手册，生产机上不需要源仓库。同一份快照两端加载结果一致。

### 3.1 中文采集

只读本站 `DocPage`（`file`, `version`），版本 10 – 19 与 0（devel）。定位规则：快照 `source_url` 的文件名与锚点 →
`DocPage(file=文件, version=版本)`；有锚点先找 `id=锚点` 的元素，再找它后面第一张标题里含关系名的 `table.table`；无锚点取页面里第一张标题含关系名的表。

两种表格式都要认：

- PG 13+：单列 `td.catalog_table_entry`，`p.column_definition` 里 `code.structfield` 是字段名、`code.type` 是类型，后面的 `<p>` 是描述；引用写在定义行"（引用 pg_x.col）"里。
- PG 10 – 12：四列 `<td>`：`code.structfield` / `code.type` / 引用 / 描述（统计视图为三列，无引用）。

描述存纯文本（去标签，保留 `<code>` 内文字，折叠空白）。关系说明段取该节标题之后、第一张表之前的 `<p>`（去掉 `indexterm`）。
总览一句话来自 `catalogs-overview.html`、`catalogs.html`、`views-overview.html` 或 `views.html`、`monitoring-stats.html`
（动态/收集统计视图两张表）；只认表头两列、首格是 `code.structname` 的表。目录表那张总览 14 起才在
`catalogs-overview.html`，10 – 14 在 `catalogs.html` 里，两处都要读——只读前者会丢掉当前稳定版之前就移除的关系
（`pg_pltemplate` 的"过程语言的模板数据"就在 12 的 `catalogs.html` 里）。进度视图没有总览表，取节首段第一句。
按 18 → 19 → 20 → 17 … 10 的顺序取第一个有的。

回退规则要诚实：某版某字段没有译文时，只在**英文描述完全相同**的情况下借用另一份快照的译文
（`zh_from='inherited'`）；否则留空，页面显示英文。不做近似匹配。两处可以借：

- 同一关系的另一个版本，就近优先（先同距离里的新版）；
- `alias_of` / `derived_from` 指向的基表的同一版本。`pg_stat_xact_*`、`pg_statio_*`、`pg_stat_sys_*`、
  `pg_stat_user_*` 这 14 个变体手册里从来没有自己的字段表（10 – 19 每版都定位不到，报告 `unlocated` 里
  列的就是它们），但它们的英文字段描述是基表的逐字拷贝，同一条判据成立，就借基表的译文——
  否则这 14 个关系一个中文字都没有。关系说明段不借：变体的说明和基表本来就不同。

### 3.2 PostgreSQL 20 开发版推导

cat 到 19 beta 3 为止；20 由本站 devel 手册（`DocPage.version=0`）推出，规则：

- 遍历 19 里的每个关系：按同样的定位规则在 devel 手册里找表，解析字段名、类型（用 cat 的 `TYPE_ALIASES` 规范化：int4→integer、bool→boolean、timestamptz→timestamp with time zone 等）、中文描述、引用。英文描述沿用 19 同名字段的，20 新增字段英文留空。
- devel 手册里新出现的 `catalog-*.html` / `view-*.html` 页面（页名即关系名，且页内有同名的表），以及 `monitoring-stats.html` / `progress-reporting.html` 里新出现的 `structname` 表，作为 20 新增关系（`status='added'`）。早先移除、devel 手册里又有了的关系挂回原来那条记录，不另建一条——否则 `validate()` 会以"关系重复"中止。
- 19 快照带 `derived_from` 或 `alias_of`（`pg_stat_xact_*`、`pg_statio_*` 等只在源码里定义的变体）在 devel 手册里找不到表时，原样沿用 19 的字段，快照加 `carried_from: '19'` 与 `carry_reason`（`'手册没有这张表'`）。
- 手册把字段名写成占位符时同样整份沿用，`carry_reason='手册用占位符字段名'`：`pg_statistic` 的槽位在手册里是 `stakindN / staopN / stacollN / stanumbersN / stavaluesN`，cat 从源码头文件把它们摊成 1 – 5，照手册推会说 20 删了 25 个字段又加了 5 个。判据是字段名不全小写（`COLUMN_NAME_RE`）。
- 19 有文档表、devel 手册没有的，视为 20 移除。
- 手册与运行时对不上的字段是手册的老账，不算 20 的变化，`merge_devel_columns()` 两个方向都对账：
  手册记着、19 运行时没有、**19 手册也记着**的字段，说明手册没跟上（中文手册 18/19/devel 都还留着
  PG 18 已删掉的 `pg_stat_wal.wal_write / wal_sync / wal_write_time / wal_sync_time`），从 20 快照里丢掉；
  19 运行时有、两版手册都没记的字段（cat 从源码补出来的那些），devel 手册没记同样说明不了它被删了，
  按 19 的相对位置留在 20 快照里（`splice_carried()`）。两类都记进报告的 `harvest.devel.doc_artifacts`。
- 类型只认 ASCII：译文偶尔把类型名也翻了（`pg_stat_replication.reply_time` 写成"带时区的时间戳"），
  这种照旧用 19 的类型。引用解析不到时也沿用 19 的——自引用（`pg_class.reltoastrelid` → `pg_class.oid`）
  和"any OID column"这类写法本来就解析不出来，不沿用会让 21 个字段在 20 丢掉引用。
- 顺序比的是**两版手册之间**，不是手册对运行时：19 存的是运行时顺序，20 取自手册，两者本来就不一致
  （`pg_stat_database`、`pg_stat_wal`）。再加一道信任判据 `doc_order_is_trustworthy()`：上一版手册顺序
  和运行时顺序本来就不一致的关系，手册顺序说明不了目录变了，不报"顺序调整"——同时 `trusted_order()`
  把这些关系的 20 快照按 19 的顺序摆，免得页面上字段表看着换了位置、变化那句话却说没变。
- 19→20 的变化记录用同样的形状，但只比较字段名、类型、顺序（`description_changes`、`reference_changes`、`attribute_changes` 恒为空）；快照 `schema_source='documentation'`、`runtime_verified=False`、`relation_oid=None`、`release=''`，`source_url` 指 `/docs/devel/<页>`，`definition_source_url` 把 tag 换成 `master`。
- `CatalogVersion('20')`：`label='20 devel'`、`status='devel'`、`support_status='devel'`、`source_tag='master'`、`documentation_version='devel'`、`doc_slug='devel'`。
- 本地没有 devel 手册时跳过 20，报告 `harvest.devel = {'derived': False, 'reason': …}`。
- 推导的基准版本是 cat 的最后一版，不写死 `'19'`；开发版号取 `pgweb.docs.versions.DEVEL_MAJOR_VERSION`。

## 4. 地址与页面

```
/docs/catalog/                    索引：导览 + 版本条 + 筛选 + 按类别分组的大表（含版本轨迹）
/docs/catalog/<name>/             详情，?v=<major> 切版本；默认 status='stable' 的那一版（当前 18）
/docs/catalog/changes/            302 → /docs/catalog/changes/<默认版本>/
/docs/catalog/changes/<major>/    该版本相对上一版的变更；?from=<major> 改比较基准
```

`<name>` 匹配 `^pg_[a-z0-9_]+$`；`changes/` 路由排在 `<name>/` 之前。无效 `?v=` 落回默认版本；无效 name 404。
`shell()` 给"文档"侧栏把 `/docs/catalog/` 标为 active；`LOCAL_ONLY_SECTIONS` 加 `/docs/catalog/`；`struct.py` 把索引、每个关系、每个版本变更页都写进 sitemap。
`columns.py` 里 `catalog` 置 `live: True`，规模写"158 个关系 · 4 类"（cat 的 157 加上 20 推导层的
`pg_stat_kind_info`），覆盖写"PostgreSQL 9.0 – 20 devel"。
三个视图都要挂 `@queryparams`（索引 `q / kind / present / first`、详情 `v`、变更页 `from`）：
`PgMiddleware.process_view` 会把没声明的查询参数整个删掉，不挂就等于 `?v=` 永远收不到。

### 4.1 索引页上下文（`catalog.index()`，缓存 5 分钟）

```
total, kind_count, default_major, earliest_major('9.0'), latest_major('20'),
versions: [ver]                 # 版本条：major, label, status, status_label, support_status,
                                #   relation_count, column_count, kinds, position, doc_slug, release,
                                #   source_tag, documentation_version, runtime_verified, schema_source,
                                #   url('/docs/catalog/changes/<major>/'), preview(bool), devel(bool), is_default
groups: [{kind, label, eyebrow, anchor('kind-catalog'), count, rows: [row]}]
row: {name, url, kind, kind_label, summary, summary_zh, first, last, removed(bool), removed_in('13' 或 ''),
      column_count, changed_in: [...], change_count,
      strip: [{major, label, state, url, preview, devel}],   # state ∈ absent | present | added | changed | removed
      present_tokens('9.0 9.1 … 20'), text(名称+两种一句话+最新字段名，供前端搜索)}
filters: [{param:'kind', label:'类别', options:[{value,label,count}]},
          {param:'present', label:'存在于版本', options:[...]},
          {param:'first', label:'引入版本', options:[...]}]
stats: {relations, columns(最新版字段总数), snapshots, structural_changes}
```

轨迹（strip）的状态：`absent` 该版没有；`added` 首次出现（9.0 基线除外）；`changed` 该版落地了结构变化；`removed` 只标在 `last_version` 的下一版（`pg_pltemplate` 在 13 标 removed）；其余 `present`。`url` 指向 `/docs/catalog/<name>/?v=<major>`，absent 与 removed 无 url。

`versions()`（版本条）与 `doc_pages()`（本站手册已收录的 `(版本段, 文件名)`）各自缓存 5 分钟。
默认版本在建版本条缓存时算一次就记在 `is_default` 上，`default_major()` 与 `pick_major()` 读它，不再查库。

### 4.2 详情页上下文（`catalog.detail(name, wanted_major)`）

```
relation, kind_label, eyebrow, name
version: ver                    # 选中版本（同索引页 ver，多 doc_slug）
previous_major                  # 选中版本的上一版（按 present_in 顺序），9.0 为 ''
snapshot                        # 该版快照（含 doc / description / description_zh …）
description, description_zh     # 快照两种说明
columns: [{name, type, documented_type, description, description_zh, zh_from,
           hidden, not_null, array_dimensions, attnum,
           added(bool 本版新增), type_change({from,to} 或 None),
           references: {text:'pg_namespace.oid', name:'pg_namespace', column:'oid', url:'/docs/catalog/pg_namespace/?v=18' 或 ''} 或 None,
           schema_note}]
removed_columns: [同形，本版相对上一版移除的字段（取上一版快照的值）]
change: 落在本版的 change 记录或 None       # 9.0 基线 None
change_note: str                # 见 4.4 措辞
ribbon: [{major, label, state, url, current(bool), preview, devel, doc_url}]   # state 同 strip；doc_url 本站手册该版有页则给
links: {doc: 本站手册 URL 或 '', doc_label: 'PostgreSQL 18 手册', official: source_url, definition: definition_source_url 或 ''}
facts: [{label, value, url}]    # 类别 / 关系 OID / 关系类型（r 普通表, v 视图 …）+ 共享 / 字段数 / 引入版本 / 状态 / 结构变更次数
timeline: [{to, from, status, url('?v=<to>'), structural, added:[name…], removed:[…], types:[{name,from,to}],
            attrs:[{name, attribute, from, to}], order_changed, descriptions:[{name, from, to}], relation_description_changed,
            references:[{name,from,to}], carried(bool 20 沿用)}]   # 新的在前
matrix: {versions: [ver], rows: [{name, cells: [{major, state, type, url}]}]}   # state ∈ exists | changed | removed | absent
                                # changed = 与上一版相比类型/隐式/可空/数组维数有变；removed 只标在最后存在版本的下一版
system_columns: [{name, type, attnum}]
doc_versions: [{major, label, url}]   # 本站手册收录了该关系的版本
sibling_groups: [索引页 groups 里本类别那一组，供页尾复用索引表；current=name]
notice: '' | '19 beta 3 为预发行快照…' | '20 开发版快照来自本站 devel 手册，只比较字段名与类型…'
versions: [ver]                 # 整条版本条，模板要判"最新一版是哪个"时用
```

字段表默认展示中文描述，没有译文时显示英文并加 `lang="en"`；`references.url` 只在目标关系在本站且该版存在时给。
`facts` 里沿用上一版字段的快照多一行"字段来源：沿用 19（手册没有这张表）"，取自 `carried_from` 与 `carry_reason`。
`ribbon` 的每格另带 `status`（该版的 `CatalogVersion.status`）。

### 4.3 版本变更页上下文（`catalog.changes(major, from_major='')`）

```
version, previous(ver 或 None), from_major, arbitrary(bool 非相邻比较)
versions: [ver]                 # 发布导航条，含 url、is_current
summary: {added_relations, removed_relations, changed_relations, structurally_changed, added_columns, removed_columns, type_changes, description_changes}
added: [card], removed: [card], changed: [card 结构变化], wording: [card 仅描述/引用变化]
card: {name, url('/docs/catalog/<name>/?v=<major>'), kind, kind_label, summary_zh, summary, status,
       tags: [{kind: added|removed|type|attr|order|desc|ref, text}], column_count}
baseline: bool                  # 9.0：列出当时的全部关系
baseline_groups: [索引页 groups 形状，只含 9.0 存在的关系]
```

相邻比较直接用库里的 `changes`，和索引页一样按版本各缓存 5 分钟（`catalog.changes()` 是缓存壳，
`changes_payload()` 是本体）；`?from=` 非相邻比较现算不缓存，用 `catalog.compare(left, right)`
（cat `compare_snapshots` 的移植）。`summary` 里的 `added_columns / removed_columns` 只统计既存关系的增减，
和 cat `transitions[]` 一个口径（12→13 逐项核对过）；新增关系的字段数由"新增的关系"那一段自己说。
另有 `notice` 与 `baseline_note` 两个键。`forget()` 一次清索引页、版本条、手册页清单和每个版本的变更页缓存。

### 4.4 措辞

- 9.0 且存在："9.0 是本数据集的收录基线，不代表该关系首次于 9.0 引入。"
- 本版新增："PostgreSQL 18 新增此关系，共 N 个字段。"
- 有结构变化："相对 PostgreSQL 17：新增 a 个字段，移除 b 个，类型变更 c 处，描述更新 d 处。"（为 0 的项不写）
- 无变化："相对 PostgreSQL 17 无变化。"
- 预发行/开发版在句末追加 `notice`。

## 5. 前端

模板 `templates/wiki/catalog_index.html`、`catalog_table.html`（可复用的分组表，参数 `groups / table_id / top_link / current`）、
`catalog_detail.html`、`catalog_changes.html`，都 `{% extends "wiki/base.html" %}`。
样式追加到 `media/css/wiki.css` 末尾一节 `/* ===== 系统目录 ===== */`，类名前缀 `cat-`（`.wiki .cat-…`），色调用 `.wiki-tone-cat`（绿）；
CSP 禁内联样式，状态一律走 class。亮暗两套。脚本追加到 `media/js/wiki.js`：整行可点改为通用 `table[data-rowlink]`；索引筛选沿用错误码那套逻辑，按 `data-kind / data-present / data-first / data-text` 过滤，URL 写查询参数。

页面结构：

- 索引：面包屑 → H1「PostgreSQL 系统目录」→ 导语 → 四个类别入口（同 `wiki-classnav`）→ 版本条（18 个版本药丸，链到变更页；预发行/开发版虚线）→ 搜索框 + 三个下拉 → 分组大表（每关系两行：名称 · 引入 · 字段数 · 版本轨迹 · 最近变更 / 一句话 · 状态）→ 说明段。
  轨迹是一排 18 个小方格（共用的 `.wiki-cell`），方格 `title` 写"12 · 结构变更"，能点的进该版详情；表头下方的横向刻度隔一格写一个版本号，由 `pgweb/wiki/ruler.py` 的 `mark_ticks()` 标出。
- 详情：面包屑 → 眉题 + H1（等宽）+ 一句话 → 徽章（类别 / 引入 / 状态）→ 事实卡（三栏，同状态码）与三个链接按钮（本站手册 · 官方文档 ↗ · 源码定义 ↗）→ 版本条（当前高亮，变化版本带角标，缺席灰）→ 本版变化一句话 → 本页目录 → 「字段」表（新增字段带「新」角标、类型变化带 from→to、引用可点；本版移除字段另列）→ 「演化历史」时间线（新在前，每项 + − ~ ↕ 标签，描述变化折叠可展开看前后文）→ 「字段矩阵」（字段 × 版本，首列吸附，横向滚动）→ 「系统列」折叠 → 「同类关系」复用索引表 → 页脚（数据来源、纠错入口）。
- 变更页：面包屑 → H1「PostgreSQL 18 系统目录变更」→ 发布导航条 → 汇总数字（七项）→ 新增的关系 / 移除的关系 / 结构变更 / 仅描述更新（折叠）四段卡片 → 9.0 显示基线名单。

## 6. 检索集成

`pgweb/search/indexer.py` 加 `catalog_entry()` 与 `rebuild_catalog()`，`source='catalog'`、`kind='relation'`、`subtype=关系类别`、
`entity_key='relation:' + normalize_name(name)`（与手册页抽出的关系条目一致，结果列表折叠成一条并让本站词条胜出）、
`url='/docs/catalog/<name>/'`、正文含两种一句话、最新版说明与全部字段名、预览含一句话 + 事实 + 字段名。
别名一律有去下划线的形式（`pgstatactivity`）；去掉 `pg_` 前缀的那个只在剩下的部分仍是复合名时才加——
`stat_activity` 指得明确，`class` / `index` / `type` / `database` 是手册里的词，不该把 `pg_class` 顶到手册条目前面。
`service.py` 的来源元组与排序偏好加 `'catalog'`，`source_label` 为「本站词条」；`search-ui.js` 把 `catalog` 与 `errcode` 同等对待。
`index_docs --catalog` 只重建这批条目。

## 7. 维护

```
.venv/bin/python tools/wiki/sync_catalog.py --export /tmp/catalog-YYYYMMDD.json.gz   # 本地导出（读 cat 仓库 + 本地手册）
.venv/bin/python tools/wiki/sync_catalog.py --input /tmp/catalog-….json.gz --write   # 写本地
.venv/bin/python tools/wiki/sync_catalog.py --input /tmp/catalog-….json.gz --target production --write
.venv/bin/python manage.py index_docs --catalog
```

不给 `--write` 就只预览（`preview()`），什么都不写。迁移是 `wiki.0002_catalog`。

发布顺序：拉代码 → `manage.py migrate wiki` → `sync_catalog.py --input … --write` → `index_docs --catalog` → `systemctl restart pgsql.cc`。
页面缓存 5 分钟，导入后命令主动清缓存（`catalog.forget()`）。cat 出新版本（例如 19 正式发布、20 进入 beta）时：更新 `~/pg.center/cat`，重新导出导入即可；20 推导层跟着本站 devel 手册走，手册重灌后重导一次。

导入报告的形状：

```
versions(写了几个版本), added / updated / unchanged(关系数), pruned(bool)
missing: {relations: [...], versions: [...]}    # 快照里没有、库里还在的
removed: {relations: n, versions: [major…]}     # 只有 --prune 才非空
note                                            # 没加 --prune 且 missing 非空时说明这些记录保留了
coverage: {columns: {doc, inherited, none}, relations: {同}, summary_zh}
harvest: {columns_doc, columns_alias, devel: {derived, relations, from_manual,
          carried: [...], added: [...], removed: [...], changed, structural, doc_artifacts: {关系: [字段…]}}}
unlocated                                       # 定位不到字段表的「关系 @ 版本」条数
```

`--prune` 同时删关系和版本；不加就一律保留，只在 `missing` 与 `note` 里报出来。
`validate()` 会逐个检查 `VERSION_FIELDS` / `RELATION_FIELDS` 是否齐全，缺哪个就报哪个字段名。

测试：`manage.py test pgweb.wiki pgweb.search --noinput`（2026-09-11：144 个用例全过）。
本地整条链路核验过的命令：

```
.venv/bin/python manage.py migrate wiki
.venv/bin/python tools/wiki/sync_catalog.py --export /tmp/catalog-snapshot.json.gz
.venv/bin/python tools/wiki/sync_catalog.py --input /tmp/catalog-snapshot.json.gz --write
.venv/bin/python manage.py index_docs --catalog          # → {"catalog": 158}
.venv/bin/python manage.py test pgweb.wiki pgweb.search --noinput
```

页面：`/docs/catalog/`、`/docs/catalog/pg_class/?v=12`、`/docs/catalog/pg_stat_activity/`、
`/docs/catalog/pg_pltemplate/`、`/docs/catalog/pg_statistic/?v=20`、`/docs/catalog/changes/18/`、
`/docs/catalog/changes/9.0/`、`/docs/catalog/changes/20/` 都 200，`/docs/catalog/changes/` 302，无效关系名 404。
