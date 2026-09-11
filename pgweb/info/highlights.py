"""The 博览 block on the home page: the latest day's items as a compact list, cached briefly."""

from django.core.cache import cache
from django.db.models import Max

HOME_CACHE_KEY = 'pgweb:info-home'
NAV_CACHE_KEY = 'pgweb:info-nav'
HOME_CACHE_SECONDS = 300
NAV_DAYS = 7


def home_highlights():
    """{'date', 'url', 'count', 'entries': [...]}; empty and harmless when nothing is loaded.

    Every published item of the latest day in reading order (tier, position),
    without tiers, pictures or paragraphs: the home page shows the day as a
    compact digest and links each title to its article and to the day page.
    """
    cached = cache.get(HOME_CACHE_KEY)
    if cached is not None:
        return cached
    result = {'date': None, 'url': '/info/', 'count': 0, 'entries': []}
    try:
        from .models import InfoItem
        rows = InfoItem.objects.filter(status='published')
        latest = rows.aggregate(date=Max('date'))['date']
        if latest is not None:
            items = list(rows.filter(date=latest).order_by('tier', 'position', 'id'))
            result.update({
                'date': latest,
                'url': '/info/{}/'.format(latest.isoformat()),
                'count': len(items),
                'entries': [{
                    'title': item.title,
                    'url': item.url or item.anchor_url,
                    'external': bool(item.url),
                    'source': item.source or item.author,
                    'anchor_url': item.anchor_url if item.summary else '',
                    'tier': item.tier,
                } for item in items],
            })
    except Exception:
        # The home page never fails because the column is missing or unmigrated.
        return result
    cache.set(HOME_CACHE_KEY, result, HOME_CACHE_SECONDS)
    return result


def info_nav():
    """The 博览 dropdown: 新闻博览, PG 日报 with the last seven days and the
    archive underneath, then the community news and events pages."""
    cached = cache.get(NAV_CACHE_KEY)
    if cached is not None:
        return cached
    days = []
    try:
        from .views import day_counts
        days = day_counts(NAV_DAYS)
    except Exception:
        # Navigation never fails because the column is missing or unmigrated.
        days = []
    items = [
        {'title': '新闻博览', 'link': '/info/', 'keep': True},
        {'title': 'PG 日报', 'link': days[0]['url'] if days else '/info/daily/', 'submenu': [
            {'title': day['date'].isoformat(), 'link': day['url']} for day in days
        ] + [{'title': '日报归档', 'link': '/info/archive/'}]},
        {'title': '社区新闻', 'link': '/about/newsarchive/'},
        {'title': '近期活动', 'link': '/about/events/'},
    ]
    if days:
        cache.set(NAV_CACHE_KEY, items, HOME_CACHE_SECONDS)
    return items


def forget_highlights():
    cache.delete(HOME_CACHE_KEY)
    cache.delete(NAV_CACHE_KEY)
