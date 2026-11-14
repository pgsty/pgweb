# PostgreSQL 中文手册导入与发布

中文源文在 `../pgdoc/zh/<大版本>/`。导入前先查最新交付报告和产物哈希；`zh/<版本>/html/`、`tmp/pdf/zh/` 可能仍是旧构建，不能仅凭路径选取。核对产物对应的源文件清单与当前源码，再固定本次 HTML/PDF 快照。

> 2026-09-26 全量重导：pgdoc 侧完成全角字符间假空格源头清理（`../pgdoc/bin/fix_cjk_spacing.py`，31 版共删约 33.9 万处，tag `pre-cjk-despace-20260926`），31 版 HTML 全量重建后按本文流程重导两端 docs 表并 `index_docs`；`pgweb/search/extract.py` 同步升级 body 全角相邻直连（PIPELINE_VERSION 4）。pgdoc 源改动后须先过 `fix_cjk_spacing.py --check zh/<版本>`（退出 0）再构建导入。

## 版本与位置

- PG10–19 使用同名的 `core_version.tree` / `docs.version`。
- PG20 开发快照使用上游约定的 `tree = 0`，网址为 `/docs/devel/`；`/docs/20/` 跳转到这里，检索使用 `pg20:`。实际开发版本号统一维护于 `pgweb/docs/versions.py`。
- PG19 当前为 `19rc2`；保持版本表原有测试状态，不能当作正式版本或当前稳定版本。当前稳定版为 18.7，其后为 17.12、16.16、15.20、14.25；14 已于 2026-11-12 结束支持。当前稳定手册由 `core_version.current` 决定。
- 每版两份 PDF 放入 `static/documentation/pdf/<大版本>/postgresql-<大版本>-A4.pdf` 和 `postgresql-<大版本>-US.pdf`。开发版的目录为 `20`，不能与 PG19 的 PDF 混用。

导入器按版本决定源文件编码：PG10 及以上和开发版按 UTF-8，PG9.x 及更早版本按旧工具链的 Latin-1 兼容路径处理。部分发布说明等 HTML 片段没有 XML 声明，因此不能用文件开头是否有 `<?xml ... encoding="UTF-8"?>` 来判断编码；该声明只用于选择 Tidy 的 XML 清理选项。导入后应抽查中文字符和页面哈希，避免把 UTF-8 内容按 Latin-1 解码后以乱码写入 `docs.content`。

## 导入

先备份本地和生产的 `docs`、`core_version`、`docsalias`、`docs_docpageredirect`、派生搜索表及现有 PDF，保存校验和。导入工具直接连接 `tools/docs/docload.ini`，应核对其目标与本地 Django 设置一致；不要将连接凭据写入报告。

```bash
.venv/bin/python tools/docs/docload.py 10 /path/to/frozen/10/html
# 对 PG11–19 重复上述步骤。
.venv/bin/python tools/docs/docload.py -g <上游源码提交> 0 /path/to/frozen/20/html
.venv/bin/python manage.py index_docs
```

导入按 `(version, file)` 原位更新，移除本版构建不再包含的文件，保留未变化页面的 ID。将本地导入后的文档数据固定导出，同步到生产时按同一键在事务内更新并核对每版记录数及内容摘要；同时同步 `docsloaded` 与开发源码提交。不覆盖新闻、用户、扩展目录等业务数据。别名、重定向表如有差异，应先核对具体记录。

生产 PDF 位于 `/data/app/pgsql.cc/static/documentation/pdf/`，对应 `/files/documentation/pdf/`。逐文件比较源产物、本地副本和生产副本 SHA256，并检查公网下载响应。历史 `/data/app/pgweb` 是回退实例，不是当前中文站的发布目标。

## 发布与检索

生产发布应用代码后安装 `requirements.txt`、应用 `search` 迁移、重建 `index_docs`，再重启 `pgsql.cc`。文档检索来自 `docs`，包括 PG10–19 与 PG20 开发快照；索引数据可以直接从文档重新生成，无需复制本地派生表。

生产页面就绪后运行站内爬虫：

```bash
cd /data/app/pgsql.cc/tools/search/crawler
../../../.venv/bin/python -u webcrawler.py
```

爬虫读取当前目录的 `search.ini`，通过 `local_baseurl` 获取主 sitemap 和包含开发快照的内部 sitemap，更新 `webpages.fti`。已有的 `webpages_fti_idx` GIN 索引会自动更新；完成后核查索引有效性、执行 `ANALYZE webpages`，并验证 `/search/?site=1`。不要重复运行整个 `tools/search/sql/indexes.sql` 删除重建无关索引。

验收包括每版手册首页和正文、开发版路由、受影响版本的全部 A4/US PDF 链接、文档检索及结果锚点、站内全文检索，以及两端文档内容摘要一致性。文档检索使用中文分词；原有站内爬虫的 `public.pg` 配置以英文分词为主，不能把它等同于文档检索的中文分词能力。

## 2026-11-13 最终审校批次

本批源译文提交为 pgdoc `b9f0e7232f60f380d642ac9b99226606c254b552`。六版 HTML、A4/US PDF 已按最终源码重新构建，并以冻结产物校验值入库。PG14/15 的发行说明保留在 `release.html`；导入、版本比较和独立发行说明页按 `RELEASE-*` 锚点提取，不假设一定存在独立文件。

引用更新使用 `tools/docs/apply_reference_delta.py --before <基线目录> --after <审阅后的目录> --receipt <回执>`，默认在事务内核验后回滚，明确加 `--write` 才提交。只更新基线与目标之间实际变化的字段；遇到并行编辑冲突即停止。更新后重建相应 `index_docs` 栏目和站内全文索引，核验真实页面及 PDF 下载字节。冻结目录与本地验证回执位于 `tmp/docs-update-20261113/`；生产发布方案见 [本批发布记录](docs-release-20261113.md)。
