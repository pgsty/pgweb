# 扩展目录 `/ext/` 与 `/e/`

扩展目录使用站点标准的 `base/page.html` 布局、页头、页脚和左侧导航，页面为纯中文。
入口在“下载”下拉菜单的“软件目录”下方，名称为“扩展目录”；目录和详情页均归属“下载”栏目。
左侧沿用“下载、软件目录、扩展目录、浏览文件”的标准导航，在“扩展目录”下展开十六个功能分类。点击分类会在当前页面筛选，点击“扩展目录”清除分类条件，保留其他筛选。
软件目录首页与产品分类页采用同样的展开方式，在“软件目录”下列出数据库中的 8 个产品分类，链接到 `/download/products/<ID>/`，进入分类后继续保留这些入口。

## 地址与页面

| 地址 | 内容 |
| --- | --- |
| `/ext/` | “PostgreSQL 扩展目录”标题、来源说明、方格阵列、搜索框与四个下拉框、表格；每页 50 条 |
| `/ext/?q=…&category=…&license=…&language=…&repo=…&page=…` | 搜索、功能分类、许可证、编程语言、仓库来源与分页；筛选始终使用此页面 |
| `/e/<扩展名>/` | 扩展详情：概览、相关扩展和导航链接；第一个链接为 `https://pgext.cloud/e/<扩展名>` |
| `/ext/cloud/` | 跨云服务矩阵，默认 PG18，Pigsty 在首列；支持筛选、选择服务、分页及 CSV 导出 |
| `/ext/cloud/<service>/` | 单服务 PG18–14 扩展支持矩阵，服务来自数据库，自动生成页面 |
| `/ext/cloud/evidence/?service=…&pg=…&entry=…` | 单元格的来源、版本、支持边界；有 JS 时原位打开详情，无 JS 时独立阅读 |
| `/ext/sitemap.xml` | 目录、云服务矩阵及中文扩展详情地址；全站 `/sitemap.xml` 同步收录 |

来源说明中的总数取自 `pgext.universe`，筛选时仍显示完整目录的收录数；默认不在矩阵下重复展示总数，只在有筛选时显示匹配数量。
方格阵列展示全部匹配结果，一格一个扩展，颜色表示分类，深色表示已打包，点击进入扩展详情；表格分页不影响阵列的完整性。
矩阵下不显示图注。鼠标悬浮或键盘聚焦方格时立即显示扩展名、中文简介、版本、分类、许可证、语言和打包状态；离开、滚动或按 Escape 后收起。
搜索框和功能分类、许可证、编程语言、仓库来源四个下拉框均位于矩阵下方、表格上方。
表格保留固定顺序（星标优先，搜索时名称精确匹配优先），不提供排序、卡片切换、分类卡片或独立索引。

直接输入即可过滤，四个下拉框与侧栏分类也会原位更新页面，筛选和翻页状态保存在 URL 中，浏览器前进后退可恢复。
中文输入法组字期间不会发起搜索。无 JavaScript 时，普通 GET 表单、分类和分页链接仍可使用。
搜索匹配名称、项目、双语简介、标签、语言、许可证与厂商；界面和简介只显示中文，缺失中文时提示缺失，不回退成英文页。扩展正文由外部文档链接提供，本站不保存或渲染。
下拉框计数按其余筛选条件计算；侧栏分类保留当前关键词和其他筛选。

旧 `/ext/gis/`、`/ext/license/<值>/` 等地址 301 到对应查询条件；旧 `/ext/list/`、维度索引地址统一 301 到目录。
旧 `/ext/<扩展名>/` 跳转到 `/e/<扩展名>/`，`lang`、`sort`、`view` 等旧展示参数移除，`repository` 转为 `repo`。
搜索与筛选结果标记 `noindex,follow`，站点地图保留目录、云矩阵和扩展详情，不包含旧索引、单元格详情或英文地址。

