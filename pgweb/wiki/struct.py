from .columns import live_columns
from .models import CatalogRelation, CatalogVersion, ErrorCode


def get_struct():
    for column in live_columns():
        yield ('docs/{}/'.format(column['slug']), None)
    for sqlstate in ErrorCode.objects.values_list('sqlstate', flat=True):
        yield ('docs/sqlstate/{}/'.format(sqlstate), None)
    for name in CatalogRelation.objects.values_list('name', flat=True):
        yield ('docs/catalog/{}/'.format(name), None)
    for major in CatalogVersion.objects.values_list('major', flat=True):
        yield ('docs/catalog/changes/{}/'.format(major), None)
