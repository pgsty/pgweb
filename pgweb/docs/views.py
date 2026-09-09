from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponsePermanentRedirect, HttpResponseNotFound
from django.http import HttpResponse, Http404
from pgweb.util.decorators import login_required, content_sources, allow_frames
from django.db.models import Q
from django.conf import settings

from decimal import Decimal, ROUND_DOWN
from html.parser import HTMLParser
import os
import re

from pgweb.util.contexts import THIRD_PARTY_DOCS, get_nav_menu, render_pgweb
from pgweb.util.helpers import template_to_string
from pgweb.util.misc import send_template_mail
from pgweb.util.decorators import xkey
from pgweb.util.yamldataloader import YamlDataLoader
from pgweb.util.seo import summarize_html

from pgweb.core.models import Version, UserSubmission
from pgweb.util.db import exec_to_dict

from .models import DocPage, DocPageRedirect
from .forms import DocCommentForm


re_cjk = re.compile(r'[\u4e00-\u9fff]')
re_whitespace = re.compile(r'\s+')
re_book_date = re.compile(r'^([A-Za-z]+) (\d{4})(.*)$')

BOOK_LANGUAGES_ZH = {
    'English': '英语',
    'French': '法语',
    'German': '德语',
    'Russian': '俄语',
    'Spanish': '西班牙语',
    'Turkish': '土耳其语',
}
BOOK_FORMATS_ZH = {
    'eBook': '电子书',
    'Hardback': '精装书',
    'Paperback': '平装书',
    'PDF': 'PDF',
}
BOOK_MONTHS_ZH = {
    'January': '1 月',
    'February': '2 月',
    'March': '3 月',
    'April': '4 月',
    'May': '5 月',
    'June': '6 月',
    'July': '7 月',
    'August': '8 月',
    'September': '9 月',
    'October': '10 月',
    'November': '11 月',
    'December': '12 月',
}


def _clean_meta_description(text):
    return re_whitespace.sub(' ', text or '').strip()


def _doc_meta_description(page, contentpreview=''):
    """Return a short description from the document's actual prose.

    Imported PostgreSQL pages contain a navigation header, table of contents,
    and often a large amount of syntax markup.  ``summarize_html`` knows how
    to skip those parts.  A few index/legal pages contain no paragraph that
    can be selected, so their own title is the safest fallback; inventing a
    description about all SQL or administration topics would be misleading.
    """
    summary = summarize_html(page.content or contentpreview, max_length=180)
    if summary:
        return _clean_meta_description(summary)
    return _clean_meta_description(page.title)


def _doc_language(page, description):
    """Infer the rendered manual language without translating the content."""
    if re_cjk.search(description or '') or re_cjk.search(page.title or ''):
        return 'zh'
    return 'en'


def _doc_path(version, filename):
    return '/docs/{}/{}'.format(version, filename)


def _doc_page_title(page):
    """Build a distinct metadata title for ECPG command pages.

    PostgreSQL's SQL and ECPG manuals use the same short command title (for
    example, ``DECLARE``).  The filename is the stable distinction in the
    imported documentation, so keep ordinary SQL titles unchanged and add
    the ECPG context only for that file family.
    """
    title = (page.title or '').strip()
    if page.file.startswith('ecpg-sql-') and not title.upper().startswith('ECPG '):
        title = 'ECPG ' + title
    return 'PostgreSQL {} 文档 · {}'.format(page.display_version(), title)


def _release_major_label(major):
    """Match the PostgreSQL release-note version formatting filter."""
    value = Decimal(major)
    if value >= 10 or value <= 1:
        return '{:f}'.format(value.normalize())
    return str(value)


def _release_minor_label(major, minor):
    if str(major) in ('0', '1', '1.0'):
        value = int(minor)
        return '0' if value == 0 else '{:02}'.format(value)
    return str(minor)


def _release_version_label(major, minor):
    return '{}.{}'.format(_release_major_label(major), _release_minor_label(major, minor))


