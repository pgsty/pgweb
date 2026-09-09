# 需要单独定夺的项目

本文件仅供 Review，所有条目均待确认；页面源文件和数据库均未改动。

返回 [总览](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/REVIEW.md)。

| 编号 | 候选项目 | 判断 |
| --- | --- | --- |
| D01 | 两份中文行为准则的处理方式 | 需单独决定 |
| D02 | Quorum commit 的译法与历史引语 | 需单独确认译法和引语 |
| D03 | 历史许可介绍中混用“版权”与“许可证” | 需单独确认历史文字 |
| D04 | 中文版权起始年份不一致 | 需确认事实 |
| D05 | PL/Perl 验证器条目写成 PL/pgSQL | 待核实上游事实 |

原文与建议以可见文字为主；模板变量、链接和源字符串的完整记录保存在 review.json。行号以本次审阅基线为准。

## D01 · 两份中文行为准则的处理方式

**待确认 · 需单独决定**

/coc/ 是已校对的现行中文页，/coc/zh/ 仍可由模板回退路由访问，而且含义存在差异。建议保留现行译文，旧入口复用同一份正文；如果希望保留历史译文，应明确标为历史版本。 依据：[现行中文页](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/coc.html:1)；[旧中文页](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/coc/zh.html:1)；[旧页 canonical 指向现行页](/Users/vonng/pgsty/pgweb/data/page_metadata.yaml:1)；[上游现行行为准则](https://www.postgresql.org/about/policies/coc/)。

说明：以下列出旧译的关键差异供核对。推荐复用已有现行译文，不重译整份准则；不在此次报告中改路由、正文或 canonical。

**1. 原文**：`丧失承诺特权`

**建议**：`撤销提交权限`

落点：

- [templates/pages/about/policies/coc/zh.html:95](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/coc/zh.html:95) — `暂时或永久禁止使用某些或所有社区管理的空间，包括但不限于社区邮件列表、论坛、IRC 和丧失承诺特权;`

**2. 原文**：`任何证明不成立的指控，以及被证明是恶意或有意为虚假的指控`

**建议**：`任何经证实缺乏事实依据、且经证实出于恶意或明知虚假的指控`

落点：

- [templates/pages/about/policies/coc/zh.html:112](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/coc/zh.html:112) — `对事件进行投诉的任何人都应本着诚信的态度行事，并且有合理的理由相信所披露的信息表明违反了本政策。任何证明不成立的指控，以及被证明是恶意或有意为虚假的指控，都将被视为严重的社区违规行为，并且违反了本《行为准则》。`

**3. 原文**：`网址`

**建议**：`邮箱地址`

落点：

- [templates/pages/about/policies/coc/zh.html:57](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/coc/zh.html:57) — `如果您是不当行为的接受者，或目睹此类行为，请立即将其报告给行为规范委员会，网址为 coc@postgresql.org。如果不幸的是您希望对委员会的某个成员提出投诉，您可以改为单独联系任何其他委员会成员。`

**4. 原文**：`委员会将制作一份年度报告，总结上一年的每年第一季度末之前收到的投诉类型以及为解决这些投诉所采取的措施，并与社区分享该报告。`

**建议**：`委员会将在每年第一季度结束前编制一份年度报告，总结上一年收到的投诉类型和所采取的措施，并与社区分享该报告。`

落点：

- [templates/pages/about/policies/coc/zh.html:108](/Users/vonng/pgsty/pgweb/templates/pages/about/policies/coc/zh.html:108) — `委员会将制作一份年度报告，总结上一年的每年第一季度末之前收到的投诉类型以及为解决这些投诉所采取的措施，并与社区分享该报告。投诉和行为将被匿名化，以保护所有相关方的身份。`

**5. 原文**：`English → /about/policies/coc/（实际是中文）`

**建议**：`English → https://www.postgresql.org/about/policies/coc/；中文入口采用统一后的现行译文`

落点：

- [templates/base/cocpage.html:11](/Users/vonng/pgsty/pgweb/templates/base/cocpage.html:11) — `与正文统一方案一起确认；不要只改标签留下两份不同的中文准则。`

## D02 · Quorum commit 的译法与历史引语

**待确认 · 需单独确认译法和引语**

术语表将 quorum 译为“法定人数”。当前“仲裁提交／优选提交／优化提交”不统一，历史引语中还加入了英文没有的读写副本数解释。 依据：[quorum：法定人数](/Users/vonng/pgsty/pgdoc/tmp/ref/glossary.tsv:423)；[PostgreSQL 10 英文新闻资料包](https://www.postgresql.org/about/press/presskit10/)。

说明：建议采用“基于法定人数的提交”，首次出现保留 Quorum Commit。历史引语保留其余文字，只统一术语并去掉误导性插注。也可决定在新闻宣传材料中直接保留英文 Quorum Commit。

**1. 原文**：`仲裁提交`

**建议**：`基于法定人数的提交`

落点：

- [data/featurematrix_zh.yaml:661](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:661) — `name: 同步复制的仲裁提交`
- [data/featurematrix_zh.yaml:662](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:662) — `description: 使用 synchronous_standby_names 配置参数，可以设置同步复制以允许任意数量的备用服务器确认写入已提交，而不考虑其顺序。这也被称为“仲裁提交”。`

**2. 原文**：`优选提交`

**建议**：`基于法定人数的提交`

落点：

- [templates/pages/about/press/presskit10/cn.html:68](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:68) — `同步复制的优选提交（Quorum Commit） - 更加自信地分发数据`
- [templates/pages/about/press/presskit10/cn.html:74](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:74) — `"PostgreSQL 10.0 版本中的同步复制的优选提交（Quorum Commit，即通过读写副本数的优化来平衡读写性能）功能，从应用程序的角度给了我们更多的选择，以几乎零停机的代价来扩展我们基础设施的能力。这允许我们可以连续发布或是更新数据库基础设施而不必忍受长时间停机维`
- [templates/pages/about/press/presskit10/cn.html:167](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:167) — `"PostgreSQL 10.0 版本中的同步复制的优选提交（Quorum Commit，即通过读写副本数的优化来平衡读写性能）功能，从应用程序的角度给了我们更多的选择，以几乎零停机的代价来扩展我们基础设施的能力。这允许我们可以连续发布或是更新数据库基础设施而不必忍受长时间停机维`

**3. 原文**：`优化提交机制`

**建议**：`基于法定人数的提交机制`

落点：

- [templates/pages/about/press/presskit10/cn.html:70](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:70) — `PostgreSQL 10 引入了优化提交机制（Quorum Commit），这使得主数据库在接收到远程备库更新成功的确认信息时具备灵活性。数据库管理员现在可以指定当固定数量的备库已确认对更新进行写入后，数据才被认为是安全写入。`

**4. 原文**：`Quorum Commit，即通过读写副本数的优化来平衡读写性能`

**建议**：`Quorum Commit`

落点：

- [templates/pages/about/press/presskit10/cn.html:74](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:74) — `"PostgreSQL 10.0 版本中的同步复制的优选提交（Quorum Commit，即通过读写副本数的优化来平衡读写性能）功能，从应用程序的角度给了我们更多的选择，以几乎零停机的代价来扩展我们基础设施的能力。这允许我们可以连续发布或是更新数据库基础设施而不必忍受长时间停机维护的代价,"`
- [templates/pages/about/press/presskit10/cn.html:167](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:167) — `"PostgreSQL 10.0 版本中的同步复制的优选提交（Quorum Commit，即通过读写副本数的优化来平衡读写性能）功能，从应用程序的角度给了我们更多的选择，以几乎零停机的代价来扩展我们基础设施的能力。这允许我们可以连续发布或是更新数据库基础设施而不必忍受长时间停机维护的代价。"`

## D03 · 历史许可介绍中混用“版权”与“许可证”

**待确认 · 需单独确认历史文字**

9.0–9.3 和 10 的历史资料包把 license、proprietary、vendor lock-in 等译成了版权相关词。建议只修正这些概念，不更改历史许可条款与正式版权声明。 依据：[PostgreSQL 9.2 原始许可介绍](https://www.postgresql.org/about/press/presskit92/#license)。

说明：不进行“版权 → 许可证”的全局替换；copyright 的正确译文仍是版权。每个拟改片段和文件都列在下方。

**1. 原文**：`PostgreSQL 版权`

**建议**：`PostgreSQL 许可证`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:126](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:126) — `PostgreSQL 使用 PostgreSQL 版权，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权`
- [templates/pages/about/press/presskit91/zh_cn.html:137](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:137) — `PostgreSQL 使用 PostgreSQL 版权，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权`

**2. 原文**：`类似 BSD 的版权`

**建议**：`类似 BSD 的许可证`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:126](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:126) — `PostgreSQL 使用 PostgreSQL 版权，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 Postg`
- [templates/pages/about/press/presskit91/zh_cn.html:137](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:137) — `PostgreSQL 使用 PostgreSQL 版权，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 Postg`
- [templates/pages/about/press/presskit92/zh_CN.html:102](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:102) — `PostgreSQL 使用 PostgreSQL 版权声明，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 Postg`
- [templates/pages/about/press/presskit93/zh_CN.html:118](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:118) — `PostgreSQL 使用 PostgreSQL 版权声明，它是类似 BSD 的版权。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因`
- [templates/pages/about/press/presskit10/cn.html:109](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:109) — `PostgreSQL 使用 PostgreSQL 版权声明，它是类似 BSD 的版权。由于这个经 OSI 认证的版权不限制`

**3. 原文**：`OSI 认证的版权`

**建议**：`OSI 认证的许可证`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:126](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:126) — `QL 版权，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的`
- [templates/pages/about/press/presskit91/zh_cn.html:137](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:137) — `QL 版权，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的`
- [templates/pages/about/press/presskit92/zh_CN.html:102](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:102) — `版权声明，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的`
- [templates/pages/about/press/presskit93/zh_CN.html:118](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:118) — `about/licence">PostgreSQL 版权声明，它是类似 BSD 的版权。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的`
- [templates/pages/about/press/presskit10/cn.html:109](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:109) — `about/licence">PostgreSQL 版权声明，它是类似 BSD 的版权。由于这个经 OSI 认证的版权不限制`

