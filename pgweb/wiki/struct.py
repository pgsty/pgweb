from .columns import live_columns
from .models import ErrorCode


def get_struct():
    yield ('wiki/', None)
    for column in live_columns():
        yield ('wiki/{}/'.format(column['slug']), None)
    for sqlstate in ErrorCode.objects.values_list('sqlstate', flat=True):
        yield ('wiki/errcode/{}/'.format(sqlstate), None)
