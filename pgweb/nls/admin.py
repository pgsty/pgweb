from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Inspection only; decisions are made on /nls/. Grant reviewers the
    "nls | message | Can review message translations" permission here."""

    list_display = ('language', 'pg_major', 'component', 'number', 'short_msgid', 'status', 'version', 'updated_by', 'updated_at')
    list_filter = ('language', 'pg_major', 'component', 'status', 'old_assessment')
    search_fields = ('msgid', 'forms', 'note')
    ordering = ('language', 'pg_major', 'component', 'number')
    readonly_fields = tuple(f.name for f in Message._meta.fields)

    def short_msgid(self, obj):
        return obj.msgid[:80]
    short_msgid.short_description = 'msgid'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