**4. 原文**：`有版权的源代码`

**建议**：`获许可的源代码`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:126](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:126) — `PostgreSQL 使用 PostgreSQL 版权，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和`
- [templates/pages/about/press/presskit91/zh_cn.html:137](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:137) — `PostgreSQL 使用 PostgreSQL 版权，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和`
- [templates/pages/about/press/presskit92/zh_CN.html:102](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:102) — `PostgreSQL 使用 PostgreSQL 版权声明，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和`

**5. 原文**：`版权和授权的信息`

**建议**：`版权和许可信息`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:126](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:126) — `PostgreSQL 使用 PostgreSQL 版权，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用`
- [templates/pages/about/press/presskit91/zh_cn.html:137](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:137) — `PostgreSQL 使用 PostgreSQL 版权，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用`
- [templates/pages/about/press/presskit92/zh_CN.html:102](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:102) — `PostgreSQL 使用 PostgreSQL 版权声明，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用`

**6. 原文**：`有版权的应用程序`

**建议**：`专有应用程序`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:126](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:126) — `保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版`
- [templates/pages/about/press/presskit91/zh_cn.html:137](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:137) — `保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版`
- [templates/pages/about/press/presskit92/zh_CN.html:102](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:102) — `保留其版权和授权的信息即可。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版`
- [templates/pages/about/press/presskit93/zh_CN.html:118](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:118) — `，它是类似 BSD 的版权。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版`
- [templates/pages/about/press/presskit10/cn.html:110](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:110) — `PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版`

