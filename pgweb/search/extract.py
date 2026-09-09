"""Extract definitions and full text from the locally served PostgreSQL manual.

No crawler, third-party manuals, runtime catalogs or guessed metadata are used.
Generated anchors are also applied by the document reader, without changing docs.
"""
import copy
import hashlib
import itertools
import re
from functools import lru_cache
from urllib.parse import urljoin

import bleach
from bs4 import BeautifulSoup, Tag

from .taxonomy import normalize_name

PIPELINE_VERSION = '3'
SECTIONS = ('chapter', 'sect1', 'sect2', 'sect3', 'sect4', 'sect5', 'refentry',
            'refsect1', 'refsect2', 'refsect3', 'appendix', 'part', 'preface')
TAGS = frozenset(('a', 'p', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'code', 'pre',
                  'em', 'strong', 'b', 'i', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'thead',
                  'tbody', 'tr', 'td', 'th', 'br', 'hr', 'blockquote', 'sub', 'sup', 'img', 'kbd', 'samp'))
SPACE = re.compile(r'\s+')
NUMBERED = re.compile(r'^(?:(?:Chapter|Appendix|Part)\s+[\w.]+\.?\s*|(?:[A-Z]\.)?\d+(?:\.\d+)*\.?\s*)', re.I)
SPECIAL_SYNTAX = frozenset(('COALESCE', 'NULLIF', 'GREATEST', 'LEAST', 'CASE', 'GROUPING',
                            'COLLATION FOR', 'CURRENT_DATE', 'CURRENT_TIME', 'CURRENT_TIMESTAMP',
                            'LOCALTIME', 'LOCALTIMESTAMP', 'CURRENT_USER', 'SESSION_USER', 'CURRENT_ROLE'))
# Reader-oriented names for definitions whose technical identifier is never translated.
GUC_ALIASES = {
    'shared_buffers': ('共享缓冲区', '共享内存缓冲区'),
    'work_mem': ('工作内存',), 'max_connections': ('最大连接数',),
    'search_path': ('模式搜索路径',), 'statement_timeout': ('语句超时',),
    'lock_timeout': ('锁超时',), 'wal_level': ('WAL级别',),
}


def text(node):
    # Do not insert spaces at every inline tag in Chinese prose.
    return SPACE.sub(' ', node.get_text() if isinstance(node, Tag) else str(node)).strip().strip('#').strip()


def title_text(node):
    return NUMBERED.sub('', text(node)).strip()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def source_hash(title, content):
    return digest(PIPELINE_VERSION + '\0' + (title or '') + '\0' + (content or ''))


def add_anchors(soup):
    used = {node['id'] for node in soup.select('[id]')}
    for node in soup.select('dt, tbody tr, p.func_signature, h1, h2, h3, h4, h5, h6, .refnamediv'):
        if node.get('id'):
            continue
        # Text hashes survive unrelated insertions; identical definitions get a suffix.
        base = 'SEARCH-' + digest(node.name + '\0' + text(node))[:16]
        anchor = base
        n = 1
        while anchor in used:
            n += 1
            anchor = base + '-' + str(n)
        node['id'] = anchor
        used.add(anchor)
    return soup


@lru_cache(maxsize=64)
def reading_html(content):
    return str(add_anchors(BeautifulSoup(content or '', 'html.parser')))


def is_section(node):
    return isinstance(node, Tag) and node.attrs is not None and bool(set(node.get('class', ())).intersection(SECTIONS))


def heading_for(node, fallback):
    headings = []
    for parent in reversed(list(node.parents)):
        if is_section(parent):
            heading = parent.find(re.compile('^h[1-6]$'))
            if heading:
                value = title_text(heading)
                if value and value not in headings:
                    headings.append(value)
    return ' › '.join(headings[-3:]) or fallback


def anchor_for(node):
    if node.get('id'):
        return node['id']
    link = node.select_one('a.id_link[href^="#"]')
    if link:
        return link['href'][1:]
    if node.select_one('[id]'):
        return node.select_one('[id]')['id']
    parent = node.find_parent(id=True)
    return parent['id'] if parent else ''