**权威输入是 PGEXT 元数据库，默认本地数据库 `data` 的 `pgext.universe`。**
`~/pgsty/pgext` 负责整理、加载该元数据库。先按 PGEXT 的流程更新源库，再运行本工具。
PGEXT 网站和 `pgext/server/web` 是界面参考，不抓取网站页面作为数据源，也不使用旧的 `extension_all` 视图。

PGWeb 在自己的数据库中保存 `pgext.universe`、`pgext.cloud`、`pgext.cloud_fact`；运行页面时只查询本地副本，不连接 PGEXT 源库。源库的 `pgext.doc` 保持原样，不再复制到 PGWeb。
功能分类的中文名称和配色是代码中的展示常量，计数来自 `universe`，不需要分类表。
仓库来源使用 `universe.extra.repo`、`contrib`、`rpm_repo`、`deb_repo` 的已有来源标签。
这些标签不代表具体平台的安装包可用性；这里没有 PKG 页面或包可用性矩阵。

`ext.0001_catalog` 保留原迁移历史，`ext.0002_remove_doc` 删除 PGWeb 的 `pgext.doc` 副本。应用 `0002` 前先备份并恢复校验正文表，见下方归档说明。`ext.0003_cloud` 新增两张云支持表。
`universe` 保留源列类型、主键与名称唯一性，不引入对其他 PGEXT 表的外键；云事实通过扩展名称引用本地 Universe。扩展目录与 PostgreSQL 官方文档保持独立；三方组件文档仅提供外链。

## 云服务支持矩阵

云资料继续由 `~/pgsty/pgext/cloud/` 归档和整理，权威数据为源库 `data.pgext.cloud` 与 `data.pgext.cloud_fact`。PGWeb 不增加厂商专用表、矩阵持久表或站内抓取器：

| 表 | 粒度与内容 |
| --- | --- |
| `pgext.cloud` | 每个服务 × PG 大版本一行；服务名称、引擎状态、清单完整性、适用范围、官方来源、资料采集时间与来源元数据 |
| `pgext.cloud_fact` | 每个服务 × PG 大版本 × 原始扩展名称一行；规范名称、支持状态、版本原文、注释与补充信息 |

同步时从源库 `extension` 与 `pkg` 生成 Pigsty 锚点，写入上述同两张表，不复制整张包表。打包基线以 `extension` 为准；锚点汇总 Pigsty/PGDG 仓库各操作系统的包可用性。直接包记录展示包版本；发行包中的子扩展不冒用主扩展版本，只标可用性，并在详情保留发行包版本与各平台证据。缺少兼容性证据时标为资料不足。

对比页面默认列出打包基线与所有云服务正向支持事实的并集，列表不随所选 PG 版本或服务列变化。2026-09-26 初次集成包含 33 个云服务、PG14–18、584 个打包扩展，默认共 689 条（584 个打包扩展、78 个规范名称补充、27 个服务限定的原始名称条目）。不同服务的未归一同名条目不合并。单服务默认显示该服务列明支持的条目，可切换为打包基线、全部收录、待归一条目。

只有完整清单中缺失的规范名称，才推导为不支持；部分或缺失资料显示未知，未提供对应 PG 引擎显示不可用。版本原文、厂商状态与注释保持原样；未知版本不借用目录版本。所有页面显示历史资料日期：首批云资料为 2026-08-24，Pigsty 包锚点另标导出时间，导入不会刷新云资料采集日期。

页面复用下载栏目、扩展分类配色和站点浅色/暗色主题。侧栏仅列目录、对比和当前服务；折叠选择器与表头可进入全部服务页面。支持中文输入法、原位筛选、URL 前进后退、固定扩展名/Pigsty 列、横向滚动、移动端、来源弹窗及普通 GET 回退。CSV 导出当前筛选下的全部结果，包含服务、PG、状态、来源以及 `entry_key`/`raw_name`，不受分页限制。

