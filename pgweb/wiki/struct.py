from .columns import live_columns


def get_struct():
    yield ('wiki/', None)
    for column in live_columns():
        yield ('wiki/{}/'.format(column['slug']), None)