def preview_html(nodes, url):
    markup = ''.join(str(node) for node in nodes)
    soup = BeautifulSoup(markup, 'html.parser')
    for node in soup.select('script, style, .toc, .navheader, .navfooter, a.indexterm, a.id_link'):
        node.decompose()
    for node in soup.select('a[href], img[src]'):
        attr = 'href' if node.name == 'a' else 'src'
        node[attr] = urljoin(url, node[attr])
    # Table rows and cells must have legal wrappers when inserted into a div.
    first = next((n for n in soup.contents if isinstance(n, Tag)), None)
    markup = str(soup)
    if first and first.name == 'tr':
        markup = '<table><tbody>' + markup + '</tbody></table>'
    elif first and first.name in ('td', 'th'):
        markup = '<table><tbody><tr>' + markup + '</tr></tbody></table>'
    elif first and first.name in ('dt', 'dd'):
        markup = '<dl>' + markup + '</dl>'
    return bleach.clean(markup, tags=TAGS, attributes={
        '*': ['class'], 'a': ['href', 'title'], 'td': ['colspan', 'rowspan'],
        'th': ['colspan', 'rowspan'], 'img': ['src', 'alt', 'width', 'height'],
    }, protocols=['http', 'https', 'mailto'], strip=True)


def definition_nodes(dt):
    nodes = [dt]
    for sibling in dt.next_siblings:
        if isinstance(sibling, Tag):
            if sibling.name != 'dd':
                break
            nodes.append(sibling)
    return nodes


