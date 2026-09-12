from .columns import live_columns
from .models import (CatalogRelation, CatalogVersion, ErrorCode, GucParameter, GucVersion,
                     WaitEvent, WaitEventVersion)


def get_struct():
    for column in live_columns():
        yield ('docs/{}/'.format(column['slug']), None)
    for sqlstate in ErrorCode.objects.values_list('sqlstate', flat=True):
        yield ('docs/sqlstate/{}/'.format(sqlstate), None)
    for name in CatalogRelation.objects.values_list('name', flat=True):
        yield ('docs/catalog/{}/'.format(name), None)
    for major in CatalogVersion.objects.values_list('major', flat=True):
        yield ('docs/catalog/changes/{}/'.format(major), None)
    for name in GucParameter.objects.values_list('name', flat=True):
        yield ('docs/guc/{}/'.format(name), None)
    for major in GucVersion.objects.values_list('major', flat=True):
        yield ('docs/guc/changes/{}/'.format(major), None)
    for type_slug, name in WaitEvent.objects.values_list('type_slug', 'name'):
        yield ('docs/waitevent/{}/{}/'.format(type_slug, name), None)
    for major in WaitEventVersion.objects.values_list('major', flat=True):
        yield ('docs/waitevent/changes/{}/'.format(major), None)
    from . import sqlcmd
    for slug in sqlcmd.SqlCommand.objects.values_list('slug', flat=True):
        yield ('docs/sql/{}/'.format(slug), None)
    for version in sqlcmd.versions():
        yield ('docs/sql/changes/{}/'.format(version['major']), None)
