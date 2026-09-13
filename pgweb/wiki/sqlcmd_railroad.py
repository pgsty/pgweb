"""Railroad diagrams from the handbook's synopsis, without a second grammar source.

The HTML distinguishes replaceable names from literal SQL; phrase spans introduce
named productions. Brackets, braces, bars and ellipses follow notation.html.
Parentheses remain SQL tokens, but bound choices/repetitions within their contents.
Rendering is cached by syntax, so identical snapshots share the expensive work.
"""

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from io import StringIO
import re

from bs4 import BeautifulSoup
import railroad as rr


@dataclass(frozen=True)
class Node:
    kind: str
    text: str = ''
    children: tuple = ()


def container(kind, children):
    children = tuple(children)
    return children[0] if len(children) == 1 and kind in ('seq', 'choice') else Node(kind, children=children)


TOKEN = re.compile(r'\ue100(\d+)\ue101|\.\.\.|…|[\[\]{}|(),\'=]|[^\s\[\]{}|(),\'=\ue100]+')
MARKER = re.compile(r'\ue000(\d+)\ue001')


def tokenize(text, names):
    return [Node('var', names[int(m[1])]) if m[1] is not None else Node('text', m[0])
            for m in TOKEN.finditer(text)]


def repeat_start(items, comma, rules):
    """Find the list item before [...]: include its arguments and modifiers.

    A list item's replaceables and optional modifiers form a unit, e.g.
    expression [ASC|DESC], name(args), or window_name AS (window_definition).
    Clause introducers are outside it. Explicit { ... } units take precedence.
    """
    if not items:
        raise ValueError('Repetition has no preceding item')
    if items[-1].kind == 'group':
        return len(items) - 1
    if not comma and items[0].text == 'FOR':
        return 0
    start = len(items) - 1
    # Modifiers after the required item repeat with it, including modifiers
    # made only of keywords (ASC/DESC, NULLS FIRST/LAST, or a table's '*').
    while start and items[start].kind == 'optional':
        start -= 1
    if items[start].kind == 'group' or (items[start].kind == 'var' and items[start].text in rules):
        return start
    while start > 0:
        previous = items[start - 1]
        if previous.kind == 'var':
            start -= 1
        elif previous.kind == 'group':
            if items[start].kind == 'paren' or any(n.kind == 'var' for n in walk(previous)):
                start -= 1
            break
        elif previous.kind == 'optional':
            # Optional argument modes/names and ONLY belong to a list item;
            # command switches such as IF EXISTS do not.
            if any(n.kind == 'var' or n.text == 'ONLY' for n in walk(previous)):
                start -= 1
            else:
                break
        elif previous.text in ('=', 'AS', 'WITH') and start > 1 and items[start - 2].kind == 'var':
            start -= 1
        else:
            break
    return start


def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)


class Parser:
    def __init__(self, tokens, rules=frozenset()):
        self.tokens, self.pos = tokens, 0
        self.rules = rules

    def parse(self, end=''):
        alternatives, items = [], []
        while self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            text = token.text if token.kind == 'text' else ''
            if text == end and end:
                self.pos += 1
                return container('choice', alternatives + [container('seq', items)])
            if text in (']', '}', ')'):
                raise ValueError('Unexpected closing token ' + text)
            if text == '|':
                alternatives.append(container('seq', items))
                items = []
                self.pos += 1
                continue
            # PostgreSQL's abbreviated lists x [, ...] and x [...] repeat the
            # preceding unit; neither the comma nor dots is an optional SQL item.
            tail = [n.text for n in self.tokens[self.pos:self.pos + 4]]
            marker = (3 if tail[:3] == ['[', '...', ']'] else
                      4 if tail == ['[', ',', '...', ']'] else 0)
            if marker or text in ('...', '…'):
                comma = marker == 4
                start = repeat_start(items, comma, self.rules)
                unit = container('seq', items[start:])
                repeat = Node('repeat', ',' if comma else '', (unit,))
                # CALL ([argument] [, ...]) is a possibly empty argument list;
                # the comma accompanies another argument, never an empty item.
                if unit.kind == 'optional':
                    repeat = Node('optional', children=(Node('repeat', repeat.text, unit.children),))
                items[start:] = [repeat]
                self.pos += marker or 1
                continue
            self.pos += 1
            if text == "'":
                literal = []
                while self.pos < len(self.tokens) and self.tokens[self.pos].text != "'":
                    literal.append(self.tokens[self.pos])
                    self.pos += 1
                if self.pos == len(self.tokens):
                    raise ValueError('Unclosed quoted value')
                self.pos += 1
                items.append(Node('quoted', children=(container('seq', literal),)))
            elif text in ('[', '{', '('):
                child = self.parse({'[': ']', '{': '}', '(': ')'}[text])
                kind = {'[': 'optional', '{': 'group', '(': 'paren'}[text]
                items.append(Node(kind, children=(child,)))
            else:
                items.append(token)
        if end:
            raise ValueError('Missing closing token ' + end)
        return container('choice', alternatives + [container('seq', items)])


