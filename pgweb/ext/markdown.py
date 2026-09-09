"""Render catalog Markdown with sanitized HTML and local extension links."""

from html import escape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit

import bleach
import markdown
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from pgweb.util.prose import ProseExtension
from .catalog import CATEGORIES, browse_url, detail_url, safe_url


class Links(HTMLParser):
    def __init__(self, names, language, base):
        super().__init__(convert_charrefs=False)
        self.names, self.language, self.base = names, language, base
        self.output = []

    def destination(self, value):
        try:
            parsed = urlsplit(value)
        except ValueError:
            return ''
        if not value or value.startswith('#'):
            return value
        path = unquote(parsed.path).strip('/')
        parts = path.split('/')
        if parts and parts[0] in ('en', 'zh'):
            parts.pop(0)
        local = not parsed.netloc or parsed.hostname in ('pgext.cloud', 'ext.pgsty.com', 'ext.pgsty.cc')
        name = parts[-1].removesuffix('.md') if parts else ''
        if local and name in self.names and (len(parts) == 1 or parts[0] in ('e', 'ext')):
            params = {k: v for k, v in parse_qsl(parsed.query) if k not in ('lang', 'ui_lang', 'path')}
            return detail_url(name, self.language, **params) + ('#' + parsed.fragment if parsed.fragment else '')
        if local and len(parts) == 2 and parts[0] in ('cate', 'category', 'categories') and parts[1].upper() in CATEGORIES:
            return browse_url(self.language, {'category': parts[1].upper()})
        return value if parsed.scheme or parsed.netloc else urljoin(self.base, value)

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.output.append('<div class="pg-table-scroll" tabindex="0">')
        attrs = [(key, self.destination(value or '') if key in ('href', 'src') else value) for key, value in attrs]
        self.output.append('<' + tag + ''.join(' {}="{}"'.format(key, escape(value or '', quote=True)) for key, value in attrs) + '>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self.output.append('</' + tag + '>')
        if tag == 'table':
            self.output.append('</div>')

    def handle_data(self, data):
        self.output.append(data)

    def handle_entityref(self, name):
        self.output.append('&' + name + ';')

    def handle_charref(self, name):
        self.output.append('&#' + name + ';')


def render_document(content, names, language, base):
    converter = markdown.Markdown(extensions=['tables', 'fenced_code', 'toc', 'sane_lists', ProseExtension()])
    html = converter.convert(content or '')
    links = Links(names, language, safe_url(base) or 'https://pgext.cloud/')
    links.feed(html)
    clean = bleach.clean(
        ''.join(links.output), strip=True,
        tags={'p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'img', 'pre', 'code', 'blockquote',
              'ul', 'ol', 'li', 'strong', 'em', 'del', 's', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
              'dl', 'dt', 'dd', 'details', 'summary', 'kbd', 'sup', 'sub', 'div', 'span'},
        attributes={'*': ['id'], 'a': ['href', 'title'], 'img': ['src', 'alt', 'title', 'width', 'height'],
                    'code': ['class'], 'div': ['class', 'tabindex'], 'span': ['class'], 'ol': ['start'], 'th': ['align'], 'td': ['align']},
        protocols={'http', 'https', 'mailto'},
    )
    toc = []
    def headings(tokens):
        for token in tokens:
            if token['level'] <= 3:
                toc.append({'id': token['id'], 'name': strip_tags(token['name']), 'level': token['level']})
            headings(token.get('children', []))
    headings(converter.toc_tokens)
    return mark_safe(clean), toc
