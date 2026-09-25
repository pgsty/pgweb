PGSQL.CC 参考资料模型整理计划，2026-09-25。

本文保留已获授权执行的原始计划，现已完成本地与生产实施，实际结果与验收见 [实施记录](reference-model-rollout.md)。下文保留规划时的研究基线：当时研究基于本地仓库 `c0aaae4d`、本地 `pgweb` 数据库，尚未修改应用代码、迁移或数据库，也未核验生产结构。下文的将来时与拟定名称属于历史规划，最终实现以设计契约及实施记录为准。

**1. 本轮目标是 12 张业务表，以及完整适配它们的读写链路。** 六个领域各自保留实体表；SQLSTATE 的附属内容收进 JSONB，保留类别和版本资料两张公共表；检索继续使用原有两张派生表。业务表由 20 张减到 12 张，连同检索共 14 张。

数据库表名采用小写、单数、领域名称。Django 应用继续使用 `pgweb.wiki` 和 `app_label='wiki'`；Python 主模型名称、管理命令名称、公开 URL、检索身份和 CSS 命名继续沿用。这样表名可以独立整理，已有应用接口和迁移历史也有明确的连续性。

本轮交付覆盖数据库、ORM、快照导入导出、页面组装、模板、检索、缓存、检查脚本、测试与运维文档。五张版本资料表继续独立，SQL 命令继续从实体快照与 `core.Version` 组装版本信息。通用实体表、关系边表、通用图查询引擎和新的报文反查功能不属于本轮交付。

**2. 表名与去向逐一确定如下。** 只有最后八张附属表会在完成内容迁移和验收后删除。

| 当前表 | 目标表或内容位置 | 处理 |
| --- | --- | --- |
| `wiki_errcode` | `sqlstate` | 改名，增加文档内容与列表摘要字段 |
| `wiki_errcode_class` | `sqlstate_class` | 改名，保留类别公共资料 |
| `wiki_errcode_release` | `sqlstate_version` | 改名，保留所采样 release/tag/commit |
| `wiki_catalog` | `catalog` | 改名，保留逐版本 JSON |
| `wiki_catalog_version` | `catalog_version` | 改名 |
| `wiki_guc` | `guc` | 改名，保留现有领域字段 |
| `wiki_guc_version` | `guc_version` | 改名 |
| `wiki_waitevent` | `waitevent` | 改名，保留身份映射与档案 |
| `wiki_waitevent_version` | `waitevent_version` | 改名 |
| `wiki_sqlcmd` | `sqlcmd` | 改名，保留语法和正文快照 |
| `wiki_func` | `func` | 改名，保留各版签名集合 |
| `wiki_func_version` | `func_version` | 改名 |
| `wiki_errcode_text` | `sqlstate.texts[lang]` | 合并全部语言正文与翻译元信息 |
| `wiki_errcode_presence` | `sqlstate.facts` 内的两组区间 | 与已有区间逐项合并，保留证据计数 |
| `wiki_errcode_source` | `sqlstate.evidence.sources[]` | 保留完整来源记录 |
| `wiki_errcode_claim` | `sqlstate.evidence.claims[]` | 保留论断、方法、限制与引用 |
| `wiki_errcode_message` | `sqlstate.evidence.messages[]` | 保留身份、限制、原始记录 |
| `wiki_errcode_template` | `evidence.messages[].templates[]` | 按所属报文嵌套，保留所有模板形态 |
| `wiki_errcode_runtime` | `sqlstate.evidence.runtimes[]` | 保留原始运行证据 |
| `wiki_errcode_case` | `sqlstate.evidence.cases[]` | 保留场景、断言、修复和清理步骤 |

`search_indexedpage` 与 `search_searchentry` 保持表名和分工。公开链接仍为 `/docs/sqlstate/`、`/docs/catalog/`、`/docs/guc/`、`/docs/waitevent/`、`/docs/sql/`、`/docs/func/`。

现有显式业务索引同步去掉历史应用前缀，例如 `wiki_errcode_condition` → `sqlstate_condition`、`wiki_guc_group` → `guc_group`。表改名并不等于所有索引、约束和序列名称自动改名：实施时从数据库目录列出受影响对象，使用 Django `RenameIndex` 或明确的 SQL 处理遗留名称。以真实对象清单为依据，不猜测自动生成的名字。外键的列、目标与删除行为保持原有语义。

