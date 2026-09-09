from django.db import models
from pgweb.core.models import Version


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


class DocProject(models.Model):
    id = models.AutoField(primary_key=True)
    slug = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=100)
    license = models.TextField(
        null=True, blank=True, default=None, db_default=None,
        db_comment='Default documentation license; NULL means unknown. A revision may override it in meta.license.',
    )
    upstream_url = models.CharField(max_length=2048, blank=True, default='', db_default='')
    meta = models.JSONField(default=dict, db_default={})

    class Meta:
        db_table = 'doc_project'


class DocRevision(models.Model):
    id = models.TextField(primary_key=True)
    project = models.ForeignKey(
        DocProject, to_field='slug', db_column='project_id', db_index=False,
        on_delete=models.DO_NOTHING, related_name='revisions',
    )
    version = models.CharField(max_length=64)
    lang = models.CharField(max_length=32)
    name = models.CharField(max_length=256, blank=True, default='', db_default='')
    upstream_url = models.CharField(max_length=2048, blank=True, default='', db_default='')
    meta = models.JSONField(default=dict, db_default={})

    class Meta:
        db_table = 'doc_revision'
        constraints = [
            models.UniqueConstraint(
                fields=('project', 'version', 'lang'),
                name='doc_revision_project_version_lang_key',
            ),
        ]


class EcosystemDocPage(models.Model):
    id = models.AutoField(primary_key=True)
    rev = models.ForeignKey(
        DocRevision, db_column='rev_id', db_index=False,
        on_delete=models.DO_NOTHING, related_name='pages',
    )
    path = models.CharField(max_length=512, blank=True, default='', db_default='')
    source_path = models.CharField(max_length=512)
    upstream_url = models.CharField(max_length=2048, blank=True, default='', db_default='')
    title = models.CharField(max_length=256)
    meta = models.JSONField(default=dict, db_default={})
    description = models.TextField(blank=True, default='', db_default='')
    content = models.TextField()

    class Meta:
        db_table = 'doc_page'
        constraints = [
            models.UniqueConstraint(fields=('rev', 'path'), name='doc_page_rev_path_key'),
            models.UniqueConstraint(fields=('rev', 'source_path'), name='doc_page_rev_source_path_key'),
        ]
