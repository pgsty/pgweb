"""The upstream development manual uses tree 0 and the /devel/ URL."""

DEVEL_MAJOR_VERSION = 20


def manual_major(tree):
    return DEVEL_MAJOR_VERSION if tree == 0 else int(tree)


def manual_tree(major):
    return 0 if major == DEVEL_MAJOR_VERSION else major


MANUAL_GROUPS_CACHE_KEY = 'pgweb:manual-groups'


def manual_prerelease(version):
    """Read the loaded manual's build, independently of the latest release."""
    import re
    from django.core.cache import cache
    from pgweb.docs.models import DocPage
    from pgweb.util.versions import ParsedVersion

    loaded = version.docsloaded.isoformat() if version.docsloaded else 'unknown'
    key = 'pgweb:manual-prerelease:{}:{}'.format(version.numtree, loaded)
    missing = object()
    value = cache.get(key, missing)
    if value is missing:
        title = DocPage.objects.filter(version=version, file='index.html').values_list('title', flat=True).first()
        match = re.search(r'PostgreSQL\s+(\d+)\s*(alpha|beta|rc)\s*(\d+)\b', title or '', re.I)
        value = ''.join(match.groups()).lower() if match and int(match[1]) == version.numtree else ''
        cache.set(key, value, 600)
    return ParsedVersion(value) if value else None


def manual_groups():
    """Loaded manuals for navigation, grouped by state.

    supported: majors still in their support window, newest first;
    historical: majors past end of life (PostgreSQL 10 onward), newest first;
    testing: [{'major', 'label'}] for betas and release candidates;
    devel: the development major, or None when its snapshot is not loaded.
    Only versions whose manual index page is loaded are listed. Cached briefly.
    """
    from django.core.cache import cache
    from pgweb.core.models import Version
    from pgweb.docs.models import DocPage

    groups = cache.get(MANUAL_GROUPS_CACHE_KEY)
    if groups is not None:
        return groups
    loaded = set(DocPage.objects.filter(file__in=('index.html', 'postgres.html', 'postgres.htm', 'book01.htm'))
                 .values_list('version_id', flat=True))
    versions = [v for v in Version.objects.order_by('-tree') if v.tree in loaded]
    groups = {
        'supported': [int(v.tree) for v in versions if v.tree > 0 and not v.testing and v.supported],
        'historical': [int(v.tree) for v in versions if 10 <= v.tree and not v.testing and not v.supported],
        'testing': [{'major': int(v.tree), 'label': build.type if (build := manual_prerelease(v)) else '预览'}
                    for v in versions if v.tree > 0 and v.testing],
        'devel': DEVEL_MAJOR_VERSION if any(v.tree == 0 for v in versions) else None,
    }
    cache.set(MANUAL_GROUPS_CACHE_KEY, groups, 600)
    return groups
