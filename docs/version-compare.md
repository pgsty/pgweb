# PostgreSQL 版本对比

入口 `/docs/compare/`，`/docs/compare` 由 Django 规范化到带斜杠地址。入口位于文档导航的“发行说明”之后，发布说明归档也提供链接。

这是 PGSQL.CC 原生 Django 页面，交互参考 pgversions.com / neondatabase/pgversionreport，独立实现，没有复制其 React 代码或过时的数据集。本站支持指定起始与目标两个版本，覆盖 PostgreSQL 10 起全部已发布小版本；预览版本独立标注，没有变更正文的开发占位版本不提供对比。

## 使用与接口

- `/docs/compare/?from=17.0&to=18.6`：跨大版本比较。
- `/docs/compare/?from=18.0&to=18.6`：同分支补丁比较。
- 裸大版本（例如 `17`）归一化为 `17.0`；`from` 也接受完整 `SELECT version()` 输出。两个版本相同时返回空比较；目标更早、未知版本和未发布的 `18.5` 返回可读的 400 错误。
- `q`、`kind` 保存前端全文关键词与分类筛选，分享链接同时保留版本、筛选和条目锚点。分页只影响显示，服务端返回完整清单，关闭 JS 仍可浏览、提交版本和展开正文。
- 相同参数增加 `format=json` 下载完整报告。JSON 与页面使用同一比较器，不因前端分页和筛选而丢失条目。

每条记录包括完整中文正文、代码、嵌套步骤、主题路径和原始说明链接。迁移与兼容性操作单独保留。分类用于浏览，分为新功能、BUG 修复、性能改进、安全相关、兼容性变化和其他改进。

## 比较语义

同一分支直接取 `(起始小版本, 目标小版本]` 中的每一条发布记录，不能因为两次修复的标题相同而删除后一次记录。

跨分支比较采用发布历史的继承路径：经过的每个大版本纳入其首发内容，旧分支的补丁只纳入截至下一大版本首发日期的部分，且任何补丁均不得晚于目标的发布日期。从目标历史中减去起始版本已含的记录。旧分支较晚的修复只有在新分支也有对应记录时才纳入。

回补关系取自上游在中文 SGML 中保留的逐分支提交注释。每个独立提交的回补组分别保留，不能将一条含多个提交的记录看成一个提交；已知其中一个提交并不代表另外几个提交也已包含。未能确认相同的记录保留，不以模糊相似度删除。兼容性操作与普通变更即便来自同一提交，也分别保留。

一般修复的计数是发布说明记录，不推断未在发布说明中记录的二进制差异或每个 BUG 的精确受影响范围。

## 安全信息

`data/compare/security.json` 从 PostgreSQL 官方安全索引、历史分支归档、每个 CVE 的详情页与 PostgreSQL CNA 发布的 CVE JSON 构建。记录 CVSS **基础分**、向量、逐分支修复版本与精确受影响区间。CNA 区间起点包含、终点排除；未提供的历史日期和评分保持空值。

页面的 CVE 修复清单只列“起始版本受影响、目标版本已修复或不受影响”的漏洞，和发布说明全文中提到的 CVE 编号分别处理。回归修复提及旧 CVE 不增加修复数。目标版本重新暴露起始版本没有的已知漏洞时，另列风险及修复版本。官方矩阵未覆盖的测试分支显示“—”，不推断安全状态。

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
```

同时提交两份快照及代码。生产使用 `/data/app/pgsql.cc` 的 `main`，拉取后执行 Django 检查和测试，再重启 `pgsql.cc`；不需迁移、不新增数据库表。普通数据更新使用已审核快照，生产不用复制 pgdoc checkout。若另外导入了手册页面，须对涉及版本增量运行 `index_docs --versions ...`。

访问页面、版本对比 JSON、小版本/CVE 示例、预览和错误边界，并检查桌面与手机的明暗主题、键盘操作、分类/搜索/分页、分享链接、条目锚点与禁用 JS 情形。快照加载以文件修改时间和大小为缓存键，更换后立即读取新内容。

## 2026-09-26 首次数据补齐

本地和生产原有手册缺少 `10.23 / 11.22 / 12.22 / 13.23 / 14.24 / 15.19` 六份最新发布说明。中文 SGML 已存在于同级 `pgdoc/zh/<major>/release-<major>.sgml`，使用其现有 DocBook 样式单独渲染对应章节；PG10 先用 OpenSP 转 XML。生成结果应用 pgdoc 的 CJK 空白规范化，仅通过 `get_or_create` 插入缺失页面，保留所有已有页面。

生成脚本、HTML、完整入库 JSON 位于本地 `tmp/compare-missing/`，生产原记录查询备份及入库数据位于 `/data/app/pgsql.cc/tmp/compare-release-20260926/`。六页包含 29、31、1、43、83、90 条变更；PostgreSQL 12.22 确实只有一条修复。两端插入后重建相关版本文档索引。

首次验收：175 份原始发布快照（173 正式版、19beta4、20 开发占位页），共 9,294 条变更；页面排除无正文的 20 占位页。官方安全快照有 177 个 CVE、58 份精确受影响区间。逐页核验条目数量、涉及 CVE 与完整正文无遗漏，945 个内部手册目标页面全部存在。所有正式分支的 1,922 组同分支比较与源记录的条目 ID、顺序、分类计数及迁移正文逐一一致，65 项提取、比较、中间件、缓存和既有发布说明测试通过；Django 检查、迁移检查与 JS 语法检查通过。

浏览器验证包括 18.0 → 18.6（351 条记录、46 个修复 CVE）、17.11 → 18.6（297 条记录、0 个新增修复 CVE）、10.0 → 18.6（3,749 条记录、79 个修复 CVE）、19beta4 预览、重复及倒序输入、未修复和新增风险提示。320/390 px、桌面明暗主题均无横向溢出；筛选、分页、条目直达、分享、JSON 和无 JavaScript 浏览通过，无 CSP 或 JavaScript 错误。

回退时使用发布提交的反向提交并重启 `pgsql.cc`；六份补齐的中文手册页面是独立内容，可以保留。无需撤销数据库结构。