def extract_page(filename, title, content, version):
    soup = add_anchors(BeautifulSoup(content or '', 'html.parser'))
    for node in soup.select('.navheader, .navfooter, .toc, script, style'):
        node.decompose()
    page_title = title_text(title or filename)
    url = '/docs/{}/{}'.format(version, filename)
    entries = {}

    def emit(kind, name, node, nodes=None, aliases=(), signature='', subtype='', entity_key=None, key_suffix=''):
        name = SPACE.sub(' ', name).strip()
        if not name or len(name) > 500:
            return
        anchor = anchor_for(node)
        nodes = nodes or [node]
        body = '\n'.join(text(n) for n in nodes)
        if not body:
            return
        name_key = normalize_name(name)
        names = set(normalize_name(v) for v in aliases if v and v.strip())
        names.add(name_key)
        # Compact identifier aliases are explicit index entries, not fuzzy symbol matching.
        if re.fullmatch('[a-z][a-z0-9_]+', name_key) and '_' in name_key:
            names.add(name_key.replace('_', ''))
        if kind == 'function':
            names.add(name_key + '()')
        key = digest(kind + '\0' + name + '\0' + anchor + key_suffix)
        entry = {
            'key': key, 'entity_key': entity_key or kind + ':' + name_key,
            'kind': kind, 'subtype': subtype, 'name': name, 'name_key': name_key,
            'aliases': sorted(names), 'anchor': anchor,
            'heading': heading_for(node, page_title), 'signature': signature,
            'body': body, 'preview': preview_html(nodes, url),
        }
        entries.setdefault(key, entry)

    # SQL reference entries and executable tools.
    namediv = soup.select_one('.refnamediv')
    if namediv:
        name = namediv.select_one('.refentrytitle') or namediv.find(re.compile('^h[1-6]$'))
        synopsis = soup.select_one('.refsynopsisdiv')
        nodes = [namediv] + ([synopsis] if synopsis else [])
        if filename.startswith('sql-'):
            emit('sql', text(name), namediv, nodes)
        elif filename.startswith(('app-', 'postgres', 'pg-')):
            emit('tool', text(name), namediv, nodes)

    # Parameter definitions, psql slash commands, libpq and utility options.
    for dt in soup.select('dt'):
        identifier = dt.get('id', '')
        nodes = definition_nodes(dt)
        variables = dt.select('code.varname')
        if identifier.startswith('GUC-') and variables:
            for var in variables:
                emit('guc', text(var), dt, nodes, aliases=GUC_ALIASES.get(text(var), ()), signature=text(dt))
        elif filename == 'app-psql.html' and text(dt).startswith('\\'):
            names = re.findall(r'\\(?:[A-Za-z]+|[^\s\w\[\]{}])', text(dt))
            if names:
                # \d[S+] documents \d, \dS, \d+ and \dS+ as one definition.
                aliases = list(names)
                for name in names:
                    flags = re.search(re.escape(name) + r'\s*\[([A-Za-z+]+)\]', text(dt))
                    if flags:
                        for size in range(1, len(flags[1]) + 1):
                            aliases.extend(name + ''.join(parts) for parts in itertools.combinations(flags[1], size))
                emit('psql', names[0], dt, nodes, aliases=aliases, signature=text(dt))
        elif identifier.startswith('LIBPQ-CONNECT-') and dt.select_one('code.literal'):
            emit('option', text(dt.select_one('code.literal')), dt, nodes, subtype='connection')
        elif dt.select('code.option') and filename.startswith(('app-', 'postgres')):
            options = [text(n) for n in dt.select('code.option')]
            tool = page_title
            emit('option', tool + ' ' + options[-1], dt, nodes,
                 aliases=[tool + ' ' + n for n in options], signature=text(dt), subtype='cli')
        elif filename == 'sql-createtable.html' and variables:
            emit('option', text(variables[0]), dt, nodes, subtype='storage')

    for li in soup.select('li.listitem') if filename == 'libpq-envars.html' else ():
        env = li.select_one('code.envar')
        if env:
            emit('option', text(env), li, subtype='environment')

    # Function/operator definitions: only inside tbody, never mentions or table headers.
    for sig in soup.select('tbody .func_signature'):
        td = sig.find_parent('td')
        if not td:
            continue
        fns = sig.select('code.function')
        for fn in fns:
            name = text(fn)
            kind = 'syntax' if name.upper() in SPECIAL_SYNTAX else 'function'
            subtype = ('aggregate' if 'aggregate' in filename else 'window' if 'window' in filename else '')
            emit(kind, name, sig, [td], signature=text(sig), subtype=subtype)
        if not fns:
            for literal in sig.select('code.literal'):
                name = text(literal)
                if re.fullmatch(r'[+*/<>=~!@#%^&|?\-]+', name):
                    emit('operator', name, sig, [td], signature=text(sig))
                elif name.upper() in SPECIAL_SYNTAX:
                    emit('syntax', name, sig, [td], signature=text(sig))

    # Error rows have a deterministic row anchor shared with the reader.
    if filename == 'errcodes-appendix.html':
        for row in soup.select('tbody tr'):
            cells = row.find_all('td', recursive=False)
            if len(cells) == 2 and re.fullmatch('[0-9A-Z]{5}', text(cells[0])):
                emit('error', text(cells[0]), row, aliases=[text(cells[1])], signature=text(cells[1]))

    # The overview table includes canonical type names and documented aliases.
    if filename in ('datatype.html', 'datatype-pseudo.html'):
        for row in soup.select('tbody tr'):
            cells = row.find_all('td', recursive=False)
            if len(cells) < 2 or not cells[0].select_one('code.type'):
                continue
            name = re.split(r'\s*[\[(]', text(cells[0]), 1)[0].strip()
            aliases = [re.split(r'\s*[\[(]', text(n), 1)[0].strip() for n in cells[1].select('code.type')]
            if name in ('time', 'timestamp'):
                if 'with time zone' in text(cells[0]):
                    name += ' with time zone'
                else:
                    aliases.append(name)
                    name += ' without time zone'
            emit('type', name, row, aliases=aliases,
                 subtype='shorthand' if 'serial' in name else 'pseudo' if 'pseudo' in filename else '')

    if filename == 'rangetypes.html':
        for item in soup.select('li.listitem'):
            for value in item.select('code.type'):
                name = text(value)
                if re.fullmatch(r'(?:int[48]|num|ts|tstz|date)(?:multi)?range', name):
                    emit('type', name, item, subtype='multirange' if 'multi' in name else 'range')

    for heading in soup.select('h1, h2, h3, h4, h5, h6'):
        if filename.startswith(('queries-', 'sql-', 'functions-')):
            for literal in heading.select('code.literal'):
                name = text(literal)
                if re.fullmatch(r'[A-Z]+(?: [A-Z]+)*', name):
                    parent = next((p for p in heading.parents if is_section(p)), heading)
                    fragment = copy.copy(parent)
                    for nested in list(fragment.find_all(is_section)):
                        nested.decompose()
                    emit('syntax', name, heading, [fragment])
        name_node = heading.select_one('code.structname')
        if name_node and (filename.startswith(('catalog-', 'view-', 'infoschema-', 'monitoring-'))):
            name = text(name_node)
            if filename.startswith('infoschema-'):
                name = 'information_schema.' + name
            parent = next((p for p in heading.parents if is_section(p)), heading)
            # A relation preview shows the introduction and the first columns, not a whole chapter.
            fragment = copy.copy(parent)
            for nested in list(fragment.find_all(is_section)):
                nested.decompose()
            emit('relation', name, heading, [fragment], subtype='catalog' if filename.startswith('catalog-') else 'view')

    # Module/language/AM entry points from the official manual only.
    first_heading = soup.find(re.compile('^h[1-6]$'))
    if first_heading:
        module = re.match(r'^([a-z][a-z0-9_-]+)(?:\s*[—–]|$)', page_title)
        if module and re.match(r'^[A-Z]\.\d+\.', text(title)):
            root = next((p for p in first_heading.parents if is_section(p)), first_heading)
            intro = [first_heading] + root.find_all('p', recursive=False)[:4]
            emit('extension', module.group(1), first_heading, intro)
        language_names = {'plpgsql.html': ('PL/pgSQL', 'plpgsql'), 'plpython.html': ('PL/Python', 'plpython3u'),
                          'plperl.html': ('PL/Perl', 'plperl'), 'pltcl.html': ('PL/Tcl', 'pltcl')}
        if filename in language_names:
            name, alias = language_names[filename]
            emit('language', name, first_heading, aliases=[alias])
        am_names = {'btree.html': 'btree', 'gin.html': 'gin', 'gist.html': 'gist',
                    'spgist.html': 'spgist', 'brin.html': 'brin', 'hash-index.html': 'hash'}
        if filename in am_names:
            emit('am', am_names[filename], first_heading, aliases=[page_title, 'B-tree' if filename == 'btree.html' else page_title])

    # Full text: local contents of each structural section, excluding nested sections.
    # Long sections are split at block boundaries; each fragment retains its section heading.
    sections = soup.find_all(is_section)
    if not sections:
        sections = [soup]
    for section in sections:
        local = copy.copy(section)
        for child in list(local.find_all(is_section)):
            child.decompose()
        if not text(local):
            continue
        heading = local.find(re.compile('^h[1-6]$'))
        name = title_text(heading) if heading else page_title
        anchor_node = heading or section
        # Recursively unwrap large containers without dropping prose around their tables.

        def split_blocks(block):
            if not text(block):
                return
            if not isinstance(block, Tag):
                wrapper = soup.new_tag('p')
                wrapper.string = str(block)
                yield wrapper
            elif len(text(block)) <= 5000 or block.name in ('p', 'pre', 'tr', 'dt', 'dd'):
                yield block
            else:
                for child in block.children:
                    yield from split_blocks(child)

        blocks = [block for child in local.children for block in split_blocks(child)]
        if not blocks:
            blocks = [local]
        chunks, chunk, length = [], [], 0
        for block in blocks:
            if chunk and length + len(text(block)) > 5000:
                chunks.append(chunk)
                chunk, length = [], 0
            chunk.append(block)
            length += len(text(block))
        if chunk:
            chunks.append(chunk)
        for i, chunk in enumerate(chunks):
            # Use a row anchor when the chunk starts with a definition inside a large table.
            target = chunk[0] if chunk[0].get('id') else anchor_node
            emit('guide', name, target, chunk,
                 entity_key='guide:' + filename + ':' + anchor_for(anchor_node),
                 key_suffix='\0' + digest('\n'.join(text(block) for block in chunk)))
    return list(entries.values())
