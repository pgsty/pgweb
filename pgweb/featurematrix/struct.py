from .views import matrixdata


def get_struct():
    yield ('about/featurematrix/', None)
    matrixdata._conditional_load()
    for slug in sorted(matrixdata.slugmap):
        if slug:
            yield ('about/featurematrix/detail/{}/'.format(slug), 0.4)
