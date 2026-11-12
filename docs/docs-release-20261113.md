# PostgreSQL 14–19 中文文档发布批次（2026-11-13）

本地 PGSQL.CC 的手册、PDF、百科引用、发行说明与检索已更新至 **19rc2、18.7、17.12、16.16、15.20、14.25**。18 为当前稳定版，19 仍为测试版，14 已于 2026-11-12 结束维护。生产 `pgsql.cc` 尚未发布。

## 来源、提交与入库

译文终审提交为 pgdoc `b9f0e7232f60f380d642ac9b99226606c254b552`；本批完整增量审读覆盖 593 个独立英文语义单元及其跨版复用。构建保留了此前人工修改，实际工作区文件与工具哈希另行记录，不将提交号当作整个构建树的唯一身份。

六版共 6,788 页中文 HTML、12 份 A4/US PDF。HTML 原位导入并保留页面身份，PDF 放入 `static/documentation/pdf/<大版本>/`；原英文、中文与最终来源台账另存于 `../postgresql-docs/`。来源和排版验收见 pgdoc 的 `docs/release-20261113.md`。

相关代码提交：

- `db2bc55a`：按版本识别 UTF-8 手册，正确导入不含 XML 声明的发行说明片段；支持 14/15 的 `release.html#RELEASE-*` 内嵌章节。
- `001b3af9`：引用差异导入工具、参数小版本边界与事实来源展示、当前手册导航标签，以及手机发行说明布局修正。

引用导入采用本站自己的 37 表基线，更新 979 行；事务预演和重复导入验证通过，重复写入为零。`composite_type_mismatch` 按各分支小版本收录，源码核验不冒充运行实测，也不因旧 PG20 快照缺席而标记移除。保留已有 SQLSTATE `22P07` 的独立来源与释文。19rc2 删除的 `servicefile` 连接关键字不再显示为该版定义，`PGSERVICEFILE` 仍在手册中。百科工具导航使用当前手册版本，来源展开栏继续保留实际采样构建。

发行说明导入后为 358 个快照、16,895 个有效条目；旧 occurrence、patch、修订与安全数据保留。14.25、15.20 的独立发行说明路由与版本比较读取实际内嵌章节。

## 本地验收

完整备份实际恢复到 `test_pgweb_docs_20261113`，140 表、618,869 行，内容与 schema 指纹一致。`pgweb.before.dump` 的 SHA-256 为 `3ba82eb505460eca0320db03171d7216fc65d2e4badcd58e95a76b7d36635f96`。

42 项发行说明测试、4 项编码测试和 68 项参数/引用页面测试通过。受影响六版文档索引和相应百科索引已重新生成；站内全文索引最终包含 36,300 个可检索页面，缺失正文为零；六版逐版本文档搜索与两项站内全文查询通过。完整主站爬虫之后补抓预览重启时失败的请求及受显示修正影响的页面。索引验收按实际响应区分可检索 HTML、SVG 资源及 `/community/lists/listinfo/` 的 JSON 接口，不把非 HTML 内容计入缺失正文。

12 份 PDF 的本地 HTTP 完整下载与审校产物逐字节一致。版本状态、当前版本路由、参数正文与小版本边界、SQLSTATE、手册锚点、发行说明、版本比较和文档搜索通过实际请求验收；桌面/手机 12 个浏览器用例无页面横向溢出或破损图片，并复看了实际截图。文档搜索使用本站支持的 `pg` / `pg18` 等 scope，不能将未知 `scope=all` 的错误响应当作命中。

本地证据位于 `tmp/docs-update-20261113/`；最终 HTTP 与 PDF 下载回执集中在相邻 Go 项目的同名目录。重点回执为 `restore-verified.json`、`reference-final-check.json`、`site-search-repaired.json`、`browser-pgweb.json`，以及 Go 项目中的 `pgweb-final-http.json` 和 `pgweb-pdf-downloads.json`。

## 待生产发布

联合输入包位于 `../pg.center/tmp/docs-update-20261113/release-bundle/`；以其中 `manifest.json`、`CHECKSUMS.sha256` 和 `pgsql.cc/` 固定输入为准，不使用未冻结的工作目录。代码、来源及轻量发布说明入 Git；HTML、PDF、压缩包和数据库备份不入 Git。

1. 核对 `ssh pg` 上 `/data/app/pgsql.cc`、`pgsql.cc` 服务与生产 `pgweb` 数据库/角色。备份生产文档、版本、百科、发行说明和派生索引，并实际恢复检查；保留旧程序和 PDF。
2. 在实际生产目录部署精确代码提交并执行 Django 检查。核对生产 `docload.ini` 和应用设置连接同一 `pgweb`；以输入包六版 HTML 调用 `docload.py`，保留未变页面 ID，并同步当前版本、测试状态、维护期限和 `docsloaded`。PG20 的固定来源不随本批改变。
3. 以 `tools/docs/apply_reference_delta.py --target production --before <固定基线> --after <审阅目标> --receipt <新回执>` 做事务预演。生产差异字段若与基线不符，先合并其自己的修改；核验后才加 `--write`。运行发行说明 `import_compare <固定快照> --language zh --complete --prune` 预演，核验生产自身历史后加 `--write`。
4. 复制六版 A4/US PDF 到生产静态目录并逐文件校验 SHA-256。重建六版手册与受影响百科索引，重启且只重启 `pgsql.cc`；页面稳定后运行主站爬虫，验证每版查询、站内全文检索、来源/锚点、版本比较及公网 PDF 完整下载。

生产原位更新必须保留新闻、用户、扩展、历史实测和其他并行修订。失败时恢复该目标自身的旧文档/引用/发行说明、版本状态、PDF 与程序，再从其旧内容重建索引；数据库级恢复使用验证过的独立恢复库做可逆切换。旧备份、快照和测试恢复库继续保留。Go PG.CENTER 有独立的编号迁移、原生来源和搜索发布流程，不向 `center_old` 导入本批数据。
