"""Canonical extension pages for the site's public sitemap."""

from .catalog import catalog


def get_struct():
    yield ('ext/', None)
    yield ('ext/cloud/', None)
    from .cloud import snapshot
    for service in snapshot()['services']:
        yield ('ext/cloud/{}/'.format(service['id']), None)
    for row in catalog():
        yield ('e/{}/'.format(row['name']), None)
