# PostgreSQL 版本对比

入口 `/docs/compare/`，`/docs/compare` 由 Django 规范化到带斜杠地址。入口位于文档导航的“发行说明”之后，发布说明归档也提供链接。

这是 PGSQL.CC 原生 Django 页面。本站支持指定起始与目标两个版本，也可阅读某次发布的完整清单；覆盖 PostgreSQL 9.0 起全部已发布小版本。预览版本独立标注，没有变更正文的开发占位版本不提供对比。发布、原始条目、提交关联组与数据集元信息存入四张数据库表，数据模型和无损导入导出见 [version-compare-storage.md](version-compare-storage.md)。

## 使用与接口

- `/docs/compare/?from=17.0&to=18.6`：跨大版本比较。
- `/docs/compare/?from=18.0&to=18.6`：同分支补丁比较。
- `/docs/compare/?release=9.6.24`：该次发布的全部原始变更，包括兼容性说明；首发版本也可独立阅读。
- `/docs/compare/?from=9.0&to=18.6`：从 9.0 首发开始的累计差异。
- 裸大版本 `17` 归一化为 `17.0`，`9.6` 归一化为 `9.6.0`；`from` 也接受完整 `SELECT version()` 输出。9.x 使用三段版本号，9.6.10 排在 9.6.9 之后。两个版本相同时返回空比较；目标更早、未知版本和未发布的 `18.5` 返回可读的 400 错误。
- `q`、`kind` 保存前端全文关键词与分类筛选，分享链接同时保留版本、筛选和条目锚点。分页只影响显示，服务端返回完整清单，关闭 JS 仍可浏览、提交版本和展开正文。
- 相同参数增加 `format=json` 下载完整报告。JSON 与页面使用同一比较器，不因前端分页和筛选而丢失条目。

每条记录包括完整中文正文、代码、嵌套步骤、主题路径和原始说明链接。迁移与兼容性操作单独保留。分类用于浏览，分为新功能、BUG 修复、性能改进、安全相关、兼容性变化和其他改进。

条目展开后提供其他版本的关联记录及跳转锚点。`equivalent`（同一变更）需要完整对应证据；`related`（相关提交）表示部分共享、后续修正或首发功能与维护补丁的提交关联，不能直接视作重复。原始条目始终按发布版本独立保留。JSON 提供稳定数据库 ID、提交组 ID、关系类型及证据；数据库保存原始字段和历史修订，合并只影响对比报告的呈现。

## 比较语义

同一分支直接取 `(起始小版本, 目标小版本]` 中的每一条发布记录，不能因为两次修复的标题相同而删除后一次记录。

跨分支比较采用发布历史的继承路径：经过的每个大版本纳入其首发内容，旧分支的补丁只纳入截至下一大版本首发日期的部分，且任何补丁均不得晚于目标的发布日期。从目标历史中减去起始版本已含的记录。旧分支较晚的修复只有在新分支也有对应记录时才纳入。这是发行说明的历史路径，旧分支维护记录不表示已经逐项验证目标二进制也需要同一个修复。

例如 `17.0 → 18.0` 的候选是 `17.1` 至 `17.6` 与 `18.0`，不包含 `17.7` 至 `17.11`；`17.11 → 18.6` 的候选只有 `18.0 / 18.1 / 18.2 / 18.3 / 18.4 / 18.6`，再排除 `17.11` 已经含有的共享修复。不会把 17 与 18 两个分支的全部小版本相加。被跳过的 `18.5` 是上游未发布的版本号，不补造记录。

回补关系取自上游 SGML 中保留的逐分支提交注释。每个独立提交的回补组分别保留，不能将一条含多个提交的记录看成一个提交；已知其中一个提交并不代表另外几个提交也已包含。未能确认相同的记录保留，不以模糊相似度删除。兼容性操作与普通变更即便来自同一提交，也分别保留。

同一 `Author:` 块仅证明提交存在回补关系，不证明两个分支拥有完全相同的功能。大版本首发条目只有在完整英文说明一致时才允许按提交对应关系合并；不能因为某个功能的一部分回补到旧分支，就删掉新大版本的完整功能。真实反例包括：17.5 的 Snowball 内存不足修复与 18.0 的爱沙尼亚语词干支持；15.4 的认证文件令牌上限 10240 字节与 16.0 的无限长度；12.3 对长 `bytea` 的 `get_bit/set_bit` 修复与 13.0 允许访问 256MB 以外位的 `int8` 参数。这些记录现在分别保留。