### 加载与更新云资料

先同步 Universe，再应用 `ext` 迁移。以下命令仅更新 Django 配置的本地目标库；源库只读：

```bash
.venv/bin/python manage.py migrate ext

# 固定同一份云资料与 Pigsty 包锚点
.venv/bin/python tools/ext/sync_cloud.py --export data/ext/cloud.json.gz

# 验证后导入；仓库已附带首批固定快照，可直接使用
.venv/bin/python tools/ext/sync_cloud.py --input data/ext/cloud.json.gz --dry-run
.venv/bin/python tools/ext/sync_cloud.py --input data/ext/cloud.json.gz
```

`--source-db` 默认 `host=/tmp port=5432 dbname=data user=postgres`；`--database` 可覆盖目标数据库名用于隔离验证。快照格式为 `pgweb-cloud-v1`，只有两张表，约 328 KiB。源读取使用只读一致性事务，目标按主键逐列比较、事务内仅更新变化行。重复加载同一快照为 no-op，目标独有事实保留并计数；规范名称缺失或原始名称冲突会阻断，要求先整理权威源。同步不改 Universe 或站内全文搜索索引。

新服务通过新增 `cloud`/`cloud_fact` 数据自动进入页面、选择器及站点地图，无需写专用路由或模板。数据缓存最长 60 秒；导入会清除当前进程缓存，无需重启页面服务。新增代码和迁移仍须单独部署，本次本地集成不代表生产发布。

## 第一次加载

在 PGWeb 项目根目录执行，使用 `.venv` 中的 Python。先应用迁移：

```bash
.venv/bin/python manage.py migrate ext
```

本地默认从 libpq 可连接的 `data` 数据库读取，目标连接使用当前 PGWeb 的 `pgweb/settings_local.py`：

```bash
# 预览 universe 会新增、更新、保留多少记录，不写永久数据
.venv/bin/python tools/ext/sync_catalog.py --dry-run

# 导入本地 PGWeb 数据库
.venv/bin/python tools/ext/sync_catalog.py
```

`--source-db` 可指定源数据库名或 libpq service/DSN；密码使用 `.pgpass` 或环境配置。
`--database` 只替换目标数据库名，适合使用已经应用迁移的独立测试库。
建表由 migration 完成，加载工具不会自动变更表结构。

## 将同一份数据发布到本地与生产

先在生产部署扩展应用和同步脚本，并应用迁移。生产连接通过 `ssh pg`，使用远端的 Django 配置，
默认代码目录 `/data/app/pgsql.cc`。可用 `--ssh-host`、`--remote-root` 更换环境。

```bash
# 固定源库快照，只导出，不修改目标库；文件是压缩 JSON
.venv/bin/python tools/ext/sync_catalog.py --export /tmp/pgext-catalog.json.gz

# 先预览，再加载本地
.venv/bin/python tools/ext/sync_catalog.py --input /tmp/pgext-catalog.json.gz --dry-run
.venv/bin/python tools/ext/sync_catalog.py --input /tmp/pgext-catalog.json.gz

# 先预览，再加载生产
.venv/bin/python tools/ext/sync_catalog.py --input /tmp/pgext-catalog.json.gz --target production --dry-run
.venv/bin/python tools/ext/sync_catalog.py --input /tmp/pgext-catalog.json.gz --target production
```

源库的 `universe` 在只读、一致性快照中读取。格式 2 的快照只包含 `universe`，通过压缩后的 SSH 标准输入传输。旧格式 1 的两表快照会明确报错，需要用当前工具重新导出，不会悄悄重新导入正文。
报告中的 `snapshot` 是数据内容 SHA-256；同一快照在两端应该报告相同值。
`created`、`updated`、`unchanged`、`deleted`、`retained` 分别表示新增、更新、未变、删除和保留的缺失记录。
两端分别核验，单端成功不代表另一端成功。运行本工具不会修改源库或 Markdown 文件。

