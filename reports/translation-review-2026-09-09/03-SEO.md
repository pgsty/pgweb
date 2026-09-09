# SEO 标题与摘要

本文件仅供 Review，所有条目均待确认；页面源文件和数据库均未改动。

返回 [总览](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/REVIEW.md)。

| 编号 | 候选项目 | 判断 |
| --- | --- | --- |
| S01 | 标题前缀：PostgreSQL：内容 → PostgreSQL 内容 | 按要求列出，待确认 |
| S02 | 媒体页面与新闻列表分清用途 | 建议修改 |
| S03 | 政策页标题增加用途区分 | 可选改进 |
| S04 | 手册标题的完整格式 | 可选改进 |
| S05 | 避免扩展首页和生态文档首页重复名称 | 建议修改 |
| S06 | 动态页 HTML 标题与分享标题统一 | 可选改进 |
| S07 | 六个账户页面缺少页面名称 | 建议修改 |
| S08 | 页面主标题层级 | 可选结构调整 |
| S09 | 首页视觉标题是否同步去掉冒号 | 可选风格调整 |
| S10.01 | 页面摘要：/about/contact/ | 建议修改摘要 |
| S10.02 | 页面摘要：/about/press/ | 建议修改摘要 |
| S10.03 | 页面摘要：/about/press/faq/ | 建议修改摘要 |
| S10.04 | 页面摘要：/about/governance/ | 建议修改摘要 |
| S10.05 | 页面摘要：/about/governance/contributors/ | 建议修改摘要 |
| S10.06 | 页面摘要：/about/governance/sysadmin/ | 建议修改摘要 |
| S10.07 | 页面摘要：/about/policies/project-name/ | 建议修改摘要 |
| S10.08 | 页面摘要：/about/policies/news-and-events/ | 建议修改摘要 |
| S10.09 | 页面摘要：/about/policies/services-and-hosting/ | 建议修改摘要 |
| S10.10 | 页面摘要：/about/policies/archives/ | 建议修改摘要 |
| S10.11 | 页面摘要：/about/press/presskit12/zh/ | 建议修改摘要 |
| S10.12 | 页面摘要：/about/press/presskit13/zh/ | 建议修改摘要 |
| S10.13 | 页面摘要：/about/press/presskit14/zh/ | 建议修改摘要 |
| S10.14 | 首页摘要：补全句子与并列结构 | 建议修改摘要 |

原文与建议以可见文字为主；模板变量、链接和源字符串的完整记录保存在 review.json。行号以本次审阅基线为准。

## S01 · 标题前缀：PostgreSQL：内容 → PostgreSQL 内容

**待确认 · 按要求列出，待确认**

按你的明确偏好去掉品牌后的中文冒号，以一个空格连接正文。只做这个改动时，不顺带改标题措辞或标题内其他标点。

说明：完整的 89 条中文元数据标题见 TITLES.md：86 条有此前缀，3 条无需处理。运行时覆盖、非静态页和新增标题分别在后续条目列出。移除冒号是站点风格选择，不是搜索引擎对冒号的惩罚。

89 条静态元数据的逐页对照见 [完整标题清单](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/TITLES.md)。下列仅列共同模板和动态标题来源；静态元数据逐页记录保存在标题清单和 review.json 中。

**1. 原文**：`PostgreSQL：{%block title%}`

**建议**：`PostgreSQL {%block title%}`

落点：

- [templates/base/base.html:4](/Users/vonng/pgsty/pgweb/templates/base/base.html:4) — `{%block fulltitle%}{%if seo.title%}{{seo.title}}{%else%}PostgreSQL：{%block title%}{%endblock%}{%endif%}{%endblock%}`

**2. 原文**：`PostgreSQL：`

**建议**：`PostgreSQL`

落点：

