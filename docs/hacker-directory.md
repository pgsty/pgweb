# PostgreSQL 开发者大全

入口 `/developer/hacker/`，详情 `/developer/hacker/<slug>/`，头像 `/developer/hacker/<slug>/avatar/`。
早期预览地址 `/hacker/` 及其个人页、头像地址永久跳转到上述规范路径，保留搜索、筛选与分页参数。
顶部与侧栏“开发者”菜单中提供入口，保留原核心团队、提交者和贡献者栏目。

## 收录与来源

名单以 [PGNexus Hacker Profiles](https://pgnexus.ai/hacker-profiles) 的完整公开列表为边界。
采集列表的所有分页、每人的详情 HTML、Next.js Flight 数据和公开活动分页；保留所有源字段、链接、文本、原图与下载错误。
公开邮箱、角色、机构和贡献说明从 [PostgreSQL 贡献者档案](https://www.postgresql.org/community/contributors/)、核心团队与提交者页面补充。
仅按明确匹配的姓名归属资料，不推测邮箱。补充信息带来源，机构不一致时两源分别保留。
存在同名身份疑点的记录放入 `data.review_notes`，页面通过中文编辑字段注明待核实；不能仅凭同名拼接人物资料。当前源 ID 103、209 已保留核查记录。
这里的“全部”是源站当前名单、详情和公开分页的完整快照，不表示已穷尽每个人在互联网上的所有资料。

原始证据放在 `tmp/hacker/<UTC时间>/`，每次运行保留独立目录；官方补充在 `tmp/hacker/official/`。
`manifest.json` 记录请求 URL、抓取时间、响应状态、文件路径与 SHA-256，`report.json` 记录覆盖率及未取得项。
源头像成功下载后转成最长边不超过 512 像素的 WebP；原图不动。源站通用占位图不算真人头像，未取得头像在页面上用姓名首字母代替。
用于重建数据库的固定快照和处理后头像位于 `data/hacker/`。原始采集目录默认被 Git 忽略。

## 一个表足够

Django 应用 `pgweb.hacker`，数据库表 `hacker_profile`，一人一行：

| 字段 | 用途 |
| --- | --- |
| `id` | 本地自动主键 |
| `source_id` | PGNexus 稳定 ID，唯一；同步匹配键 |
| `slug` | 稳定页面路径，唯一；姓名变化不改已有 URL |
| `name`, `organization`, `country`, `bio` | 原始姓名、机构、国家与简介 |
| `texts` JSONB | 独立编辑内容，`zh` 保存中文简介、职务、机构、所在地及核实提示 |
| `data` JSONB | 完整列表、详情、活动、公开邮箱与链接、官方补充、来源证据 |
| `avatar` BYTEA | 已验证的 WebP 头像，与档案一起备份和同步 |
| `avatar_content_type`, `avatar_sha256` | 正确响应类型、浏览器缓存与完整性校验 |
| `content_hash` | 业务内容摘要，跳过未变化的档案 |
| `source_fetched_at` | 该行所保存快照的来源采集时间 |
| `imported_at` | 该行内容最后一次写入时间 |

`data` 的主要结构：

```json
{
  "list": {"原始列表字段": "原样保留"},
  "detail": {"type": "contributor", "profile": {}},
  "sections": {"DiscussionsSection": {"initialItems": [], "items": [], "total": 0}},
  "emails": [{"email": "developer@example.org", "source_url": "https://example.org/profile"}],
  "links": [{"label": "GitHub", "url": "https://github.com/example"}],
  "official": {"role": "Major Contributors", "contribution": "…", "source_url": "…"},
  "source_url": "https://pgnexus.ai/c/example-1"
}
```

不拆邮箱、链接、任职、讨论或头像子表，不另建全文索引。组织和国家普通索引即可；当前百人规模用 `icontains` 搜索。
列表查询只读取常用列和小型 `texts` JSON，不读取 `data` 大列或头像字节；详情才加载完整档案。头像只从本站读取，避免依赖远端临时 URL。
源文本按普通文本转义，外部链接只允许 HTTP(S)，公开邮箱单独验证后生成 `mailto:`。

## 更新步骤

在仓库根目录使用项目 Python：

```bash
.venv/bin/python tools/hacker/collect.py --help
.venv/bin/python tools/hacker/enrich_official.py --help
.venv/bin/python manage.py migrate hacker
.venv/bin/python manage.py hacker_import data/hacker/profiles.json.gz --check
.venv/bin/python manage.py hacker_import data/hacker/profiles.json.gz
.venv/bin/python manage.py hacker_localize data/hacker/zh.json --check
.venv/bin/python manage.py hacker_localize data/hacker/zh.json
```

采集与官方补充工具的参数以 `--help` 为准。原始快照经过补充后，将完整快照与它引用的 `avatars/` 一起放进 `data/hacker/`，再导入。
导入先验证全批次、唯一 ID/slug、头像路径范围、哈希、实际图像格式与尺寸，再在一个事务中写入。
导入按 `source_id` 原位更新，未变化不写，快照缺失的人不自动删除。来源元数据和采集时间本身不会触发无意义更新。
中文整理文件为 `data/hacker/zh.json`，通过 `hacker_localize` 写入独立的 `texts.zh`，原始同步不会覆盖它。中文导入按源 ID 与姓名核对完整名单，整批验证后原子更新，未变化不写入；不改来源 `content_hash`，也不改其他语言的编辑内容。

页面只呈现人物档案：头像、姓名、中文身份与简介、公开链接及来源。邮箱、LinkedIn、GitHub 等链接以图标放在姓名下方，保留可访问标签和悬浮提示。机构优先采用官方档案，列表与筛选使用相同的中文整理值。来源行链接 PostgreSQL 名录及公开专业资料；不展示 PGNexus 名称或链接，也不展示采集日期、联系信息标题、活动列表、讨论对象或补丁列表。活动原始素材仍保留在归档和 `data`，供内部追溯。

生产发布应只包含本栏目相关改动，先核对 `/data/app/pgsql.cc` 工作区和数据库连接，再安装依赖、迁移 `hacker`、导入同一快照、重启 `pgsql.cc`。
无需改动 Nginx。本站 sitemap 自动包含目录和全部个人页；独立文档检索不混入人物，站内爬虫后续正常抓取即可。
回退页面代码前导出 `hacker_profile`；仅撤入口不需删除该表或任何现有资料。

## 验证

```bash
PGWEB_TEST_DB=test_pgweb_hacker .venv/bin/python manage.py test pgweb.hacker --noinput
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations hacker --check --dry-run
```

测试覆盖全量源字段保留、幂等与原子导入、头像校验、搜索筛选分页、文本与链接安全、SEO/导航/sitemap、列表大列延迟加载。
验收还需将名单 ID 集合与数据库逐项比较，检查全部头像响应、详情页、中文覆盖和旧活动入口移除；只通过单元测试不代表源素材全部取得。

## 2026-09-26 首次收录结果

- PGNexus 名单 98 人，98 个唯一源 ID 与本地数据库逐项一致；所有个人页和 5 页目录通过 HTTP 检查。
- 头像 88 份（原源 84，加 4 份已确认身份的专业资料来源），61 人有公开邮箱，64 人匹配官方贡献者资料。
- 全量活动关联共 5,851 条：讨论 3,600、补丁 2,088、提及 136、推荐文章 16、知识文章 7、沙箱 1、评价 3。关联数不是去重后的全站讨论/文章数。
- 10 人未取得头像：7 个源站通用占位图、2 个过期链接、1 个 404；16 张源页面内容配图中归档 12 张，4 张连接失败。额外找到的 Shveta 人物介绍 HTML 已归档，表彰海报下载不完整，仅留失败记录，不用作头像。
- 源 ID 103、209 的身份疑点保留在 JSON 并在详情页提示；原始来源不覆写，不对它们补未经核实的邮箱或头像。
- `tmp/hacker/20260926T111044Z/manifest-final.json` 为补充完成后的素材文件清单，`manifest.json` 保留采集阶段清单；最终导入数据在 `data/hacker/profiles.json.gz`。
- 验收报告 `tmp/hacker/qa/acceptance.json`、逐页报告 `tmp/hacker/qa/http-acceptance.json`；23 项 Django 测试与 2 项采集解析回归测试通过。重复导入预检为 98 条未变化。
- 本轮只导入本地数据库，预览端口 8003；尚未提交、推送或部署生产。

## 2026-09-26 人物档案整理

98 人已覆盖中文编辑字段；有原始简介或官方贡献说明的内容已译为中文，缺失资料保持留空，身份存疑者不拼接未经确认的简介与机构。中文全文可搜索。`hacker.0002_hackerprofile_texts` 仅增加一个 JSONB 字段，仍为一人一行的单表结构。

本次验收：27 项 Django 测试通过；98 个个人页和全部 5 页目录均返回 200，未渲染 PGNexus 名称/链接、讨论或补丁等活动区块，中文简介与姓名下方图标检查通过。完整报告 `tmp/hacker/qa/zh-acceptance.json`。中文导入与原始导入预检均为 98 条未变化。