def top_lines(text):
    """Logical lines with nesting depth, retaining source indentation."""
    depth = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        before = depth
        depth += sum(line.count(c) for c in '[{(') - sum(line.count(c) for c in ']})')
        yield before, len(line) - len(line.lstrip()), stripped


def has_top_bar(lines):
    depth = 0
    for _, _, line in lines:
        for index, char in enumerate(line):
            if char in '[{(':
                depth += 1
            elif char in ']})':
                depth -= 1
            elif char == '|' and depth == 0 and index in (0, len(line) - 1):
                return True
    return False


@lru_cache(maxsize=512)
def productions(html, name):
    soup = BeautifulSoup(html, 'html.parser')
    phrases, names = [], []
    for phrase in soup.select('.phrase'):
        var = phrase.select_one('.replaceable')
        phrases.append((var.get_text(' ', strip=True) if var else '', phrase.get_text(' ', strip=True)))
        phrase.replace_with('\n\ue000{}\ue001\n'.format(len(phrases) - 1))
    for var in soup.select('.replaceable'):
        names.append(var.get_text(' ', strip=True))
        var.replace_with('\ue100{}\ue101'.format(len(names) - 1))
    text = soup.get_text()
    parts = MARKER.split(text)
    blocks = [('', '', parts[0])]
    for i in range(1, len(parts), 2):
        key, label = phrases[int(parts[i])]
        if not key and label.lower().strip(':：') in ('or', '或') and blocks:
            old_key, old_label, body = blocks[-1]
            blocks[-1] = (old_key, old_label, body + '\n|\n' + parts[i + 1])
        else:
            blocks.append((key, label, parts[i + 1]))

    result = []
    # Some handbooks put a short command form after the named productions
    # (TABLE after SELECT, legacy VACUUM). It remains a main command form.
    verbs = {name.split()[0]}
    if name == 'SELECT':
        verbs.add('TABLE')
    if name.startswith('SET '):
        verbs.add('RESET')
    rule_names = frozenset(key for key, _ in phrases if key)
    for key, label, body in blocks:
        main_extra, kept = [], []
        extra = False
        for depth, indent, line in top_lines(body):
            if key and depth == 0 and indent == 0 and line.split()[0] in verbs:
                extra = True
            (main_extra if extra else kept).append((depth, indent, line))
        entries = [(key, label, kept)]
        if main_extra:
            entries.append(('', '', main_extra))
        for key, label, lines in entries:
            if not lines:
                continue
            # Root command forms are alternatives; named productions explicitly
            # saying 'one of/can be' also use unbarred, aligned alternatives.
            implicit_choice = bool(re.search(r'之一|可以|can be|one of', label))
            has_bar = has_top_bar(lines)
            indents = [indent for d, indent, l in lines if d == 0 and not l.startswith('|')]
            # A few translated lines lost their indentation; the predominant
            # level still separates alternatives from deeper continuations.
            base = (Counter(indents).most_common(1)[0][0] if key and indents else min(indents, default=0))
            forms, current = [], []
            for depth, indent, line in lines:
                split = depth == 0 and current and (
                    (not key and indent == base and not line.startswith(('[', '|'))
                     and line.split()[0] in verbs
                     and any(s.split()[0] in verbs for s in current)) or
                    (key and implicit_choice and not has_bar and indent <= base))
                # Continuation lines in implicit lists are indented further.
                if split:
                    forms.append('\n'.join(current))
                    current = []
                current.append(line)
            forms.append('\n'.join(current))
            asts = [Parser(tokenize(form, names), rule_names).parse() for form in forms]
            if key:
                result.append({'key': key, 'label': key, 'note': label,
                               'node': container('choice', asts), 'source': '\n'.join(forms)})
            else:
                result.extend({'key': '', 'label': name, 'note': label, 'node': ast, 'source': form}
                              for form, ast in zip(forms, asts))
    return tuple(result)


