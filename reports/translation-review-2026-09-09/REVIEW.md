# pg.center 中文翻译、术语与 SEO 审阅

> 后续状态：用户已确认并完成修订。请查看 [修订结果](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/REVISION.md)。以下保留原始审阅提案。

**本轮只记录建议，没有修改页面、模板、应用代码或数据库。** 所有条目均待你确认。本次仅创建此审阅目录。初始工作区已建立 1218 个文件的摘要基线；审阅期间检测到 19 个文件存在其他并行改动，已保留并复核受影响原文和定位。变动名单见验证记录。

以你指定的 [最新 PostgreSQL 术语表](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv) 为准。严格区分术语校准、明确误译、有限润色与需要定夺的政策／历史文字；能清楚表达原意的既有译文保持原样。

| Review 文件 | 范围 | 候选项 |
| --- | --- | --- |
| [术语校准](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/01-TERMS.md) | 术语表对应、具体语境及全部拟改落点 | 26 |
| [明确误译与有限润色](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/02-COPY.md) | 含义有偏差的译文、错字与少量确有改善的句子 | 33 |
| [SEO 标题与摘要](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/03-SEO.md) | 标题前缀、用途区分、摘要与标题输出 | 23 |
| [界面补译](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/04-UI.md) | 源码生成的英文界面提示；与正文润色分开 | 8 |
| [需要单独定夺的项目](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/05-DECISIONS.md) | 两份行为准则、Quorum、历史许可与待核实事实 | 5 |

另附 [89 个中文元数据标题逐页对照](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/TITLES.md)。共 95 个 Review 编号；编号是建议组，不代表同等数量的错误。S01 一组包含 86 个标题前缀，界面补译也按页面流程成组；每个片段均列出了原文、建议及源码位置。

## 优先看这些

| 编号 | 原文或问题 | 建议 |
| --- | --- | --- |
| S01 | PostgreSQL：项目简介与核心特性 | PostgreSQL 项目简介与核心特性；先只移除这一处冒号 |
| T01 / T04 / T06 | 全文搜索／排除约束／最常用值 | 全文检索／排他约束／高频值 |
| C05 | 复制槽的最大 WAL 保持时间 | 复制槽的最大 WAL 保留量 |
| C06 | 原生 Windows 端口 | Windows 原生移植版 |
| C14 | 平均将空间利用率降低了约 40% | 平均减少约 40% 的空间占用 |
| C18 / C19 | IMPORT FOREIGN SCHEMA 被写成批量插入命令；PG15 默认权限变化被写成“允许撤销” | 分别订正功能归属和默认行为 |
| S02 | 媒体资料入口叫“新闻”，新闻资料包叫“版本发布说明” | 区分媒体资料、新闻资料包和正式发行说明 |
| D01 | 旧中文行为准则与现行译文并存 | 优先复用已校对的现行译文，单独确认旧入口方案 |
| D04 / D05 | 中文版权起始年不一致；PL/Perl 条目描述成 PL/pgSQL | 保留为待核实项，不混入普通替换批次 |

## 审阅口径与保留项

- 只核对仓库中的普通页面、公共模板、导航、SEO 元数据和界面文案。特性矩阵的中文名称和描述直接从 [YAML](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml) 运行时读取，因此纳入；数据库记录、导入的手册正文、新闻、博客、生态文档与扩展数据均不修改。
- 盘点 385 个 HTML 模板，识别 151 个含中文的模板文件；日文页面的汉字未当成中文。审阅覆盖普通内容页、公共外壳和 13 份中文历史新闻资料包，管理后台和外语正文不纳入补译范围。
- 审阅了 89 条中文静态元数据以及特性矩阵的 420 个特性、26 个分组。其他 217 条语言元数据不修改。
- “可扩展性”在 extensibility 语境中保留；“可伸缩性”用于 scalability。“集群”在多节点语境中保留，单个数据库安装／数据目录才用“集簇”。
- SQL 命令、参数名、模块名、英文 YAML 键和 URL 不按中文术语表机械替换。VACUUM、CREATE EXTENSION、PUBLIC / public、B-tree 英文数据键都需要按语境保护。
- 已准确的正文不做风格统一。主版本／主要版本、发布说明／发行说明、内建／内置、公共表表达式／公用表表达式等本轮不因个人偏好批量改写。
- 历史资料中的年份、性能数字、人物引语与当时支持平台不自动更新为现在；发现的明确误译单列。外部数据源作为面向用户的分类名称暂保留，不机械改成外部数据包装器。
- U 类是另外发现的界面补译。来自数据库的选项、第三方验证码界面及 Django 自带英文校验消息，不通过全站语言配置变更顺带处理。

## SEO 口径

默认建议保留 PostgreSQL 品牌，将品牌后的中文冒号换成一个空格；已有简洁的品牌后缀格式保留。S04 的手册标题重排、S03 的政策用途补充、S08 的标题层级和 S09 的首页可见标题是独立选项。不会因确认 S01 而一并应用。

86 条元数据的前缀不是唯一入口。公共模板、手册和部分视图还会生成标题；手册保留版本与 ECPG 区分，动态标题不通过修改数据库原题解决品牌重复。/docs/release/ 已由视图覆盖成“PostgreSQL 发布说明归档”，完整清单对这一例单独说明。

Google 建议标题清晰、简洁、能够区分页面，品牌文字可以用多种分隔方式。这里没有“中文冒号导致排名惩罚”的判断，也不承诺改词会提高排名。参见 [Google 标题链接说明](https://developers.google.com/search/docs/appearance/title-link)。

## 验证范围与后续确认

已在显式禁用数据库连接的情况下离线渲染 89 个中文元数据模板，核对 HTML title 与 Open Graph title，并检查账户表单标签和缺失的页面名称。这是模板级证据，不等于各真实视图完整执行或生产站点已经采用这些内容；没有启动服务器、部署或写入数据库。

每项都可以按编号单独确认，例如“S01、T01–T26 同意；C 类仅确认 C05、C06；D 类保留”。确认只覆盖明细中列出的原文与建议。若同时确认多个命中同一段的项目，实施时合并成一次最小修改；不直接执行全局词语替换。

完整记录：[原文、建议与定位数据](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/review.json)；[审阅基线与验证记录](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/verification.json)；[离线标题渲染记录](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/rendered-metadata.json)。
