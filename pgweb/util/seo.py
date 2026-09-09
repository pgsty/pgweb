"""Page metadata and plain-text summaries shared by public content views."""

from functools import lru_cache
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import re

import yaml


METADATA_FILE = Path(__file__).resolve().parents[2] / 'data' / 'page_metadata.yaml'
_SPACE = re.compile(r'\s+')
_SOURCE_FIELD = re.compile(
    r'^(?:原文(?:链接)?|来源|发布日期|发布时间|作者|Source|Original(?: article)?|Published|Author)\s*[:：]|'
    r'^原文\s*https?://', re.I,
)
_BOILERPLATE = re.compile(r'^(?:Copyright\b|版权|版权所有|Table of Contents\b|目录\s*$|Synopsis\s*$)', re.I)


def clean_text(value):
    # Older imported manuals contain another escaped layer of HTML entities.
    for _ in range(2):
        decoded = unescape(value)
        if decoded == value:
            break
        value = decoded
    return _SPACE.sub(' ', value).strip()


class _SummaryParser(HTMLParser):
    excluded_tags = {'script', 'style', 'head', 'nav', 'footer', 'form', 'pre', 'table'}
    excluded_classes = {
        'navheader', 'navfooter', 'toc', 'lot', 'refsynopsisdiv', 'synopsis',
        'programlisting', 'screen', 'copyright', 'legalnotice',
    }
    void_tags = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.paragraphs = []
        self.plain = []
        self.had_paragraph = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        excluded = (
            any(frame[1] for frame in self.stack) or
            tag in self.excluded_tags or
            bool(set(attrs.get('class', '').split()) & self.excluded_classes) or
            bool(re.fullmatch('h[1-6]', tag))
        )
        if tag in self.void_tags:
            if tag in {'br', 'hr'}:
                self.handle_data(' ')
            return
        if tag == 'p':
            self.had_paragraph = True
        paragraph = {'parts': [], 'has_prose': False} if tag == 'p' and not excluded else None
        self.stack.append((tag, excluded, paragraph))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void_tags:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for _, _, paragraph in self.stack[i:]:
                    if paragraph is not None and paragraph['has_prose']:
                        self.paragraphs.append(clean_text(''.join(paragraph['parts'])))
                del self.stack[i:]
                return

    def handle_data(self, data):
        if any(frame[1] for frame in self.stack):
            return
        self.plain.append(data)
        outside_link = not any(frame[0] == 'a' for frame in self.stack)
        for _, _, paragraph in self.stack:
            if paragraph is not None:
                paragraph['parts'].append(data)
                if outside_link and clean_text(data):
                    paragraph['has_prose'] = True


def summarize_html(content, max_length=180):
    """Select prose, excluding navigation, syntax and migrated source fields."""
    if not content or max_length <= 0:
        return ''
    parser = _SummaryParser()
    parser.feed(str(content))
    parser.close()
    for _, _, paragraph in parser.stack:
        if paragraph is not None and paragraph['has_prose']:
            parser.paragraphs.append(clean_text(''.join(paragraph['parts'])))
    candidates = parser.paragraphs
    if not candidates and not parser.had_paragraph:
        candidates = [clean_text(''.join(parser.plain))]
    candidates = [text for text in candidates if text and not _SOURCE_FIELD.search(text) and not _BOILERPLATE.search(text)]
    if not candidates:
        return ''
    text = candidates[0]
    if len(text) <= max_length:
        return text
    excerpt = text[:max_length - 1]
    # Prefer a complete sentence without reducing a useful summary to a label.
    stops = list(re.finditer(r'[。！？]|[.!?](?=\s)', excerpt))
    if stops and stops[-1].end() >= max_length // 2:
        return excerpt[:stops[-1].end()]
    if not re.search(r'[\u3400-\u9fff]', excerpt) and ' ' in excerpt:
        excerpt = excerpt.rsplit(' ', 1)[0]
    return excerpt.rstrip() + '…'


@lru_cache(maxsize=1)
def _load_page_metadata(filename, modified):
    with open(filename, encoding='utf8') as stream:
        return (yaml.safe_load(stream) or {}).get('pages', {})


def page_metadata(path):
    """Read reviewed static-page metadata; dynamic entities provide their own og."""
    try:
        modified = METADATA_FILE.stat().st_mtime_ns
    except FileNotFoundError:
        return {}
    metadata = _load_page_metadata(str(METADATA_FILE), modified).get(path, {})
    if not metadata:
        return {}
    result = dict(metadata)
    result.setdefault('canonical', path)
    return result
