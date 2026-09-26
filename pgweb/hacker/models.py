"""Developer directory: one person per row, with the complete source in JSON."""

from django.db import models


class HackerProfile(models.Model):
    source_id = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=160, unique=True)
    name = models.CharField(max_length=250)
    organization = models.CharField(max_length=250, blank=True, default='', db_index=True)
    country = models.CharField(max_length=100, blank=True, default='', db_index=True)
    bio = models.TextField(blank=True, default='')
    # Original list, detail and section records, plus public emails and links.
    data = models.JSONField(default=dict, blank=True)
    # Curated translations are independent of source snapshots and refreshes.
    texts = models.JSONField(default=dict, blank=True)
    avatar = models.BinaryField(null=True, blank=True, editable=False)
    avatar_content_type = models.CharField(max_length=50, blank=True, default='')
    avatar_sha256 = models.CharField(max_length=64, blank=True, default='')
    content_hash = models.CharField(max_length=64)
    source_fetched_at = models.DateTimeField()
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hacker_profile'
        ordering = ('name', 'source_id')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return '/developer/hacker/{}/'.format(self.slug)

    @property
    def zh(self):
        return self.texts.get('zh', {})

    @property
    def avatar_url(self):
        # Use the small digest column so listing pages can defer the image bytes.
        return '{}avatar/'.format(self.get_absolute_url()) if self.avatar_sha256 else ''