- [pgweb/downloads/views.py:256](/Users/vonng/pgsty/pgweb/pgweb/downloads/views.py:256) — `'title': 'PostgreSQL：软件目录与产品分类',`
- [pgweb/downloads/views.py:271](/Users/vonng/pgsty/pgweb/pgweb/downloads/views.py:271) — `'title': 'PostgreSQL：软件目录：{}'.format(category.catname),`
- [pgweb/profserv/views.py:27](/Users/vonng/pgsty/pgweb/pgweb/profserv/views.py:27) — `'title': 'PostgreSQL：{}'.format(title),`
- [pgweb/profserv/views.py:57](/Users/vonng/pgsty/pgweb/pgweb/profserv/views.py:57) — `'title': 'PostgreSQL：{}：{}'.format(whatname, regname),`
- [pgweb/docs/views.py:103](/Users/vonng/pgsty/pgweb/pgweb/docs/views.py:103) — `return 'PostgreSQL：文档：{}：{}'.format(page.display_version(), title)`

## S02 · 媒体页面与新闻列表分清用途

**待确认 · 建议修改**

导航已经使用“媒体资料”；/about/press/ 的页面标题却叫“新闻”。新闻资料包也应与正式发行说明区分。

说明：保留已经广泛使用的“新闻资料包”用词；不为了统一而把 9.0–9.2 的“发布宣传资料”全部重写。

**1. 原文**：`{%block title%}新闻{%endblock%}`

**建议**：`{%block title%}媒体资料{%endblock%}`

落点：

- [templates/pages/about/press.html:2](/Users/vonng/pgsty/pgweb/templates/pages/about/press.html:2) — `{%block title%}新闻{%endblock%}`

**2. 原文**：`新闻`

**建议**：`媒体资料`

落点：

- [templates/pages/about/press.html:4](/Users/vonng/pgsty/pgweb/templates/pages/about/press.html:4) — `新闻`

**3. 原文**：`新闻咨询`

**建议**：`媒体咨询`

落点：

- [templates/pages/about/press.html:7](/Users/vonng/pgsty/pgweb/templates/pages/about/press.html:7) — `如有任何新闻咨询，请联系 PostgreSQL 公关团队：press@postgresql.org`

**4. 原文**：`PostgreSQL 新闻常见问题`

**建议**：`媒体常见问题`

落点：

- [templates/pages/about/press/faq.html:2](/Users/vonng/pgsty/pgweb/templates/pages/about/press/faq.html:2) — `{%block title%}PostgreSQL 新闻常见问题{%endblock%}`

**5. 原文**：`常见问题`

**建议**：`媒体常见问题`

落点：

- [templates/pages/about/press/faq.html:5](/Users/vonng/pgsty/pgweb/templates/pages/about/press/faq.html:5) — `常见问题`

**6. 原文**：`新闻志愿者`

**建议**：`媒体志愿者`

落点：

- [templates/pages/about/press/faq.html:37](/Users/vonng/pgsty/pgweb/templates/pages/about/press/faq.html:37) — `答：请联系 press@postgresql.org，我们的新闻志愿者将尽力安排联系。`

**7. 原文**：`新闻常见问题`

**建议**：`媒体常见问题`

落点：

- [templates/pages/docs/faq.html:7](/Users/vonng/pgsty/pgweb/templates/pages/docs/faq.html:7) — `新闻常见问题`
- [templates/pages/docs/faq.html:10](/Users/vonng/pgsty/pgweb/templates/pages/docs/faq.html:10) — `关于我们收到的许多 PostgreSQL 问题的概要介绍，请查阅我们的新闻常见问题。`

**8. 原文**：`PostgreSQL：新闻与新闻资料包`

**建议**：`PostgreSQL 媒体资料与新闻资料包`

落点：

- [data/page_metadata.yaml:257](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:257) — `/about/press/ / title: PostgreSQL：新闻与新闻资料包`

**9. 原文**：`PostgreSQL：新闻常见问题`

**建议**：`PostgreSQL 媒体常见问题`

落点：

- [data/page_metadata.yaml:261](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:261) — `/about/press/faq/ / title: PostgreSQL：新闻常见问题`

**10. 原文**：`PostgreSQL：10.0 版本发布说明`

