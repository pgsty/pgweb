from django.contrib import admin

from .models import HackerProfile


@admin.register(HackerProfile)
class HackerProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'country', 'source_id', 'imported_at')
    list_filter = ('country', 'organization')
    search_fields = ('name', 'organization', 'bio', 'source_id')
    readonly_fields = tuple(field.name for field in HackerProfile._meta.fields if field.name != 'avatar')
    exclude = ('avatar',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