**3. SQLSTATE 的最终实体采用普通列加三块 JSONB。** 前轮概念方案中的历史块在实施时继续叫 `facts`：现有内容还包括定义事实、来源与可信度材料，保留名称及未知键更便于准确迁移。

| 字段组 | 最终约定 |
| --- | --- |
| 身份 | `sqlstate` 为五字符大写主键；`klass` 继续映射数据库列 `class_code`，关联 `sqlstate_class` |
| 名称与筛选 | 保留 `condition_name`、`condition_names`、`aliases`、`macros`、`primary_macro`、`severity_classes`、`status` |
| 列表中文 | 新增 `name_zh`、`summary_zh`，由最终中文内容派生 |
| 版本边界 | 保留 `introduced`、`removed`、`known_present_by`、`present_in`、`preview_in`；语义区分精确边界与观测范围 |
| 可信度 | 保留 `depth`、`editorial_review`、`runtime_verification`、`evidence_tier`；证据等级仍是该码曾达到的最高档，不代表所有版本和场景都验证过 |
| 计数 | 保留 `case_count`、`snippet_count`，从同一份证据文档计算 |
| `facts` | 保留当前事实 JSON 的信息；吸收两类存在性区间中子表独有的字段 |
| `texts` | 新增对象，按现有语言键 `zh`、`en` 组织，其他合法已有语言也保留 |
| `evidence` | 新增对象，含 `sources`、`claims`、`messages`、`runtimes`、`cases` 五个数组 |
| 导入元信息 | 保留 `source_rev`、`imported_at`，新增稳定的 `content_hash` |

正文对象的完整字段是 `title`、`name`、`description`、`summary`、`body_md`、`sections`、`translation_source_rev`、`is_stale`。`sections` 继续保存章节锚点、标题与已清洗的 HTML。中文缺失时按现有规则回退英文；不会因为站点只显示中文而删除英文资产。

证据数组中的字段直接继承现有业务字段，保留 `source_id`、`claim_id`、`message_id`、`runtime_id`、`case_id` 和 `position`。报文保留 `raw`，其 `templates` 保留 `kind`、`role`、`template`、`literal`、`position`；运行记录也保留 `raw`。数组按 `position` 排列，模板的父级通过嵌套关系确定。数据库生成的附属表行号不作为新的业务身份；完整旧备份保留它们用于审计。

当前 `facts` 已经由 `trim_facts()` 裁剪过，不能拿它代替八张子表的内容。迁移以现有库记录为准，保留源文件重新导出不能覆盖的本站摘要、翻译状态和已有人工内容。

存在性区间的合并以 `(era, position)` 对齐：`modern` 对应 `facts.presence_intervals`，`pre9` 对应 `facts.pre9_presence_intervals`。保留事实数组中原有的额外字段，再补入子表的证据计数及必要排序信息；共同端点或条数冲突时报告差异，不能静默选一边。旧快照只有子表区间时按其已有字段构造。验证器能把最终区间展开成旧子表的全部业务字段。

新增 SQLSTATE 格式、类别前缀一致性及 JSON 顶层类型检查。内部记录 ID、引用和数组结构由导入校验负责。现阶段不为大块 JSON 自动建立 GIN 索引；名称、类别等实际使用的列继续承担检索和列表查询。

**4. 证据引用需要按真实目标呈现。** 本地实查发现，`claim.sources` 有 89 处、`message.sources` 有 6 处无法在同一码的来源表中匹配。进一步按所有证据记录的业务 ID 对齐，其中 83 处指向运行记录、8 处指向其他断言，只有 4 处在当前已入库的证据中尚未找到目标。它们不能一律解释为丢失源码链接。

未解析的四处均是 `runtime.observation` 断言中的 `manifest.22001`、`manifest.22003`、`manifest.22004`、`manifest.22007`。这些 ID 原样迁移并进入差异报告；实施时到权威材料核对，确认有出处才补全。迁移完整性以没有新增或丢失引用为准，不能通过删除四个 ID 让校验通过。