**建议**：`PostgreSQL 10 新闻资料包`

落点：

- [data/page_metadata.yaml:288](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:288) — `/about/press/presskit10/cn/ / title: PostgreSQL：10.0 版本发布说明`

**11. 原文**：`PostgreSQL 10.0 版本发布说明`

**建议**：`PostgreSQL 10 新闻资料包`

落点：

- [templates/pages/about/press/presskit10/cn.html:2](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:2) — `{%block title%}PostgreSQL 10.0 版本发布说明{%endblock%}`
- [templates/pages/about/press/presskit10/cn.html:23](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:23) — `PostgreSQL 10.0 版本发布说明`

**12. 原文**：`PostgreSQL：9.3 版本发布说明`

**建议**：`PostgreSQL 9.3 新闻资料包`

落点：

- [data/page_metadata.yaml:3731](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:3731) — `/about/press/presskit93/zh_CN/ / title: PostgreSQL：9.3 版本发布说明`

**13. 原文**：`PostgreSQL 9.3 版本发布说明`

**建议**：`PostgreSQL 9.3 新闻资料包`

落点：

- [templates/pages/about/press/presskit93/zh_CN.html:2](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:2) — `{%block title%}PostgreSQL 9.3 版本发布说明{%endblock%}`
- [templates/pages/about/press/presskit93/zh_CN.html:5](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:5) — `PostgreSQL 9.3 版本发布说明`

## S03 · 政策页标题增加用途区分

**待确认 · 可选改进**

对政策页增加“政策”或主题限定，避免与项目服务或赞助者目录同名。其他已经清楚的标题保留。

**1. 原文**：`Planet PostgreSQL`

**建议**：`Planet PostgreSQL 博客收录政策`

落点：

- [data/page_metadata.yaml:224](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:224) — `/about/policies/planet-postgresql/ / title: Planet PostgreSQL`

**2. 原文**：`PostgreSQL：赞助`

**建议**：`PostgreSQL 赞助政策`

落点：

- [data/page_metadata.yaml:241](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:241) — `/about/policies/sponsorship/ / title: PostgreSQL：赞助`

**3. 原文**：`PostgreSQL：归档政策`

**建议**：`PostgreSQL 邮件列表归档政策`

落点：

- [data/page_metadata.yaml:57](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:57) — `/about/policies/archives/ / title: PostgreSQL：归档政策`

## S04 · 手册标题的完整格式

**待确认 · 可选改进**

在 S01 之外，若愿意进一步简化连续的“文档：版本：章节”，建议使用“PostgreSQL 版本 文档 · 章节”。这是额外的格式选择，不默认随 S01 应用。

说明：保留版本号和 ECPG 前缀；不修改数据库里的手册标题和正文。只确认 S01 时，结果仍为 PostgreSQL 文档：18：章节。

**1. 原文**：`PostgreSQL：文档：{}：{}`

**建议**：`PostgreSQL {} 文档 · {}`

落点：

- [pgweb/docs/views.py:103](/Users/vonng/pgsty/pgweb/pgweb/docs/views.py:103) — `return 'PostgreSQL：文档：{}：{}'.format(page.display_version(), title)`

**2. 原文**：`文档：{{page.display_version}}：{{page.title}}`

**建议**：`{{page.display_version}} 文档 · {{page.title}}`

落点：

- [templates/docs/docspage.html:4](/Users/vonng/pgsty/pgweb/templates/docs/docspage.html:4) — `{% block title %}文档：{{page.display_version}}：{{page.title}}{% endblock %}`

## S05 · 避免扩展首页和生态文档首页重复名称

**待确认 · 建议修改**

标题拼接使扩展目录首页出现两次 PostgreSQL，生态文档首页出现两次组件名。仅精简首页的重复信息。

说明：下列是从代码拼接规则推导的示例，非数据库查询或线上抓取结果。版本号为示例值。

**1. 原文**：`PostgreSQL 扩展目录 · PostgreSQL`

**建议**：`PostgreSQL 扩展目录`

