from .columns import live_columns
from .models import (CatalogRelation, CatalogVersion, ErrorCode, FuncVersion, GucParameter,
                     GucVersion, LockMode, PgFunction, WaitEvent, WaitEventVersion)


def get_struct():
    yield ('wiki/', None)
    for column in live_columns():
        yield ('wiki/{}/'.format(column['slug']), None)
    for sqlstate in ErrorCode.objects.values_list('sqlstate', flat=True):
        yield ('wiki/sqlstate/{}/'.format(sqlstate), None)
    for name in CatalogRelation.objects.values_list('name', flat=True):
        yield ('wiki/catalog/{}/'.format(name), None)
    for major in CatalogVersion.objects.values_list('major', flat=True):
        yield ('wiki/catalog/changes/{}/'.format(major), None)
    for name in GucParameter.objects.values_list('name', flat=True):
        yield ('wiki/guc/{}/'.format(name), None)
    for major in GucVersion.objects.values_list('major', flat=True):
        yield ('wiki/guc/changes/{}/'.format(major), None)
    for type_slug, name in WaitEvent.objects.values_list('type_slug', 'name'):
        yield ('wiki/waitevent/{}/{}/'.format(type_slug, name), None)
    for major in WaitEventVersion.objects.values_list('major', flat=True):
        yield ('wiki/waitevent/changes/{}/'.format(major), None)
    from . import sqlcmd
    for slug in sqlcmd.SqlCommand.objects.values_list('slug', flat=True):
        yield ('wiki/sql/{}/'.format(slug), None)
    for version in sqlcmd.versions():
        yield ('wiki/sql/changes/{}/'.format(version['major']), None)
    for slug in PgFunction.objects.values_list('slug', flat=True):
        yield ('wiki/func/{}/'.format(slug), None)
    for major in FuncVersion.objects.values_list('major', flat=True):
        yield ('wiki/func/changes/{}/'.format(major), None)
    for slug in LockMode.objects.values_list('slug', flat=True):
        yield ('wiki/lock/{}/'.format(slug), None)
    from .topics import TOPICS
    for kind, spec in TOPICS.items():
        for slug in spec['model'].objects.values_list('slug', flat=True):
            yield ('wiki/{}/{}/'.format(kind, slug), None)