页面组装建立本条 SQLSTATE 内的来源、断言、运行记录、案例映射。保留原始引用数组，同时生成供模板使用的带类型引用：源码链接指向原始来源，运行和断言引用指向相应页内记录。部分 ID 同时属于来源和运行记录，应返回明确的匹配类型并保留两者关联，不以字符串前缀猜测唯一目标。引用只展开一层，避免断言互引产生递归。

现有 `source_index()` 及 `[sources[s] for s in ... if s in sources]` 会过滤掉非源码目标，需要改成上述引用组装。未解析的目标在证据区保留可见标识和缺失状态；有来源的记录继续显示固定 commit、tag、位置和限制条件。

**5. 页面继续呈现工具书内容，新结构通过统一组装入口驱动。** `pgweb/wiki/errcode.py` 负责把普通列和 JSON 转为模板字典，模板直接使用明确字段。无需模拟旧 Django RelatedManager。

| 页面或组件 | 调整后的行为 |
| --- | --- |
| SQLSTATE 索引 | 一次读取摘要列和类别；`defer('facts', 'texts', 'evidence')`；名称、摘要、筛选与分组来自同一份派生结果 |
| SQLSTATE 详情 | 主行和类别联查；直接读取三块 JSON；取消八组附属记录预取；保留正文与结构化面板插入顺序 |
| 报文模板 | 字典提供 `kind_label`，替换 ORM 的 `get_kind_display`；单复数、变体、DETAIL/HINT/CONTEXT 完整显示 |
| 证据区 | 显示来源、断言、案例、运行记录及带类型引用；保留适用范围和缺口 |
| 版本事实卡 | 有精确证据时显示“引入版本”；只有下界时显示“最早已知存在”；移除证据不足时只显示已移除及已知观测范围 |
| 版本条 | 覆盖来自已有版本事实；未取样与确认缺席分别呈现，取消凭 `status='active'` 自动推断存在于硬编码开发版的行为 |
| 版本选择 | SQLSTATE 的 `?v=` 仍用于选择手册链接，源码证据保持原核验提交；不把一次运行记录扩展成所选版本的实测结论 |
| 其他五个领域 | 继续读取各自主表的 `versions`、`changes` 和专属 JSON；在索引与搜索卡片中一致呈现基线、沿用和未知状态 |
| 搜索结果与预览 | 使用同一套 SQLSTATE 摘要和版本措辞；保持与手册实体折叠；SQL 命令版本预览和铁道图照常读取 `SqlCommand.versions` |

`first_version` 与 `last_version` 在其余领域表示收录范围。已有的 `baseline`、`carried_from`、`carry_reason`、`prose_only` 等信息继续参与呈现。版本顺序使用现有版本排序规则；GUC 的规范大小写、等待事件的更名和类型迁移、函数重载集合及 SQL 命令 slug 都保持原来的实体身份规则。

版本资料表记录的是所采样的数据构建。页面当前支持状态可以参考 `core.Version`，但 beta 3 的快照不能因此被改称 beta 4。合并布局不扩大数据已验证的版本范围。

**6. 导入统一为校验、组装、比较、写入四步。** 一份固定快照先升级到目标格式，校验内容与引用，再算摘要和指纹，最后在事务内原位更新实体及公共资料。

- SQLSTATE 快照升级为 `format=2`，`codes[]` 包含最终三块 JSON。新导入器保留读取 `format=1` 的纯转换函数，旧导入器遇到新版快照仍应拒绝。
- `tools/wiki/sync_errcode.py` 与 `wiki_import_errcode` 两个入口走相同的格式升级和校验；其他五组导入入口保持既有接口。
- `data/wiki/errcode-summaries.json` 继续作为本站摘要覆盖源。导出阶段应用覆盖后再计算 `texts.zh.summary`、`summary_zh` 和指纹，使固定快照自包含；迁移当前库时使用库里的有效摘要。生产加载 `--input` 时不再用另一个本地文件偷偷改写快照结果。
- `name_zh`、`summary_zh`、案例计数、片段计数只有一份派生规则。HTML 继续走现有清洗和链接改写逻辑。
- 默认保留快照缺项；完整快照经核对后使用现有 `--prune` 语义删除。实体、类别与版本的引用一致性一并校验。
- 事务成功后清除该栏目的缓存，输出准确的对应检索重建命令。把 `sync_errcode.py` 里的旧 `index_docs --wiki` 提示改成当前支持的 `--errcodes`。

