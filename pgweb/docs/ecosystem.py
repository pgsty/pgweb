"""Read-only, versioned ecosystem manuals backed by doc_project/revision/page."""

import posixpath
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from django.conf import settings
from django.http import Http404, HttpResponseRedirect, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.views.decorators.http import require_safe

from pgweb.util.decorators import queryparams
from .ecosystem_markup import render_manual
from .models import DocProject, DocRevision, EcosystemDocPage


COMPONENTS = {
    'patroni': {'name': 'Patroni', 'icon': 'fa-heartbeat', 'description': 'PostgreSQL 高可用与自动故障切换'},
    'pgbouncer': {'name': 'PgBouncer', 'icon': 'fa-exchange-alt', 'description': '轻量级 PostgreSQL 连接池'},
    'pgbackrest': {'name': 'pgBackRest', 'icon': 'fa-database', 'description': '可靠的备份、恢复与归档管理'},
    'pgbadger': {'name': 'pgBadger', 'icon': 'fa-chart-bar', 'description': 'PostgreSQL 日志分析与性能报告'},
}


def manual_url(revision, path=''):
    return '/docs/{}/{}/{}/{}'.format(
        quote(revision.project_id, safe=''), quote(revision.version, safe=''), revision.lang,
        quote(path.strip('/'), safe='/') + '/' if path else '',
    )


def safe_external(value):
    try:
        parsed = urlsplit(value or '')
        return value if parsed.scheme in ('http', 'https') and parsed.netloc else ''
    except ValueError:
        return ''


def logical_path(path, project):
    path = unquote(path).strip('/')
    parts = path.split('/')
    if parts[0] in ('en', 'zh'):
        parts.pop(0)
    if parts and parts[0] == 'docs':
        parts.pop(0)
    if parts and parts[0] == project:
        parts.pop(0)
    return '/'.join(parts).strip('/')


class Library:
    def __init__(self):
        self.projects = {p.slug: p for p in DocProject.objects.filter(slug__in=COMPONENTS)}
        self.revisions = list(DocRevision.objects.filter(project_id__in=COMPONENTS))
        self.editions = {(r.project_id, r.version, r.lang): r for r in self.revisions}
        self._pages = {}
        self._indexes = {}

    def default(self, project, language='zh'):
        if project not in self.projects:
            raise Http404('Documentation project not found')
        version = self.projects[project].meta.get('default_version')
        # Default links may fall back to the actual English edition. Explicit
        # version/language URLs below always require that exact edition.
        revision = self.editions.get((project, version, language)) or self.editions.get((project, version, 'en'))
        if revision is None:
            raise Http404('Default documentation edition is not loaded')
        return revision

    def pages(self, revision):
        if revision.id not in self._pages:
            rows = list(EcosystemDocPage.objects.filter(rev_id=revision.id).values('path', 'source_path', 'title', 'meta'))
            self._pages[revision.id] = rows
            index = {}
            for row in rows:
                for key in (row['path'], row['source_path']):
                    index[key] = row
            for row in rows:
                for alias in row['meta'].get('frontmatter', {}).get('aliases', []):
                    index.setdefault(logical_path(alias, revision.project_id), row)
            self._indexes[revision.id] = index
        return self._pages[revision.id]

    def lookup(self, revision, path):
        self.pages(revision)
        return self._indexes[revision.id].get(path.strip('/'))

    def corresponding(self, revision, page):
        self.pages(revision)
        index = self._indexes[revision.id]
        return index.get(page.source_path) or index.get(page.path)

    def link(self, revision, page, value, asset=False):
        try:
            parsed = urlsplit(value)
        except ValueError:
            return ''
        if not value or value.startswith('#'):
            return value
        base = revision.meta.get('source_base_url') or 'https://pgsql.cc/docs/{}/'.format(revision.project_id)
        if parsed.scheme and parsed.scheme not in ('http', 'https'):
            return value
        if parsed.netloc and parsed.hostname != urlsplit(base).hostname:
            return value
        if not parsed.path.startswith('/') and not parsed.netloc:
            relative = posixpath.normpath(posixpath.join(posixpath.dirname(page.source_path), unquote(parsed.path)))
            if not asset:
                target = self.lookup(revision, relative)
                if target:
                    return urlunsplit(('', '', manual_url(revision, target['path']), parsed.query, parsed.fragment))
            source = urljoin(base, quote(relative, safe='/'))
        else:
            source = urljoin(base, parsed.path)
        route = posixpath.normpath(unquote(urlsplit(source).path))
        if asset and route.startswith('/img/docs/'):
            local = Path(settings.STATIC_CHECKOUT) / 'ecosystem' / route.lstrip('/')
            if local.is_file():
                return urlunsplit(('', '', '/files/ecosystem' + quote(route, safe='/'), parsed.query, parsed.fragment))
        if not asset:
            parts = route.strip('/').split('/')
            if parts[0] in ('en', 'zh'):
                parts.pop(0)
            if parts and parts[0] == 'docs':
                parts.pop(0)
            if parts and parts[0] in self.projects:
                project = parts.pop(0)
                try:
                    chosen = revision if project == revision.project_id else self.default(project, revision.lang)
                except Http404:
                    return urlunsplit((urlsplit(source).scheme, urlsplit(source).netloc, urlsplit(source).path, parsed.query, parsed.fragment))
                if len(parts) >= 2 and (project, parts[0], parts[1]) in self.editions:
                    chosen = self.editions[(project, parts.pop(0), parts.pop(0))]
                path = '/'.join(parts)
                target = self.lookup(chosen, path)
                if not target and chosen.lang != 'en':
                    english = self.editions.get((project, chosen.version, 'en'))
                    if english:
                        target = self.lookup(english, path)
                        if target:
                            chosen = english
                if target:
                    return urlunsplit(('', '', manual_url(chosen, target['path']), parsed.query, parsed.fragment))
        return urlunsplit((urlsplit(source).scheme, urlsplit(source).netloc, urlsplit(source).path, parsed.query, parsed.fragment))

    def cards(self):
        cards = []
        for slug, info in COMPONENTS.items():
            if slug not in self.projects:
                continue
            try:
                revision = self.default(slug)
            except Http404:
                continue
            cards.append({**info, 'slug': slug, 'url': '/docs/{}/'.format(slug), 'version': revision.version,
                          'language': revision.lang, 'pages': len([n for n in revision.meta.get('navigation', []) if n.get('path') is not None])})
        return cards