落点：

- [pgweb/ext/views.py:59](/Users/vonng/pgsty/pgweb/pgweb/ext/views.py:59) — `browse() 已传入带品牌的标题；详情页与分类页的后缀格式可保留。`

**2. 原文**：`Patroni 文档 · Patroni 4.1.0 · PostgreSQL`

**建议**：`Patroni 4.1.0 文档 · PostgreSQL`

落点：

- [pgweb/docs/ecosystem.py:270](/Users/vonng/pgsty/pgweb/pgweb/docs/ecosystem.py:270) — `仅空 document.path 对应的文档首页；章节页保留章节名、组件和版本。`

## S06 · 动态页 HTML 标题与分享标题统一

**待确认 · 可选改进**

无静态元数据时，HTML 标题采用公共模板前缀，Open Graph 则直接采用 og.title；现有来源的品牌、标点有差异。建议两者使用同一份最终标题。 依据：[HTML title](/Users/vonng/pgsty/pgweb/templates/base/base.html:4)；[Open Graph 元数据回退](/Users/vonng/pgsty/pgweb/pgweb/core/templatetags/pgseo.py:12)。

说明：示例使用假定的标题或编号，只演示当前源码规则，不读取或修改新闻、特性、安全漏洞等数据库内容。正文中已有的 PostgreSQL 不删，标题输出避免重复添加品牌。

**1. 原文**：`HTML：PostgreSQL：专业服务 - 亚洲；OG：PostgreSQL：专业服务：亚洲`

**建议**：`HTML / OG：PostgreSQL 专业服务 - 亚洲`

落点：

- [pgweb/profserv/views.py:57](/Users/vonng/pgsty/pgweb/pgweb/profserv/views.py:57)

**2. 原文**：`HTML：PostgreSQL：特性：全文搜索；OG：特性：全文搜索`

**建议**：`HTML / OG：PostgreSQL 特性：全文检索`

落点：

- [pgweb/featurematrix/views.py:155](/Users/vonng/pgsty/pgweb/pgweb/featurematrix/views.py:155) — `术语修改由 T01 单独确认；若不确认 T01，维持原特性名。`

**3. 原文**：`HTML：PostgreSQL：安全信息：版本 18；OG：安全信息：版本 18`

**建议**：`HTML / OG：PostgreSQL 安全信息：版本 18`

落点：

- [pgweb/security/views.py:22](/Users/vonng/pgsty/pgweb/pgweb/security/views.py:22)

**4. 原文**：`当记录标题为 PostgreSQL 18 发布时，HTML 为 PostgreSQL：PostgreSQL 18 发布`

**建议**：`HTML / OG：PostgreSQL 18 发布`

落点：

- [templates/news/item.html:3](/Users/vonng/pgsty/pgweb/templates/news/item.html:3) — `events/item.html 使用相同的包装模式；只调整标题输出，不改记录。`

**5. 原文**：`HTML 自动添加 PostgreSQL：；OG 使用活动原题`

**建议**：`HTML / OG 使用同一最终标题；以 PostgreSQL 开头的原题保留，其余在开头添加 PostgreSQL 空格`

落点：

- [templates/events/item.html:3](/Users/vonng/pgsty/pgweb/templates/events/item.html:3) — `保留数据库中的活动名称。`

## S07 · 六个账户页面缺少页面名称

**待确认 · 建议修改**

这六个模板没有 title block，离线渲染时标题仅为“PostgreSQL：”。新增与页面内容对应的名称，改善标签页与历史记录识别。

说明：本条不是建议把账户页当作 SEO 引流页面；signup_oauth 和 submit_form 由视图传入表单名称，不误报为缺失。

**1. 原文**：`PostgreSQL：`

**建议**：`PostgreSQL 社区认证暂不可用`

落点：

- [templates/account/communityauth_cooloff.html:1](/Users/vonng/pgsty/pgweb/templates/account/communityauth_cooloff.html:1) — `新增 title block，配合 S01 公共标题前缀。`