def sequence(items, width):
    if not items:
        return rr.Skip()
    rows, row, used = [], [], 0
    for item in items:
        size = item.width + (20 if item.needsSpace else 0)
        if row and used + size > width - 40:
            rows.append(rr.Sequence(*row))
            row, used = [], 0
        row.append(item)
        used += size
    rows.append(rr.Sequence(*row))
    return rows[0] if len(rows) == 1 else rr.Stack(*rows)


def choice(items):
    """Keep wrapped branches inside their bounds (railroad-diagrams 3.0.1).

    The library's Choice.down calculation omits the last branch's height.
    That works for single-line branches, but overlaps following stations when a
    branch is a Stack. Match Choice.format's actual branch positions instead.
    """
    diagram = rr.Choice(0, *items)
    offset, bottom = 0, items[0].height + items[0].down
    for index, item in enumerate(items[1:], 1):
        previous = items[index - 1]
        offset += max(rr.AR * (2 if index == 1 else 1), previous.height + previous.down + rr.VS + item.up)
        bottom = max(bottom, offset + item.height + item.down)
    diagram.down = bottom - diagram.height
    return diagram


class Reference(rr.NonTerminal):
    def format(self, x, y, width):
        super().format(x, y, width)
        # 3.0.1 appends linked text twice; retain one label per station.
        for child in self.children:
            if (isinstance(child, rr.DiagramItem) and child.name == 'a'
                    and len(child.children) == 2 and child.children[0] is child.children[1]):
                child.children.pop()
        return self


def draw(node, keys, width=540):
    kind = node.kind
    if kind == 'var':
        return Reference(node.text, href='#rr-rule-' + node.text if node.text in keys else None)
    if kind == 'text':
        return rr.Terminal(node.text)
    if kind == 'group':
        return draw(node.children[0], keys, width)
    if kind == 'optional':
        return choice([rr.Skip(), draw(node.children[0], keys, max(260, width - 40))])
    if kind == 'repeat':
        return rr.OneOrMore(draw(node.children[0], keys, max(260, width - 40)),
                            rr.Terminal(',') if node.text else rr.Skip())
    if kind == 'choice':
        return choice([draw(c, keys, max(260, width - 40)) for c in node.children])
    if kind in ('paren', 'quoted'):
        left, right = ('(', ')') if kind == 'paren' else ("'", "'")
        return sequence([rr.Terminal(left), draw(node.children[0], keys, width - 60), rr.Terminal(right)], width)
    # Put adjacent literal keywords on one station, retaining punctuation.
    children = []
    for child in node.children:
        if (children and child.kind == children[-1].kind == 'text'
                and re.fullmatch(r'[A-Z_ ]+', children[-1].text) and re.fullmatch(r'[A-Z_]+', child.text)):
            children[-1] = Node('text', children[-1].text + ' ' + child.text)
        else:
            children.append(child)
    return sequence([draw(c, keys, width) for c in children], width)


@lru_cache(maxsize=512)
def diagrams(html, name):
    rules = productions(html, name)
    keys = frozenset(r['key'] for r in rules if r['key'])
    result = []
    main_number = 0
    for rule in rules:
        main_number += not bool(rule['key'])
        diagram = rr.Diagram(draw(rule['node'], keys))
        diagram.attrs.update({'role': 'img', 'aria-label': rule['label'] + ' 语法铁道图',
                              'xmlns': 'http://www.w3.org/2000/svg'})
        out = StringIO()
        diagram.writeSvg(out.write)
        # SVG2 href works both in HTML and standalone XML, without xlink setup.
        svg = out.getvalue().replace('xlink:href=', 'href=')
        result.append({'key': rule['key'] or 'form-' + str(main_number),
                       'label': rule['label'], 'main': not bool(rule['key']),
                       'number': main_number, 'svg': svg})
    return tuple(result)


def context(snapshot, namespace):
    html, name = snapshot['synopsis_html'], snapshot['name']
    rows = []
    for rule in diagrams(html, name):
        rows.append({**rule, 'id': namespace + '-' + rule['key'],
                     'svg': rule['svg'].replace('#rr-rule-', '#' + namespace + '-')})
    return {'rules': rows, 'digest': sha256(html.encode()).hexdigest()[:16],
            'forms': sum(row['main'] for row in rows),
            'definitions': sum(not row['main'] for row in rows)}
