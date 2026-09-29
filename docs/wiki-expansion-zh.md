# PG.CENTER 百科的中文同步

PGWeb 的 `/wiki/` 与 PG.CENTER 使用同一组 30 个栏目和 6 个分区。原有 11 类中文百科继续使用自己的数据与阅读器；本次新增 18 个版本化实体集合，并从 PGWeb 已有的发布数据生成“版本发布”栏目。Index AM 后紧接 Table AM，运算符类与族统一从“运算符族”入口查阅。

## 来源与翻译

英文输入锁定在 PG.CENTER 提交 `a709ab85caf7026e89e07a4ebb1a68091d520444` 的 `data/wiki/` 文件。中文输出位于本项目同名文件，`language` 为 `zh`。生成器 `tools/wiki/localize_expansion.py` 只生成文件，不写数据库。

中文手册定义按同一 PostgreSQL 大版本匹配。匹配使用稳定锚点、唯一技术键、结构，以及代码标识与数值指纹；不能用相邻大版本代替。源码说明、能力边界与未匹配的短定义使用 `data/wiki/translations/` 的固定词典。SQL、函数签名、目录标识、版本号和机器比较数据保留原值。

英文原始证据仍指向 PG.CENTER 的确切手册页面或固定源码，保留原始哈希。`snapshot.localization` 单独记录中文页面 URL、SHA-256、匹配节点、词典来源与原文；`comparison_data` 不参与翻译。某些完整来源段落仍保留英文时，以 `manual_language`、`fallback_fields` 及页面提示标明，英文节点使用 `lang="en"`。译文不被当作新的源码事实或运行时测量。

扩展目录的中文描述按扩展名称匹配 PGWeb 的 `pgext.universe` 固定快照。FDW、Table AM、逻辑解码插件的核心版本与第三方目录采集日期分开；分类及兼容性声明不能替代能力证据。

“版本发布”直接复用中文 `releases:zh` 数据、已有安全快照和实际加载的手册。版本数量、发布数量和下载入口从当前数据计算；英文安全证据保留语言标识。同步不导入英文发布说明，不重建原有中文手册。

## 重建与导入

先准备独立运行目录，读取两站本地数据库导出固定手册束，随后离线匹配与生成：

```sh
.venv/bin/python tools/wiki/localize_expansion.py --source-commit a709ab85 --export-sources
.venv/bin/python tools/wiki/localize_expansion.py --source-commit a709ab85 --align
.venv/bin/python tools/wiki/localize_expansion.py --source-commit a709ab85 --build
```

生成前核对两站数据库身份。默认手册束位于忽略的 `tmp/wiki-localization-20260930/`；后续运行通过 `--bundle RUN/manuals.json.gz` 指定新的独立位置。提交快照、词典和 `data/wiki/translations/report.json`，不提交数据库备份或私有报告。

迁移 `wiki.0013` 与 `wiki.0014` 只新增 18 张表。导入前保存业务库备份以及原有百科、手册、发布数据的行数和内容指纹，执行 `wiki_import_topics FILES --check`，再使用完全相同的固定文件执行写入。一次提交全部文件时会先校验全部输入，再在单个事务中应用；重复导入应全部报告 unchanged。不要把旧的 hooks、relopts、roles、oid_types 中文快照混入本次同步。

只重建新增来源的实体搜索索引：

```sh
.venv/bin/python manage.py index_docs --topic-kinds type indexam plan operator opclass fdw tableam psql tool conn metric storage protocol language fts auth locale decode --releases
```

## 发布边界

中文部署目录为 `ssh pg:/data/app/pgsql.cc`，数据库与角色为 `pgweb`，服务为 `pgsql.cc`。部署准确提交后，在该目录的实际运行环境中应用迁移、校验并导入固定文件、重建上述搜索来源、执行 `check`、`migrate --check`、`collectstatic`，然后只重启 `pgsql.cc`。

英文 PG.CENTER 使用 `/data/app/pg.center`、数据库与角色 `center`、服务 `pg.center`，不在本次同步中写入。旧的 `/data/app/pgweb` 是保留实例，不是当前中文发布目录；`domain-migration.md` 中最初关于英文旧入口共库的记录不代表现在的独立英文部署。

验收包含全部栏目入口、实体及版本边界、导出与比较、重载搜索、中文关键词、分区锚点、紧凑卡片、移动端和主题。发布前后核对原有 11 类百科、中文手册和发布资料指纹，并分别验证源站与公开 HTTPS 页面。