**2. 原文**：`PostgreSQL：`

**建议**：`PostgreSQL 访问被拒绝`

落点：

- [templates/account/communityauth_nogroup.html:1](/Users/vonng/pgsty/pgweb/templates/account/communityauth_nogroup.html:1) — `新增 title block，配合 S01 公共标题前缀。`

**3. 原文**：`PostgreSQL：`

**建议**：`PostgreSQL 社区认证信息不完整`

落点：

- [templates/account/communityauth_noinfo.html:1](/Users/vonng/pgsty/pgweb/templates/account/communityauth_noinfo.html:1) — `新增 title block，配合 S01 公共标题前缀。`

**4. 原文**：`PostgreSQL：`

**建议**：`PostgreSQL 账户登录`

落点：

- [templates/account/login.html:1](/Users/vonng/pgsty/pgweb/templates/account/login.html:1) — `新增 title block，配合 S01 公共标题前缀。`

**5. 原文**：`PostgreSQL：`

**建议**：`PostgreSQL 密码重置完成`

落点：

- [templates/account/password_reset_complete.html:1](/Users/vonng/pgsty/pgweb/templates/account/password_reset_complete.html:1) — `新增 title block，配合 S01 公共标题前缀。`

**6. 原文**：`PostgreSQL：`

**建议**：`PostgreSQL 账户已创建`

落点：

- [templates/account/signup_complete.html:1](/Users/vonng/pgsty/pgweb/templates/account/signup_complete.html:1) — `新增 title block，配合 S01 公共标题前缀。`

## S08 · 页面主标题层级

**待确认 · 可选结构调整**

