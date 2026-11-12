from django.contrib.syndication.views import Feed
from django.conf import settings

from .models import Version

from datetime import datetime, time


class VersionFeed(Feed):
    title = "PostgreSQL 最新版本"
    link = settings.SITE_ROOT.rstrip('/') + '/'
    description = "PostgreSQL 最新版本"

    description_template = 'core/version_rss_description.html'
    title_template = 'core/version_rss_title.html'

    def items(self):
        return Version.objects.filter(tree__gt=0).filter(testing=0)

    def item_link(self, obj):
        url = obj.relnotes_url
        return settings.SITE_ROOT.rstrip('/') + url if url.startswith('/') else url

    def item_pubdate(self, obj):
        return datetime.combine(obj.reldate, time.min)
