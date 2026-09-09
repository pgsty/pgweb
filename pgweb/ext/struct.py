"""Canonical extension pages for the site's public sitemap."""

from .catalog import catalog


def get_struct():
    yield ('ext/', None)
    for row in catalog():
        yield ('e/{}/'.format(row['name']), None)