行为准则侧栏使用了三个 h1，PG12–14 新闻资料包正文又有一个与页面名称并列的 h1。建议侧栏降为 h2，新闻正文发布标题降为 h2，文字不改。 依据：[Google 标题链接说明](https://developers.google.com/search/docs/appearance/title-link)。

说明：这不是“多个 h1 就会受惩罚”的判断；目的仅是让页面主标题清楚。涉及样式级联，确认后应检查视觉效果。

**1. 原文**：`<h1>翻译</h1>`

**建议**：`<h2>翻译</h2>`

落点：

- [templates/base/cocpage.html:9](/Users/vonng/pgsty/pgweb/templates/base/cocpage.html:9) — `翻译`

**2. 原文**：`<h1>委员会</h1>`

**建议**：`<h2>委员会</h2>`

落点：

- [templates/base/cocpage.html:17](/Users/vonng/pgsty/pgweb/templates/base/cocpage.html:17) — `委员会`

**3. 原文**：`<h1>年度报告</h1>`

**建议**：`<h2>年度报告</h2>`

落点：

- [templates/base/cocpage.html:21](/Users/vonng/pgsty/pgweb/templates/base/cocpage.html:21) — `年度报告`

**4. 原文**：`<h1>PostgreSQL 12 版本发布!</h1>`

**建议**：`<h2>PostgreSQL 12 版本发布!</h2>`

落点：

- [templates/pages/about/press/presskit12/zh.html:5](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit12/zh.html:5) — `PostgreSQL 12 版本发布!`

**5. 原文**：`<h1>PostgreSQL 13 正式发布！</h1>`

**建议**：`<h2>PostgreSQL 13 正式发布！</h2>`

落点：

- [templates/pages/about/press/presskit13/zh.html:5](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit13/zh.html:5) — `PostgreSQL 13 正式发布！`

**6. 原文**：`<h1>PostgreSQL 14 发布！</h1>`

**建议**：`<h2>PostgreSQL 14 发布！</h2>`

落点：

- [templates/pages/about/press/presskit14/zh.html:5](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit14/zh.html:5) — `PostgreSQL 14 发布！`

## S09 · 首页视觉标题是否同步去掉冒号

**待确认 · 可选风格调整**

你明确提出的是 SEO 标题；首页大标题的标点也列为独立选择。它是可见文案，不默认跟着元数据改动。

**1. 原文**：`PostgreSQL：世界上最先进的开源关系型数据库`

**建议**：`PostgreSQL 世界上最先进的开源关系型数据库`

落点：

- [templates/index.html:51](/Users/vonng/pgsty/pgweb/templates/index.html:51) — `PostgreSQL：世界上最先进的开源关系型数据库`

## S10.01 · 页面摘要：/about/contact/

**待确认 · 建议修改摘要**

摘要应概括整页，不沿用只谈 Bug 的首段和“点击下方按钮”。

**1. 原文**：`PostgreSQL 社区始终致力于提供能够可靠存储数据的软件。如果您认为发现了 Bug，请点击下方按钮，并按照说明提交 Bug 报告`

**建议**：`汇总 PostgreSQL 的 Bug、安全问题、技术支持、媒体与社区联系渠道，并说明如何反馈 pg.center 的译文和网站问题。`

落点：

- [data/page_metadata.yaml:25](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:25) — `/about/contact/ / description: PostgreSQL 社区始终致力于提供能够可靠存储数据的软件。如果您认为发现了 Bug，请点击下方按钮，并按照说明提交 Bug 报告`

## S10.02 · 页面摘要：/about/press/

**待确认 · 建议修改摘要**

页面用途比一段联系邮箱说明更完整。

**1. 原文**：`如有任何新闻咨询，请联系 PostgreSQL 公关团队：press@postgresql.org`

**建议**：`获取 PostgreSQL 新闻资料包、媒体常见问题和公关团队联系方式，查阅各版本发布资料及不同语言版本。`

落点：

- [data/page_metadata.yaml:258](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:258) — `/about/press/ / description: 如有任何新闻咨询，请联系 PostgreSQL 公关团队：press@postgresql.org`

## S10.03 · 页面摘要：/about/press/faq/

**待确认 · 建议修改摘要**

不用第一个问题的时效性答案作为整页摘要。

**1. 原文**：`问：PostgreSQL 的当前版本是什么？答：18，于 2025 年 9 月 25 日发布。这是我们在超过 39 年开发历程中的第 35 个主要版本。我们每年发布一个新的 PostgreSQL 版本，这在 SQL 数据库中是独一无二的`

**建议**：`面向媒体介绍 PostgreSQL 的版本发布、许可证、项目治理、用户与社区支持，并解答常见的数据库选型问题。`

落点：

- [data/page_metadata.yaml:262](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:262) — `/about/press/faq/ / description: 问：PostgreSQL 的当前版本是什么？答：18，于 2025 年 9 月 25 日发布。这是我们在超过 39 年开发历程中的第 35 个主要版本。我们每年发布一个新的 PostgreSQL 版本，这在 SQL 数据库中是独一无二的`

## S10.04 · 页面摘要：/about/governance/

**待确认 · 建议修改摘要**

去掉“本页列出链接／请查看链接”等界面指示。

**1. 原文**：`本页列出了构成项目治理层级的各个团队和委员会的页面链接。请查看各个链接页面以了解每个小组的更多信息，包括成员和章程`

**建议**：`了解 PostgreSQL 的项目治理结构，查阅核心团队、各委员会与工作小组的职责、成员和章程。`

落点：

- [data/page_metadata.yaml:37](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:37) — `/about/governance/ / description: 本页列出了构成项目治理层级的各个团队和委员会的页面链接。请查看各个链接页面以了解每个小组的更多信息，包括成员和章程`

## S10.05 · 页面摘要：/about/governance/contributors/

**待确认 · 建议修改摘要**

保留主题，避免把冗长的决策程序直接截断作为摘要。

**1. 原文**：`所有贡献者的认可由贡献者委员会负责管理，委员会根据个人情况决定每位贡献者或潜在贡献者的状态。决定依据认可的贡献者政策作出。当前确定谁有资格成为贡献者的方式是通过委员会成员的简单多数投票。委员会的决定是最终决定，除非被核心团队推翻`

**建议**：`了解 PostgreSQL 贡献者委员会的职责、成员与工作方式，以及贡献者认可政策和联系渠道。`

落点：

- [data/page_metadata.yaml:41](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:41) — `/about/governance/contributors/ / description: 所有贡献者的认可由贡献者委员会负责管理，委员会根据个人情况决定每位贡献者或潜在贡献者的状态。决定依据认可的贡献者政策作出。当前确定谁有资格成为贡献者的方式是通过委员会成员的简单多数投票。委员会的决定是最终决定，除非被核心团队推翻`

## S10.06 · 页面摘要：/about/governance/sysadmin/

**待确认 · 建议修改摘要**

概括团队页面，不以 Git 仓库细节结尾。

**1. 原文**：`基础设施团队负责运行所有 postgresql.org 基础设施，包括各种公共和非公共服务。PostgreSQL 网站开发在 pgsql-www 邮件列表上讨论。postgresql.org 网站的源代码存储在公共的 GIT 代码仓库中`

**建议**：`了解 PostgreSQL 基础设施团队负责的服务、工作方式与联系渠道，以及网站开发和基础设施管理的分工。`

落点：

- [data/page_metadata.yaml:45](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:45) — `/about/governance/sysadmin/ / description: 基础设施团队负责运行所有 postgresql.org 基础设施，包括各种公共和非公共服务。PostgreSQL 网站开发在 pgsql-www 邮件列表上讨论。postgresql.org 网站的源代码存储在公共的 GIT 代码仓库中`

## S10.07 · 页面摘要：/about/policies/project-name/

**待确认 · 建议修改摘要**

原摘要以引语引导语结尾，单独出现在搜索结果中不完整。

**1. 原文**：`Postgres 是 PostgreSQL 项目的一个公认别名。但它只是别名或昵称，并非项目的官方名称。引用 PostgreSQL 核心团队成员 Dave Page 的话：`

**建议**：`了解 PostgreSQL 的正式项目名称、Postgres 简称的由来与使用惯例，以及社区对项目名称的说明。`

落点：

- [data/page_metadata.yaml:234](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:234) — `/about/policies/project-name/ / description: Postgres 是 PostgreSQL 项目的一个公认别名。但它只是别名或昵称，并非项目的官方名称。引用 PostgreSQL 核心团队成员 Dave Page 的话：`

## S10.08 · 页面摘要：/about/policies/news-and-events/

**待确认 · 建议修改摘要**

概括政策内容，不以首页广告价值的背景说明作为摘要。

**1. 原文**：`postgresql.org 首页包含新闻和活动列表，这些列表完全为 PostgreSQL 社区的利益而维护。由于这些版位若商业化提供会非常有价值（每条公告最高可达 400 美元），管理员对首页允许发布的内容拥有完全裁量权`

**建议**：`查阅 PostgreSQL 新闻与活动的收录政策，了解提交要求、审核标准、发布频率及活动公告规则。`

落点：

- [data/page_metadata.yaml:215](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:215) — `/about/policies/news-and-events/ / description: postgresql.org 首页包含新闻和活动列表，这些列表完全为 PostgreSQL 社区的利益而维护。由于这些版位若商业化提供会非常有价值（每条公告最高可达 400 美元），管理员对首页允许发布的内容拥有完全裁量权`

## S10.09 · 页面摘要：/about/policies/services-and-hosting/

**待确认 · 建议修改摘要**

摘要直接回答这项政策管什么。

**1. 原文**：`www.postgresql.org 主页上包含专业服务和托管（统称为“服务”）列表，这些列表完全是为了 PostgreSQL 社区的利益而维护的。由于这些空间如果商业化将具有相当的价值，因此我们的管理员有权对主页上允许展示的内容进行严格限制`

**建议**：`查阅 PostgreSQL 专业服务与托管服务的收录政策，了解企业资料、服务描述、覆盖地区和审核要求。`

落点：

- [data/page_metadata.yaml:238](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:238) — `/about/policies/services-and-hosting/ / description: www.postgresql.org 主页上包含专业服务和托管（统称为“服务”）列表，这些列表完全是为了 PostgreSQL 社区的利益而维护的。由于这些空间如果商业化将具有相当的价值，因此我们的管理员有权对主页上允许展示的内容进行严格限制`

## S10.10 · 页面摘要：/about/policies/archives/

**待确认 · 建议修改摘要**

避免把上游邮件归档站的“本站”身份直接套在中文翻译站上。

**1. 原文**：`PostgreSQL 邮件列表在 www.postgresql.org 上进行归档。本站旨在提供对列表活动的准确记录，因此不会进行修改`

**建议**：`了解 PostgreSQL 邮件列表的归档原则、准确记录要求及隐私相关说明。`

落点：

- [data/page_metadata.yaml:58](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:58) — `/about/policies/archives/ / description: PostgreSQL 邮件列表在 www.postgresql.org 上进行归档。本站旨在提供对列表活动的准确记录，因此不会进行修改`

## S10.11 · 页面摘要：/about/press/presskit12/zh/

**待确认 · 建议修改摘要**

明确是历史版本资料，不把“最新版本”作为独立摘要。

**1. 原文**：`PostgreSQL 全球开发组今天宣布发布 PostgreSQL 12，这是世界上最先进的开源数据库的最新版本`

**建议**：`PostgreSQL 12 新闻资料包：介绍查询性能、索引优化、SQL/JSON 路径等改进，并提供下载和文档资源。`

落点：

- [data/page_metadata.yaml:1081](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:1081) — `/about/press/presskit12/zh/ / description: PostgreSQL 全球开发组今天宣布发布 PostgreSQL 12，这是世界上最先进的开源数据库的最新版本`

## S10.12 · 页面摘要：/about/press/presskit13/zh/

**待确认 · 建议修改摘要**

明确版本和资料用途，避免孤立的“最新版本”表述。

**1. 原文**：`PostgreSQL 全球开发组今天宣布 PostgreSQL 13 正式发布。作为世界上最先进的开源数据库，PostgreSQL 13 是目前的最新版本`

**建议**：`PostgreSQL 13 新闻资料包：介绍索引、查询性能、并行清理与受信任扩展等改进，并提供下载和文档资源。`

落点：

- [data/page_metadata.yaml:1315](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:1315) — `/about/press/presskit13/zh/ / description: PostgreSQL 全球开发组今天宣布 PostgreSQL 13 正式发布。作为世界上最先进的开源数据库，PostgreSQL 13 是目前的最新版本`

## S10.13 · 页面摘要：/about/press/presskit14/zh/

**待确认 · 建议修改摘要**

明确版本和资料用途，避免孤立的“最新版本”表述。

**1. 原文**：`PostgreSQL 全球开发组今天宣布 PostgreSQL 14 正式发布，这是世界上最先进的开源数据库的最新版本`

**建议**：`PostgreSQL 14 新闻资料包：介绍多范围类型、查询性能、逻辑复制与监控等改进，并提供下载和文档资源。`

落点：

- [data/page_metadata.yaml:1469](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:1469) — `/about/press/presskit14/zh/ / description: PostgreSQL 全球开发组今天宣布 PostgreSQL 14 正式发布，这是世界上最先进的开源数据库的最新版本`

## S10.14 · 首页摘要：补全句子与并列结构

**待确认 · 建议修改摘要**

保留中文翻译站和 Pigsty 维护者身份，仅去掉零散名词堆叠与多余逗号。

**1. 原文**：`PostgreSQL 官方网站中文翻译，由 Pigsty 维护的中文文档，信息资讯，软件目录，与知识库`

**建议**：`pg.center 是由 Pigsty 团队维护的 PostgreSQL 官方网站中文翻译站，提供中文文档、技术资讯、软件目录与知识库。`

落点：

- [pgweb/core/views.py:101](/Users/vonng/pgsty/pgweb/pgweb/core/views.py:101) — `'description': 'PostgreSQL 官方网站中文翻译，由 Pigsty 维护的中文文档，信息资讯，软件目录，与知识库',`
