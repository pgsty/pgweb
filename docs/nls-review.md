# 消息翻译（/nls）实施说明

实现更新：2026-09-20，支持 PostgreSQL 14–19 的 `zh_CN` 与 `zh_TW` 消息，新增语言迁移和导入流程须单独部署。这是 [pgsty/pgnls](https://github.com/pgsty/pgnls) 消息校准工作台的站内版本：让登录且获授权的人一起校对，其他人只读浏览。

## 1. 定义与权限

- 地址 `/nls/`，入口在“开发者”下拉菜单最后一项“消息翻译”。界面（列名、按钮、状态、提示，以及后端返回的错误文案）全部中文；pgnls 里的独立版工具仍是英文界面。左侧组件按名称排序，首次打开落在体积不大的 `ecpg`，之后记住上次的组件。
- 所有人可浏览、搜索、展开详情、用键盘移动；**保存**需要登录且持有权限 `nls.review`（admin 里显示为 *nls | message | 可以校对消息翻译*），超级用户天然拥有。未登录 POST 返回 401 并附登录地址，已登录无权限返回 403；页面本身按 `data-can-edit` 切成只读模式（勾选框禁用、译文不可编辑、工具栏隐藏、顶部提示登录）。
- 授权：admin 用户页勾选权限，或 `manage.py nls_grant <username>`（`--revoke` 收回）。
- 语言在页头切换：`/nls/?lang=zh_TW&v=19`。没有 `lang` 的旧链接仍默认 `zh_CN`。界面本身保持中文；译文单元格的 HTML `lang` 随目录设为 `zh-CN` / `zh-TW`。组件偏好按语言和 PG 版本分别保存，切换前先保存当前草稿，清空旧范围的撤销栈；读取失败则保留原范围和表格。
- 简繁使用同一个审校权限，但消息、状态、历史和相近消息检索按语言隔离。已有简体审批不会自动批准繁体。
- 写请求带 `X-CSRFToken`（模板把 `{{ csrf_token }}` 放在 `#nls[data-csrf]`，因为 Cookie 是 HttpOnly）。审校人身份取 `request.user`，不再手填署名。

## 2. 数据：一张表 `nls_message`

应用 `pgweb/nls`，模型 `Message`，迁移 `nls.0001_initial`（含 `CREATE EXTENSION IF NOT EXISTS pg_trgm`，受信扩展，`pgweb` 角色可建，测试库同样可用）。

| 字段 | 说明 |
| --- | --- |
| `id` | `m_<sha256>`，pgnls 的稳定消息 ID（版本、语言、组件、msgctxt、msgid、msgid_plural） |
| `language`, `pg_major` | 消息语言和 PostgreSQL 大版本。`0003_message_language` 将既有行归入 `zh_CN`，原 ID 和审校记录保持不变；数据库约束当前只接受 `zh_CN` / `zh_TW` |
| `number`, `component`, `msgid`, `msgid_plural`, `msgctxt`, `flags`, `plural_forms` | 原文与 PO 元数据；`flags` 已去掉 `fuzzy`，`plural_forms` 是该组件 PO 的 Plural-Forms 头 |
| `original_forms`, `suggested_forms`, `suggestion_source`, `calibration`, `old_assessment`, `assessment_reason`, `context`, `plural_issue` | 既有译法、nls-v2 推荐及其校准依据；键 `''` 为单数，`'0'`/`'1'` 为复数形式 |
| `revision`, `workbook_sha256` | 推荐的基线哈希与来源工作簿；导出时原样带回 pgnls |
| `status`, `forms`, `note`, `source_revision`, `version`, `updated_by`, `updated_at` | 人工状态。`forms` 永远是当前译文（未编辑时等于推荐）；`version` 是乐观锁；`source_revision` 与 `revision` 不同且已决定的行显示为“需重审” |
| `history` | 最近 40 次保存的状态（版本、状态、译文、备注、审校人、时间），撤销就是把上一状态再保存一次 |

索引：主键、`(language, pg_major, component, status)`、`component`、`(component, status)`、`msgid` 的 `gist_trgm_ops`（相近消息检索）。PG14–18 的部分简体消息使用历史 ID，导入不重算这些 ID；同一语言、版本、组件和英文身份若以另一个 ID 出现，导入会报错，避免重复记录和丢失校对历史。2026-09-20 PO 快照每语种为 162 个目录、67,494 条消息。

## 3. 数据流

```bash
# pgnls 侧：导出自包含 bundle（含 PO flags、Plural-Forms、两种译文、校准数据、当前人工状态）
cd ~/pgsty/pgnls && review-app/.venv/bin/python review-app/manage.py bundle outputs/nls-bundle-YYYYMMDD.jsonl.gz

# pgweb 侧：导入。源字段总是刷新；本地已有人工保存（version > 0）的行只更新源字段，不覆盖人工状态
.venv/bin/python manage.py migrate nls
.venv/bin/python manage.py nls_import outputs/nls-bundle-YYYYMMDD.jsonl.gz          # --check 只校验不写
# 生产：scp bundle 后在 /data/app/pgsql.cc 下执行同一命令，再 systemctl restart pgsql.cc（首次需要迁移）

# 回流：导出 pgnls-human-review-v1，交给 pgnls 的 manage.py import / results.py 回写 PO
.venv/bin/python manage.py nls_export /tmp/pgsql-cc-review.json
cd ~/pgsty/pgnls && review-app/.venv/bin/python review-app/manage.py import /tmp/pgsql-cc-review.json
```

页面右上“导出 JSON”（审校人可见）与 `/nls/api/export/` 输出同一格式。导入按 `id` 幂等，重复导入只刷新源字段。

新增语言可以直接从已校准 PO 和同批 Babel 原译生成候选，不必恢复历史 review-app：

```bash
# pgnls 中运行；--upstream 指向该语言的 Babel 下载目录，下面有 master / REL_*_STABLE。
python3 bin/pgweb-bundle.py --language zh_TW \
  --upstream tmp/babel-snapshot/download/zh_TW --output /tmp/nls-zh_TW.jsonl.gz
# 可重复 --major 19 --major 18 选择版本，默认 14–19；输出文件不得已经存在。

# pgweb 中运行
.venv/bin/python manage.py migrate nls
.venv/bin/python manage.py nls_import /tmp/nls-zh_TW.jsonl.gz --check
.venv/bin/python manage.py nls_import /tmp/nls-zh_TW.jsonl.gz
.venv/bin/python manage.py nls_export /tmp/pg19-zh_TW-review.json --language zh_TW --major 19
```

Bundle 头部的 `language` 指定整批语言，条目如另带 `language` 必须一致；无语言字段的旧 bundle 仍视为简体。PO 生成器核对当前 PO 与 Babel 的英文集合，保留原译，使用独立语言 ID，所有候选初始为待审，不会从另一语言复制审批。已有人工稿导入后保留状态、版本和历史；推荐变化仍通过 `source_revision` 标为需重审。审核导出增加顶层 `language`，文件名包含语言与大版本，回写 PO 时须核对这两个范围。

部署顺序：备份并恢复验证消息表 → 部署代码并执行 `migrate nls` → 重启 `pgsql.cc` → 确认 `bootstrap/?lang=zh_TW` 已返回 `language: zh_TW` → 导入繁体 bundle → 核对两语种的统计、译文与审核状态。导入繁体前应确保所有应用进程都已启用语言过滤。旧简体消息的 ID、译文和校对历史须在迁移前后逐条比较；新语言的审核单独进行。

以后增加语言时，在 `pgweb/nls/languages.py` 注册代码和显示名，生成相应的字段选项与数据库约束迁移，并为 pgnls 的 PO bundle 生成器增加该语言。每个目录携带自己的 `Plural-Forms`，须用该语言的真实单复数消息测试保存与导出；不能沿用中文只有一种复数形式的假设。现有列表、统计、相近消息和人工状态直接复用语言范围，无须复制一套校对页面。语言显示名、翻译规则与审批结论分别维护。

## 4. 接口

| 方法 路径 | 用途 | 权限 |
| --- | --- | --- |
| GET `/nls/` | 页面 | 公开 |
| GET `/nls/api/bootstrap/` | 组件统计、总数、当前用户与权限 | 公开 |
| GET `/nls/api/component/?name=` | 组件全部消息（gzip，`postgres` 6,850 条约 1.5 MB）；`name=*` 返回全部组件的消息（约 12,700 条），按组件名、编号排序 | 公开 |
| GET `/nls/api/references/?id=` | 相近消息（pg_trgm）、语境、与上一轮推荐的差异 | 公开 |
| POST `/nls/api/decide/` | 保存一条：`{id, expected_version, status, forms, note}` | nls.review |
| POST `/nls/api/save/` | 组件批量保存 / 提交（`submit: true` 需含组件全部消息；未改动的行只传 `id` + `expected_version`）；任一条失败整批不写。`component: '*'` 可跨组件批量保存，但不能 `submit` | nls.review |
| GET `/nls/api/export/` | pgnls-human-review-v1 JSON | nls.review |

读取接口统一接受 `lang=zh_CN|zh_TW` 和 `major=<版本>`；省略语言默认简体。`decide` / `save` 的 JSON 使用 `language` 和 `major`，前端每次写入都携带这两个字段。单条保存、批量保存（含「全部组件」）、组件提交、相近消息和导出均限制在所选范围内，夹带另一语言或版本的 ID 会整批拒绝。旧单条简体客户端没有 `major` 时仍可按稳定 ID 保存。

校验：每次保存检查形式完整、长度、NUL；状态改为“已校对”时再检查首尾空白、制表符和回车与英文一致，不允许新增换行。仅为行宽折行的句子或说明可合并，选项行、标签行、列表项和空行仍须保留结构。随后用 GNU `msgfmt --check --check-format` 编译隔离 PO 片段（服务器需安装 gettext；缺失时退化为占位符多重集比较）。任何校验失败返回 409，页面在状态列显示“保存失败”并回退勾选框。`ValidationError` 与版本冲突都是 409；查询参数受 `@queryparams` 白名单约束。

## 5. 界面

组件列表顶上钉着「全部组件」：一次载入全部消息，跨组件搜索相近措辞、统一译法，此时勾选框后多出一列「组件名称」；搜索框只匹配英文原文与校准译文（现有翻译与二次推荐只作对照）；「提交组件」在这个模式下隐藏，保存照常。表格分批渲染（每批 400 行，滚到表尾、点「继续显示」或用键盘走到最后一行时续显），单个组件与全部组件都走这条路。

与 pgnls 独立版一致（见其 README）：☑ 已校对勾选框；英文原文 / 现有翻译 / 校准译文 / 状态 四列；既有译法整格背景绿 = 与校准译文一致、黄 = 有差异、红 = 占位符与英文不匹配；两列之间逐字 diff（红删、绿增、蓝改）；状态列一行内放状态徽标、校准类别图标、二次更新与审校人图标、展开箭头；键盘 `↑↓` 移动、`空格` 勾选、`⏎` 编辑、`→/←` 展开收起、`⌘S` 保存本组件。译文停笔 650 ms 自动保存为待审；编辑已校对的译文回到待审。

表格右上角的全屏按钮让 `#nls` 铺满视口（隐藏站点页头页脚和组件侧栏，组件改为工具栏里的下拉选择），表格获得整页宽度；`Esc` 或再点一次退出。三列文本表头右缘可拖动调整列宽（相邻两列互换宽度，双击恢复默认），列宽以占比存于浏览器 `localStorage`（`pgnls-col-fractions`、`pgnls-status-width`），窗口大小或全屏切换时按比例重算。

样式全部在 `media/css/nls.css` 且限定在 `#nls` 之下，表面、文字、线条用站内 `--pg-*` 令牌，diff 与背景色在亮暗两套主题各有定义；脚本 `media/js/nls.js` 为 ES module，无内联样式与脚本（CSP）。

爬虫排除：`robots.txt` 有 `Disallow: /nls/`；页面 `<meta name="robots" content="noindex,nofollow">`，页面与全部 `/nls/api/*` 响应带 `X-Robots-Tag: noindex, nofollow`；sitemap 不含 `/nls/`，站内搜索爬虫按 sitemap 抓取因此也不会进来。

## 6. 验证

```bash
.venv/bin/python manage.py test pgweb.nls --noinput        # 权限、乐观锁、批量原子性、msgfmt、导入幂等、导出格式、导航
# 多语言用例还覆盖旧链接兼容、语言/版本隔离、空目录、跨范围写入拒绝、旧 ID 保护及导出范围。
```

浏览器联调：生产 Cookie 为 Secure，本地 http 需用覆盖配置（`SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = False`）起 `runserver`，登录后用真实账号测试保存。