def component_cards():
    return Library().cards()


def navigation(library, revision, page):
    metadata = {n['path']: n for n in revision.meta.get('navigation', []) if n.get('path') is not None}
    nodes = {}
    for row in library.pages(revision):
        path = row['path']
        frontmatter = row['meta'].get('frontmatter', {})
        info = metadata.get(path, {})
        parent = info.get('parent', posixpath.dirname(path))
        nodes[path] = {**row, 'title': info.get('title', frontmatter.get('linkTitle', row['title'])),
                       'parent': parent, 'weight': info.get('weight', frontmatter.get('weight', 0)),
                       'url': manual_url(revision, path), 'active': path == page.path,
                       'expanded': bool(frontmatter.get('sidebar_expanded')) or page.path.startswith(path + '/'), 'children': []}
    roots = []
    for path, node in nodes.items():
        if path and node['parent'] and node['parent'] in nodes and node['parent'] != path:
            nodes[node['parent']]['children'].append(node)
        else:
            roots.append(node)
    ordered = []

    def walk(items):
        items.sort(key=lambda n: (n['path'] != '', n['weight'], n['source_path']))
        for node in items:
            ordered.append(node)
            walk(node['children'])

    walk(roots)
    current = next(i for i, n in enumerate(ordered) if n['active'])
    ancestors = []
    node = nodes[page.path]
    visited = {page.path}
    while node['parent'] and node['parent'] in nodes and node['parent'] not in visited:
        node = nodes[node['parent']]
        visited.add(node['path'])
        ancestors.insert(0, node)
    return roots, ordered[current - 1] if current else None, ordered[current + 1] if current + 1 < len(ordered) else None, ancestors, nodes[page.path]['children']


@queryparams('lang')
@require_safe
def entry(request, project, path='', language='zh'):
    library = Library()
    revision = library.default(project, 'en' if request.GET.get('lang', language) == 'en' else 'zh')
    row = library.lookup(revision, logical_path(path, project))
    if not row:
        raise Http404('Documentation page not found')
    response = HttpResponseRedirect(manual_url(revision, row['path']))
    response['Cache-Control'] = 'no-cache'
    return response


