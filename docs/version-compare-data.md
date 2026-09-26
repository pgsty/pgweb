# 版本比较的数据快照

`/docs/compare/` 使用 PostgreSQL 官方发布说明作为事实来源。中文正文来自本站原生 `DocPage`，英文正文来自 PG.CENTER 独立 `center` 数据库中的原生英文手册。两端使用同一份上游英文 SGML 提供与语言无关的条目身份、分类和提交关系，分别生成 `data/compare/releases.json.gz`；请求不联网，不重新解析手册，不新增数据库表。

## 来源与完整覆盖

已发布版本的独立清单取自 [PostgreSQL 官方发布说明归档](https://www.postgresql.org/docs/release/)，而不是从本站数据库的最大版本号推断。2026-09-26 校准覆盖 PostgreSQL 10–18 的全部 **173 个正式发布版本**：

| 分支 | 完整范围 | 版本数 |
| --- | --- | ---: |
| 10 | 10.0–10.23 | 24 |
| 11 | 11.0–11.22 | 23 |
| 12 | 12.0–12.22 | 23 |
| 13 | 13.0–13.23 | 24 |
| 14 | 14.0–14.24 | 25 |
| 15 | 15.0–15.19 | 20 |
| 16 | 16.0–16.15 | 16 |
| 17 | 17.0–17.11 | 12 |
| 18 | 18.0–18.6，跳过未发布的 18.5 | 6 |

另收录 `19beta4` 预览正文；20 开发占位页无变更，不是可选择的对比目标。每个正式分支的 `release-<major>.sgml` 自带该分支历次小版本记录。原文位于同级 `pgdoc/en/<完整构建号>/`，中文对应 `pgdoc/zh/<大版本>/`。

`tools/docs/audit_compare_sources.py` 独立验证原文的可信链：重新获取官方归档版本清单和源码包 SHA256，校验缓存的 9 个正式版本源码包，再将其中的发布说明文件与英文 SGML 逐字节比较。PG19 预览取固定提交 `b73d13c32c834a2c8e1c60cb92f79530376cedf1`（`REL_19_BETA4`）的官方仓库原文。源码包和构建位置记录于 `pgdoc/en/SOURCES.json`，但审计会实际验证文件，不把已有记录视为验证结果。

## 重建与独立审计

先更新对应语言手册和 `core_version` 元数据，并准备同级 `pgdoc` 中匹配 `manual_build` 的英文 SGML：

```sh
.venv/bin/python manage.py build_compare --check
.venv/bin/python manage.py build_compare
.venv/bin/python tools/docs/audit_compare_sources.py --refresh
.venv/bin/python manage.py test pgweb.docs.test_compare_data --noinput
```

首次抓取的证据缓存位于 `tmp/compare-source-audit/`。完全离线重放：

```sh
.venv/bin/python tools/docs/audit_compare_sources.py --offline
# 也可以校验英文站的独立快照
.venv/bin/python tools/docs/audit_compare_sources.py \
  --language en --snapshot ../pg.center/data/compare/releases.json.gz \
  --output /tmp/compare-source-audit-en.json --offline
```

默认输出 `data/compare/source-audit.json`，包含本次快照 SHA256、来源 URL/校验值、逐版本日期/条目数/CVE 集合、验证计数和全部差异。`--refresh` 与 `--offline` 互斥。版本清单、条目数、日期、正文、CVE、提交、身份或段落结构存在未解释差异时审计返回非零，发布前必须解决。两份快照和各自审计结果应随代码提交；生产读取已审核快照，不需要复制源码 checkout。

`build_compare --check` 重新构建并验证但不写文件；`--output PATH` 可先生成候选快照；`--pgdoc-root PATH` 可指定源码目录。实际源码构建缺少精确构建版本的英文 SGML 会拒绝，不借用相邻版本。数据库覆盖检查仍保留，作为独立归档审计之外的第二道检查。

## 提取与身份契约

实现位于 `pgweb/docs/compare_data.py` 与 `pgweb/docs/management/commands/build_compare.py`。快照保持 `format=1`，本轮 `parser_version=2`。每份发布说明保留完整 Changes 与迁移/不兼容列表，跳过重复 Overview 和致谢。条目内部代码、嵌套步骤、链接和解释全部保留；迁移正文另外保留。分类是浏览辅助，不是上游的正式分类。

| 层级 | 字段 | 含义 |
| --- | --- | --- |
| 快照 | `generated_at`、`parser_version` | 生成时间与规则版本 |
| 快照 | `canonical_sources`、`backport_sources` | 英文权威源与中文源的相对路径、SHA256 |
| 快照 | `source_calibration` | 按英文重新校准的条目、分类与提交组统计 |
| 发布 | `version`、`major`、`minor` | 版本坐标，首发为 `.0` |
| 发布 | `status`、`build`、`supported`、`eol_date` | 正式版、预览、开发占位及维护状态 |
| 发布 | `date`、`source_as_of`、`date_text` | 发布日期、预览截止日期与原文日期措辞 |
| 发布 | `manual_build`、`manual_url`、`source_url` | 原生手册构建与来源链接 |
| 发布 | `entries`、`migration_html`、`placeholder` | 完整条目、迁移正文及占位状态 |
| 条目 | `id`、`title`、`html`、`text` | 页面原有稳定锚点、标题、完整安全 HTML 与检索正文 |
| 条目 | `source_entry_id` | 与语言无关的 `版本/部分/三位序号`，用于对应固定源快照内的同一条记录 |
| 条目 | `identity_text`、`source_hash` | 英文完整规范正文、原始英文条目 SHA256 |
| 条目 | `section`、`section_path`、`category` | 本地语言主题路径，以及统一按英文判断的分类 |
| 条目 | `commits` | 渲染正文中原有的提交链接，保留原样 |
| 条目 | `source_commits` | 完整英文 SGML 的独立提交，含注释中未显示为链接的部分 |
| 条目 | `commit_groups`、`commit_aliases` | 每个提交的跨分支对应组，以及这些组的并集 |
| 条目 | `cves` | 全文提及的 CVE 编号，不等于本次新修复漏洞清单 |

两种语言对相同英文 `source_entry_id` 的 `identity_text`、CVE、分类和提交组必须一致。页面旧锚点 `id` 不因这次校准而重写。位置标识针对已固定并校验的源快照，不宣称源码插入条目后序号永不变化。

SGML 提交关系必须处理四种实际格式：条目内注释、紧邻条目之前的注释、`Branch: ... Release: ... [hash]` 标记、同一 Author 下重复出现分支名的新提交序列。不能把一个 Author 名下的多个独立提交合并。中文历史注释与原文存在删节时以英文为准；HTML 中只显示部分提交时不丢弃其余独立提交。

**提交对应不等于发布说明语义相同。** 同一源码提交在开发分支与稳定分支可能只应用其中一部分：例如 Snowball 的完整升级支持爱沙尼亚语，稳定分支只回补内存不足崩溃修复。比较器不得仅凭相同提交关系删除大版本新增功能。跨版本的具体继承和保留规则见 [version-compare.md](version-compare.md)。

## 本轮校准结果与边界

独立审计核对了 **9,294 条变更、16,385 段正文、32 份代码示例**；中英文原文的逐条 Changes/Migration 数量、段落与示例结构一致。每条中文渲染正文与其 SGML 完整正文比较，忽略 DocBook 生成的交叉引用标签、排版引号及空白等差异；正文中的其他文本、CVE 与标点仍参与比较。提交关系使用独立逐行解析器核对，避免用构建器自己的结果重复证明自己。

其中 **9,235 条**在原始中英文 SGML 中均有相符的提交证据，可独立确认逐条对应关系；另外 **59 条**两种原文都没有提交编号，保留完整正文与对应顺序，不虚构提交关系。此次保持所有中文正文原样，按英文统一调整 385 条分类，并纠正 2,283 条记录的提交组。

修复了旧 SGML `xref` 作为 HTML 非空元素时吞入后文、漏读条目前置提交注释、只采集 HTML 中部分提交、漏读 `Release:` 注释及同一作者多组提交误合并等问题。英文对应审计另发现 PostgreSQL 10.22 贡献者姓名 `Mannsåker` 的一处编码错误，已校正原生英文页面。

结构和全文保留检查能证明没有丢弃已有译文，不能单独证明每句话的翻译语义正确；中文翻译仍沿用经维护的本站手册。本页比较的是发布说明所记录的变更，不从记录推断未记载的二进制行为。CVE 受影响范围及修复状态由单独的官方安全矩阵与 CNA 数据校准，详见 [version-compare.md](version-compare.md)。

`html` 经过标签和属性白名单清理，拒绝脚本、事件属性、内联样式与非 HTTP(S) 链接；相对手册链接转换到当前站点对应版本。日期只认发布字段中的有效完整日期，不使用 beta 时间替代正式发布日期。预览中的“截至”日期单独记录。
