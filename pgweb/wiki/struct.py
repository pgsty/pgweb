from .columns import live_columns
from .models import ErrorCode


def get_struct():
    for column in live_columns():
        yield ('docs/{}/'.format(column['slug']), None)
    for sqlstate in ErrorCode.objects.values_list('sqlstate', flat=True):
        yield ('docs/sqlstate/{}/'.format(sqlstate), None)