## 重复加载、订正与版本更新

- **相同数据重复加载**：按源 `id` 匹配，逐列比较，无变化不执行 UPDATE，不制造重复记录。
- **简介、元数据订正**：同一 ID 原位更新；目标库里的人工修改会被源数据覆盖，应先回写 PGEXT 权威源。
- **扩展版本更新，包括小版本**：更新该扩展的 `version` 和相关元数据，URL 保持不变。目录呈现源库当前状态，不另建 revision，也不自动保存旧版本。
- **新增扩展**：插入新的 universe 记录，自动出现在目录、筛选和详情中。
- **源库移除记录**：默认保留目标旧记录，报告 `retained`。确认快照完整且希望目标严格镜像源库时，显式加 `--prune`，只删除 universe 中源快照已不存在的 ID。
- **源结构或 ID 分配规则变化**：先调整 migration、列清单及同步逻辑；字段缺失、重复 ID/名称会报错，不能靠随意重编号解决。

每次目标写入都在一个事务中完成，整体成功或回滚，并串行化同工具的并发导入。
预览只建立事务内临时表，不写永久表、不推进序列。页面的目录缓存最长 60 秒过期；
普通数据更新无需重启。应用代码更新仍按 PGWeb 部署流程重启服务。

## 2026-09-09 正文副本归档

本地归档目录为 `tmp/ext-overview-only-20260909T024313Z/`，包含 `pgext-doc.dump`、DDL、修改前文件、两表数据摘要与恢复校验结果。2,355 条正文已恢复到临时数据库校验，记录数与完整内容摘要均一致，临时库随后删除。此记录仅覆盖本地；生产迁移前需要在生产独立备份和校验。

如需恢复旧实现，先运行 `manage.py migrate ext 0001` 恢复空表，再使用相同目标连接运行 `pg_restore --data-only --single-transaction --exit-on-error --no-owner --no-privileges --dbname=pgweb tmp/ext-overview-only-20260909T024313Z/pgext-doc.dump`。反向迁移只恢复表结构，数据需从归档恢复；再选择性合并归档中的旧实现，不应整体覆盖期间的其他修改。

## 维护入口

- 应用：`pgweb/ext/`（`catalog.py` 常量、URL 与查询，`views.py` 页面，`urls.py` 为 `/ext/`，`urls_e.py` 为 `/e/`）；页面：`templates/ext/`（`base` 复用标准侧栏布局、`browse` 目录、`row` 表格条目、`detail` 详情）。
- 样式和交互：`media/css/extensions.css` 仅负责方格、筛选框、表格与分类颜色；`media/js/extensions.js` 提供即时筛选。常规排版和正文复用站点公共组件。
- 分类顺序与中文名称在 `catalog.py`，配色仅维护于 `extensions.css`，颜色通过 `ext-tone-*` 类传递（CSP 禁止内联样式）。新增分类时同步两处定义。
- 同步入口：`tools/ext/sync_catalog.py`；实现：`pgweb/ext/sync.py`；列清单：`pgweb/ext/columns.json`。
- 云数据同步：`tools/ext/sync_cloud.py`、`pgweb/ext/cloud_sync.py`；渲染与查询：`pgweb/ext/cloud.py`、`cloud_views.py`；模板：`templates/ext/cloud*.html`；样式/交互：`media/css/ext-cloud.css`、`media/js/ext-cloud.js`。
- 测试：`pgweb/ext/tests.py`，在独立测试库执行 `manage.py test pgweb.ext`。数据库用户需要建测试库的权限，或由管理员预建后使用 `--keepdb`。
- 浏览器验收：`tools/ext/check_cloud_browser.py`（需 Playwright），覆盖默认矩阵、筛选/历史、中文输入、CSV、来源详情、无 JS、移动端及暗色主题；截图和报告位于 `tmp/ext-cloud-review/`。