**7. 原文**：`我们的版权使得`

**建议**：`这一许可证使得`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:126](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:126) — `censes/postgresql">OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit91/zh_cn.html:137](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:137) — `censes/postgresql">OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit92/zh_CN.html:102](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:102) — `censes/postgresql">OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit93/zh_CN.html:118](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:118) — `censes/postgresql">OSI 认证的版权不限制 PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit10/cn.html:110](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:110) — `PostgreSQL 在商业环境和有版权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`

**8. 原文**：`嵌入软件的版权锁`

**建议**：`供应商锁定`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:126](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:126) — `权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit91/zh_cn.html:137](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:137) — `权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit92/zh_CN.html:102](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:102) — `权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit93/zh_CN.html:118](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:118) — `权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit10/cn.html:110](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:110) — `权的应用程序中使用，因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`

**9. 原文**：`版权条款的改变`

**建议**：`许可条款的改变`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:126](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:126) — `因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit91/zh_cn.html:137](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:137) — `因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit92/zh_CN.html:102](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:102) — `因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit93/zh_CN.html:118](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:118) — `因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`
- [templates/pages/about/press/presskit10/cn.html:110](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:110) — `因此被公认为是非常有灵活性和对商业应用是友好的。加上有多个公司的支持和源代码归属公共所有，我们的版权使得 PostgreSQL 在那些希望在自己的产品里嵌入数据库的厂商中很流行，因为他们不用担心费用、嵌入软件的版权锁以及版权条款的改变。`

