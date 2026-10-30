from urllib.parse import quote

from .models import Badge, Contributor


def get_struct():
    yield ('community/contributors/', None)
    yield ('community/people/', None)
    for username in Contributor.objects.exclude(user=None).values_list('user__username', flat=True):
        yield ('community/people/{}/'.format(quote(username, safe='')), None)
    for slug in Badge.objects.filter(approved=True).values_list('slug', flat=True):
        yield ('community/badge/{}/'.format(quote(slug, safe='')), None)