六个主实体表统一增加 `content_hash`。指纹来自规范化后的落库业务字段，排除 `source_rev`、`imported_at`、导出时刻和指纹自身，包含实际正文、摘要、顺序、证据及快照内容；对象键稳定排序，数组顺序保留。输入如提供指纹必须重新计算校验，不盲目信任。

`source_rev` 保留来源身份；新导出不再把本次运行时间拼入内容变更依据。旧行已有值原样迁移，无法从中恢复的源提交不编造。来源身份变了但内容没变时可单独刷新来源元信息，统计上与内容更新分开；`imported_at` 保持最近一次业务内容写入的时间。发布执行时间留在发布记录中。

SQLSTATE 当前的整码哈希跳过逻辑，以及其余领域包含 `source_rev` 的逐字段比较都要相应修改。可新增小型 `pgweb/wiki/snapshot.py` 共享稳定编码与指纹函数；各领域仍保留自己的字段列表、校验与转换，避免引入通用导入框架。

**7. 检索保留独立的派生边界。** 错误码内容从新主表生成 `SearchEntry`；正文和模板两张旧表的空 `search_vector` 随表删除，当前统一检索内容不会因此丢失。

| 检索身份 | 保留值 |
| --- | --- |
| SQLSTATE | `source='errcode'`、`kind='error'`、原有归一化 `error:<code>` 实体键 |
| 系统目录 | `source='catalog'`、`kind='relation'` |
| GUC | `source='guc'`、`kind='guc'` |
| 等待事件 | `source='wait'`、`kind='waitevent'` |
| SQL 命令 | `source='sqlcmd'`、`kind='sql'` |
| 函数 | `source='func'`、`kind='function'` |

表名、检索来源标识和 URL 分别有自己的职责，表改名不触发这些身份的批量替换。`rebuild_errcodes()` 从 `code.texts` 取正文，取消对 `ErrorCodeText` 的依赖；复用详情页事实卡的边界措辞，避免搜索预览仍显示旧结论。

保留手册条目的 `(document_id, key)` 唯一约束，为 `document_id IS NULL` 的条目新增 `(source, key)` 条件唯一约束。迁移前检查包括扩展目录在内的所有这类条目，有冲突时先定位生产者。当前本地未发现此类重复。保持 `SearchEntry.document` 的既有外键和数据库级级联行为，使用独立 `AddConstraint`，不借此改动该字段。

上线时重建六个百科来源即可，手册和扩展的数据源并未改变。检索重建会重新分配派生条目的 ID，验收比较业务键、URL、内容与结果折叠，不把派生行号当永久链接。

**8. 项目引用按下面清单调整和验收。** “必须修改”表示当前实现已确定依赖旧表或旧对象形状；“适配检查”表示通过 ORM 读取主表，表名变化可以由模型承接，但需要覆盖查询与页面行为。

