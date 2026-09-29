# 独立百科栏目

百科现为独立一级栏目，首页为 `/wiki/`。文档栏目继续提供手册、发行说明、版本比较和其他文档资料，路径保留 `/docs/`。

十一类百科统一使用 `/wiki/<栏目>/`：`sql`、`sqlstate`、`catalog`、`guc`、`waitevent`、`func`、`lock`、`hook`、`relopts`、`role`、`oid`。详情、版本变化页、查询参数与锚点的含义保持不变。Django 路由名与 `wiki` 应用标识不变；`wiki:reference` 指向百科首页。

旧 `/docs/<栏目>/...` 以 301 跳转到对应新路径，并保留完整查询参数。`/docs/reference/`、`/wiki/reference/` 跳转到 `/wiki/`；`/docs/errcode/...`、`/wiki/errcode/...` 跳转到 `/wiki/sqlstate/...`。

早期开发快照中的 `WAIT FOR` 已按当前固定手册归并为 `WAIT`；`/wiki/sql/wait-for/` 与 `/wiki/sql/waitfor/`（含大小写别名）301 到 `/wiki/sql/wait/`，保留查询参数。旧 `/docs/sql/` 地址经同一兼容路径处理。

桌面与移动导航、侧栏、面包屑、规范链接、站点地图、生成器、导入器与搜索结果均使用新路径。已有搜索索引、正文 HTML 与主题快照中的旧链接在展示时转换，不改写原始来源记录或手册坐标；含链接的缓存使用新键。本次不需要数据库迁移；发布时重建十一类百科的派生搜索索引，使数据库 URL 与新路由一致，展示时的转换继续兼容旧缓存与历史正文。后续导入和建索引直接生成新路径。

发布顺序：部署代码 → `manage.py index_docs --errcodes --catalog --guc --waitevents --sqlcmd --func --locks --topics` → `psql service=pgweb.pg -f tools/wiki/check_data.sql` → 重启 `pgsql.cc` → 核验公网百科、旧地址重定向、搜索和站点地图。本地使用本地数据库连接运行同一检查；不对英文 `center` 库执行中文发布命令。此命令只重建百科条目，不重建手册与扩展索引。站内全文搜索的历史 URL 在响应时转换，后续爬取由新站点地图收集新地址。

英文 `~/pgsty/pg.center` 同步使用该路径体系，一级栏目名称为 **Wiki**。两站数据库与发布流程仍相互独立；本地完成修改不代表已经发布。

百科首页按查询语言、索引与存储、运行与维护、扩展机制分区，锚点与页脚分区链接均来自 `pgweb/wiki/columns.py`。没有已上线栏目的分区不显示。紧凑卡片将图标与标题并排、简介限制为两行，底部分别显示当前导入数据的条目数和采样版本范围；数量与范围由模型只读汇总。英文百科入口保留在首页引言，页脚仅列出四个分区。

验证使用 `pgweb.wiki.test_routes`，并运行百科、搜索回归测试。数据库测试使用隔离的 `PGWEB_TEST_DB`；本地真实数据检查覆盖十一类百科、两种搜索、规范链接、旧地址跳转和站点地图。