class _ReleaseHtmlNode(object):
    """Small stdlib-only tree used to inspect imported release-note HTML."""

    def __init__(self, tag='', attrs=None, parent=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.parent = parent
        self.children = []


class _ReleaseHtmlParser(HTMLParser):
    _void_tags = {
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
        'link', 'meta', 'param', 'source', 'track', 'wbr',
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _ReleaseHtmlNode()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _ReleaseHtmlNode(tag, dict(attrs), self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in self._void_tags:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self._void_tags:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _release_walk(node):
    for child in node.children:
        if isinstance(child, _ReleaseHtmlNode):
            yield child
            for descendant in _release_walk(child):
                yield descendant


def _release_node_text(node):
    """Extract prose while dropping commit markers and section-only links."""
    parts = []
    for child in node.children:
        if not isinstance(child, _ReleaseHtmlNode):
            parts.append(child)
            continue

        if child.tag == 'a':
            link_text = _clean_meta_description(_release_node_text(child))
            classes = set(child.attrs.get('class', '').split())
            href = child.attrs.get('href', '')
            if link_text == '§':
                continue
            if 'xref' in classes and (
                link_text.lower().startswith('section')
                or link_text.startswith('章节')
                or 'release-' in href
            ):
                continue

        parts.append(_release_node_text(child))
    text = _clean_meta_description(''.join(parts))
    text = re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])', '', text)
    text = re.sub(r'\s+([，。；：！？、）】』》])', r'\1', text)
    text = re.sub(r'([（【『《])\s+', r'\1', text)
    return text


def _release_section(root, suffix):
    suffix = '-' + suffix.upper()
    for node in _release_walk(root):
        node_id = node.attrs.get('id', '').upper()
        if node_id.endswith(suffix):
            return node
    labels = {
        'HIGHLIGHTS': ('概述', 'Overview', 'Highlights'),
        'CHANGES': ('变更', 'Changes'),
    }.get(suffix[1:], ())
    for node in _release_walk(root):
        if node.tag != 'h3' or not any(label in _release_node_text(node) for label in labels):
            continue
        ancestor = node.parent
        while ancestor is not None and ancestor is not root:
            if ancestor.tag == 'div' and 'sect2' in ancestor.attrs.get('class', '').split():
                return ancestor
            ancestor = ancestor.parent
    return None


def _release_top_level_items(section):
    items = []
    for node in _release_walk(section):
        if node.tag != 'li':
            continue
        ancestor = node.parent
        nested = False
        while ancestor is not None and ancestor is not section:
            if ancestor.tag == 'li':
                nested = True
                break
            ancestor = ancestor.parent
        if nested:
            continue
        paragraphs = [child for child in node.children
                      if isinstance(child, _ReleaseHtmlNode) and child.tag == 'p']
        if paragraphs:
            text = _release_node_text(paragraphs[0])
        else:
            text = _release_node_text(node)
        text = re.sub(r'\s*[§#]+\s*$', '', text).strip()
        # Imported translations append the contributor to the first sentence;
        # the contributor is not part of the change being summarized.
        author = re.search(r'[（(]([^（）()]{2,80})[）)]\s*$', text)
        if author and re.fullmatch(
            r"[A-Z][A-Za-z.'’-]*(?:\s+[A-Z][A-Za-z.'’-]*)+",
            author.group(1).strip(),
        ):
            text = text[:author.start()].rstrip()
        if not text or re.match(r'^(?:Section|章节|迁移到版本|Migration to)\b', text, re.I):
            continue
        items.append(text)
    return items


def _release_section_prose(section):
    if section is None:
        return []
    prose = []
    for node in _release_walk(section):
        if node.tag != 'p':
            continue
        if any(ancestor.tag == 'li' for ancestor in _release_ancestors(node)):
            continue
        text = _release_node_text(node)
        if text and not re.match(r'^(?:Section|章节|迁移到版本|Migration to)\b', text, re.I):
            prose.append(text)
    return prose


def _release_ancestors(node):
    ancestor = node.parent
    while ancestor is not None:
        yield ancestor
        ancestor = ancestor.parent


def _release_date(root):
    date_pattern = re.compile(
        r'(?:发布日期|Release date|Date of release|Released)\s*[:：.]*\s*'
        r'(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{4}年\s*\d{1,2}月\s*\d{1,2}日?)',
        re.I,
    )
    for node in _release_walk(root):
        if node.tag != 'p':
            continue
        match = date_pattern.search(_release_node_text(node))
        if match:
            return re_whitespace.sub(' ', match.group(1)).strip()
    return ''


def _release_fallback_prose(root):
    date_pattern = re.compile(r'(?:发布日期|Release date|Date of release|Released)\b', re.I)
    for node in _release_walk(root):
        if node.tag != 'p':
            continue
        ancestors = list(_release_ancestors(node))
        if any(
            ancestor.tag in ('nav', 'header', 'footer')
            or 'navheader' in ancestor.attrs.get('class', '').split()
            or 'navfooter' in ancestor.attrs.get('class', '').split()
            or 'toc' in ancestor.attrs.get('class', '').split()
            for ancestor in ancestors
        ):
            continue
        text = _release_node_text(node)
        if text and not date_pattern.search(text):
            return text
    return ''


def _release_description_text(release_title, release_date, highlights, fallback):
    prefix = release_title.strip()
    if release_date:
        prefix += '（发布日期：{}）'.format(release_date)
    if highlights:
        highlights = [item.rstrip('。！？；') for item in highlights[:2]]
        text = '{}：{}'.format(prefix, '；'.join(highlights))
    elif fallback:
        text = '{}：{}'.format(prefix, fallback)
    else:
        text = prefix + '。'
    if len(text) <= 180:
        return text
    return text[:179].rstrip('，、；： ') + '…'


def _release_notes_description(content, release_title, version):
    """Describe a release from its date and concrete release-note entries.

    Major releases use the Overview/Highlights list; patch releases use the
    Changes list.  This avoids turning the generic migration paragraph into
    the description for every minor release while keeping the source wording
    and its language intact.
    """
    parser = _ReleaseHtmlParser()
    try:
        parser.feed(str(content or ''))
        parser.close()
    except Exception:
        # The normal fallback still gives a truthful description for an older
        # malformed import.
        pass

    try:
        is_major = Decimal(str(version).split('.')[-1]) == 0
    except (ValueError, ArithmeticError):
        is_major = False
    section = _release_section(parser.root, 'HIGHLIGHTS' if is_major else 'CHANGES')
    highlights = _release_top_level_items(section) if section else []
    if not highlights:
        highlights = _release_section_prose(section)
    fallback = _release_fallback_prose(parser.root) if not highlights else ''
    if not fallback and not highlights:
        fallback = summarize_html(content, max_length=140)
    return _release_description_text(
        release_title,
        _release_date(parser.root),
        highlights,
        fallback,
    )


def _official_release_target(major, minor):
    """Return the exact upstream release archive route for a known version.

    The upstream archive exposes one stable route shape for old and new
    releases alike (for example ``/docs/release/0.01/`` and
    ``/docs/release/15.19/``).  The caller validates the version table or the
    small legacy list before using this fallback, so this helper never needs
    to guess a version-specific HTML filename.
    """
    if Decimal(major) < 0:
        return None
    return 'https://www.postgresql.org/docs/release/{}/'.format(
        _release_version_label(major, minor),
    )


def _versioned_404(msg, version):
    r = HttpResponseNotFound(msg)
    r['xkey'] = 'pgdocs_{}'.format(version)
    return r


@content_sources('style', "'unsafe-inline'")
def docpage(request, version, filename):
    loaddate = None
    loadgit = None
    if version == 'current':
        ver = Version.objects.filter(current=True)[0].tree
    elif version == 'devel':
        ver = Decimal(0)
        verobj = Version.objects.get(tree=Decimal(0))
        loaddate = verobj.docsloaded
        loadgit = verobj.docsgit
    else:
        ver = Decimal(version)
        if ver == Decimal(0):
            return _versioned_404("Version not found", "all")

    if ver < Decimal("7.1") and ver > Decimal(0):
        extension = "htm"
    else:
        extension = "html"

    if ver < Decimal("7.1") and ver > Decimal(0):
        indexname = "postgres.htm"
    elif ver == Decimal("7.1"):
        indexname = "postgres.html"
    else:
        indexname = "index.html"

    if ver >= 10 and version.find('.') > -1:
        # Version 10 and up, but specified as 10.0 / 11.0 etc, so redirect back without the
        # decimal.
        return HttpResponsePermanentRedirect("/docs/{0}/{1}.html".format(int(ver), filename))

    fullname = "%s.%s" % (filename, extension)

    # Before looking up the documentation, we need to make a check for release
    # notes. Based on a change, from PostgreSQL 9.4 and up, release notes are
    # only available for the current version (e.g. 11 only has 11.0, 11.1, 11.2)
    # This checks to see if there is a mismatch (e.g. ver = 9.4, fullname = release-9-3-2.html)
    # or if these are the development docs that are pointing to a released version
    # and performs a redirect to the older version
    if fullname.startswith('release-') and (ver >= Decimal("9.4") or version == "devel") and not fullname.startswith('release-prior'):
        # figure out which version to redirect to. Note that the oldest version
        # of the docs loaded is 7.2
        release_version = re.sub(r'release-((\d+)(-\d+)?)(-\d+)?.html',
                                 r'\1', fullname).replace('-', '.')
        # convert to Decimal for ease of manipulation
        try:
            release_version = Decimal(release_version)
        except Exception as e:
            # If it's not a proper decimal, just return 404. This can happen from many
            # broken links around the web.
            raise Http404("Invalid version format")

        # if the version is greater than 10, truncate the number
        if release_version >= Decimal('10'):
            release_version = release_version.quantize(Decimal('1'), rounding=ROUND_DOWN)
        # if these are developer docs (i.e. from the nightly build), we need to
        # determine if these are release notes for a branched version or not,
        # i.e. if we are:
        # a) viewing the docs for a version that does not exist yet (e.g. active
        #    development before an initial beta) OR
        # b) viewing the docs for a beta, RC, or fully released version
        is_branched = Version.objects.filter(tree=release_version).exists() if version == "devel" else True
        # If we are viewing a released version of the release notesand the
        # release versions do not match, then we redirect
        if is_branched and release_version != ver:
            url = "/docs/"
            if release_version >= Decimal('10'):
                url += "{}/{}".format(int(release_version), fullname)
            elif release_version < Decimal('7.2'):
                url += "7.2/{}".format(fullname)
            else:
                url += "{}/{}".format(release_version, fullname)
            return HttpResponsePermanentRedirect(url)

    # try to get the page outright. If it's not found, check to see if it's a
    # doc alias with a redirect, and if so, redirect to that page
    try:
        page = DocPage.objects.select_related('version').get(version=ver, file=fullname)
    except DocPage.DoesNotExist:
        # if the page does not exist but there is a special page redirect, check
        # for the existence of that. if that does not exist, then we're really
        # done and can 404
        try:
            page_redirect = DocPageRedirect.objects.get(redirect_from=fullname)
            url = "/docs/{}/{}".format(version, page_redirect.redirect_to)
            return HttpResponsePermanentRedirect(url)
        except DocPageRedirect.DoesNotExist:
            return _versioned_404("Page not found", ver)

    versions = DocPage.objects.select_related('version').extra(
        where=["file=%s OR file IN (SELECT file2 FROM docsalias WHERE file1=%s) OR file IN (SELECT file1 FROM docsalias WHERE file2=%s)"],
        params=[fullname, fullname, fullname],
    ).order_by('-version__supported', 'version').only('version', 'file')

    description = _doc_meta_description(page)
    language = _doc_language(page, description)

    # Only the current numeric version and its /current/ alias are the same
    # public document.  Older numeric manuals must retain their own
    # canonical URL; otherwise every historical version collapses into the
    # current manual merely because the filename happens to be shared.
    if version == 'current' or page.version.current:
        canonical_path = _doc_path('current', page.file)
    elif version == 'devel':
        canonical_path = _doc_path('devel', page.file)
    else:
        canonical_path = _doc_path(page.display_version(), page.file)

    current_page = next((v for v in versions if v.version.current), None)
    if current_page is not None:
        current_page_url = _doc_path('current', current_page.file)
        current_page_label = '当前版本'
    else:
        # The current branch does not necessarily contain an old appendix,
        # command, or historical page.  Point readers to the usable manual
        # entry instead of emitting a guaranteed 404.
        current_page_url = '/docs/current/'
        current_page_label = '当前版本手册首页'

    page_title = _doc_page_title(page)
    from pgweb.search.extract import reading_html
    page.content = reading_html(page.content)
    r = render(request, 'docs/docspage.html', {
        'page': page,
        'supported_versions': [v for v in versions if v.version.supported],
        'devel_versions': [v for v in versions if not v.version.supported and v.version.testing],
        'unsupported_versions': [v for v in versions if not v.version.supported and not v.version.testing],
        'current_page_url': current_page_url,
        'current_page_label': current_page_label,
        'title': page.title,
        'doc_index_filename': indexname,
        'loaddate': loaddate,
        'loadgit': loadgit,
        'og': {
            'url': canonical_path,
            'modified_time': page.version.docsloaded,
            'title': page_title,
            'description': description,
            'sitename': 'PostgreSQL 中文文档',
        },
        'seo': {
            'title': page_title,
            'lang': language,
            'canonical': canonical_path,
        },
    })
    r['xkey'] = 'pgdocs_{}'.format(page.display_version())
    if version == 'current':
        r['xkey'] += ' pgdocs_current'
    return r


@allow_frames
@content_sources('style', "'unsafe-inline'")
def docsvg(request, version, filename):
    if version == 'current':
        ver = Version.objects.filter(current=True)[0].tree
    elif version == 'devel':
        ver = Decimal(0)
    else:
        ver = Decimal(version)
        if ver == Decimal(0):
            return _versioned_404("Version not found", "all")

    if ver < Decimal(12) and ver > Decimal(0):
        raise Http404("SVG images don't exist in this version")

    page = get_object_or_404(DocPage, version=ver, file="{0}.svg".format(filename))

    r = HttpResponse(page.content, content_type="image/svg+xml")
    r['xkey'] = 'pgdocs_{}'.format(page.display_version())
    if version == 'current':
        r['xkey'] += ' pgdocs_current'
    return r


def docspermanentredirect(request, version, typ, page, *args):
    """Provides a permanent redirect from the old static/interactive pages to
    the modern pages that do not have said keywords.
    """
    url = "/docs/%s/" % version
    if page:
        url += page
    return HttpResponsePermanentRedirect(url)


def docsrootpage(request, version):
    return docpage(request, version, 'index')


def redirect_root(request, version):
    return HttpResponsePermanentRedirect("/docs/%s/" % version)


def root(request):
    versions = Version.objects.filter(Q(supported=True) | Q(testing__gt=0, tree__gt=0)).order_by('-tree')
    r = render_pgweb(request, 'docs', 'docs/index.html', {
        'versions': _loaded_version_wrappers(versions),
        'devel_a4pdf': _find_devel_pdf('A4'),
        'devel_uspdf': _find_devel_pdf('US'),
        'og': {
            'url': '/docs/',
            'type': 'website',
            'title': 'PostgreSQL 中文文档',
            'description': 'PostgreSQL 中文手册、各版本在线文档、PDF 下载与旧版手册归档。',
            'sitename': 'PostgreSQL 中文站',
        },
    })
    r['xkey'] = 'pgdocs_all pgdocs_pdf'
    return r


def third_party(request):
    navmenu = get_nav_menu('docs')
    navmenu[-1].update({'submenu': THIRD_PARTY_DOCS, 'active': True})
    return render(request, 'docs/third_party.html', {
        'navmenu': navmenu,
        'components': THIRD_PARTY_DOCS,
        'source_url': 'https://www.postgresql.org/docs/',
        'source_label': 'PostgreSQL 官方文档',
        'og': {
            'url': '/docs/third-party/',
            'type': 'website',
            'title': '三方文档',
            'description': 'PostgreSQL 生态组件介绍与中文文档入口，涵盖高可用、连接池、备份恢复、监控、空间数据、时序数据与分布式数据库。',
            'sitename': 'PostgreSQL 中文站',
        },
    })


class _VersionPdfWrapper(object):
    """
    A wrapper around a version that knows to look for PDF files, and
    return their sizes.
    """
    def __init__(self, version, loaded=True):
        self.__version = version
        self.loaded = loaded
        self.a4pdf = self._find_pdf('A4')
        self.uspdf = self._find_pdf('US')
        # Some versions have, ahem, strange index filenames
        self.indexname = _doc_index_filename(self.__version.tree)

    def __getattr__(self, name):
        return getattr(self.__version, name)

    def _find_pdf(self, pagetype):
        try:
            return os.stat('%s/documentation/pdf/%s/postgresql-%s-%s.pdf' % (settings.STATIC_CHECKOUT, self.__version.numtree, self.__version.numtree, pagetype)).st_size
        except Exception as e:
            return 0


def _find_devel_pdf(pagetype):
    try:
        return os.stat('%s/documentation/pdf/19/postgresql-19-%s.pdf' % (settings.STATIC_CHECKOUT, pagetype)).st_size
    except Exception:
        return 0


def _doc_index_filename(tree):
    if tree < Decimal('6.4'):
        return 'book01.htm'
    if tree < Decimal('7.0'):
        return 'postgres.htm'
    if tree < Decimal('7.2'):
        return 'postgres.html'
    return 'index.html'


def _loaded_version_wrappers(versions):
    """Keep version tables aligned with documentation rows actually loaded."""
    versions = list(versions)
    if not versions:
        return []
    indexnames = {_doc_index_filename(version.tree) for version in versions}
    loaded = set(DocPage.objects.filter(
        version__in=versions,
        file__in=indexnames,
    ).values_list('version_id', 'file'))
    return [
        _VersionPdfWrapper(
            version,
            loaded=(version.tree, _doc_index_filename(version.tree)) in loaded,
        )
        for version in versions
    ]


def manuals(request):
    # Legacy URL for manuals, redirect to the main docs page
    return HttpResponsePermanentRedirect('/docs/')


def manualarchive(request):
    versions = Version.objects.filter(testing=0, supported=False, tree__gt=0).order_by('-tree')
    r = render_pgweb(request, 'docs', 'docs/archive.html', {
        'versions': _loaded_version_wrappers(versions),
        'og': {
            'url': '/docs/manuals/archive/',
            'title': 'PostgreSQL 手册归档',
            'description': '不再受支持的 PostgreSQL 版本手册与可用 PDF 归档。',
            'sitename': 'PostgreSQL 中文站',
        },
    })
    r['xkey'] = 'pgdocs_all pgdocs_pdf'
    return r


# Store a list of versions for which we have release notes, but nothing else,
# so we don't have to add them to core_version.
# NOTE! Order-sensitive!
_release_notes_only_versions = [
    # PostgreSQL 6.2
    [Decimal('6.2'), 1],
    [Decimal('6.2'), 0],
    # PostgreSQL 6.1
    [Decimal('6.1'), 1],
    [Decimal('6.1'), 0],
    # PostgreSQL 6.0
    [Decimal('6.0'), 0],
    # PostgresSQL 1
    [1, 9],
    [1, 2],
    [1, 1],
    [1, 0],
    # Postgres95
    [0, 3],
    [0, 2],
    [0, 1],
]
release_notes_only_versions = [{'major': major, 'minor': minor} for major, minor in _release_notes_only_versions]

no_release_notes_versions = [
    {'major': 18, 'minor': 5},
]


def _release_note_neighbors(available_minor_versions, minor_version):
    """Return the older and newer release notes around a version."""
    previous_minor = None
    next_minor = None
    for i, version in enumerate(available_minor_versions):
        if version['minor'] == minor_version:
            if i > 0:
                next_minor = available_minor_versions[i - 1]['minor']
            if i + 1 < len(available_minor_versions):
                previous_minor = available_minor_versions[i + 1]['minor']
            break
    return previous_minor, next_minor


def release_notes_list(request):
    """Lists the available release notes"""
    # We only keep 6.3 and newer in core_version (for legacy reasons)
    releases = exec_to_dict("SELECT tree AS major, minor FROM core_version INNER JOIN generate_series(0, latestminor) g(minor) ON true WHERE testing=0 AND tree > 6.2 ORDER BY tree DESC, minor DESC")

    release_entries = []
    for release in releases + release_notes_only_versions:
        if release in no_release_notes_versions:
            continue
        entry = dict(release)
        entry['label'] = _release_version_label(entry['major'], entry['minor'])
        # Keep the historical record visible.  For branches whose exact
        # release page is no longer available, render it as text rather than
        # creating a link that is guaranteed to 404.
        entry['url'] = (
            '/docs/release/{}/'.format(entry['label'])
            if _official_release_target(entry['major'], entry['minor'])
            else ''
        )
        release_entries.append(entry)

    r = render_pgweb(request, 'docs', 'docs/release_notes_list.html', {
        'releases': release_entries,
        'og': {
            'url': '/docs/release/',
            'type': 'website',
            'title': 'PostgreSQL 发布说明归档',
            'description': 'PostgreSQL 各版本发布说明归档。',
            'sitename': 'PostgreSQL 中文站',
        },
        'seo': {
            'title': 'PostgreSQL 发布说明归档',
            'canonical': '/docs/release/',
            'lang': 'zh',
        },
    })
    r['xkey'] = 'pgdocs_all'
    return r


def release_notes(request, version):
    """Contains the main archive of release notes."""

    version_pieces = version.split('.')  # Gives 1, 2 or 3 pieces due to regexp
    if len(version_pieces) == 3:
        # This is always major.major.minor
        major_version = Decimal('.'.join(version_pieces[0:2]))
        minor_version = Decimal(version_pieces[2])
        if major_version >= 10:
            # There is no three-digit version for 10+, so redirect back
            return HttpResponseRedirect('/docs/release/{}/'.format(major_version))
        if minor_version > 0:
            version_file = 'release-{}-{}.html'.format(str(major_version).replace('.', '-'), minor_version)
        else:
            version_file = 'release-{}.html'.format(str(major_version).replace('.', '-'))
    elif len(version_pieces) == 2:
        # This can be either a full version (10.3) *or* it can be
        # a major version without minor (9.5).
        major_version = Decimal(version_pieces[0])
        minor_version = Decimal(version_pieces[1])
        if int(version_pieces[0]) >= 10 or int(version_pieces[0]) <= 1:
            if major_version > 1:
                if {'major': major_version, 'minor': minor_version} in no_release_notes_versions:
                    # PostgreSQL 18.5 was never released. Redirect gaps to the
                    # following release, as the upstream archive does.
                    return HttpResponseRedirect('/docs/release/{}.{}/'.format(major_version, minor_version + 1))
                if minor_version == 0:
                    version_file = 'release-{}.html'.format(major_version)
                else:
                    version_file = 'release-{}-{}.html'.format(major_version, minor_version)
            elif major_version in (0, 1):
                if minor_version == 0:
                    version_file = 'release-{}-0.html'.format(major_version)
                else:
                    version_file = 'release-{}-{:02}.html'.format(major_version, minor_version)
        else:
            # Major version without a minor we redirect to the .0 minor
            return HttpResponseRedirect('/docs/release/{}.{}.0/'.format(major_version, minor_version))
    else:
        # Single digit major version, so redirect to a point-zero version of it
        if version_pieces[0] == '0':
            # Postgres95 did not have a .0 version :O
            return HttpResponseRedirect('/docs/release/0.1/')
        else:
            return HttpResponseRedirect('/docs/release/{}.0/'.format(Decimal(version_pieces[0])))

    version_info_rows = exec_to_dict(
        "SELECT latestminor, testing FROM core_version WHERE tree=%(major_version)s",
        {'major_version': major_version},
    )
    version_info = version_info_rows[0] if version_info_rows else None

    # If we have an exact match for our major version, get that one. If not,
    # use a precise upstream page for stable branches.  Beta/devel branches
    # must not link to guessed future release notes.
    release_notes = exec_to_dict("SELECT content FROM docs WHERE file=%(filename)s AND version > 0 ORDER BY version=%(major_version)s DESC, version DESC LIMIT 1", {
        'filename': version_file,
        'major_version': major_version,
    })
    try:
        release_note = release_notes[0]
    except IndexError:
        legacy_release = {'major': major_version, 'minor': minor_version}
        if major_version <= 1:
            if legacy_release not in release_notes_only_versions:
                # A legacy/devel core_version row (notably tree=0) is not a
                # catalogue of every possible Postgres95/early PostgreSQL
                # release.  Only the explicitly known release-note routes may
                # use the upstream archive fallback.
                return _versioned_404("Minor version release notes not found", major_version)
        elif version_info:
            latest_minor = version_info.get('latestminor')
            if version_info.get('testing') or (latest_minor is not None and minor_version > latest_minor):
                return _versioned_404("Minor version release notes not found", major_version)
        elif legacy_release not in release_notes_only_versions:
            # Do not turn an arbitrary, unknown branch into an external
            # redirect merely because the archive URL has a regular shape.
            return _versioned_404("Minor version release notes not found", major_version)
        official_target = _official_release_target(major_version, minor_version)
        if official_target:
            # Keep this temporary while the Chinese database may still gain
            # the missing page; a permanent cache redirect would make a later
            # local restore unnecessarily hard to observe.
            response = HttpResponseRedirect(official_target)
            response['xkey'] = 'pgdocs_{}'.format(major_version)
            return response
        # Must version this one, as this minor version can show up later and in that case we
        # need it to render once purged.
        return _versioned_404("Minor version release notes not found", major_version)

    # We only keep 6.3 and newer in core_version (for legacy reasons)
    if major_version > 6.2:
        if version_info and version_info.get('testing'):
            # A beta version's latestminor is a testing counter, not a list
            # of published release notes.  Derive the navigator from files
            # actually loaded for this branch.
            loaded_files = exec_to_dict(
                "SELECT file FROM docs WHERE version=%(major_version)s AND file LIKE %(pattern)s",
                {'major_version': major_version, 'pattern': 'release-%.html'},
            )
            major_label = _release_major_label(major_version).replace('.', '-')
            available_minor_versions = []
            for loaded in loaded_files:
                filename = loaded.get('file', '')
                if filename == 'release-{}.html'.format(major_label):
                    minor = 0
                else:
                    match = re.match(r'^release-{}-(\d+)\.html$'.format(re.escape(major_label)), filename)
                    if not match:
                        continue
                    minor = int(match.group(1))
                available_minor_versions.append({'minor': minor})
            available_minor_versions.sort(key=lambda item: item['minor'], reverse=True)
        else:
            available_minor_versions = exec_to_dict("SELECT minor FROM generate_series(0, (SELECT latestminor FROM core_version WHERE tree=%(major_version)s)) g(minor) ORDER BY minor DESC", {
                'major_version': major_version,
            })
        unavailable_minors = {
            version['minor'] for version in no_release_notes_versions
            if version['major'] == major_version
        }
        available_minor_versions = [
            version for version in available_minor_versions
            if version['minor'] not in unavailable_minors
        ]
    else:
        available_minor_versions = [v for v in release_notes_only_versions if v['major'] == major_version]

    previous_minor, next_minor = _release_note_neighbors(available_minor_versions, minor_version)

    release_version = _release_version_label(major_version, minor_version)
    release_product = 'Postgres95' if major_version == 0 else 'PostgreSQL'
    release_title = '{} {} 发布说明'.format(release_product, release_version)
    if version_info and version_info.get('testing'):
        release_title = '{} {} 发布说明（开发预览）'.format(release_product, _release_major_label(major_version))
    description = _release_notes_description(
        release_note.get('content', ''),
        release_title,
        release_version,
    )
    release_path = '/docs/release/{}/'.format(release_version)

    r = render_pgweb(request, 'docs', 'docs/release_notes.html', {
        'major_version': major_version,
        'minor_version': minor_version,
        'release_version': release_version,
        'release_title': release_title,
        'release_note': release_note,
        'available_minor_versions': available_minor_versions,
        'previous_minor_release': previous_minor,
        'next_minor_release': next_minor,
        'og': {
            'url': release_path,
            'title': release_title,
            'description': description,
            'sitename': 'PostgreSQL 中文站',
        },
        'seo': {
            'title': release_title,
            'lang': 'zh' if re_cjk.search(description) else 'en',
            'canonical': release_path,
        },
    })
    r['xkey'] = 'pgdocs_{}'.format(major_version)
    return r


class BooksData(YamlDataLoader):
    DATAFILE = "books.yaml"


booksdata = BooksData()


def _localize_book(book):
    """Keep upstream book metadata canonical while supplying Chinese labels."""
    localized = dict(book)
    localized['language_zh'] = BOOK_LANGUAGES_ZH.get(book['language'], book['language'])
    localized['format_zh'] = '、'.join(
        BOOK_FORMATS_ZH.get(part.strip(), part.strip())
        for part in book['format'].split(',')
    )

    published = book['published']
    match = re_book_date.match(published)
    if match and match.group(1) in BOOK_MONTHS_ZH:
        suffix = match.group(3)
        if suffix == ' (auf Deutsch/in German)':
            suffix = '（德语版）'
        localized['published_zh'] = '{} 年 {}{}'.format(
            match.group(2),
            BOOK_MONTHS_ZH[match.group(1)],
            suffix,
        )
    else:
        localized['published_zh'] = published
    return localized


@xkey('data_books')
@content_sources('style', "'unsafe-inline'")
def books(request):
    return render_pgweb(request, 'docs', 'docs/books.html', {
        'books': [_localize_book(book) for book in booksdata.get()['books']],
        'og': {
            'url': '/docs/books/',
            'title': 'PostgreSQL 图书',
            'description': 'PostgreSQL 社区维护的相关书目与出版信息。',
            'sitename': 'PostgreSQL 中文站',
        },
    })


@login_required
def commentform(request, itemid, version, filename):
    if version == 'current':
        v = Version.objects.get(current=True)
    else:
        v = get_object_or_404(Version, tree=version)
    if not v.supported:
        # No docs comments on unsupported versions
        return HttpResponseRedirect("/docs/{0}/{1}".format(version, filename))

    if request.method == 'POST':
        form = DocCommentForm(request.POST)
        if form.is_valid():
            if version == '0.0':
                version = 'devel'

            send_template_mail(
                settings.DOCSREPORT_NOREPLY_EMAIL,
                settings.DOCSREPORT_EMAIL,
                '%s' % form.cleaned_data['shortdesc'],
                'docs/docsbugmail.txt', {
                    'version': version,
                    'filename': filename,
                    'details': form.cleaned_data['details'],
                },
                cc=form.cleaned_data['email'],
                replyto='%s, %s' % (form.cleaned_data['email'], settings.DOCSREPORT_EMAIL),
                sendername='PG Doc comments form'
            )
            UserSubmission(user=request.user, what='Added comment to {}/{}'.format(version, filename)).save()
            return HttpResponseRedirect("done/")
    else:
        form = DocCommentForm(initial={
            'name': '%s %s' % (request.user.first_name, request.user.last_name),
            'email': request.user.email,
        })

    return render_pgweb(request, 'docs', 'base/form.html', {
        'form': form,
        'formitemtype': 'documentation comment',
        'operation': 'Submit',
        'form_intro': template_to_string('docs/docsbug.html', {
            'user': request.user,
        }),
        'savebutton': 'Send Email',
    })


@login_required
def commentform_done(request, itemid, version, filename):
    return render_pgweb(request, 'docs', 'docs/docsbug_completed.html', {})
