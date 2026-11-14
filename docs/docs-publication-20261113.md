# PostgreSQL 14–19 生产文档更新（2026-11-13）

[PGSQL.CC](https://pgsql.cc/docs/) 的文档页面、导航、PDF、百科引用、发行说明、文档检索和站内全文索引已更新并通过公网验收。本批为 **19rc2、18.7、17.12、16.16、15.20、14.25**；当前版本指向 18.7，19rc2 按预发行展示，14.25 按结束维护的历史版本展示。

## 内容与代码

来源、翻译标准、终审和构建记录见 [本地发布批次](docs-release-20261113.md)。六版共 6,788 页中文 HTML 和 12 份 A4/US PDF，原位导入保留页面身份。引用更新基于本站自己的生产基线，只修改本批差异字段，保留人工内容、历史运行事实及 SQLSTATE 的独立证据。发行说明保留原 occurrence、patch 和修订，支持 14/15 的内嵌发行章节。

生产代码位于 `/data/app/pgsql.cc`，精确提交为 `36b0e43578b01c730f69cfc60f4fca224c3e7560`。该提交在桌面和手机导航中列出已加载的预发行手册，菜单包含 19、18、17、16、15；14 仍可从版本首页及历史归档进入。入口链接实测落到 19rc2，当前文档链接落到 18.7。此前编码修正、参数小版本边界、来源展示和手机布局修正一并部署。

## 索引与验收

六版手册与受影响百科的专用索引已重建。全站索引按 sitemap 核对 36,331 个目标，保留未变历史内容，并强制刷新 14–19/current 手册、Wiki 与读者入口；最后有 36,319 个可检索页面，缺失可索引页面为零。另复抓 20 个不在 sitemap 中的已有可检索 URL，并补验当前扩展地址。`/e/pg_mooncake_rust/` 与 `/e/pg_opencc/` 经源站和公网确认均为 404，且不在当前目录和 sitemap 中：原索引记录先完整归档，再从派生检索退出；业务表未删除。收尾重新读取当前 sitemap 核对完整覆盖。

中途为完整生产备份暂停的爬虫连接过期，已从可核验的提交进度继续：复用导航更新后完成的 5,067 个目标，续抓 12,017 个 HTML 页面，并逐批保存已提交进度。32 个 SVG/JSON 响应按实际类型单列，不冒充 HTML 正文，也不因请求失败删除已有索引。

- 源站与公网各 69 个页面检查通过；公网 sitemap 含 35,169 个 URL。
- 六版各两项文档查询及两项全站查询，共 14 次搜索检查实际手册与 Wiki 结果。
- 12 份 PDF 全量公网下载，与固定产物大小和 SHA-256 一致。
- 12 个正文浏览器用例和 2 个导航用例通过；桌面/手机无横向溢出、破损图片或脚本异常，并复看实际截图。

## 恢复与运维记录

生产数据库/角色始终为 `pgweb`。完整备份实际恢复到隔离库 `test_pgweb_docsprod_20261113`，140 表、618,972 行内容与 schema、ACL、序列一致；备份 SHA-256 为 `8f39d40b0e00e94d13c0f69ea21a6fb7c79c81e6936b0971aacc09dfb52733c7`。旧程序、PDF、版本状态、引用/发行说明基线和数据库备份继续保留。已用完的服务器传输副本在逐文件核验后归档至本地固定包，位置和重新展开方法见联合目录中的 `used-transport-retained-locally.json`；复用导入输入时先按回执恢复该目录。

联合生产证据位于相邻 Go 项目的 `../pg.center/tmp/docs-publish-20261113/`；服务器为 `/data/app/pg.center-v2/maintenance/docs-20261113/`，备份为 `/data/backup/docs-20261113/`。关键回执：`pgweb-published.json`、`pgweb-navigation-published.json`、`pgweb-restore-verified.json`、`pgweb-site-search.json`、`pgweb-index-extras-refreshed.json`、`pgweb-public-navigation-http.json`、`pgweb-public-search.json`、`pgweb-public-pdfs.json`、`browser-pgweb.json` 和联合 `production-acceptance.json`。

需要回退时先核对后来修改，以该目标自身的旧文档/引用/发行说明和版本状态恢复，替换原 PDF 与精确程序后重建派生索引。数据库级恢复使用已验证的隔离库做可逆切换，不清空在线数据库，不覆盖新闻、用户、扩展或其他后续内容。PG.CENTER 的 Go 数据与搜索遵循独立的原生发布契约。
