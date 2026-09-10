<div align="center">

<a href="https://pgsql.cc/">
  <img src="media/img/misc/Postgresql_elephant.svg" alt="PostgreSQL 大象标识" width="104" height="108">
</a>

# PostgreSQL 中文网

**pgsql.cc · 用中文探索 PostgreSQL**

中文官网内容 · 多版本手册 · 定义检索 · 扩展目录

**简体中文** · [English](README.en.md)

[![访问网站](https://img.shields.io/badge/访问网站-pgsql.cc-336791?style=flat-square)](https://pgsql.cc/) [![中文手册](https://img.shields.io/badge/中文手册-PostgreSQL%2010–20-4169E1?style=flat-square)](https://pgsql.cc/docs/) [![Django](https://img.shields.io/badge/Django-5.2-0C4B33?style=flat-square&logo=django&logoColor=white)](requirements.txt) [![许可证](https://img.shields.io/badge/许可证-PostgreSQL-2F855A?style=flat-square)](https://www.postgresql.org/about/licence/)

[**进入网站 →**](https://pgsql.cc/) · [阅读手册](https://pgsql.cc/docs/) · [搜索文档](https://pgsql.cc/search/) · [浏览扩展](https://pgsql.cc/ext/)

</div>

---

**[pgsql.cc](https://pgsql.cc/) 是 PostgreSQL 的中文社区网站。** 本项目基于 [postgres/pgweb](https://github.com/postgres/pgweb)，将 [postgresql.org](https://www.postgresql.org/) 的网站内容与 PostgreSQL 手册带给中文读者，并提供适合中文使用习惯的文档检索、扩展目录和阅读界面。

项目由[冯若航](https://vonng.com/)与 [Pigsty](https://pigsty.cc/) 项目组发起并维护，作为独立社区项目运行。内容来源、翻译与署名说明见[关于 pgsql.cc](https://pgsql.cc/about/pgsql/)。

## 在这里找到什么

<table>
<tr>
<td width="50%" valign="top">
<h3><img src="docs/assets/readme/manuals.svg" width="28" height="28" alt=""> 多版本中文手册</h3>
<p>PostgreSQL 10–20 中文手册，涵盖历史版本、正式版本、测试版和开发快照；支持在线阅读与 A4 / US Letter PDF 下载。</p>
<a href="https://pgsql.cc/docs/">打开手册 →</a>
</td>
<td width="50%" valign="top">
<h3><img src="docs/assets/readme/search.svg" width="28" height="28" alt=""> 直达定义的检索</h3>
<p>按版本查找配置参数、SQL、函数、类型、错误码与工具命令。支持中文检索、定义预览和锚点定位，宽屏可用 <code>/</code> 或 <code>⌘K</code> 唤起搜索。</p>
<a href="https://pgsql.cc/search/">搜索文档 →</a>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<h3><img src="docs/assets/readme/extensions.svg" width="28" height="28" alt=""> PostgreSQL 扩展目录</h3>
<p>基于 PGEXT 元数据展示扩展概览，按功能分类、许可证、编程语言与仓库来源筛选，并链接到各扩展的文档与项目主页。</p>
<a href="https://pgsql.cc/ext/">发现扩展 →</a>
</td>
<td width="50%" valign="top">
<h3><img src="docs/assets/readme/community.svg" width="28" height="28" alt=""> 中文社区与资源</h3>
<p>项目介绍、新闻、活动、发行说明、下载指引与社区资源，沿用上游信息结构，保留内容来源，并补充面向中文读者的说明。</p>
<a href="https://pgsql.cc/">浏览社区首页 →</a>
</td>
</tr>
</table>

试试搜索 `work_mem`、`pg18: pg_stat_activity`、`23505` 或 `ex: postgis`。手册实体检索和扩展检索由本站 PostgreSQL 数据库提供；新闻及普通页面使用单独的站内全文索引。

## 项目分工与内容来源

| 项目 | 职责 |
| :--- | :--- |
| **[pgsty/pgweb](https://github.com/pgsty/pgweb)** · 本仓库 | 中文网站的 Django 应用、页面模板、样式、搜索与内容导入工具 |
| **[pgsty/pgdoc](https://github.com/pgsty/pgdoc)** | PostgreSQL 多版本中文 SGML 源文档、译风与术语规则，以及 HTML / PDF 构建 |
| **[pgsty/pgext](https://github.com/pgsty/pgext)** | 扩展目录的权威元数据；本站同步 `pgext.universe`，提供目录展示与检索 |
| **[postgres/pgweb](https://github.com/postgres/pgweb)** | postgresql.org 的上游网站代码；本项目在其基础上维护中文化改动 |

网站内容以对应上游页面为依据。同步更新时保留已有中文译文、技术标识符、代码示例和来源链接；手册由 `pgdoc` 构建后导入，再更新本站检索索引。Patroni、PgBouncer、pgBackRest 等[第三方文档](https://pgsql.cc/docs/third-party/)以精选外链提供，正文由各自的文档站点维护。

## 技术与目录

| 层次 | 实现 |
| :--- | :--- |
| **应用** | Python 3、Django 5.2、PostgreSQL |
| **页面** | Django 模板、Bootstrap、项目 CSS / JavaScript、Font Awesome 与 SVG 图标 |
| **文档检索** | PostgreSQL 全文检索与 `pg_trgm`、jieba 中文分词、按实体提取的定义索引 |
| **内容维护** | 数据库迁移、手册导入、扩展目录同步、新闻与 RSS 工具 |

```text
pgweb/
├── pgweb/       # Django 应用：手册、搜索、扩展、新闻、活动等
├── templates/   # 页面与组件；普通内容页位于 templates/pages/
├── media/       # CSS、JavaScript、图片和图标，对应 /media/
├── data/        # 纳入版本管理的页面元数据等配置
├── tools/       # 内容导入、同步、搜索爬虫与部署工具
├── sql/         # 数据库辅助函数与索引定义
└── docs/        # 开发、内容维护和部署说明
```

PDF 等业务文件放在本地 `static/`，通过 `/files/` 提供；它们和本地配置、缓存、临时报告一样由 Git 忽略，按各自流程准备。

## 本地开发

先准备 Python 3、PostgreSQL，并按[开发环境指南](docs/dev_install.rst)配置数据库和依赖：

```bash
git clone https://github.com/pgsty/pgweb.git
cd pgweb
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

在 **`pgweb/settings_local.py`** 中设置本地数据库、`SECRET_KEY`、`DEBUG`、`SITE_ROOT` 和本地 Cookie 选项。接着按指南完成数据库迁移、辅助 SQL 与初始数据准备，再启动应用：

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

打开 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)。手册、扩展、新闻和搜索结果依赖相应数据的导入与索引；所需流程见下表。

## 维护指南

| 要做的事 | 文档 |
| :--- | :--- |
| 了解应用与前端结构 | [架构概览](docs/overview.rst) · [Django](docs/django.rst) · [前端](docs/frontend.rst) |
| 翻译、校对页面与维护 SEO | [中文内容与 SEO](docs/content-maintenance.md) |
| 导入中文手册和 PDF | [手册导入与发布](docs/manual-import.md) |
| 建立与更新定义索引 | [文档检索](docs/document-search.md) |
| 更新扩展目录 | [扩展目录与同步](docs/extension-catalog.md) |
| 整理生态组件的外部文档 | [第三方文档外链](docs/third-party-docs.md) |
| 配置域名与部署网站 | [pgsql.cc 部署说明](docs/domain-migration.md) |

## 参与贡献

欢迎通过 [Issue](https://github.com/pgsty/pgweb/issues) 反馈错译、漏译、失效链接或功能问题，也欢迎提交 [Pull Request](https://github.com/pgsty/pgweb/pulls)。请附上页面链接、复现步骤或对应上游原文，便于核对。

普通内容页主要位于 `templates/pages/`；手册正文的翻译修改请提交到 [pgdoc](https://github.com/pgsty/pgdoc)，扩展元数据请在 [PGEXT](https://github.com/pgsty/pgext) 源头维护。涉及上游网站的通用改进，也欢迎在 [pgsql-www 邮件列表](https://www.postgresql.org/list/pgsql-www/)参与讨论。

## 致谢与许可

感谢 PostgreSQL 全球开发组、上游 `pgweb` 维护者，以及所有参与中文翻译、校对和反馈的贡献者。网站代码沿用 [PostgreSQL 许可证](https://www.postgresql.org/about/licence/)，原有版权与许可声明予以保留。PostgreSQL 大象 SVG 复用本仓库已有素材；第三方名称、标识与内容归各自权利人所有。

<details>
<summary>上游组件的许可证</summary>

| 组件 | 许可证 |
| :--- | :--- |
| Django | [BSD](https://github.com/django/django/blob/main/LICENSE) |
| Bootstrap | [MIT](https://github.com/twbs/bootstrap/blob/main/LICENSE) |
| Font Awesome | 代码：[MIT](https://opensource.org/license/mit)；图标：[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)；字体：[SIL OFL 1.1](https://openfontlicense.org/)；见[许可说明](https://fontawesome.com/license) |
| normalize.css | [MIT](https://github.com/necolas/normalize.css/blob/master/LICENSE.md) |

</details>

---

<div align="center">

**[pgsql.cc](https://pgsql.cc/) · [中文手册](https://pgsql.cc/docs/) · [Pigsty](https://pigsty.cc/)**

</div>
