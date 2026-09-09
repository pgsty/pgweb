"""Markdown presentation for the ecosystem manuals (stored Markdown is unchanged)."""

from html import escape
from html.parser import HTMLParser
import re
import unicodedata
from xml.etree import ElementTree

import bleach
import markdown
from markdown.blockprocessors import ListIndentProcessor, OListProcessor, UListProcessor
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from pgweb.util.prose import ProseExtension


def heading_slug(text):
    # Hugo's GitHub-style IDs retain Unicode and use hyphens for duplicates.
    text = text.strip().lower()
    return ''.join('-' if c.isspace() else c for c in text
                   if c.isspace() or c in '_-' or unicodedata.category(c)[0] in 'LN')


class ExistingIDs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        self.ids.update(value for key, value in attrs if key in ('id', 'name') and value)


class HeadingIDs(Treeprocessor):
    def run(self, root):
        used = {e.get('id') for e in root.iter() if e.get('id')}
        existing = ExistingIDs()
        for block in self.md.htmlStash.rawHtmlBlocks:
            existing.feed(block)
        used.update(existing.ids)
        for element in root.iter():
            if element.tag not in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6') or element.get('id'):
                continue
            base = heading_slug(''.join(element.itertext())) or 'section'
            candidate, number = base, 0
            while candidate in used:
                number += 1
                candidate = '{}-{}'.format(base, number)
            used.add(candidate)
            element.set('id', candidate)


class Alerts(Treeprocessor):
    labels = {
        'NOTE': ('说明', 'Note'), 'TIP': ('提示', 'Tip'), 'IMPORTANT': ('重要', 'Important'),
        'WARNING': ('警告', 'Warning'), 'CAUTION': ('注意', 'Caution'),
    }

    def run(self, root):
        for block in root.iter('blockquote'):
            if not len(block) or block[0].tag != 'p':
                continue
            first = block[0]
            match = re.match(r'^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\](?:\s*\n|$)', first.text or '')
            if not match:
                continue
            kind = match.group(1)
            first.text = first.text[match.end():]
            if not first.text and not len(first):
                block.remove(first)
            block.set('class', 'pg-callout pg-callout--' + kind.lower())
            title = ElementTree.Element('p', {'class': 'pg-callout__title'})
            title.text = self.labels[kind][self.md.ecosystem_language == 'en']
            block.insert(0, title)


class ManualExtension(Extension):
    def extendMarkdown(self, md):
        # Hugo sources use two-space nested lists. Keep four-space indented
        # code semantics by changing only the list processors, not the parser.
        tab_length = md.tab_length
        md.tab_length = 2
        for name, processor, priority in (('indent', ListIndentProcessor, 90), ('olist', OListProcessor, 40), ('ulist', UListProcessor, 30)):
            md.parser.blockprocessors.register(processor(md.parser), name, priority)
        md.tab_length = tab_length
        md.treeprocessors.register(HeadingIDs(md), 'ecosystem_ids', 6)
        md.treeprocessors.register(Alerts(md), 'ecosystem_alerts', 4)


class DocumentLinks(HTMLParser):
    def __init__(self, resolver):
        super().__init__(convert_charrefs=False)
        self.resolver = resolver
        self.output = []

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.output.append('<div class="pg-table-scroll" tabindex="0">')
        values = []
        for key, value in attrs:
            if key in ('href', 'src'):
                value = self.resolver(value or '', asset=key == 'src')
            values.append(' {}="{}"'.format(key, escape(value or '', quote=True)))
        if tag == 'img':
            values.append(' loading="lazy" decoding="async"')
        self.output.append('<' + tag + ''.join(values) + '>')

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


def render_manual(content, language, resolver):
    converter = markdown.Markdown(
        extensions=['tables', 'fenced_code', 'toc', 'sane_lists', 'attr_list', 'def_list', 'footnotes', 'md_in_html', ManualExtension(), ProseExtension()],
        extension_configs={'toc': {'permalink': '#', 'permalink_class': 'pg-anchor',
                                  'permalink_title': '链接到本节' if language == 'zh' else 'Link to this section'}},
    )
    converter.ecosystem_language = language
    rendered = converter.convert(content)
    links = DocumentLinks(resolver)
    links.feed(rendered)
    clean = bleach.clean(
        ''.join(links.output), strip=True,
        tags={'p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'img', 'pre', 'code', 'blockquote',
              'ul', 'ol', 'li', 'strong', 'em', 'del', 's', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
              'dl', 'dt', 'dd', 'details', 'summary', 'kbd', 'sup', 'sub', 'div', 'span'},
        attributes={'*': ['id', 'class'], 'a': ['href', 'title', 'name'], 'div': ['tabindex'],
                    'img': ['src', 'alt', 'title', 'width', 'height', 'loading', 'decoding'],
                    'ol': ['start'], 'th': ['align', 'colspan', 'rowspan'], 'td': ['align', 'colspan', 'rowspan']},
        protocols={'http', 'https', 'mailto'},
    )
    # The site's shared code.js reads the language from <pre>.
    clean = re.sub(r'<pre><code class="language-([\w+-]+)">', r'<pre data-lang="\1"><code class="language-\1">', clean)
    toc = []

    def visit(tokens):
        for token in tokens:
            if token['level'] <= 3:
                toc.append({'id': token['id'], 'title': strip_tags(token['name']), 'level': token['level']})
            visit(token.get('children', []))

    visit(converter.toc_tokens)
    return mark_safe(clean), toc