维护分支之间可按全部提交对应关系确认已知修复；缺少提交信息时，仅使用同日、完整英文正文完全相等的回退规则，不能以相同文案覆盖已经明确不同的提交。英文正文身份来自独立对齐的上游源，避免中英文翻译差异影响去重。一个条目同时含有起始版本已知的 A 与本报告已列出的新修复 B 时，不重复计算 B；仍保留整段说明。合并的各分支原文、版本与来源链接保存在代表条目的 `variants` 中。单个代表条目不会吸收同一分支的两条记录。

JSON 报告公开 `history.source/target/candidates` 与逐条 `exclusions`。`already_in_source_count` 表示起始版本已包含的记录；`duplicate_count` 表示报告内部合并的跨分支记录。每次排除均提供 `reason`、`method` 与所依据的 `matches`，已包含记录也保留全文；恒有 `candidate_count = total + already_in_source_count + duplicate_count`。

一般修复的计数是发布说明记录，不推断未在发布说明中记录的二进制差异或每个 BUG 的精确受影响范围。

## 安全信息

`data/compare/security.json` 从 PostgreSQL 官方安全索引、历史分支归档、每个 CVE 的详情页与 PostgreSQL CNA 发布的 CVE JSON 构建。记录 CVSS **基础分**、向量、逐分支修复版本与精确受影响区间。CNA 区间起点包含、终点排除；未提供的历史日期和评分保持空值。

页面的 CVE 修复清单只列“起始版本受影响、目标版本已修复或不受影响”的漏洞，和发布说明全文中提到的 CVE 编号分别处理。回归修复提及旧 CVE 不增加修复数。目标版本重新暴露起始版本没有的已知漏洞时，另列风险及修复版本。官方矩阵未覆盖的测试分支显示“—”，不推断安全状态。

单版本清单展示本版说明提到的 CVE，标题明确为“提及”，不当作新增修复数。历史漏洞仅在官方首发日期晚于已有修复发布日期等明确证据下标记新分支继承修复，并公开 `target_state_evidence`；官方 CNA 精确区间优先。结束维护后的未知漏洞状态保持未知。

```sh
.venv/bin/python tools/docs/fetch_compare_security.py --refresh
# 完全使用前一次抓取的缓存重放
.venv/bin/python tools/docs/fetch_compare_security.py --offline --output /tmp/security-replay.json
```

发布日期、停止维护时间与未发布状态来自同一快照。数据抓取和正文解析都在构建时进行，请求不访问外网。

## 更新、验证与发布

发布说明提取、字段和完整性校验见 [version-compare-data.md](version-compare-data.md)。更新中文手册和版本元数据后执行：

```sh
.venv/bin/python manage.py build_compare --check
.venv/bin/python manage.py build_compare
.venv/bin/python tools/docs/fetch_compare_security.py --refresh
.venv/bin/python manage.py test pgweb.docs.test_compare pgweb.docs.test_compare_data pgweb.docs.test_compare_security --noinput
node --check media/js/compare.js
.venv/bin/python tools/docs/audit_compare.py --output tmp/compare-recalibration/engine-audit.json
.venv/bin/python manage.py migrate docs
.venv/bin/python manage.py import_compare data/compare/releases.json.gz --language zh --check
.venv/bin/python manage.py import_compare data/compare/releases.json.gz --language zh --write
.venv/bin/python manage.py import_compare data/compare/security.json --kind security --write
.venv/bin/python tools/docs/audit_compare.py --jobs 4 --database --language zh \
  --reference data/compare/releases.json.gz --security-reference data/compare/security.json \
  --output data/compare/comparison-audit.json
```

同时提交快照、审计报告及代码。生产使用 `/data/app/pgsql.cc` 的 `main`；备份后拉取代码，执行 `migrate docs`，导入已审核发布与安全数据，核验后重启 `pgsql.cc`。英文独立项目对应 `--language en`、`center` 数据库和 `pg.center` 服务。生产不用复制 pgdoc checkout。若另外导入了手册页面，须对检索支持的涉及版本增量运行 `index_docs --versions ...`；当前定义检索不收录 9.x。

`audit_compare.py` 穷举所有可选版本对：逐项核对小版本区间的 ID 与顺序、候选条目的唯一归属、合并及排除的完整正文、所有排除的提交/英文正文证据，以及首发条目不能被部分回补掩盖的约束。输出中 `pair_digest` 基于上游 `source_entry_id`、比较决策及 CVE 获得/遗留/回归集合与继承证据，不包含中文/英文展示文字，可用于两站结果一致性核验。它不替代 SGML 抽取覆盖审计或 CVE 来源审计。

