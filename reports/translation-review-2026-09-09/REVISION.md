# 中文翻译与 SEO 修订记录

已按确认的审阅清单完成 **94 项修订**，涉及 **57 个产品文件和 3 个测试文件**。仅 D04（中文版权起始年份）待确认事实。数据库未查询或修改，未提交、推送或部署。

原始审阅提案保留在 [Review 总览](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/REVIEW.md)；本轮从当前工作区开始追加修改，保留已有手动修订。下面的差异仅包含本轮修改，不混入此前未提交的工作。

- [本轮完整差异](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/revision.patch)
- [逐项状态、文件前后哈希和验证结果](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/revision.json)
- [89 个中文页面的标题与摘要渲染记录](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/rendered-metadata-after.json)
- [动态视图标题验证记录](/Users/vonng/pgsty/pgweb/reports/translation-review-2026-09-09/dynamic-titles-after.json)

## 落实范围

术语按指定 glossary.tsv 在清单位置校准；正文仅落实已确认的误译、病句与事实方向修正。中文元数据标题移除品牌后的中文冒号，页面标题与 OG 分享标题使用同一最终值，并去掉扩展目录、生态文档首页的重复名称。账户、组织及提交表单使用中文展示标签和提示，模型字段、数据库记录和业务流程保持原样。

