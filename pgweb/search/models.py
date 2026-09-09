from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models


class IndexedPage(models.Model):
    """A rebuildable snapshot of a PG manual page, never a second content source."""

    page = models.OneToOneField('docs.DocPage', primary_key=True, on_delete=models.CASCADE)
    source_hash = models.CharField(max_length=64)
    indexed_at = models.DateTimeField(auto_now=True)


class SearchEntry(models.Model):
    document = models.ForeignKey(IndexedPage, related_name='entries', on_delete=models.CASCADE)
    version = models.DecimalField(max_digits=3, decimal_places=1)
    key = models.CharField(max_length=64)
    entity_key = models.TextField()
    kind = models.CharField(max_length=16)
    subtype = models.CharField(max_length=32, blank=True)
    name = models.TextField()
    name_key = models.TextField()
    aliases = ArrayField(models.TextField(), default=list)
    anchor = models.TextField(blank=True)
    heading = models.TextField()
    signature = models.TextField(blank=True)
    body = models.TextField()
    preview = models.TextField()
    vector = SearchVectorField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('document', 'key'), name='docsearch_entry_key')]
        indexes = [
            models.Index(fields=('version', 'kind', 'name_key'), name='docsearch_scope_kind'),
            models.Index(fields=('name_key',), name='docsearch_name_prefix', opclasses=('text_pattern_ops',)),
            GinIndex(fields=('aliases',), name='docsearch_aliases'),
            GinIndex(fields=('vector',), name='docsearch_vector'),
            GinIndex(fields=('name_key',), name='docsearch_spelling', opclasses=('gin_trgm_ops',)),
            models.Index(fields=('entity_key',), name='docsearch_entity'),
        ]
