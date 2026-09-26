from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from pgweb.core.models import Version
from .versions import manual_major


class DocPage(models.Model):
    id = models.AutoField(null=False, primary_key=True)
    file = models.CharField(max_length=64, null=False, blank=False)
    version = models.ForeignKey(Version, null=False, blank=False, db_column='version', to_field='tree', on_delete=models.CASCADE)
    title = models.CharField(max_length=256, null=True, blank=True)
    content = models.TextField(null=True, blank=True)

    def display_version(self):
        """Version as used for displaying and in URLs"""
        if self.version.tree == 0:
            return 'devel'
        else:
            return str(self.version.numtree)

    @property
    def search_version(self):
        return manual_major(self.version_id)

    class Meta:
        db_table = 'docs'
        # Index file first, because we want to list versions by file
        unique_together = [('file', 'version')]


class DocPageAlias(models.Model):
    file1 = models.CharField(max_length=64, null=False, blank=False, unique=True)
    file2 = models.CharField(max_length=64, null=False, blank=False, unique=True)

    def __str__(self):
        return "%s <-> %s" % (self.file1, self.file2)

    # XXX: needs a unique functional index as well, see the migration!
    class Meta:
        db_table = 'docsalias'
        verbose_name_plural = 'Doc page aliases'


class DocPageRedirect(models.Model):
    """DocPageRedirect offers the ability to redirect from a page that has been
    completely removed from the PostgreSQL documentation
    """
    redirect_from = models.CharField(max_length=64, null=False, blank=False, unique=True, help_text='Page to redirect from, e.g. "old_page.html"')
    redirect_to = models.CharField(max_length=64, null=False, blank=False, unique=True, help_text='Page to redirect to, e.g. "new_page.html"')

    def __str__(self):
        return "%s => %s" % (self.redirect_from, self.redirect_to)

    class Meta:
        verbose_name_plural = "Doc page redirects"


class CompareDataset(models.Model):
    """Activated source manifest; entry bodies live only in their entity rows."""

    key = models.CharField(max_length=32, primary_key=True)
    kind = models.CharField(max_length=16)
    language = models.CharField(max_length=8, blank=True)
    metadata = models.JSONField(default=dict)
    members = models.JSONField(default=list)
    revisions = models.JSONField(default=list)
    release_count = models.PositiveIntegerField(default=0)
    entry_count = models.PositiveIntegerField(default=0)
    content_hash = models.CharField(max_length=64)
    revision = models.PositiveBigIntegerField(default=1)
    imported_at = models.DateTimeField()

    class Meta:
        db_table = 'release_dataset'


class CompareRelease(models.Model):
    """One complete release coordinate, with independent language payloads."""

    version = models.CharField(max_length=24, primary_key=True)
    major = models.CharField(max_length=12, db_index=True)
    minor = models.PositiveIntegerField()
    sort_num = models.PositiveIntegerField(db_index=True)
    status = models.CharField(max_length=16)
    released_at = models.DateField(null=True, blank=True, db_index=True)
    active_languages = ArrayField(models.CharField(max_length=8), default=list)
    payloads = models.JSONField(default=dict)
    revisions = models.JSONField(default=list)
    content_hash = models.CharField(max_length=64)
    imported_at = models.DateTimeField()

    class Meta:
        db_table = 'release'
        ordering = ('sort_num',)


class ComparePatch(models.Model):
    """An upstream commit/backport group, not a semantic-equivalence assertion."""

    id = models.CharField(max_length=32, primary_key=True)
    commits = ArrayField(models.CharField(max_length=40), default=list)
    evidence = models.JSONField(default=dict)
    merged_into = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT,
                                    related_name='merged_groups')
    revisions = models.JSONField(default=list)
    content_hash = models.CharField(max_length=64)
    imported_at = models.DateTimeField()

    class Meta:
        db_table = 'release_patch'
        indexes = [GinIndex(fields=['commits'], name='release_patch_commits_gin')]


class CompareEntry(models.Model):
    """An original release-note occurrence; matching never deletes occurrences."""

    id = models.CharField(max_length=32, primary_key=True)
    release = models.ForeignKey(CompareRelease, on_delete=models.PROTECT, related_name='changes')
    part = models.CharField(max_length=24)
    position = models.PositiveIntegerField()
    category = models.CharField(max_length=24, db_index=True)
    statement_hash = models.CharField(max_length=64, db_index=True)
    patch_ids = ArrayField(models.CharField(max_length=32), default=list)
    cves = ArrayField(models.CharField(max_length=32), default=list)
    active_languages = ArrayField(models.CharField(max_length=8), default=list)
    payloads = models.JSONField(default=dict)
    revisions = models.JSONField(default=list)
    relations = models.JSONField(default=list)
    content_hash = models.CharField(max_length=64)
    imported_at = models.DateTimeField()

    class Meta:
        db_table = 'release_entry'
        ordering = ('release__sort_num', 'position', 'id')
        indexes = [
            models.Index(fields=['release', 'position'], name='release_entry_order_idx'),
            GinIndex(fields=['patch_ids'], name='release_entry_patches_gin'),
            GinIndex(fields=['cves'], name='release_entry_cves_gin'),
            GinIndex(fields=['relations'], name='release_entry_relations_gin'),
        ]
