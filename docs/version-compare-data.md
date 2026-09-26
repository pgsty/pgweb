# 版本比较的数据来源与校准

`/docs/compare/` 的事实来源是 PostgreSQL 官方发布说明。中文正文取自 PGSQL.CC 的原生 `DocPage`，英文正文取自 PG.CENTER 独立 `center` 数据库中的英文手册；统一的条目身份、分类与提交关系取自固定版本的上游英文 SGML。

数据库保存每份发行版的原始记录、独立语言正文与提交关系；同一修复在不同版本出现的记录全部保留，比较时再选择并合并。`data/compare/releases.json.gz` 是可审核的传输与导出格式，请求读取已启用的数据库数据集。表结构、幂等导入、版本记录和恢复流程见 [version-compare-storage.md](version-compare-storage.md)。

## 覆盖范围

完整版本清单独立取自 [PostgreSQL 官方发布说明归档](https://www.postgresql.org/docs/release/)，不从本站数据库中的最大版本推断。2026-09-26 校准覆盖 PostgreSQL **9.0–18 的全部 351 个正式版本**：

| 分支 | 完整范围 | 版本数 |
| --- | --- | ---: |
| 9.0 | 9.0.0–9.0.23 | 24 |
| 9.1 | 9.1.0–9.1.24 | 25 |
| 9.2 | 9.2.0–9.2.24 | 25 |
| 9.3 | 9.3.0–9.3.25 | 26 |
| 9.4 | 9.4.0–9.4.26 | 27 |
| 9.5 | 9.5.0–9.5.25 | 26 |
| 9.6 | 9.6.0–9.6.24 | 25 |
| 10 | 10.0–10.23 | 24 |
| 11 | 11.0–11.22 | 23 |
| 12 | 12.0–12.22 | 23 |
| 13 | 13.0–13.23 | 24 |
| 14 | 14.0–14.24 | 25 |
| 15 | 15.0–15.19 | 20 |
| 16 | 16.0–16.15 | 16 |
| 17 | 17.0–17.11 | 12 |
| 18 | 18.0–18.6，跳过未发布的 18.5 | 6 |

再加 `19beta4` 预览和不提供对比的 20 开发占位页，共 **353 份快照、16,113 条原始变更**。9.x 使用三段规范版本：`9.6.0` 的 `major='9.6'`、`minor=0`，界面显示 `9.6`；`9.6.24` 的补丁号为 24。10 起沿用 `18.0`、`18.6` 等两段版本。排序按整数元组，不按浮点数或字符串顺序。

## 原始来源与可信链

每个正式分支的 `release-<major>.sgml` 包含该分支历次小版本记录。英文源位于同级 `pgdoc/en/<完整构建号>/`，通常中文源位于 `pgdoc/zh/<大版本>/`。9.x 的 SGML 文件名含点，如 `release-9.6.sgml`；HTML 名使用短横线，如 `release-9-6.html`、`release-9-6-24.html`。

**9.2 的中文来源是一个明确例外：** 原生 `zh/9.2/release-9.2.sgml` 保留英文，而 `zh/9.3/release-9.2.sgml` 已有完整中文。构建器使用后者，经逐版数量、全文、结构与 CVE 核对后恢复到本站原生 9.2 页面。快照与审计报告均保留真实的译文源路径，不借用 9.3 的新功能记录。

`tools/docs/audit_compare_sources.py` 重新获取官方归档和源码包 SHA256，实际校验缓存中的 **16 个正式分支源码包**，再将包内发布说明与英文 SGML 逐字节比较。PG19 取固定提交 `b73d13c32c834a2c8e1c60cb92f79530376cedf1`（`REL_19_BETA4`）的官方仓库文件。构建位置见 `pgdoc/en/SOURCES.json`，已有清单不会替代本轮实际文件校验。

## 构建、审计与导入

先更新对应语言的原生手册和版本元数据，并准备匹配 `manual_build` 的英文 SGML：

```sh
.venv/bin/python manage.py build_compare --check
.venv/bin/python manage.py build_compare
.venv/bin/python tools/docs/audit_compare_sources.py --refresh
.venv/bin/python manage.py test pgweb.docs.test_compare_data --noinput
```

证据缓存位于 `tmp/compare-source-audit/`；离线重放及英文快照校验：

```sh
.venv/bin/python tools/docs/audit_compare_sources.py --offline
.venv/bin/python tools/docs/audit_compare_sources.py \
  --language en --snapshot ../pg.center/data/compare/releases.json.gz \
  --output /tmp/compare-source-audit-en.json --offline
```

审计默认输出 `data/compare/source-audit.json`，记录快照 SHA256、来源 URL 与哈希、逐版本日期/条目数/CVE、验证计数和全部差异。`--refresh` 与 `--offline` 互斥。遗漏版本或条目、正文不符、CVE 不符、提交解析不符、相互矛盾的中英提交证据或结构差异均返回非零。只有一侧或两侧都没有提交证据时如实计数，不伪造对应关系。

`build_compare --check` 重新提取但不写文件；`--output PATH` 生成候选；`--pgdoc-root PATH` 指定源码目录。缺少精确构建版本的英文 SGML 会拒绝，不能借用相邻版本。数据库完整性检查仍保留，作为独立归档审计之外的检查。

验证后按数据库存储文档备份、迁移和导入。例如中文发行数据：

```sh
.venv/bin/python manage.py migrate docs
.venv/bin/python manage.py import_compare data/compare/releases.json.gz --language zh --check
.venv/bin/python manage.py import_compare data/compare/releases.json.gz --language zh --complete --write
```

安全数据独立导入；两种语言分别导入，保留统一身份。生产导入已审核数据，不需要复制 SGML checkout。提交传输快照与审计报告，并复核数据库导出和页面实际使用的数据集。

## 提取与身份契约

实现位于 `pgweb/docs/compare_data.py` 与 `pgweb/docs/management/commands/build_compare.py`，传输格式保持 `format=1`，当前 `parser_version=3`。完整保留 Changes、迁移/不兼容列表及其内部代码、嵌套步骤和解释；跳过重复 Overview 与致谢。迁移正文另外保留，分类只是浏览辅助。

| 层级 | 字段 | 含义 |
| --- | --- | --- |
| 快照 | `generated_at`、`parser_version` | 生成时间与规则版本 |
| 快照 | `canonical_sources`、`backport_sources` | 英文权威源与中文源路径、SHA256 |
| 快照 | `source_calibration` | 按英文校准的条目、分类与提交组统计 |
| 发布 | `version`、`major`、`minor` | 规范版本、分支与补丁号 |
| 发布 | `status`、`build`、`supported`、`eol_date` | 正式、预览、开发占位及维护状态 |
| 发布 | `date`、`source_as_of`、`date_text` | 发布日期、预览截止日期与原文措辞 |
| 发布 | `manual_build`、`manual_url`、`source_url` | 精确手册构建与来源链接 |
| 发布 | `entries`、`migration_html`、`placeholder` | 原始记录、迁移正文与占位状态 |
| 条目 | `id`、`title`、`html`、`text` | 页面锚点、标题、完整安全 HTML 与检索正文 |
| 条目 | `source_entry_id` | 固定源快照中的 `版本/部分/三位序号` |
| 条目 | `identity_text`、`source_hash` | 英文规范正文与源条目哈希 |
| 条目 | `section`、`section_path`、`category` | 本地语言主题路径与统一英文分类 |
| 条目 | `commits`、`source_commits` | 原有 HTML 提交链接、英文 SGML 完整独立提交 |
| 条目 | `commit_groups`、`commit_aliases` | 各提交的跨分支组及其并集 |
| 条目 | `cves` | 正文提及的编号，不等于新增修复漏洞清单 |

同一 `source_entry_id` 的英文规范正文、CVE、分类和提交组在两种语言中必须相同。原有页面锚点保留；位置身份只针对固定源快照，不承诺未来源码插入条目后序号不变。

历史格式需要分别处理：SGML 的 `</>` 短结束标签与 EMPTY 元素、9.x 的 `REL9_6_STABLE` 分支名、DSSSL 大写 class 和标题中的 `a[name]` 锚点、独立 Note 中的发布日期。提交信息包括条目内/条目前注释、可选 `Release:` 标记和同一 Author 下的多个提交序列。分支名再次出现即开始新的提交组，不能把同一作者所有提交合并。

**提交关系不等于条目语义完全相同。** 例如开发分支完整升级 Snowball 并增加爱沙尼亚语，稳定分支只回补内存不足修复。不能仅凭对应提交删除大版本新增功能；比较规则见 [version-compare.md](version-compare.md)。

## 当前验证结果与原生页面修复

全量核对 **16,113 条记录、27,219 段正文、66 份代码示例和 6 个内嵌列表项**，逐条 Changes/Migration 数量、结构、日期和 CVE 一致。完整渲染正文与相应语言 SGML 比较，只规范化空白、DocBook 引号、生成的交叉引用/警告标题及空链接所显示的 URL。正文中的其他文本仍参与比较。

提交证据分三类：**11,056 条**中英源具有相符提交；**276 条**只有英文源有提交，来自中文 9.5 的注释删节；**4,781 条**两侧都没有编号。独立逐行解析器核对上游分支注释，避免仅用构建器自身重复证明其结果。没有证据的旧条目仍完整保留。

中文本地和生产各修复 **48 份原生页面**，事先核对原文哈希和标题、备份原行及缺失项，再事务写入并复核：

- 新增每个 9.x 分支缺少的最后一个小版本，共 7 页。
- 将原生 9.2 的 24 份英文页恢复为已有中文；加上新增的 9.2.24，25 份发布说明全部中文。
- 对 17 份原生 9.3 页面精确还原 67 处 OpenSP SDATA 占位符，包括贡献者姓名和 `Bokmål` 区域名；其余内容字节保持不变。

41 个已有页面 ID 和 `core_version` 元数据保持不变。两端 `tmp/compare-nine/maintenance/` 保存导入前完整行、缺失项、导入结果与复核记录；候选及来源清单为 `tmp/compare-nine/candidate-pages.json`、`candidate-manifest.json`。9.x 的 `IndexedPage` 和 `SearchEntry` 均为零，因此本批没有需要重建的文档定义索引。

历史首次实现只覆盖 PG10–18：175 份快照、9,294 条记录；随后一轮校正了 2,283 条提交组、385 条分类及英文 10.22 的一处姓名编码。它们是历史批次，当前范围和数量以本页前述 9.0+ 全量结果为准。

结构与正文检查证明原有内容完整保留，不能单独证明每句话的翻译语义。比较对象是发布说明所记载的变化；CVE 的实际受影响范围和修复状态使用独立官方安全矩阵及 CNA 数据。HTML 经过标签/属性白名单，拒绝脚本、事件属性、内联样式和非 HTTP(S) 链接。正式日期只取有效发布字段，预览“截至”日期另外记录。
