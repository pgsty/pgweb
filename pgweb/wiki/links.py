"""Canonical Wiki links, including URLs in previously imported content."""

import re
from urllib.parse import urlsplit, urlunsplit


_COLLECTION = re.compile(r'^/docs/(sql|sqlstate|catalog|guc|waitevent|func|lock|hook|relopts|role|oid)(?=/|$)')
_ERRCODE = re.compile(r'^/(?:docs|wiki)/errcode(?=/|$)')
_HREF = re.compile(
    r'''(?P<prefix><a(?=\s)(?:[^>"']|"[^"]*"|'[^']*')*?\s+href\s*=\s*)'''
    r'''(?P<quote>["'])(?P<url>.*?)(?P=quote)''', re.I | re.S)


def canonical_url(url):
    """Keep queries, fragments, manual links and external sites intact."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if parts.netloc and parts.hostname not in {'pg.center', 'pgsql.cc'}:
        return url
    path = parts.path
    if path in ('/docs/reference/', '/docs/reference', '/wiki/reference/', '/wiki/reference'):
        path = '/wiki/'
    elif _ERRCODE.match(path):
        path = _ERRCODE.sub('/wiki/sqlstate', path)
    elif _COLLECTION.match(path):
        path = '/wiki/' + path[len('/docs/'):]
    return urlunsplit(parts._replace(path=path)) if path != parts.path else url


def rewrite_links(html):
    """Update hrefs in rendered fragments without changing source snapshots."""
    return _HREF.sub(lambda match: match['prefix'] + match['quote'] +
                     canonical_url(match['url']) + match['quote'], html)
