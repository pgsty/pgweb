"""博览: one editorial item per row, one table for the whole column."""

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models


TIERS = ((1, '大新闻'), (2, '小新闻'), (3, '迷你'))
DOMAINS = ('pg', 'db', 'cloud', 'infra', 'ai')
DOMAIN_LABEL = {'pg': 'PostgreSQL', 'db': '数据库', 'cloud': '云计算', 'infra': '基础设施', 'ai': 'AI'}
STATUSES = (('published', '已发布'), ('hidden', '已撤下'))


class InfoItem(models.Model):
    """A curated item. `key` is sha1(date + "|" + url or title)[:16], so the
    same batch file produces the same rows on every install."""

    key = models.CharField(max_length=16, unique=True)
    date = models.DateField()
    tier = models.SmallIntegerField(choices=TIERS)
    position = models.SmallIntegerField(default=0)
    title = models.TextField()
    summary = models.TextField(blank=True, default='')
    url = models.TextField(blank=True, default='')
    author = models.TextField(blank=True, default='')
    source = models.TextField(blank=True, default='')
    source_date = models.DateField(null=True, blank=True)
    image = models.TextField(blank=True, default='')
    # 500 × 300 WebP served at /info/img/<key>.webp; loaded from data/info/img/<key>.webp
    thumb = models.BinaryField(null=True, blank=True, editable=False)
    domain = models.CharField(max_length=8, default='pg')
    tags = ArrayField(models.TextField(), default=list, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default='published')
    origin = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    search_vector = SearchVectorField(null=True)

    class Meta:
        db_table = 'info_item'
        # The reading order of the column: newest day first, tiers in order.
        ordering = ('-date', 'tier', 'position', 'id')
        indexes = [
            models.Index(fields=('status', '-date', 'tier', 'position'), name='info_item_stream'),
            GinIndex(fields=('search_vector',), name='info_item_vector'),
        ]

    def __str__(self):
        return '{} {}'.format(self.date, self.title)

    @property
    def day_url(self):
        return '/info/{}/'.format(self.date.isoformat())

    @property
    def anchor_url(self):
        return '{}#{}'.format(self.day_url, self.key)

    @property
    def thumb_url(self):
        return '/info/img/{}.webp'.format(self.key) if self.thumb else ''

    @property
    def picture_url(self):
        """The local thumbnail when it exists, else the source picture."""
        return self.thumb_url or self.image

    @property
    def domain_label(self):
        return DOMAIN_LABEL.get(self.domain, self.domain)
