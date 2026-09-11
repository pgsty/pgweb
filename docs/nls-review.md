# 消息翻译（/nls）实施说明

状态：2026-09-11 上线本地，据此维护。这是 [pgsty/pgnls](https://github.com/pgsty/pgnls) 里 PostgreSQL 19 简体中文消息（PO 文件）校准工作台的站内版本：把逐条审校搬到 pgsql.cc，让登录且获授权的人一起校对，其他人只读浏览。

## 1. 定义与权限

- 地址 `/nls/`，入口在“开发者”下拉菜单最后一项“消息翻译”。界面（列名、按钮、状态、提示，以及后端返回的错误文案）全部中文；pgnls 里的独立版工具仍是英文界面。左侧组件按名称排序，首次打开落在体积不大的 `ecpg`，之后记住上次的组件。
- 所有人可浏览、搜索、展开详情、用键盘移动；**保存**需要登录且持有权限 `nls.review`（admin 里显示为 *nls | message | 可以校对消息翻译*），超级用户天然拥有。未登录 POST 返回 401 并附登录地址，已登录无权限返回 403；页面本身按 `data-can-edit` 切成只读模式（勾选框禁用、译文不可编辑、工具栏隐藏、顶部提示登录）。
- 授权：admin 用户页勾选权限，或 `manage.py nls_grant <username>`（`--revoke` 收回）。
- 写请求带 `X-CSRFToken`（模板把 `{{ csrf_token }}` 放在 `#nls[data-csrf]`，因为 Cookie 是 HttpOnly）。审校人身份取 `request.user`，不再手填署名。

## 2. 数据：一张表 `nls_message`

应用 `pgweb/nls`，模型 `Message`，迁移 `nls.0001_initial`（含 `CREATE EXTENSION IF NOT EXISTS pg_trgm`，受信扩展，`pgweb` 角色可建，测试库同样可用）。

| 字段 | 说明 |
| --- | --- |
| `id` | `m_<sha256>`，pgnls 的稳定消息 ID（版本、语言、组件、msgctxt、msgid、msgid_plural） |
| `number`, `component`, `msgid`, `msgid_plural`, `msgctxt`, `flags`, `plural_forms` | 原文与 PO 元数据；`flags` 已去掉 `fuzzy`，`plural_forms` 是该组件 PO 的 Plural-Forms 头 |
| `original_forms`, `suggested_forms`, `suggestion_source`, `calibration`, `old_assessment`, `assessment_reason`, `context`, `plural_issue` | 既有译法、nls-v2 推荐及其校准依据；键 `''` 为单数，`'0'`/`'1'` 为复数形式 |
| `revision`, `workbook_sha256` | 推荐的基线哈希与来源工作簿；导出时原样带回 pgnls |
| `status`, `forms`, `note`, `source_revision`, `version`, `updated_by`, `updated_at` | 人工状态。`forms` 永远是当前译文（未编辑时等于推荐）；`version` 是乐观锁；`source_revision` 与 `revision` 不同且已决定的行显示为“需重审” |
| `history` | 最近 40 次保存的状态（版本、状态、译文、备注、审校人、时间），撤销就是把上一状态再保存一次 |

索引：主键、`component`、`(component, status)`、`msgid` 的 `gist_trgm_ops`（相近消息检索）。当前 12,699 行、28 个组件，表连索引约 41 MB。

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

## 4. 接口

| 方法 路径 | 用途 | 权限 |
| --- | --- | --- |
| GET `/nls/` | 页面 | 公开 |
| GET `/nls/api/bootstrap/` | 组件统计、总数、当前用户与权限 | 公开 |
| GET `/nls/api/component/?name=` | 组件全部消息（gzip，`postgres` 6,850 条约 1.5 MB） | 公开 |
| GET `/nls/api/references/?id=` | 相近消息（pg_trgm）、语境、与上一轮推荐的差异 | 公开 |
| POST `/nls/api/decide/` | 保存一条：`{id, expected_version, status, forms, note}` | nls.review |
| POST `/nls/api/save/` | 组件批量保存 / 提交（`submit: true` 需含组件全部消息；未改动的行只传 `id` + `expected_version`）；任一条失败整批不写 | nls.review |
| GET `/nls/api/export/` | pgnls-human-review-v1 JSON | nls.review |

校验：每次保存检查形式完整、长度、NUL；状态改为“已校对”时再检查首尾空白与换行/制表数与英文一致，并用 GNU `msgfmt --check --check-format` 编译隔离 PO 片段（服务器需安装 gettext；缺失时退化为占位符多重集比较）。任何校验失败返回 409，页面在状态列显示“保存失败”并回退勾选框。`ValidationError` 与版本冲突都是 409；查询参数受 `@queryparams` 白名单约束。

## 5. 界面

与 pgnls 独立版一致（见其 README）：☑ 已校对勾选框；英文原文 / 现有翻译 / 校准译文 / 状态 四列；既有译法整格背景绿 = 与校准译文一致、黄 = 有差异、红 = 占位符与英文不匹配；两列之间逐字 diff（红删、绿增、蓝改）；状态列一行内放状态徽标、校准类别图标、二次更新与审校人图标、展开箭头；键盘 `↑↓` 移动、`空格` 勾选、`⏎` 编辑、`→/←` 展开收起、`⌘S` 保存本组件。译文停笔 650 ms 自动保存为待审；编辑已校对的译文回到待审。

表格右上角的全屏按钮让 `#nls` 铺满视口（隐藏站点页头页脚和组件侧栏，组件改为工具栏里的下拉选择），表格获得整页宽度；`Esc` 或再点一次退出。三列文本表头右缘可拖动调整列宽（相邻两列互换宽度，双击恢复默认），列宽以占比存于浏览器 `localStorage`（`pgnls-col-fractions`、`pgnls-status-width`），窗口大小或全屏切换时按比例重算。

样式全部在 `media/css/nls.css` 且限定在 `#nls` 之下，表面、文字、线条用站内 `--pg-*` 令牌，diff 与背景色在亮暗两套主题各有定义；脚本 `media/js/nls.js` 为 ES module，无内联样式与脚本（CSP）。

爬虫排除：`robots.txt` 有 `Disallow: /nls/`；页面 `<meta name="robots" content="noindex,nofollow">`，页面与全部 `/nls/api/*` 响应带 `X-Robots-Tag: noindex, nofollow`；sitemap 不含 `/nls/`，站内搜索爬虫按 sitemap 抓取因此也不会进来。

## 6. 验证

```bash
.venv/bin/python manage.py test pgweb.nls --noinput        # 权限、乐观锁、批量原子性、msgfmt、导入幂等、导出格式、导航
```

浏览器联调：生产 Cookie 为 Secure，本地 http 需用覆盖配置（`SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = False`）起 `runserver`，登录后用真实账号测试保存。
