"""/info/rss/: the last 50 大新闻 and 小新闻, newest day first."""

from datetime import datetime, time

from django.conf import settings
from django.contrib.syndication.views import Feed

from .models import InfoItem

FEED_SIZE = 50


class InfoFeed(Feed):
    title = 'PostgreSQL 博览'
    description = '每日精选 PostgreSQL、数据库与云计算资讯'
    link = '/info/'
    language = 'zh-cn'

    def items(self):
        return (InfoItem.objects.filter(status='published', tier__lte=2)
                .order_by('-date', 'tier', 'position', 'id')[:FEED_SIZE])

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.summary

    def item_link(self, item):
        return item.url or '{}{}'.format(settings.SITE_ROOT.rstrip('/'), item.anchor_url)

    def item_guid(self, item):
        return item.key

    item_guid_is_permalink = False

    def item_pubdate(self, item):
        return datetime.combine(item.date, time.min)

    def item_author_name(self, item):
        return item.author or None

    def item_categories(self, item):
        return item.tags or ()
