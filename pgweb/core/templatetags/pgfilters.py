from django.template.defaultfilters import stringfilter
from django import template, forms
from django.utils.safestring import mark_safe
from django.template.loader import get_template
from django.conf import settings

from decimal import Decimal
import os
from pathlib import Path
import json
import re
import pynliner
import babel

register = template.Library()


@register.filter(name='class_name')
def class_name(ob):
    return ob.__class__.__name__


@register.filter(is_safe=True)
def field_class(value, arg):
    if 'class' in value.field.widget.attrs:
        c = arg + ' ' + value.field.widget.attrs['class']
    else:
        c = arg
    return value.as_widget(attrs={"class": c})


@register.filter(name='startswith')
def startswith(value, prefix):
    """True when the string value begins with prefix (used for nav state)."""
    try:
        return str(value).startswith(str(prefix))
    except Exception:
        return False


# Top navigation highlight: section key -> (prefixes that match, prefixes
# that belong to another entry even though they share the path).
_NAV_SECTIONS = {
    'home': ((), ()),
    'info': (('/info/',), ()),
    'about': (('/about/',), ()),
    'download': (('/download/', '/ftp/', '/ext/', '/e/'), ()),
    'docs': (('/docs/',), ()),
    'wiki': (('/wiki/',), ()),
    'community': (('/community/',), ()),
    'developer': (('/developer/',), ()),
    'support': (('/support/',), ()),
    'account': (('/account/',), ()),
}


@register.filter(name='nav_active')
def nav_active(path, key):
    """True when the request path belongs to the given top-nav section."""
    path = str(path or '')
    if key == 'home':
        return path == '/'
    prefixes, exclusions = _NAV_SECTIONS.get(key, ((), ()))
    if any(path.startswith(x) for x in exclusions):
        return False
    return any(path.startswith(x) for x in prefixes)


# Boilerplate strings the DocBook build leaves in English inside the stored
# manual pages: navigation links, the table-of-contents heading and the
# admonition titles. Translated at render time so the stored HTML stays as
# loaded. Only whole boilerplate tokens are matched, never running text.
_DOCS_UI_ZH = [
    (re.compile(r'(<a\s[^>]*accesskey="p"[^>]*>)Prev(ious)?(</a>)', re.I), r'\1上一页\3'),
    (re.compile(r'(<a\s[^>]*accesskey="n"[^>]*>)Next(</a>)', re.I), r'\1下一页\2'),
    (re.compile(r'(<a\s[^>]*accesskey="u"[^>]*>)Up(</a>)', re.I), r'\1上级\2'),
    (re.compile(r'(<a\s[^>]*accesskey="h"[^>]*>)Home(</a>)', re.I), r'\1首页\2'),
    (re.compile(r'>Table of Contents<'), '>目录<'),
    (re.compile(r'(<h3 class="title">)Note(</h3>)'), r'\1注意\2'),
    (re.compile(r'(<h3 class="title">)Tip(</h3>)'), r'\1提示\2'),
    (re.compile(r'(<h3 class="title">)Warning(</h3>)'), r'\1警告\2'),
    (re.compile(r'(<h3 class="title">)Caution(</h3>)'), r'\1小心\2'),
    (re.compile(r'(<h3 class="title">)Important(</h3>)'), r'\1重要\2'),
]


@register.filter(name='docs_ui_zh', is_safe=True)
def docs_ui_zh(content):
    """Translate the manual's navigation/TOC/admonition boilerplate to Chinese."""
    if not content:
        return content
    for pattern, repl in _DOCS_UI_ZH:
        content = pattern.sub(repl, content)
    return mark_safe(content)


@register.filter(name='hidemail')
@stringfilter
def hidemail(value):
    return value.replace('@', ' at ')


@register.filter(is_safe=True)
def ischeckbox(obj):
    return obj.field.widget.__class__.__name__ in ["CheckboxInput", "CheckboxSelectMultiple"] and not getattr(obj.field, 'regular_field', False)


@register.filter(is_safe=True)
def ismultiplecheckboxes(obj):
    return obj.field.widget.__class__.__name__ == "CheckboxSelectMultiple" and not getattr(obj.field, 'regular_field', False)


@register.filter(is_safe=True)
def isrequired_error(obj):
    if obj.errors and obj.errors[0] == "This field is required.":
        return True
    return False


