# 内容模型设计草案

本次分析建议将公开内容建模为四类：文章、结构化数据目录、从权威源生成的快照，以及保留在后端的业务状态。PG 文档可以继续使用独立的数据库与渲染方案；其余内容不需要因为已有关系表而继续在每个请求里查询数据库。

原始核验时间：2026-09-09 07:42，中国标准时间。以下数量是撤回三方文档及扩展正文副本之前的历史快照，不代表当前表结构。生产经 `ssh pg`，在 `/data/app/pgweb` 使用实际 Django 配置读取。本地也使用实际 Django 配置。两端各有 77 张表：public 74、pgext 2、monitor 1；本次观察的列定义一致，除邮件队列生产 1 条、本地 2 条外，其余表行数一致。行数一致不等于全部内容逐条一致。所有数据库操作为只读事务，没有迁移或删除数据。

原始表清单、结构和采样证据保留在本地 `tmp/review-cleanup-20260909T034100Z/reports/content-model-audit-2026-09-09/`，不作为运行时代码提交。当前文档与扩展目录边界以 [三方文档](third-party-docs.md) 和 [扩展目录](extension-catalog.md) 为准。

**Content Adapter 在构建阶段创建页面，产物仍是静态 HTML。** 它能避免人工维护几千个源文件，但不会自动消除生成几千个页面的构建成本。PG 文档是否需要请求时渲染，应通过按版本导出、构建耗时、产物大小和更新频率判断，本轮可以暂不改变。参见 [Hugo Content Adapters](https://gohugo.io/content-management/content-adapters/)。

| 内容 | 生产规模 | 推荐建模 | 权威来源与更新方式 |
| --- | ---: | --- | --- |
| 新闻 | 897 条，已发布 334 条；标签 9 条、关联 954 条 | news 类型的 Markdown 文章，tags 数组 | 迁移已发布正文；保留上游标识、原 URL 和稳定排序。采集译文后形成可审阅文件 |
| 活动 | 131 条，全部 approved；按审计日期 enddate >= 当天为 14 条 | events 类型的 Markdown 文章 | 独立开始/结束日期、地点、组织、线上和社区标记；日期改变触发列表重建 |
| Planet | 625 条索引、1 个 feed | 按年月拆分的 JSON/YAML 外链数据 | 按 feed 与 URL 去重；仅标题、URL、posttime，未存正文 |
| 组织 | 855 条，4 种类型 | organisations 共享字典 | 新闻、活动、产品、服务商、用户组使用稳定键引用；480 家出现在这五类公开记录引用中 |
| 贡献者 | 285 人、5 种分组 | 人物名单与分组 YAML | 保留分组排序、介绍及邮箱显示策略；不导出账户关联 |
| 赞助与服务器 | 34 家赞助者、3 种级别、5 台服务器、4 条服务器赞助关联 | YAML 数据目录 | 级别键、国家键和 sponsor ID 数组；Logo 是静态资产 |
| 用户组 | 67 条 | 地区目录 YAML | 组织、国家、城市、标题和网址；正文丰富后可升为实体页面 |
| 推荐语 | 54 条 | quotes.yaml | 批准内容的静态数组；构建时选取或浏览器随机选择 |
| 产品 | 262 条、8 类、4 种许可类型 | products 类型的实体页 | Markdown 描述 + 分类、许可、组织与价格说明；列表按类别和名称组织 |
| 专业服务 | 256 条 | services 类型的实体页 | 以组织为关联键；多个 region_* 列转换成 regions 数组，服务种类转换成 provides 数组 |
| 邮件列表目录 | 97 条，54 条 active；7 组 | mailing_lists.yaml | 分组、名称、简介、active；订阅和邮件归档依旧属于另一种服务 |
| PG 版本 | 31 条，5 条 supported、1 条 current | versions.yaml + 文档构建清单 | 版本以字符串存储；当前版本使用明确指针，文档装载时间与 Git 哈希放构建元数据 |
| 安全公告 | 70 条、277 条修复版本关联 | 以 CVE ID 为键的结构化记录，必要时配 Markdown 正文 | 复用 CNA JSON、中文覆盖和历史补充；从统一记录生成 CVE 页与版本列表 |
| 国家与语言 | 国家 240、语言 486 | 代码字典 | 保留现有标识与兼容映射；不生成逐条正文页 |
| 置顶公告 | 1 条 | 公告配置中的文章引用 | 公开文章引用与社交平台投递状态拆分 |
| StackBuilder | 84 条 | 安装清单 JSON/YAML | 保持 textid + version + platform 唯一性，继续生成 applications-v2.xml |
| PG 文档 | 7,975 条 | 独立的文档读取或版本快照方案 | docs 与 core_version 关系暂时保留；不作为本轮改造前提 |
| 三方文档 | 原三表已撤回，当前为九个外链 | 名称、URL、简介的共享配置 | 复用 `THIRD_PARTY_DOCS`；不保存或索引外站正文 |
| 扩展目录 | 原审计两表各 2,355 条；现只复制 universe | 扩展元数据快照 + 内容适配器 | PGEXT 源库继续权威；详情只展示概览、关联和外链 |

文章化适用于有正文、有独立地址、需要分享和归档的内容。新闻和活动可以共用 Oink 阅读组件，但使用各自的类型、列表排序和元数据。产品、服务商属于长期维护的实体，按分类、名称与地区组织；更新描述并不意味着创建一篇新博客。

**活动模型的重点是区分文章发布日期和活动发生日期。** 当前 Event 没有记录创建日期，只有 startdate/enddate，因此迁移不能虚构历史发布日期。可让活动模板只依赖事件日期排序，保留原值；新内容再显式增加 publication date。不要直接把未来的活动开始日期设为 Hugo 的发布 date，避免受未来内容过滤影响。当前只有日期精度，不能凭空补出具体时间或活动所在地时区。首页与活动归档目前对结束日期等于今天的边界使用不同条件，迁移时应统一规则。

下面是新站点的模型示意，值不是实际活动记录：

```yaml
---
title: 示例 PostgreSQL 社区活动
type: events
summary: 活动摘要
params:
  legacy_id: 12345
  organisation: org-678
  starts_on: '2026-10-10'
  ends_on: '2026-10-11'
  online: false
  country: cn
  city: 上海
  spoken_language: zho
  community_event: true
---
活动介绍、议程、报名说明等 Markdown 正文。
```

导入时保留完整原 canonical URL 或 URL manifest，不能直接依赖 Hugo 和 Django 各自的 slugify 恰好一致。新闻保留日期与上游/历史 ID，保证同一天文章顺序稳定。news_newstag 的 urlname、描述与排序放 taxonomy 元数据；多对多关系变成文章中的 tags。批准、禁发、审核人、组织邮箱、postedto 等字段属于编辑和投递工作流，不能丢失，也不应混入公开内容数据。

**数据库关系可以转为文件里的稳定引用。** 当前关系包括：组织被新闻和活动通过 org_id 引用，被产品通过 publisher_id 引用，被服务商通过 organisation_id 引用；服务商与组织是一对一，其他几类可为一对多。产品另引用类别和许可类型；活动另引用国家和语言。建议保留 organisations 字典，而不是在几百篇文件中复制完整组织资料。contributor.company、quote.org 和 sponsors_sponsor 的公司名称并没有统一引用组织表，迁移时不能仅凭名字把它们自动合并为同一实体。

一个新站点的候选文件布局如下。它是方案说明，当前没有创建这些内容或改动数据源：

```text
<新 Hugo 站点>/
  content/
    news/<stable-id>/index.md
    events/<stable-id>/index.md
    products/<stable-id>/index.md
    services/<stable-org-id>/index.md
    ecosystem/<project>/<revision>/<language>/...
  data/
    organisations/
    contributors.yaml
    contributor_groups.yaml
    sponsors.yaml
    sponsor_tiers.yaml
    servers.yaml
    user_groups.yaml
    quotes.yaml
    versions.yaml
    news_tags.yaml
    product_categories.yaml
    license_types.yaml
    countries.yaml
    languages.yaml
    mailing_lists.yaml
    feeds.yaml
    planet/<year-month>.json
    homepage.yaml
    security/
  generated/
    pgext-snapshot.json
    docs-manifest.json
    route-manifest.json
  static/
    ...业务附件与前端资源...
```

generated 是导出器的工作目录；需要通过 Hugo mount、资源读取或内容适配器接入，不是 Hugo 会自动识别的特殊目录。手工编辑数据和机器生成快照要各有明确来源；数据条数少不意味着一定放进 hugo.yaml，较大的名单应使用 data 下独立文件。详情页有实质正文时使用 Markdown，单纯记录使用 YAML/JSON。

有几处必须以当前权威来源为准：

- **特性矩阵已经文件化。** 当前 YAML 是 26 组、420 项；旧数据库只有 20 组、322 项。公开视图读取 data/featurematrix.yaml 和 data/featurematrix_zh.yaml，旧管理注册也已注释。新站应直接使用 YAML，旧表作为历史迁移对象另行评估。
- 书籍已经来自 data/books.yaml，共 87 条；发布信息已有 4 个 release YAML；下载配置已有 yum.json，页面元信息已有 page_metadata.yaml。它们只需要模板适配。
- 本地 51 份 CNA JSON 均有对应数据库记录，但数据库另有 19 条公开历史 CVE。转为文件前应补齐这 19 条及关联版本，并保留已有译文，不能仅用 JSON 目录替换全部 70 条。
- 三方文档已经收敛为 `THIRD_PARTY_DOCS` 外链配置；新站沿用同一份名称、URL、简介和顺序，不恢复旧三表、阅读器或正文索引。
- 扩展目录只从 PGEXT 的 `universe` 导出元数据，详情展示概览、关联和外链；轻量筛选可使用静态 JSON，复杂查询按实测需要保留 API。目录为中文，筛选使用查询参数，旧语言参数重定向到现行地址；软件版本更新原位更新，不建立文档 revision。

**配置文件成为编辑来源，并不意味着同一时刻可以删除原表。** 例如 docs.version 的外键仍指向 core_version.tree；只要 PG 文档继续使用现有模型，versions.yaml 可以成为权威配置，同时把这 31 条版本记录同步成数据库投影。需要先迁移引用和读取路径，再评估退表。

适合继续保留在数据库中的内容是用户、权限、会话、组织管理关系、邮箱验证、审核与禁发状态、投票计数、防重复投票状态、邮件队列以及搜索索引。生产有 11 个用户、9 条会话、1 条邮件队列；这些虽然很小，仍然是业务运行状态。投票三表、社区 SSO 站点、投稿日志、组织管理关系和 Bug 映射当前为零，但空表只说明审计时没有记录，不能证明功能可以立即删除。Django 的迁移和管理元数据不需要设计对应的公开文件模型。

webpages 的 9,692 条是可重建搜索数据，不是另一份需要人工维护的内容。可以继续供 Go 的搜索 API 使用，并在发布时由同一批公开产物生成索引。sites/site_excludes 是搜索配置；lastcrawl 是采集游标。lists/messages 是邮件归档搜索数据，目前为零，与有 97 条的 lists_mailinglist 目录不是一回事。monitor.heartbeat 属于基础设施；v_org_id 只有一行且当前仓库未检索到业务使用，需要额外核对外部脚本后再决定。

建议按下面的顺序实施：

1. 先把版本、名单、分类、推荐语和公告这些配置源整理清楚，直接复用已存在的 YAML/JSON。为仍服务旧 Django 的表保留只读投影。
2. 将 334 条已发布新闻和 131 条活动导出为文章，保留 URL、日期、发布状态、原 ID 和组织引用；未发布的 563 条新闻继续留在内部数据源中。
3. 将产品、服务商和用户组整理成目录；使用一个组织字典，减少重复元数据。
4. 三方文档复用外链配置，扩展目录从 PGEXT 导出元数据；PG 文档单独选择按版本构建或动态读取。
5. 按实际业务决定是否替换账户与投稿后台。Go 的职责可收敛到增量导入、发布导出、搜索和少量写接口。

发布流水线需要在同一快照中生成正文、列表、分类、RSS 和索引；按上游 ID/URL 幂等导入并保留人工译文；只生成已公开内容。活动到期和定时发布即使没有 Git 改动也要重建，统一使用明确时区。本次审计观察到本地数据库会话为 GMT、生产为 Asia/Shanghai；计数聚合已统一到 Asia/Shanghai。正式导出 RSS 时间必须保留准确瞬间，不能丢弃偏移后当作同一墙上时间。

本轮结论是建模建议与只读证据，不代表已完成静态迁移、生产发布或功能退役。

相关实现与设计：

- [新闻模型](../pgweb/news/models.py)、[活动模型](../pgweb/events/models.py)、[组织与版本](../pgweb/core/models.py)
- [服务商](../pgweb/profserv/models.py)、[产品与机器清单](../pgweb/downloads/models.py)
- [三方文档外链与撤回记录](third-party-docs.md)、[文档检索设计](document-search-design.md)
- [扩展目录设计](extension-catalog.md)、[特性矩阵实际读取](../pgweb/featurematrix/views.py)
