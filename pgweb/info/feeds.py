"""/info/rss/: one entry per day, the day page rendered like a post."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.db.models import Count
from django.template.loader import render_to_string
from django.utils.feedgenerator import Rss201rev2Feed

from .models import InfoItem

FEED_DAYS = 30


def site_root():
    return settings.SITE_ROOT.rstrip('/')


class DayFeed(Rss201rev2Feed):
    """RSS 2.0 with the full day in content:encoded, as blog feeds do."""

    def rss_attributes(self):
        attrs = super().rss_attributes()
        attrs['xmlns:content'] = 'http://purl.org/rss/1.0/modules/content/'
        return attrs

    def add_item_elements(self, handler, item):
        super().add_item_elements(handler, item)
        if item.get('content_html'):
            handler.addQuickElement('content:encoded', item['content_html'])


class InfoFeed(Feed):
    feed_type = DayFeed
    title = 'PostgreSQL 博览'
    description = '每日精选 PostgreSQL、数据库与云计算资讯，每天一期'
    link = '/info/'
    language = 'zh-cn'

    def items(self):
        rows = (InfoItem.objects.filter(status='published').values('date')
                .annotate(count=Count('id')).order_by('-date')[:FEED_DAYS])
        return [row['date'] for row in rows]

    def item_title(self, day):
        return 'PostgreSQL 博览 {}'.format(day.isoformat())

    def item_link(self, day):
        return '/info/{}/'.format(day.isoformat())

    def item_guid(self, day):
        return '{}/info/{}/'.format(site_root(), day.isoformat())

    item_guid_is_permalink = True

    def item_pubdate(self, day):
        return datetime.combine(day, time(8, 30), tzinfo=ZoneInfo('Asia/Shanghai'))

    def day_items(self, day):
        items = list(InfoItem.objects.filter(status='published', date=day).order_by('tier', 'position', 'id'))
        return {'day': day, 'root': site_root(),
                'lead': [i for i in items if i.tier == 1],
                'brief': [i for i in items if i.tier == 2],
                'mini': [i for i in items if i.tier == 3],
                'count': len(items)}

    def item_description(self, day):
        context = self.day_items(day)
        leads = '；'.join(item.title for item in context['lead'][:5])
        return '本期 {} 条。大新闻：{}'.format(context['count'], leads) if leads else '本期 {} 条。'.format(context['count'])

    def item_extra_kwargs(self, day):
        return {'content_html': render_to_string('info/feed_day.html', self.day_items(day))}