中文行为准则旧入口复用已经校对的现行正文。Quorum commit 与历史许可介绍按确认的清单修订。PL/Perl 验证器条目经[官方 8.1 文档](https://www.postgresql.org/docs/8.1/plperl-trusted.html)核对后修正。

## 验证结果

- 69 项相关测试通过；Django 系统检查、git diff --check 通过。
- 385 份 HTML 模板编译通过；89 个中文元数据页面的 HTML 标题、OG 标题与摘要一致。
- 额外通过 9 次动态视图渲染，覆盖中英文扩展首页、生态文档首页和章节、特性、专业服务与首页；6 个账户页标题、51 个表单标签／帮助文字均已核对。
- 217 个其他语言页面的元数据、420 个特性的英文键名及 26 个分组键保持原样。
- 现有链接、模板插值和代码示例已比对；按清单修正行为准则英文入口，并在权限解释中补充 CREATE、PUBLIC 标识。
- 离线检查显式禁止数据库连接；浏览器实看首页、行为准则页面，标题层级与排版正常。页面采用本地 HTML 样本，不代表生产部署验证。

## 保留待确认

**D04：中文版权起始年份。** 页脚写 2025，本站介绍写 2026。代码历史只说明两处文字何时加入，不能证明译文的实际起始年，因此保留现状。

## 逐项落实

| 编号 | 项目 | 结果 |
| --- | --- | --- |
| T01 | Full-Text Search：全文检索 | 已修订 |
| T02 | Failover：故障切换 | 已修订 |
| T03 | B-tree：B-树 | 已修订 |
| T04 | Exclusion Constraints：排他约束 | 已修订 |
| T05 | Operator：操作符 | 已修订 |
| T06 | Most Common Values / MCV：高频值 | 已修订 |
| T07 | HOT：堆内元组 | 已修订 |
| T08 | Merge Join：归并连接 | 已修订 |
| T09 | Partition pruning：分区剪枝 | 已修订 |
| T10 | Identity column：标识列 | 已修订 |
| T11 | WAL 与 full-page write：预写式日志、整页写入 | 已修订 |
| T12 | Visibility map：可见性映射 | 已修订 |
| T13 | Autovacuum：自动清理 | 已修订 |
| T14 | Serializable snapshot isolation：可串行化快照隔离 | 已修订 |
| T15 | 逻辑复制说明中的 publication / schema：发布／模式 | 已修订 |
| T16 | 复制语境：主库、备库、从库 | 已修订 |
| T17 | 数据库集簇与高可用集群分开使用 | 已修订 |
| T18 | 规划器 Cost：代价 | 已修订 |
| T19 | 后端概述：词元与聚合 | 已修订 |
| T20 | 可伸缩性与可扩展性按语义区分 | 已修订 |
| T21 | Trusted extension：受信任的扩展 | 已修订 |
| T22 | 最近邻索引用词 | 已修订 |
| T23 | 生成列的复合名称 | 已修订 |
| T24 | Index-only scan：仅索引扫描 | 已修订 |
| T25 | Foreign key：外键 | 已修订 |
| T26 | 事务 ID 回卷 | 已修订 |
| C01 | 简介页：数据与工作负载的搭配 | 已修订 |
| C02 | 媒体 FAQ：四处明确的直译或歧义 | 已修订 |
| C03 | Linux 下载页：发行版“快照”一个版本 | 已修订 |
| C04 | 专业服务地区页：注册地与服务地区 | 已修订 |
| C05 | 复制槽的 WAL 限制是保留量 | 已修订 |
| C06 | Windows Port：移植版 | 已修订 |
| C07 | GIN：广义倒排索引 | 已修订 |
| C08 | 分区键更新：修正主宾关系 | 已修订 |
| C09 | COPY：输入输出方向 | 已修订 |
| C10 | 受信任扩展：纠正函数与扩展混淆 | 已修订 |
| C11 | 可见性映射：纠正描述方向 | 已修订 |
| C12 | Unicode literal：字符串字面量 | 已修订 |
| C13 | auto_explain：模块名拼写 | 已修订 |
| C14 | PostgreSQL 12：空间优化的方向 | 已修订 |
| C15 | PostgreSQL 11：默认分区条件 | 已修订 |
| C16 | PostgreSQL 11：INCLUDE 与仅索引扫描 | 已修订 |
| C17 | PostgreSQL 11：连接与 JIT 表述 | 已修订 |
| C18 | PostgreSQL 14：拆开 postgres_fdw 的两项能力 | 已修订 |
| C19 | PostgreSQL 15：默认权限变化 | 已修订 |
| C20 | PostgreSQL 18：值不限定为数值 | 已修订 |
| C21 | PostgreSQL 13：受信任扩展段的病句与引号 | 已修订 |
| C22 | PostgreSQL 9.1：Heroku 与 salesforce.com 的归属关系 | 已修订 |
| C23 | PostgreSQL 9.1：三处明确的误译／错字 | 已修订 |
| C24 | PostgreSQL 10：商业伙伴错字 | 已修订 |
| C25 | PostgreSQL 9.0：RADIUS 认证 | 已修订 |
| C26 | 服务收录政策：word 不应换算为“字” | 已修订 |
| C27 | 扩展属性 relocatable：说明可以迁移什么 | 已修订 |
| C28 | 关于本站：上游入口说明 | 已修订 |
| C29 | 提交预览：说明撤回后仍可修改 | 已修订 |
| C30 | 账户邮箱提示：解释实际影响 | 已修订 |
| C31 | UNLOGGED 与导入表定义的表述 | 已修订 |
| C32 | 资金小组章程：附议主语与辩论期限 | 已修订 |
| C33 | 网站团队与网络团队 | 已修订 |
| S01 | 标题前缀：PostgreSQL：内容 → PostgreSQL 内容 | 已修订 |
| S02 | 媒体页面与新闻列表分清用途 | 已修订 |
| S03 | 政策页标题增加用途区分 | 已修订 |
| S04 | 手册标题的完整格式 | 已修订 |
| S05 | 避免扩展首页和生态文档首页重复名称 | 已修订 |
| S06 | 动态页 HTML 标题与分享标题统一 | 已修订 |
| S07 | 六个账户页面缺少页面名称 | 已修订 |
| S08 | 页面主标题层级 | 已修订 |
| S09 | 首页视觉标题是否同步去掉冒号 | 已修订 |
| S10.01 | 页面摘要：/about/contact/ | 已修订 |
| S10.02 | 页面摘要：/about/press/ | 已修订 |
| S10.03 | 页面摘要：/about/press/faq/ | 已修订 |
| S10.04 | 页面摘要：/about/governance/ | 已修订 |
| S10.05 | 页面摘要：/about/governance/contributors/ | 已修订 |
| S10.06 | 页面摘要：/about/governance/sysadmin/ | 已修订 |
| S10.07 | 页面摘要：/about/policies/project-name/ | 已修订 |
| S10.08 | 页面摘要：/about/policies/news-and-events/ | 已修订 |
| S10.09 | 页面摘要：/about/policies/services-and-hosting/ | 已修订 |
| S10.10 | 页面摘要：/about/policies/archives/ | 已修订 |
| S10.11 | 页面摘要：/about/press/presskit12/zh/ | 已修订 |
| S10.12 | 页面摘要：/about/press/presskit13/zh/ | 已修订 |
| S10.13 | 页面摘要：/about/press/presskit14/zh/ | 已修订 |
| S10.14 | 首页摘要：补全句子与并列结构 | 已修订 |
| U01 | 搜索界面的英文提示 | 已修订 |
| U02 | 公共入口的少量补译 | 已修订 |
| U03 | 政策页“查看修订历史” | 已修订 |
| U04 | 账户表单字段与帮助文字 | 已修订 |
| U05 | 账户校验消息补译 | 已修订 |
| U06 | 注册及授权页面补译 | 已修订 |
| U07 | 组织资料表单补译 | 已修订 |
| U08 | 新闻与活动提交表单补译 | 已修订 |
| D01 | 两份中文行为准则的处理方式 | 已修订 |
| D02 | Quorum commit 的译法与历史引语 | 已修订 |
| D03 | 历史许可介绍中混用“版权”与“许可证” | 已修订 |
| D04 | 中文版权起始年份不一致 | 待确认事实 |
| D05 | PL/Perl 验证器条目写成 PL/pgSQL | 已修订 |

实现细节：S01 的前缀修改与 S02–S04 的具体标题合并；T12 与 C11 合并。U07 同一表单额外补齐“添加邮箱地址”“添加管理员”两处隐式标签。S05 共用逻辑同时修正中英文首页的重复名称。

本轮修改前的文件副本保存在 /tmp/pgweb-copy-revision-20260909-074553/before。

## 提交前确认

工作区的 69 项相关测试再次通过；将暂存内容导出为独立目录后，19 项随本次提交提供的 SEO 与标题测试通过，系统检查通过。

本次按已修订文件整体提交，包含这些文件中此前未提交的内容，并补齐 13 个必要的 SEO、静态页面与文档渲染依赖文件（含已有模型和迁移定义、库版本要求及配套搜索模板）。未运行迁移，未操作数据库。其余未提交文件保留在工作区。原始修订记录中的提交状态是当时的快照。
