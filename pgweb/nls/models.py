"""消息翻译 (/nls/): one row per PostgreSQL NLS message, one table for the whole column.

The row carries the source message, the existing and recommended translations from
the pgnls calibration run, and the human review state. History is kept inside the
row so the column needs no second table; undo re-saves an earlier state.
"""

from django.conf import settings
from django.contrib.postgres.indexes import GistIndex
from django.db import models

from .languages import DEFAULT_LANGUAGE, LANGUAGES


STATUSES = (
    ('pending', '待审'),
    ('approved', '已校对'),
    ('flagged', '标疑'),
    ('rejected', '否定'),
)
HISTORY_LIMIT = 40


class Message(models.Model):
    # m_<sha256 of version, language, component, msgctxt, msgid, msgid_plural>: stable across imports.
    id = models.CharField(primary_key=True, max_length=72)
    language = models.CharField(max_length=16, choices=LANGUAGES, default=DEFAULT_LANGUAGE,
                                db_default=DEFAULT_LANGUAGE)
    pg_major = models.PositiveSmallIntegerField(default=19, db_index=True)   # PostgreSQL major version
    number = models.IntegerField(default=0)
    component = models.CharField(max_length=64, db_index=True)
    msgid = models.TextField()
    msgid_plural = models.TextField(blank=True, default='')
    msgctxt = models.TextField(null=True, blank=True)
    flags = models.JSONField(default=list, blank=True)            # ["c-format"], never "fuzzy"
    plural_forms = models.TextField(blank=True, default='')       # Plural-Forms header of the component PO

    original_forms = models.JSONField(default=dict, blank=True)   # the translation before this round
    suggested_forms = models.JSONField(default=dict, blank=True)  # the nls-v2 recommendation
    suggestion_source = models.TextField(blank=True, default='')
    calibration = models.JSONField(default=dict, blank=True)      # kind, label, previous_changed, previous_forms, …
    old_assessment = models.CharField(max_length=16, default='unreviewed')
    assessment_reason = models.TextField(blank=True, default='')
    context = models.JSONField(default=dict, blank=True)          # context, parameters, locations
    plural_issue = models.TextField(blank=True, default='')
    revision = models.CharField(max_length=64)                    # baseline of msgid + recommendation
    workbook_sha256 = models.CharField(max_length=64, blank=True, default='')

    # Human review state. `forms` always holds the current translation (the
    # recommendation until a reviewer edits it); keys are '' or the plural index.
    status = models.CharField(max_length=16, choices=STATUSES, default='pending')
    forms = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True, default='')
    source_revision = models.CharField(max_length=64, blank=True, default='')
    version = models.IntegerField(default=0)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(null=True, blank=True)
    history = models.JSONField(default=list, blank=True)          # last HISTORY_LIMIT saved states

    class Meta:
        db_table = 'nls_message'
        ordering = ('language', 'pg_major', 'component', 'number')
        permissions = [('review', '可以校对消息翻译')]
        indexes = [
            models.Index(fields=('language', 'pg_major', 'component', 'status'), name='nls_lang_major_comp_status'),
            models.Index(fields=('component', 'status'), name='nls_message_component_status'),
            GistIndex(fields=('msgid',), name='nls_message_msgid_trgm', opclasses=('gist_trgm_ops',)),
        ]
        constraints = [models.CheckConstraint(condition=models.Q(language__in=[code for code, _ in LANGUAGES]),
                                               name='nls_message_language_valid')]

    def __str__(self):
        return '{} · {}'.format(self.component, self.msgid[:60])

    @property
    def reviewer(self):
        return self.updated_by.username if self.updated_by_id and self.updated_by else ''

    @property
    def stale(self):
        # A decision taken against an older recommendation needs another look.
        return self.status != 'pending' and self.version > 0 and self.source_revision != self.revision

    @property
    def display_status(self):
        return 'stale' if self.stale else self.status
