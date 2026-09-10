<div align="center">

<a href="https://pgsql.cc/">
  <img src="media/img/misc/Postgresql_elephant.svg" alt="PostgreSQL elephant logo" width="104" height="108">
</a>

# PostgreSQL Chinese Community

**pgsql.cc · Explore PostgreSQL in Chinese**

Localized website · Versioned manuals · Definition search · Extension catalog

[简体中文](README.md) · **English**

[![Website](https://img.shields.io/badge/Website-pgsql.cc-336791?style=flat-square)](https://pgsql.cc/) [![Chinese manuals](https://img.shields.io/badge/Chinese_manuals-PostgreSQL%2010–20-4169E1?style=flat-square)](https://pgsql.cc/docs/) [![Django](https://img.shields.io/badge/Django-5.2-0C4B33?style=flat-square&logo=django&logoColor=white)](requirements.txt) [![License](https://img.shields.io/badge/License-PostgreSQL-2F855A?style=flat-square)](https://www.postgresql.org/about/licence/)

[**Visit the website →**](https://pgsql.cc/) · [Read the manuals](https://pgsql.cc/docs/) · [Search documentation](https://pgsql.cc/search/) · [Browse extensions](https://pgsql.cc/ext/)

</div>

---

**[pgsql.cc](https://pgsql.cc/) is a Chinese community website for PostgreSQL.** Built on [postgres/pgweb](https://github.com/postgres/pgweb), it brings the content of [postgresql.org](https://www.postgresql.org/) and the PostgreSQL manuals to Chinese readers, with documentation search, an extension catalog, and a reading interface designed for Chinese content.

Founded and maintained by [Ruohang Feng](https://vonng.com/) and the [Pigsty](https://pigsty.cc/) team, the site operates as an independent community project with no organizational affiliation to the PostgreSQL Global Development Group (PGDG). See [About pgsql.cc](https://pgsql.cc/about/pgsql/) for content sources, translation details, and attribution.

## What you can find

<table>
<tr>
<td width="50%" valign="top">
<h3><img src="docs/assets/readme/manuals.svg" width="28" height="28" alt=""> Versioned Chinese manuals</h3>
<p>Chinese manuals for PostgreSQL 10–20, spanning archived releases, stable releases, beta versions, and development snapshots. Read online or download A4 / US Letter PDFs.</p>
<a href="https://pgsql.cc/docs/">Open the manuals →</a>
</td>
<td width="50%" valign="top">
<h3><img src="docs/assets/readme/search.svg" width="28" height="28" alt=""> Search that finds definitions</h3>
<p>Look up configuration parameters, SQL, functions, types, error codes, and tools by version. Search Chinese text, preview definitions, and jump to anchors; use <code>/</code> or <code>⌘K</code> on wider screens.</p>
<a href="https://pgsql.cc/search/">Search documentation →</a>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<h3><img src="docs/assets/readme/extensions.svg" width="28" height="28" alt=""> PostgreSQL extension catalog</h3>
<p>Explore extension metadata from PGEXT, filter by category, license, programming language, or repository, and follow links to each extension's documentation and project.</p>
<a href="https://pgsql.cc/ext/">Discover extensions →</a>
</td>
<td width="50%" valign="top">
<h3><img src="docs/assets/readme/community.svg" width="28" height="28" alt=""> Community and resources</h3>
<p>Project information, news, events, release notes, download guides, and community resources follow the upstream information structure, retain source attribution, and add context for Chinese readers.</p>
<a href="https://pgsql.cc/">Visit the community homepage →</a>
</td>
</tr>
</table>

Try `work_mem`, `pg18: pg_stat_activity`, `23505`, or `ex: postgis`. Manual definitions and extensions are searched in the site's PostgreSQL database; news and general pages use a separate site-wide full-text index.

## Projects and content sources

| Project | Responsibility |
| :--- | :--- |
| **[pgsty/pgweb](https://github.com/pgsty/pgweb)** · this repository | The Chinese website's Django applications, templates, styles, search, and content import tools |
| **[pgsty/pgdoc](https://github.com/pgsty/pgdoc)** | Versioned Chinese SGML manuals, translation style and terminology rules, and HTML / PDF builds |
| **[pgsty/pgext](https://github.com/pgsty/pgext)** | Authoritative extension metadata; this website synchronizes `pgext.universe` for catalog browsing and search |
| **[postgres/pgweb](https://github.com/postgres/pgweb)** | The upstream code for postgresql.org, on which this project's Chinese localization is based |

Website content follows the corresponding upstream pages. Updates preserve existing translations, technical identifiers, code examples, and source links. Manuals are built in `pgdoc`, imported here, and then indexed for search. [Third-party documentation](https://pgsql.cc/docs/third-party/) for projects such as Patroni, PgBouncer, and pgBackRest is provided through curated external links, with the content maintained on the respective documentation sites.

## Technology and layout

| Layer | Implementation |
| :--- | :--- |
| **Application** | Python 3, Django 5.2, PostgreSQL |
| **Interface** | Django templates, Bootstrap, project CSS / JavaScript, Font Awesome, and SVG icons |
| **Documentation search** | PostgreSQL full-text search and `pg_trgm`, jieba Chinese segmentation, and extracted definition entries |
| **Content maintenance** | Database migrations, manual imports, extension catalog synchronization, news and RSS tools |

```text
pgweb/
├── pgweb/       # Django apps: manuals, search, extensions, news, events, etc.
├── templates/   # Pages and components; general content in templates/pages/
├── media/       # CSS, JavaScript, images, and icons, served at /media/
├── data/        # Version-controlled configuration, including page metadata
├── tools/       # Content imports, synchronization, crawlers, and deployment
├── sql/         # Database helper functions and index definitions
└── docs/        # Development, content maintenance, and deployment guides
```

Files such as PDFs live in the local `static/` directory and are served at `/files/`. Like local configuration, caches, and temporary reports, these files are excluded from Git and prepared through their respective workflows.

## Local development

Prepare Python 3 and PostgreSQL, then follow the [development installation guide](docs/dev_install.rst) to configure the database and dependencies:

```bash
git clone https://github.com/pgsty/pgweb.git
cd pgweb
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Set the local database, `SECRET_KEY`, `DEBUG`, `SITE_ROOT`, and local cookie options in **`pgweb/settings_local.py`**. Complete the migrations, helper SQL, and initial data setup described in the guide, then start the application:

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/). Manuals, extensions, news, and search results require their respective data imports and indexes; the guides below describe those workflows.

## Maintenance guides

| Task | Documentation |
| :--- | :--- |
| Understand the application and frontend | [Architecture](docs/overview.rst) · [Django](docs/django.rst) · [Frontend](docs/frontend.rst) |
| Translate and review pages, maintain SEO | [Chinese content and SEO](docs/content-maintenance.md) |
| Import Chinese manuals and PDFs | [Manual import and publication](docs/manual-import.md) |
| Build and update the definition index | [Documentation search](docs/document-search.md) |
| Update the extension catalog | [Extension catalog and synchronization](docs/extension-catalog.md) |
| Curate external ecosystem documentation | [Third-party documentation links](docs/third-party-docs.md) |
| Configure the domain and deploy the website | [pgsql.cc deployment](docs/domain-migration.md) |

The maintenance guides for the Chinese site are primarily written in Chinese; the inherited architecture and development guides are in English.

## Contributing

Report translation errors, omissions, broken links, or functional issues through [Issues](https://github.com/pgsty/pgweb/issues), or submit a [Pull Request](https://github.com/pgsty/pgweb/pulls). Include the page URL, reproduction steps, or corresponding upstream text so the change can be checked.

General content pages mostly live in `templates/pages/`. Submit manual translation changes to [pgdoc](https://github.com/pgsty/pgdoc), and maintain extension metadata at its [PGEXT](https://github.com/pgsty/pgext) source. For improvements applicable to the upstream website, join the discussion on the [pgsql-www mailing list](https://www.postgresql.org/list/pgsql-www/).

## Acknowledgments and license

Thanks to the PostgreSQL Global Development Group, upstream `pgweb` maintainers, and everyone contributing Chinese translations, reviews, and feedback. The website code retains the [PostgreSQL License](https://www.postgresql.org/about/licence/) and its existing copyright and license notices. The PostgreSQL elephant SVG is reused from the repository's existing assets; third-party names, marks, and content belong to their respective owners.

<details>
<summary>Licenses of upstream components</summary>

| Component | License |
| :--- | :--- |
| Django | [BSD](https://github.com/django/django/blob/main/LICENSE) |
| Bootstrap | [MIT](https://github.com/twbs/bootstrap/blob/main/LICENSE) |
| Font Awesome | Code: [MIT](https://opensource.org/license/mit); icons: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); fonts: [SIL OFL 1.1](https://openfontlicense.org/); see the [licensing details](https://fontawesome.com/license) |
| normalize.css | [MIT](https://github.com/necolas/normalize.css/blob/master/LICENSE.md) |

</details>

---

<div align="center">

**[pgsql.cc](https://pgsql.cc/) · [Chinese manuals](https://pgsql.cc/docs/) · [Pigsty](https://pigsty.cc/)**

</div>
