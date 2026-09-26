# 版本比较的数据快照

`/docs/compare/` 的原始数据来自本站 `DocPage` 中的 PostgreSQL 中文发布说明，覆盖 PostgreSQL 10 起已装载的正式版本与开发预览。网页只读取仓库中的 `data/compare/releases.json.gz`；请求期间不抓取上游、不重新解析手册，也不新增数据库表。

## 重建

先完成中文手册导入和 `core_version` 元数据更新，再运行：

```sh
.venv/bin/python manage.py build_compare --check
.venv/bin/python manage.py build_compare
```

`--check` 重新提取并验证，不写文件。默认命令原子替换 gzip 快照；`--output PATH` 可先写候选快照供审阅。快照中的版本清单由实际原生手册页面决定，同时按 `core_version.latestminor` 校验正式版是否齐全。缺失已发布的小版本会报错，不静默缩短比较范围，不填造发布说明。已明确跳号的 PostgreSQL 18.5 不在清单中。

跨分支回补的去重还使用 `pgdoc/zh/<major>/release-<major>.sgml` 注释中上游维护的提交对应关系。默认寻找本仓库同级的 `pgdoc`，也可传 `--pgdoc-root PATH`。每个 `Author:` 块是一组同一提交的不同分支版本；一条发布记录中包含多个 `Author:` 时分别解析，不把独立提交混为一组。快照保留实际链接中的 `commits`，并提供 `commit_aliases` 供比较时识别回补。`backport_sources` 记录源文件相对路径与 SHA256。没有 SGML checkout 时仍能提取正文，但没有这些跨分支对应信息；正式构建应提供该源。

PG10、PG11 的旧 HTML 不输出提交链接。构建器按原始 SGML 的发布版本、Changes/Migration 部分、条目数量、顺序与首段译文逐一核对，仅完全匹配的条目补充 `source_commits`。比较使用的 `commit_groups` 也包含这些有明确来源的提交；HTML 中原有的 `commits` 不被改写。未匹配或原文没有提交信息的数量记录在 `source_commit_enrichment`，不猜测对应关系。

重建后提交并发布快照；页面的数据更新与普通代码发布同步。生产可直接使用已构建的快照，无需访问 `pgdoc` checkout。

## 提取契约

解析实现位于 `pgweb/docs/compare_data.py`，命令为 `pgweb/docs/management/commands/build_compare.py`，格式版本为 `format=1`。主要字段如下：

| 层级 | 字段 | 含义 |
| --- | --- | --- |
| 快照 | `generated_at`、`parser_version` | 生成时间与提取规则版本 |
| 发布 | `version`、`major`、`minor` | 可数值比较的版本坐标；大版本首发为 `.0` |
| 发布 | `status`、`build`、`supported`、`eol_date` | 正式版、测试版、开发快照及当前支持状态、维护结束日期 |
| 发布 | `date`、`source_as_of`、`date_text` | 原文精确发布日期、预览截止日期、原文日期措辞 |
| 发布 | `manual`、`source_url`、`manual_url` | 手册版本、发布说明入口、原始手册页面 |
| 发布 | `entries`、`migration_html` | 逐条变更与独立迁移段落 |
| 发布 | `placeholder`、`summary_html` | 尚无正式 Changes 的开发占位页 |
| 条目 | `id`、`title`、`html`、`text` | 稳定标识、可读标题、完整安全 HTML、可搜索正文 |
| 条目 | `section`、`section_path` | 原文主题层级 |
| 条目 | `category` | 安全、错误修复、性能、功能、兼容性或其他改进 |
| 条目 | `cves`、`commits`、`commit_groups`、`commit_aliases` | 全文提及的 CVE、提交、各提交分别对应的回补组、所有组的并集 |

只提取 Changes 与迁移/不兼容部分的逐条记录，跳过重复的 Overview 和致谢。条目内部的子步骤、代码、链接和完整解释一并保留。迁移段落独立保留，迁移部分的逐条不兼容项进入兼容性分类。PostgreSQL 10–12 的自动生成章节 ID 通过中英标题识别；现代版本优先使用语义 ID。

`cves` 收集条目全文提到的编号，也包括回归修复引用的旧漏洞，不等于本次新公布的漏洞清单。分类是检索辅助：含 CVE 的条目归为安全，迁移列表归为兼容性，明确修复措辞归为错误修复，明确性能措辞归为性能，剩余大版本条目归为功能、小版本条目归为改进。

日期只识别发布日期字段中的完整有效日期，不使用 `firstreldate` 的 beta 日期替代正式发布日期。预览页的“截至”时间记录到 `source_as_of`。目前 PG19 页面仍为测试版，PG20 为没有变更清单的占位页；不能由它们推断正式发布或新增功能。

`html` 经 BeautifulSoup 清理与 bleach 标签/属性白名单处理，拒绝脚本、事件属性、内联样式与非 HTTP(S) 链接；手册相对链接改为本站绝对路径。标题去除尾部贡献者名单仅为便于阅读，完整归属仍在正文中。

## 验证

```sh
.venv/bin/python manage.py test pgweb.docs.test_compare_data --noinput
.venv/bin/python manage.py build_compare --check
```

测试覆盖全量条目保留、兼容性与概览区分、完整嵌套操作步骤、代码与链接、全文 CVE、预览日期、历史章节结构、稳定 ID、安全过滤、回补关系和 gzip 可重现写入。
