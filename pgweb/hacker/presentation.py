"""Public profile links; source archives are not rendered as activity feeds."""

from urllib.parse import urlsplit


def safe_url(value):
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        return ''
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower().rstrip('.')
        if host == 'pgnexus.ai' or host.endswith('.pgnexus.ai'):
            return ''
        if parsed.scheme in ('https', 'http') and host and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return ''


def link_identity(url):
    host = urlsplit(url).hostname.lower()
    for domain, label, icon in (
        ('linkedin.com', 'LinkedIn', 'fab fa-linkedin-in'),
        ('github.com', 'GitHub', 'fab fa-github'),
        ('twitter.com', 'Twitter', 'fab fa-twitter'),
        ('x.com', 'X', 'fab fa-twitter'),
        ('postgresql.org', 'PostgreSQL', 'fas fa-database'),
    ):
        if host == domain or host.endswith('.' + domain):
            return label, icon
    return host, 'fas fa-globe'
