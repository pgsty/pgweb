from .models import HackerProfile


def get_struct():
    yield ('developer/hacker/', None)
    for slug in HackerProfile.objects.order_by('slug').values_list('slug', flat=True):
        yield ('developer/hacker/{}/'.format(slug), None)
