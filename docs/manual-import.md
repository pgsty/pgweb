# PostgreSQL 中文手册导入与发布

中文源文在 `../pgdoc/zh/<大版本>/`。导入前先查最新交付报告和产物哈希；`zh/<版本>/html/`、`tmp/pdf/zh/` 可能仍是旧构建，不能仅凭路径选取。核对产物对应的源文件清单与当前源码，再固定本次 HTML/PDF 快照。

## 版本与位置

- PG10–19 使用同名的 `core_version.tree` / `docs.version`。
- PG20 开发快照使用上游约定的 `tree = 0`，网址为 `/docs/devel/`；`/docs/20/` 跳转到这里，检索使用 `pg20:`。实际开发版本号统一维护于 `pgweb/docs/versions.py`。
- PG19 为 `19beta3`；保持版本表原有测试状态，不能当作正式版本或当前稳定版本。当前稳定手册由 `core_version.current` 决定。
- 每版两份 PDF 放入 `static/documentation/pdf/<大版本>/postgresql-<大版本>-A4.pdf` 和 `postgresql-<大版本>-US.pdf`。开发版的目录为 `20`，不能与 PG19 的 PDF 混用。

## 导入

先备份本地和生产的 `docs`、`core_version`、`docsalias`、`docs_docpageredirect`、派生搜索表及现有 PDF，保存校验和。导入工具直接连接 `tools/docs/docload.ini`，应核对其目标与本地 Django 设置一致；不要将连接凭据写入报告。

```bash
.venv/bin/python tools/docs/docload.py 10 /path/to/frozen/10/html
# 对 PG11–19 重复上述步骤。
.venv/bin/python tools/docs/docload.py -g <上游源码提交> 0 /path/to/frozen/20/html
.venv/bin/python manage.py index_docs
```

导入按 `(version, file)` 原位更新，移除本版构建不再包含的文件，保留未变化页面的 ID。将本地导入后的文档数据固定导出，同步到生产时按同一键在事务内更新并核对每版记录数及内容摘要；同时同步 `docsloaded` 与开发源码提交。不覆盖新闻、用户、扩展目录等业务数据。别名、重定向表如有差异，应先核对具体记录。

生产 PDF 位于 `/data/app/pgweb/static/documentation/pdf/`，对应 `/files/documentation/pdf/`。逐文件比较源产物、本地副本和生产副本 SHA256，并检查公网下载响应。

## 发布与检索

生产发布应用代码后安装 `requirements.txt`、应用 `search` 迁移、重建 `index_docs`，再重启 `pgweb`。文档检索来自 `docs`，包括 PG10–19 与 PG20 开发快照；索引数据可以直接从文档重新生成，无需复制本地派生表。

生产页面就绪后运行站内爬虫：

```bash
cd /data/app/pgweb/tools/search/crawler
../../../.venv/bin/python -u webcrawler.py
```

爬虫读取当前目录的 `search.ini`，通过 `local_baseurl` 获取主 sitemap 和包含开发快照的内部 sitemap，更新 `webpages.fti`。已有的 `webpages_fti_idx` GIN 索引会自动更新；完成后核查索引有效性、执行 `ANALYZE webpages`，并验证 `/search/?site=1`。不要重复运行整个 `tools/search/sql/indexes.sql` 删除重建无关索引。

验收包括每版手册首页和正文、开发版路由、22 个 PDF 链接、文档检索及结果锚点、站内全文检索，以及两端文档内容摘要一致性。文档检索使用中文分词；原有站内爬虫的 `public.pg` 配置以英文分词为主，不能把它等同于文档检索的中文分词能力。