**10. 原文**：`版权声明`

**建议**：`许可证`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:124](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:124) — `版权声明`
- [templates/pages/about/press/presskit91/zh_cn.html:135](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:135) — `版权声明`
- [templates/pages/about/press/presskit93/zh_CN.html:116](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:116) — `版权声明`
- [templates/pages/about/press/presskit10/cn.html:107](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:107) — `版权声明`

**11. 原文**：`版权声明`

**建议**：`许可证`

落点：

- [templates/pages/about/press/presskit90/zh_cn.html:14](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit90/zh_cn.html:14) — `版权声明`
- [templates/pages/about/press/presskit91/zh_cn.html:15](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit91/zh_cn.html:15) — `版权声明`
- [templates/pages/about/press/presskit92/zh_CN.html:14](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:14) — `版权声明`
- [templates/pages/about/press/presskit93/zh_CN.html:14](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:14) — `版权声明`
- [templates/pages/about/press/presskit10/cn.html:32](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:32) — `版权声明`

**12. 原文**：`PostgreSQL 版权声明`

**建议**：`PostgreSQL 许可证`

落点：

- [templates/pages/about/press/presskit92/zh_CN.html:102](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit92/zh_CN.html:102) — `PostgreSQL 使用 PostgreSQL 版权声明，它是类似 BSD 的版权，只要求对有版权的源代码保留其版权和授权的信息即可。由于这个经 OSI 认`
- [templates/pages/about/press/presskit93/zh_CN.html:118](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit93/zh_CN.html:118) — `PostgreSQL 使用 PostgreSQL 版权声明，它是类似 BSD 的版权。由于这个经 OSI 认证的版权不限制 PostgreSQL 在商`
- [templates/pages/about/press/presskit10/cn.html:109](/Users/vonng/pgsty/pgweb/templates/pages/about/press/presskit10/cn.html:109) — `PostgreSQL 使用 PostgreSQL 版权声明，它是类似 BSD 的版权。由于这个经 OSI 认证的版权不限制`

## D04 · 中文版权起始年份不一致

**待确认 · 需确认事实**

本站介绍写自 2026 年起，页脚写 2025。起始年需要根据实际贡献历史确认，不能仅凭文字审校选择。

说明：本条只有事实核对，不提供未经确认的替换年份。

**1. 原文**：`中文译文著作权……自 2026 年起`

**建议**：`待确认实际起始年份后，与页脚统一。`

落点：

- [templates/pages/about/pgcenter.html:23](/Users/vonng/pgsty/pgweb/templates/pages/about/pgcenter.html:23)

**2. 原文**：`中文版权起始年 2025`

**建议**：`待确认实际起始年份后，与本站介绍统一。`

落点：

- [templates/base/footer.html:15](/Users/vonng/pgsty/pgweb/templates/base/footer.html:15)

## D05 · PL/Perl 验证器条目写成 PL/pgSQL

**待确认 · 待核实上游事实**

标题是 pl/perl，中文和英文说明却都写 pl/pgsql，明显存在内部不一致。它继承自英文特性矩阵，需对照 PostgreSQL 8.1 的原始发行记录后再确定。 依据：[英文原始条目](/Users/vonng/pgsty/pgweb/data/featurematrix.yaml:1659)。

说明：候选译文列在下方；这条不随一般术语替换批次应用。

**1. 原文**：`pl/pgsql 代码的编译时验证`

**建议**：`PL/Perl 代码的编译时验证`

落点：

- [data/featurematrix_zh.yaml:1090](/Users/vonng/pgsty/pgweb/data/featurematrix_zh.yaml:1090) — `description: pl/pgsql 代码的编译时验证`