| 文件或文件组 | 等级 | 具体工作 |
| --- | --- | --- |
| `pgweb/wiki/models.py` | 必须修改 | 12 个 `db_table`；删除八个附属模型；增加正文、证据、中文摘要和指纹字段；索引命名及必要约束 |
| `pgweb/wiki/migrations/` 的新增迁移 | 必须新增 | 兼容字段准备、历史数据组装、12 表改名、最终子表删除和逆向数据恢复 |
| `pgweb/wiki/importer.py` | 必须修改 | format 1→2、完整打包、引用校验、摘要覆盖、稳定哈希、单行写入及公共资料同步 |
| `pgweb/wiki/errcode.py` | 必须修改 | 主表摘要查询、JSON 详情组装、带类型引用、版本边界与覆盖状态、缓存失效 |
| `pgweb/wiki/views.py` | 必须修改 | 对接正文字典；修改 `text.summary` 等属性访问及描述生成；保留视图地址和异常行为 |
| `templates/wiki/errcode_index.html` | 必须修改 | 收录范围与版本语义说明、实际覆盖来源 |
| `templates/wiki/errcode_table.html` | 必须修改 | 观测下界和精确引入的不同显示、状态文案及筛选数据 |
| `templates/wiki/errcode_detail.html` | 必须修改 | `kind_label`、动态版本标签、覆盖缺口、证据引用和页内目标 |
| `pgweb/search/indexer.py` | 必须修改 | 去掉 `ErrorCodeText`；读取新内容；统一卡片语义；六领域索引回归 |
| `pgweb/search/models.py` 与新增 search 迁移 | 必须修改 | 增加非手册条目的条件唯一约束；补全当前来源枚举的说明 |
| `pgweb/wiki/{catalog,guc,waitevent,sqlcmd,func}_importer.py` | 必须修改 | 内容指纹、时间与来源分离；保持版本资料和领域专属校验 |
| `pgweb/wiki/management/commands/wiki_import_*.py` | 入口适配 | 统一调用新版校验和比较；保留当前参数、只检查模式及 JSON 报告 |
| `tools/wiki/sync_*.py` | 入口适配 | 固定快照、远端同版导入、报错和重建提示；SQLSTATE 格式升级 |
| `tools/wiki/check_data.sql` | 必须修改 | 全部新表名；把遗漏的 SQLSTATE 加入六领域验收；JSON/摘要/计数/检索对应检查 |
| `pgweb/wiki/struct.py` | 适配检查 | 六领域 sitemap 来自主实体；逐 URL 集合验收 |
| `pgweb/wiki/{catalog,guc,waitevent,sqlcmd,func}.py` | 适配检查 | 索引大列延迟加载；版本、详情和变更查询；对实际不准确的生命周期标签做必要修正 |
| `pgweb/wiki/{guc,waitevent,sqlcmd}_common.py`、`ruler.py` | 适配检查 | 共用身份、排序和版本条规则，保留不同领域的已有语义 |
| `templates/wiki/` 其余模板与 `sqlcmd_preview.html` | 适配检查 | 六个领域索引、详情、变更和预览；保留 SQL 铁道图和语言回退 |
| `pgweb/search/service.py`、`docviews.py`、`views.py` | 适配检查 | 原始 SQL 只引用检索表；检查实体折叠、SQL 命令预览和路由，无需替换来源标识 |
| `pgweb/search/management/commands/index_docs.py` | 适配检查 | 六个现有开关和全量入口均能重建新模型内容 |
| `media/js/wiki.js`、`media/css/wiki.css` | 按呈现需要修改 | 版本状态、引用样式、筛选行为；保留现有选择器，实际变更同步测试 |
| `media/js/{search-ui,docsearch,palette}.js` | 适配检查 | 预览响应形状、全站弹窗和版本切换；没有响应契约变化则无需改动 |
| `pgweb/urls.py`、`pgweb/wiki/urls.py`、`pgweb/util/contexts.py`、`pgweb/wiki/columns.py` | 适配检查 | 菜单、旧地址跳转、规模和来源说明；保持公开路由 |
| `data/wiki/errcode-summaries.json` | 保留并校验 | 保留每条有效摘要；覆盖顺序与指纹必须一致 |
| `pgweb/wiki/tests.py` 与现有各领域测试 | 必须修改／补充 | 去掉附属 ORM 断言；测试文档结构、页面与有效内容 |
| `pgweb/search/tests.py`、`tests_waitevent.py`、`test_manual_versions.py` | 必须覆盖 | 跨来源唯一性、实体折叠、预览和版本行为 |
| 新增 `pgweb/wiki/test_reference_migration.py` | 必须新增 | 使用历史模型验证旧库→新库、空库完整迁移和逆向展开 |
| `docs/encyclopedia-design.md` | 必须修改 | 更新当前数据模型，区分历史设想与已实现能力，消除已废弃 `/wiki/` 和反查描述 |
| `docs/{catalog,guc,waitevent,func,sqlcmd}-column.md` | 必须修改 | 表名、字段语义、导入与验收方式 |
| `docs/document-search.md`、`docs/wiki-data-deployment.md` | 必须修改 | 新取数来源、六领域检查与本轮切换步骤 |
| `CLAUDE.md` | 必须修改 | 更新生效表结构和操作入口；`AGENTS.md` 为软链接，不另存副本 |

旧迁移 `wiki.0001–0006`、`search.0001–0004` 保持原样。历史部署记录中的旧表名和旧时间保留，在当前操作部分补充新口径。最终搜索旧表名时，允许命中历史迁移、旧到新转换、明确标记的历史证据以及本计划；运行时路径不得依赖已移除表。

