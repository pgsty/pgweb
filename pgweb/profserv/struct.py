from .views import regions


def get_struct():
    yield ('support/professional_support/', None)
    yield ('support/professional_hosting/', None)
    for key, name in regions:
        yield ('support/professional_support/%s/' % key, None)
        yield ('support/professional_hosting/%s/' % key, None)
