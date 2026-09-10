"""The 博览 block on the home page: the latest day's 大新闻, cached briefly."""

from django.core.cache import cache
from django.db.models import Max
from django.utils.text import Truncator

HOME_CACHE_KEY = 'pgweb:info-home'
HOME_CACHE_SECONDS = 300
HOME_LIMIT = 4
HOME_SUMMARY = 80


def home_highlights(limit=HOME_LIMIT):
    """{'date': …, 'entries': [...]}; empty and harmless when nothing is loaded."""
    cached = cache.get(HOME_CACHE_KEY)
    if cached is not None:
        return cached
    result = {'date': None, 'entries': []}
    try:
        from .models import InfoItem
        rows = InfoItem.objects.filter(status='published', tier=1)
        latest = rows.aggregate(date=Max('date'))['date']
        if latest is not None:
            result['date'] = latest
            result['entries'] = [{
                'title': item.title,
                'summary': Truncator(item.summary).chars(HOME_SUMMARY),
                'source': item.source,
                'url': item.url or item.anchor_url,
                'date': item.date,
            } for item in rows.filter(date=latest).order_by('position', 'id')[:limit]]
    except Exception:
        # The home page never fails because the column is missing or unmigrated.
        return result
    cache.set(HOME_CACHE_KEY, result, HOME_CACHE_SECONDS)
    return result


def forget_highlights():
    cache.delete(HOME_CACHE_KEY)
