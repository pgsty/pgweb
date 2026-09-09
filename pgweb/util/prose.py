"""Shared Markdown presentation helpers for the site's prose pages.

Content rendered from Markdown (the ecosystem manuals, the extension
catalogue documents) is styled by the `.pg-prose` rules in pgcenter.css.
Those rules draw the site's trailing hairline after every second-level
heading with a flex `::after`, which only works when the heading's inline
content is one flex item: this treeprocessor wraps it in a span.
"""

from xml.etree import ElementTree

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor


class HeadingSpans(Treeprocessor):
    def run(self, root):
        for heading in root.iter('h2'):
            if len(heading) == 1 and heading[0].tag == 'span' and not heading.text and heading[0].get('class') == 'pg-h':
                continue
            span = ElementTree.Element('span', {'class': 'pg-h'})
            span.text = heading.text
            heading.text = None
            for child in list(heading):
                heading.remove(child)
                span.append(child)
            heading.append(span)


class ProseExtension(Extension):
    def extendMarkdown(self, md):
        # After the toc extension (priority 5) so its permalink anchor is
        # wrapped together with the heading text.
        md.treeprocessors.register(HeadingSpans(md), 'pg_prose_headings', 3)
