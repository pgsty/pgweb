"""百科正文的 Markdown 渲染。

不复用 `pgweb.util.markup.pgmarkdown`：那份的标签白名单没有 table，也没有开
tables / fenced_code / attr_list 扩展，而百科正文里三者都要用。清洗仍走同一套
bleach Cleaner，输入是本站自己导入的仓库内容，白名单按 Markdown 的产物给。
"""

import re

import markdown
from bleach.sanitizer import Cleaner


TAGS = [
    'h3', 'h4', 'h5', 'h6',
    'p', 'br', 'hr', 'div', 'span', 'blockquote',
    'strong', 'em', 'b', 'i', 'code', 'pre', 'sub', 'sup',
    'ul', 'ol', 'li', 'dl', 'dt', 'dd',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'a',
]

ATTRS = {
    '*': ['id', 'class'],
    'a': ['href', 'title', 'rel', 'target'],
    'th': ['align', 'colspan', 'rowspan', 'scope'],
    'td': ['align', 'colspan', 'rowspan'],
}

_cleaner = Cleaner(tags=TAGS, attributes=ATTRS, strip=False)

# 正文里 `## 标题 {#anchor}` 的小节分隔。
SECTION = re.compile(r'^##[ \t]+(?P<heading>.+?)(?:[ \t]*\{#(?P<anchor>[A-Za-z0-9_-]+)\})?[ \t]*$', re.M)

# generate.py 写进正文的标记块。事实表改由数据库渲染，所以整块摘掉；
# 片段块保留内容，只把标记换成一个可加样式的容器。
FACTS_BLOCK = re.compile(r'\n?<!--\s*BEGIN SQLSTATE FACTS.*?<!--\s*END SQLSTATE FACTS\s*-->\n?', re.S)
INDEX_BLOCK = re.compile(r'<!--\s*(BEGIN|END) SQLSTATE (INDEX|COVERAGE)[^>]*-->\n?')
SNIPPET_BEGIN = re.compile(r'<!--\s*BEGIN SQLSTATE SNIPPET:\s*(?P<id>[A-Za-z0-9_.-]+)\s*-->\n?')
SNIPPET_END = re.compile(r'<!--\s*END SQLSTATE SNIPPET\s*-->\n?')
COMMENT = re.compile(r'<!--.*?-->\n?', re.S)


def render(text):
    """把一段 Markdown 渲染成清洗过的 HTML。"""
    html = markdown.markdown(text, extensions=['tables', 'fenced_code', 'attr_list', 'sane_lists'])
    return _cleaner.clean(html)


def strip_generated(body):
    """摘掉生成块标记。事实表整块拿掉，片段块保留正文。"""
    body = FACTS_BLOCK.sub('\n', body)
    body = INDEX_BLOCK.sub('', body)
    body = SNIPPET_BEGIN.sub('', body)
    body = SNIPPET_END.sub('', body)
    return COMMENT.sub('', body)


def snippet_ids(body):
    return SNIPPET_BEGIN.findall(body)


def split_sections(body):
    """按 `## 标题 {#anchor}` 切成有序小节。

    返回 [{anchor, heading, markdown}]；标题之前的引言（正文里没有，但不做假设）
    归到一个 anchor 为空的前置小节里。
    """
    matches = list(SECTION.finditer(body))
    if not matches:
        lead = body.strip()
        return [{'anchor': '', 'heading': '', 'markdown': lead}] if lead else []

    sections = []
    lead = body[:matches[0].start()].strip()
    if lead:
        sections.append({'anchor': '', 'heading': '', 'markdown': lead})
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections.append({
            'anchor': match.group('anchor') or '',
            'heading': match.group('heading').strip(),
            'markdown': body[match.end():end].strip(),
        })
    return sections


# 行内标记：链接留文字，强调与代码号去掉。表格里的一句话说明是纯文本。
INLINE_LINK = re.compile(r'\[([^\]]*)\]\([^)]*\)')
INLINE_EMPHASIS = re.compile(r'(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1')


def plain(text):
    text = INLINE_LINK.sub(r'\1', text)
    text = INLINE_EMPHASIS.sub(r'\2', text)
    return text.replace('`', '')


def first_sentence(text):
    """正文第一段的第一句，用作索引页表格里的一句话说明。"""
    for block in text.split('\n\n'):
        block = block.strip()
        if not block or block.startswith(('<!--', '|', '#', '-', '*', '>', '```')):
            continue
        block = ' '.join(plain(block).split())
        parts = re.split(r'(?<=[。！？])', block)
        return (parts[0] if parts and parts[0].strip() else block).strip()
    return ''