**9. 迁移按“扩展、回填、切换、收缩”落地，生产采用短暂维护窗口。** 变更可分提交评审；涉及同一数据结构的最终读写代码与切换迁移必须一起发布，旧进程不能在表改名后继续接请求。

| 拟定迁移 | 内容 | 验收点 |
| --- | --- | --- |
| `wiki.0007_reference_documents` | 六主表增加指纹；错误码增加摘要和 JSON；处理旧反向关系名称冲突 | 原数据和旧表完整；Django 状态可渲染 |
| `wiki.0008_backfill_reference_documents` | 从历史模型读取主表与八子表，组装内容、填摘要与指纹 | 全量业务字段可逆；有效摘要与顺序一致；数据异常报告明确 |
| `wiki.0009_reference_table_names` | 12 个 `AlterModelTable` 及相关显式索引改名 | 行数、内容、主键及外键语义一致，只有命名变化 |
| `search.0005_catalog_entry_identity` | 非手册条目条件唯一约束 | 包含扩展目录的冲突预检；原级联关系完整 |
| `wiki.0010_retire_errcode_children` | 校验新旧文档等价后删除八个子表，应用最终约束 | 只剩目标 12 表；所有生产取数路径走新结构 |

迁移编号以真正实施时的迁移叶子为准。历史数据迁移通过 `apps.get_model()` 及当前数据库别名访问，转换逻辑固化在迁移中，不能导入会继续变化的现行 ORM 或导入器；迁移过程中不联网、不重抓来源、不改译文、不重新渲染旧正文。

有一个已确认的名称冲突：旧 `ErrorCodeText.errcode` 的 `related_name='texts'` 与新 `ErrorCode.texts` JSON 字段同名。添加字段前，将旧反向关系在迁移状态中改成 `legacy_texts`，数据库外键保持原样；可用明确的状态操作表达。八个旧模型最终删除后，新模型只保留 JSON 字段。

对子表进行可逆删除时，迁移操作顺序必须允许回滚先重建表，再由新文档恢复全部业务内容；恢复模板时先建立父报文并重新映射数据库行号。主行、正文、证据的业务 ID 和顺序是往返比较依据。不要使用空的逆向操作让“迁移成功回滚”留下空表。

维护窗口内停止百科导入任务与可能使用旧模型的爬虫/工作进程，备份并验证恢复后，部署同一版本代码，执行迁移、重建六来源检索、清除相关缓存，再启动新进程并做 HTTP/浏览器验收。无需长期双写或新旧表兼容视图。

回退时，先停止新进程；尚未删除子表时也要确认它们与新 JSON 一致，新代码可能已写入新内容。已完成收缩时，通过经过演练的逆向迁移从新文档恢复旧表，或恢复维护窗口备份并明确处理窗口后的写入，再启动对应旧代码。代码回退和数据库回退须成对。

本项目生产目标始终是 `ssh pg` 的 `/data/app/pgsql.cc`、数据库 `pgweb`、服务 `pgsql.cc`。实施前重新确认连接、代码版本、迁移状态、脏工作及后台任务；英文 PG.CENTER 的库与历史回退实例另有边界。

**10. 验收以数据等价和真实行为为准。** 研究时本地六类实体分别为 SQLSTATE 263、系统目录 158、GUC 449、等待事件 302、SQL 命令 188、函数 708；这些数字是本轮基线，不能硬编码成以后同步永远不变的断言。

