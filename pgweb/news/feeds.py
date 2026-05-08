from django.contrib.syndication.views import Feed
from django.conf import settings
from django.template.defaultfilters import slugify

from pgweb.util.moderation import ModerationState
from .models import NewsArticle

from datetime import datetime, time


class NewsFeed(Feed):
    title = description = "PostgreSQL 新闻"
    link = settings.SITE_ROOT.rstrip('/') + '/'

    description_template = 'news/rss_description.html'
    title_template = 'news/rss_title.html'

    def get_object(self, request, tagurl=None):
        return tagurl

    def items(self, obj):
        if obj:
            return NewsArticle.objects.filter(modstate=ModerationState.APPROVED, tags__urlname=obj)[:10]
        else:
            return NewsArticle.objects.filter(modstate=ModerationState.APPROVED)[:10]

    def item_link(self, obj):
        return "{}/about/news/{}-{}/".format(settings.SITE_ROOT.rstrip('/'), slugify(obj.title), obj.id)

    def item_pubdate(self, obj):
        return datetime.combine(obj.date, time.min)