访问页面、单版本清单与关联链接、版本对比 JSON、小版本/CVE 示例、预览和错误边界，并检查桌面与手机的明暗主题、键盘操作、分类/搜索/分页、分享链接、条目锚点与禁用 JS 情形。请求只读取当前数据库中已激活的数据集，以数据集修订号缓存；导入事务提交后各工作进程自动更新。文件仅用于构建、运输和独立审计，不作为运行时回退。未导入或损坏的数据返回 503。

## 9.x 与数据库扩展

当前收录 353 份发布快照：9.0–18 的 351 个正式版本、19beta4 与 20 开发占位；352 个可选版本，共 16,113 条原始记录。9.0–9.6 新增 178 份正式发布说明、6,819 条记录。完整来源和全部 62,128 个版本对的审计结果以已提交的 `data/compare/source-audit.json` 和 `comparison-audit.json` 为准。

原始字段、完整正文和未识别扩展字段均保留；源更正保存之前的修订。默认导入保留缺失实体，仅在显式 `--complete --prune` 时撤下缺项而保留历史。重复导入相同内容不重写实体。`export_compare --archive` 可导出四张表、历史与停用记录，普通导出可精确还原导入的源 JSON。

## 2026-09-26 首次数据补齐

后续重新校准的最终验收记录位于 `data/compare/source-audit.json` 与 `comparison-audit.json`。独立核验 173 份正式发布说明及 19beta4，共 9,294 条记录；重新校正提交解析和跨分支语义后，中英全部 15,225 个可选版本对的条目、分类与排除决策完全一致（摘要 `559cbf1afce2de1dd31bf2a26d379aebf574a1539f01dbab1bbef2618da87e88`）。`17.0 → 18.0` 为 465 条；`17.11 → 18.6` 从 561 条候选排除 264 条已知记录，保留 297 条；`10.0 → 18.6` 修正为 3,755 条。297 的总数虽未变化，爱沙尼亚语词干功能与 `pg_buffercache` 修复的实际去留已经校正。以下保留首次实施时的历史记录。

本地和生产原有手册缺少 `10.23 / 11.22 / 12.22 / 13.23 / 14.24 / 15.19` 六份最新发布说明。中文 SGML 已存在于同级 `pgdoc/zh/<major>/release-<major>.sgml`，使用其现有 DocBook 样式单独渲染对应章节；PG10 先用 OpenSP 转 XML。生成结果应用 pgdoc 的 CJK 空白规范化，仅通过 `get_or_create` 插入缺失页面，保留所有已有页面。

生成脚本、HTML、完整入库 JSON 位于本地 `tmp/compare-missing/`，生产原记录查询备份及入库数据位于 `/data/app/pgsql.cc/tmp/compare-release-20260926/`。六页包含 29、31、1、43、83、90 条变更；PostgreSQL 12.22 确实只有一条修复。两端插入后重建相关版本文档索引。

首次验收：175 份原始发布快照（173 正式版、19beta4、20 开发占位页），共 9,294 条变更；页面排除无正文的 20 占位页。官方安全快照有 177 个 CVE、58 份精确受影响区间。逐页核验条目数量、涉及 CVE 与完整正文无遗漏，945 个内部手册目标页面全部存在。所有正式分支的 1,922 组同分支比较与源记录的条目 ID、顺序、分类计数及迁移正文逐一一致，65 项提取、比较、中间件、缓存和既有发布说明测试通过；Django 检查、迁移检查与 JS 语法检查通过。

浏览器验证包括 18.0 → 18.6（351 条记录、46 个修复 CVE）、17.11 → 18.6（297 条记录、0 个新增修复 CVE）、10.0 → 18.6（3,749 条记录、79 个修复 CVE）、19beta4 预览、重复及倒序输入、未修复和新增风险提示。320/390 px、桌面明暗主题均无横向溢出；筛选、分页、条目直达、分享、JSON 和无 JavaScript 浏览通过，无 CSP 或 JavaScript 错误。

上述首次实施的回退不涉及数据库结构。当前数据库版本回退应先导出完整存储归档、保留四张表，再恢复兼容的应用代码；不要直接删除变更条目或修订历史。补齐的中文手册是独立内容，可以保留。