| 验收项目 | 标准 |
| --- | --- |
| 迁移范围 | 12 张目标业务表与两张既有检索表；八个旧子表仅在回填与比较通过后移除 |
| 全量 SQLSTATE 内容 | 263 条当前实体逐条比较，覆盖 526 份正文、5258 段区间、1294 个来源、964 个断言、565 条报文、785 个模板、169 个运行记录、100 个案例 |
| 原始事实 | 当前 `facts` 的每个信息字段有明确去向；区间合并可还原旧业务字段；`raw` 和限制条件保留 |
| 引用 | 内部 ID 唯一、模板归属正确；按目标类型解析；当前四处未解析引用保留并单列，不能新增静默丢弃 |
| 其他领域 | 改名前后实体主键集合及全部业务内容指纹一致；版本与变化 JSON 一致 |
| 幂等 | 同一快照重复导入零内容更新；内容相同但导出时间不同仍零内容更新；摘要变化能准确触发一个实体更新 |
| 格式与回退 | v1 SQLSTATE 快照可升级；v2 可双端导入；旧库前进、干净库从零迁移、逆向迁移均在独立测试库验证 |
| 页面 | 六个索引均非空且实体集合正确；SQLSTATE 263 个详情自动检查；其他领域按当前覆盖版本和特殊边界检查 |
| 版本语义 | `23505` 的历史下界、`57P04` 的精确补丁版本引入、`72000` 的未取证移除边界；PG20 未采样、beta 构建、GUC 沿用、函数 `prose_only` 均明确显示 |
| 报文与证据 | 模板总量和归属全量比较，变体与非 primary 形式不漏；运行/断言引用有实际目标或明确缺失标识 |
| 检索 | 六来源条目 URL 集合和实体集合一致；状态码与手册折叠；跨版本预览、SQL 铁道图、扩展搜索正常 |
| 缓存 | 清除栏目索引、版本、变更页及检索目录的相关缓存；避免复用旧 ORM 对象序列化结果；实例内缓存随服务重启更新 |
| 读取范围 | SQLSTATE 索引不读取大 JSON；详情不查询已删除表；冷缓存与热缓存分别检查查询和页面耗时 |
| 表示层 | 桌面／移动、亮／暗主题、筛选、锚点、旧 URL 跳转、全站搜索弹窗均通过浏览器检查 |
| 发布 | 本地与生产分别完成数据、迁移、索引、服务和公网页面验收，HTTP 200 不能代替内容核验 |

研究时已只读确认：五类证据业务 ID 没有空值或同一码内重复，模板与父报文的 SQLSTATE 无冲突；claim→runtime 和 runtime→case 引用均可匹配。生产需独立运行相同检查；普通 source 数组需要按第 4 项的多类型规则检查。

计划中的测试入口为 `.venv/bin/python manage.py test pgweb.wiki pgweb.search --noinput`，并执行 `manage.py check`、`makemigrations --check --dry-run` 与迁移专用测试。新旧快照往返和备份恢复使用隔离数据库。完成模型变更后重建六来源：

```bash
.venv/bin/python manage.py index_docs --errcodes --catalog --guc --waitevents --sqlcmd --func
```

以上为规划时给出的实施入口，执行结果见实施记录。`tools/wiki/check_data.sql` 改造后分别在正确的本地连接与 `service=pgweb.pg` 检查；SQLSTATE 按自己的实际覆盖范围校验，不套用其他领域“PG10–20 必须齐全”的规则。

**11. 工作分为四个可评审交付包。** 每包都有具体完成标准，整个重构在最终包验收后才算完成。

| 顺序 | 交付内容 | 完成标准 |
| --- | --- | --- |
| A | 表名映射、最终字段契约、v1→v2 转换与迁移实现 | 旧内容可逆，历史迁移重放通过 |
| B | 六领域导入幂等、SQLSTATE 新取数、模板与引用呈现、检索适配 | 从固定快照导入到页面与搜索的整条链路通过 |
| C | 全量数据比较、性能读取范围、浏览器检查、运维文档与测试 | 所有运行时引用适配，四处已有引用缺口处理状态明确 |
| D | 本地迁移演练、生产维护窗口、上线与回退验收 | 两端分别留下结构、数据、索引和页面证据 |

实施按上述完整链路推进；实际完成状态、执行差异和备份位置统一记入实施记录。

技术依据：[Django `db_table`](https://docs.djangoproject.com/en/5.2/ref/models/options/#db-table)、[Django 迁移操作](https://docs.djangoproject.com/en/5.2/ref/migration-operations/)、[PostgreSQL JSON 文档设计](https://www.postgresql.org/docs/18/datatype-json.html#JSON-DESIGN)、[PostgreSQL 唯一约束](https://www.postgresql.org/docs/18/ddl-constraints.html#DDL-CONSTRAINTS-UNIQUE-CONSTRAINTS)。本项目具体行为以 [`models.py`](../pgweb/wiki/models.py)、[`importer.py`](../pgweb/wiki/importer.py)、[`errcode.py`](../pgweb/wiki/errcode.py)、[`indexer.py`](../pgweb/search/indexer.py)、[现有发布验收](wiki-data-deployment.md) 为核验入口。
