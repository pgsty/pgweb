"""Function signature identity shared by import, comparison and version matrices."""

import re


def signature_key(value):
    """DocBook renderers differ in whitespace inside optional argument brackets."""
    text = ' '.join((value or '').replace('\xa0', ' ').split())
    return re.sub(r'\s+\]', ']', re.sub(r'\[\s+', '[', text))
