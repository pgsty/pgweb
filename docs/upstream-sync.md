# 上游变更同步记录

## 2026-10-03：发布信息与 RPM 下载页

本轮审查范围为 `postgres/pgweb` 的 `e5c079de..f6b76f3c`，共 10 个提交。
此前本地 `6f58f81d` 已集中吸收至 `e5c079de`。本项目采用保留中文化的内容移植，
不能仅凭 Git 祖先关系判断哪些变更尚未同步。

| 上游提交 | 本地处理 |
| --- | --- |
| `98d0205a` | 补充 19 Beta4 发布 YAML，将路线图调整为 2026 年 10 月。新闻 ID `3386` 已在本地核实为中文发布公告。 |
| `814150dc` | 修复 Amazon Linux 2023 的仓库包地址与 `dnf` 命令。 |
| `05ca93dd` | PostgreSQL 版本按数字倒序展示。 |
| `6e07ee52` | 吸收发行版、系统版本、架构三级选择，以及版本解析改进；保留本地对无受支持版本架构的过滤。未采用小版本锁定选项，原因见下文。 |
| `cd5dfa0b` | 采集器兼容历史小版本目录，并修复异常响应中的未定义变量。 |
| `6043512e` | 下载页移除 Oracle Linux 列举，保持 PGDG 的支持口径。 |
| `1ecb4e50` | 不复制容易过期的 RHEL 小版本示例，改为说明仓库当前的匹配机制。 |
| `99bec88f` | 相关外链使用 `_blank` 与 `noopener`。 |
| `f6b76f3c` | 安装命令通过 `textContent` 写入，继续兼容本站代码高亮与两种复制方式。 |
| `9b854858` | 修复社区认证示例传入用户名字的笔误：`['f'][0]` 改为 `data['f'][0]`。 |

### 小版本锁定的取舍

PGDG 在 [2026-09-28 的公告](https://yum.postgresql.org/news/repo-rpms-follow-os-minor-version/)
中说明，RHEL / Rocky Linux / AlmaLinux 9、10 的仓库配置包自 `42.0-69` 起自动跟随系统小版本。
历史 `EL-X.Y` 链接现在也提供同一个包，并不能实现小版本锁定。因此页面只提供大版本入口，
不展示旧的小版本专用入口；需要固定系统版本的用户可查阅公告中的操作说明。

RHEL 7 的 PostgreSQL 14/15 安装入口予以保留，版本标签明确为“7（RHEL）”，避免误示 Rocky Linux 或 AlmaLinux 存在第 7 版。
PGDG 的[维护公告](https://yum.postgresql.org/news/rhel7-end-of-life/)仍保留 PostgreSQL 本身的更新，不能仅凭操作系统较旧就将这些包判为不可用。

### 数据与验证

- 本地 `data/yum.json` 从[上游当前下载脚本](https://www.postgresql.org/download/js/yum.js)提取并校验，包含 Amazon Linux 2023、Fedora 43/44。该运行数据按现有约定不提交 Git；部署时需另外更新。
- 发布 YAML 仍走[现有显式发布流程](../pgweb/release/README.md)，不启用迁移时自动发布或发送公告邮件。生产发布前应独立核验目标库的新闻 ID。
- 下载交互回归：`node --test tools/ftp/test_yum.mjs`，覆盖 Amazon Linux、RHEL7、EL8 模块禁用、EL9 ARM64、EL10、Fedora、架构过滤、选择重置和纯文本输出。
- Django 回归：`manage.py test pgweb.release.test_release pgweb.core.test_home_seo --noinput`；另核验本地首页、Beta 页面及路线图的实际渲染。

本轮本地验收：8 项下载交互测试、11 项 Django 测试、系统检查、迁移一致性检查和改动 Python 文件的风格检查通过。
首页、Beta 页面、路线图及 Red Hat 下载页均返回 200；浏览器核验了桌面与窄屏表单、代码高亮、普通复制与去除 sudo 的复制。
发布处理先演练回滚，再应用到本地 `pgweb` 库：PG19 发布日期改为 `2026-09-24`，置顶公告由 `3365` 改为 `3386`，未改变新闻正文或邮件队列。
生产环境未在本轮更新。