@register.filter(is_safe=True)
def label_class(value, arg):
    return value.label_tag(attrs={'class': arg})


def _split_planet_title(title):
    parts = re.split(r'\s*[:：]\s*', title, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return '', title.strip()


@register.filter()
def planet_author(obj):
    # takes a ImportedRSSItem object from a Planet feed and extracts the author
    # information from the title
    return _split_planet_title(obj.title)[0]


@register.filter()
def planet_title(obj):
    # takes a ImportedRSSItem object from a Planet feed and extracts the info
    # specific to the title of the Planet entry
    return _split_planet_title(obj.title)[1]


@register.filter(name='dictlookup')
def dictlookup(value, key):
    if hasattr(key, 'value'):
        # Django 3.1 made this a ModelChoiceIteratorValue -- while we support both 2.2 and 3.2,
        # we need to treat them differently.
        return value.get(key.value, None)
    else:
        return value.get(key, None)


@register.filter(name='keylookup')
def keylookup(value, key):
    return value[key]


@register.filter(name='json')
def tojson(value):
    return json.dumps(value)


@register.filter()
def pg_major_version(major_version):
    """
    Turn a major version into a string. This means before 10 it's 2-digit,
    and after 10 it's 1-digit.
    """
    d = Decimal(major_version)
    if d >= 10 or d <= 1:
        return '{:f}'.format(d.normalize())
    else:
        return str(d)


@register.filter()
def release_notes_pg_minor_version(minor_version, major_version):
    """Formats the minor version number to the appropriate PostgreSQL version.
    This is particularly for very old version of PostgreSQL.
    """
    if str(major_version) in ['0', '1', '1.0']:
        if minor_version == 0:
            return '0'
        else:
            return '{:02}'.format(minor_version)
    return minor_version


@register.filter()
def joinandor(value, andor):
    # Value is a list of objects. Join them on comma, add "and" or "or" before the last.
    if len(value) == 1:
        return str(value[0])

    if not isinstance(value, list):
        # Must have a list to index from the end
        value = list(value)

    return ", ".join([str(x) for x in value[:-1]]) + ' ' + andor + ' ' + str(value[-1])


@register.filter()
def joinzh(value):
    """Join display values using the punctuation expected in Chinese prose."""
    items = [str(item) for item in value]
    if len(items) < 2:
        return ''.join(items)
    return '、'.join(items[:-1]) + ' 与 ' + items[-1]


@register.filter()
def list_templates(value):
    for f in Path(os.path.join(settings.PROJECT_ROOT, '../templates/', value)).iterdir():
        if f.is_file() and f.suffix == '.html':
            yield f.stem


@register.filter()
def sort_lower(value, reverse=False):
    return sorted(value, key=lambda x: x.lower(), reverse=reverse)


@register.filter(name="max")
def max_filter(value):
    return max(value)


@register.filter()
def languagename(lang):
    try:
        return babel.Locale(lang).english_name
    except Exception:
        return lang


@register.simple_tag(takes_context=True)
def git_changes_link(context):
    language = (context.get('seo') or {}).get('lang', 'zh')
    if language.startswith('zh'):
        return mark_safe('<a href="https://git.postgresql.org/gitweb/?p=pgweb.git;a=history;f=templates/{}">查看修订历史</a>。'.format(context.template_name))
    return mark_safe('<a href="https://git.postgresql.org/gitweb/?p=pgweb.git;a=history;f=templates/{}">View</a> change history.'.format(context.template_name))


# CSS inlining (used for HTML email)
@register.tag
class InlineCss(template.Node):
    def __init__(self, nodes, arg):
        self.nodes = nodes
        self.arg = arg

    def render(self, context):
        contents = self.nodes.render(context)
        css = ''
        path = self.arg.resolve(context, True)
        if path is not None:
            css = get_template(path).render()

        p = pynliner.Pynliner().from_string(contents)
        p.with_cssString(css)
        return p.run()


@register.tag
def inlinecss(parser, token):
    nodes = parser.parse(('endinlinecss',))

    parser.delete_first_token()

    # First part of token is the tagname itself
    css = token.split_contents()[1]

    return InlineCss(
        nodes,
        parser.compile_filter(css),
    )