@require_safe
def page(request, project, version, language, path=''):
    library = Library()
    revision = library.editions.get((project, version, language))
    if revision is None:
        raise Http404('Documentation edition not found')
    row = library.lookup(revision, path)
    if row is None:
        raise Http404('Documentation page not found')
    canonical = manual_url(revision, row['path'])
    if request.path != unquote(canonical):
        return HttpResponsePermanentRedirect(canonical)
    document = EcosystemDocPage.objects.get(rev_id=revision.id, path=row['path'])
    tree, previous, following, ancestors, children = navigation(library, revision, document)
    html, toc = render_manual(document.content, language, lambda value, asset=False: library.link(revision, document, value, asset))
    project_obj = library.projects[project]
    english = language == 'en'
    labels = {key: pair[english] for key, pair in {
        'docs': ('文档', 'Documentation'), 'chapters': ('章节目录', 'Chapters'), 'filter': ('查找章节…', 'Find a chapter…'),
        'toc': ('本页目录', 'On this page'), 'version': ('版本', 'Version'), 'overview': ('概览', 'Overview'),
        'previous': ('上一页', 'Previous'), 'next': ('下一页', 'Next'), 'source': ('上游原文', 'Upstream source'),
        'license': ('文档许可证', 'Documentation license'), 'section': ('本节内容', 'In this section'),
        'empty': ('没有匹配的章节', 'No matching chapters'), 'home': ('首页', 'Home'), 'skip': ('跳到正文', 'Skip to content'),
        'projects': ('切换文档', 'Switch documentation'), 'missing': ('本章未提供', 'Chapter unavailable'),
        'ecosystem': ('三方文档', 'Ecosystem docs'),
    }.items()}
    editions, languages, alternates = [], [], {}
    for other in library.revisions:
        if other.project_id != project or other.lang not in ('en', 'zh'):
            continue
        counterpart = library.corresponding(other, document)
        choice = {'version': other.version, 'language': other.lang, 'current': other.id == revision.id,
                  'url': manual_url(other, counterpart['path'] if counterpart else ''), 'missing': counterpart is None}
        if other.lang == language:
            editions.append(choice)
        if other.version == version:
            choice['label'] = {'zh': '中文', 'en': 'English'}.get(other.lang, other.lang)
            languages.append(choice)
            if counterpart:
                alternates[other.lang] = choice['url']
    editions.sort(key=lambda r: (not r['current'], r['version'] != project_obj.meta.get('default_version'), r['version']))
    languages.sort(key=lambda r: r['language'] != 'zh')
    attribution = project_obj.meta.get('import', {}).get('attribution', {})
    title = document.title if document.path else project_obj.name + (' Documentation' if english else ' 文档')
    if document.path:
        seo_title = '{} · {} {} · PostgreSQL'.format(title, project_obj.name, version)
    else:
        seo_title = '{} {}{} · PostgreSQL'.format(project_obj.name, version, ' Documentation' if english else ' 文档')
    response = render(request, 'docs/ecosystem/page.html', {
        'project': project_obj, 'component': COMPONENTS[project], 'components': library.cards(),
        'revision': revision, 'page': document, 'language': language, 't': labels, 'title': title,
        'tree': tree, 'previous': previous, 'next': following, 'ancestors': ancestors, 'children': children,
        'document': html, 'toc': toc, 'editions': editions, 'languages': languages,
        'home_url': manual_url(revision), 'upstream_url': safe_external(document.upstream_url),
        'doc_source_url': safe_external(document.upstream_url) or safe_external(revision.upstream_url) or safe_external(revision.meta.get('source_base_url')),
        'doc_source_label': labels['source'],
        'license': revision.meta.get('license') or project_obj.license,
        'notice_url': safe_external(urljoin(project_obj.meta.get('import', {}).get('source_site', ''), attribution.get('notice', ''))),
        'copyright': attribution.get('copyright', ''),
        'seo': {'title': seo_title,
                'description': document.description, 'canonical': canonical, 'lang': language, 'alternates': alternates},
    })
    response['xkey'] = 'pgecosystem pgecosystem_' + project
    return response
