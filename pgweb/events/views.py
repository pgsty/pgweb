from django.shortcuts import get_object_or_404
from django.http import Http404, HttpResponsePermanentRedirect
from django.template.defaultfilters import slugify

from datetime import date

from pgweb.util.contexts import render_pgweb
from pgweb.util.markup import pgmarkdown
from pgweb.util.seo import summarize_html

from .models import Event


def main(request):
    title = '近期活动'
    return render_pgweb(request, 'about', 'events/archive.html', {
        'title': title,
        'events': Event.objects.select_related('country').filter(approved=True, enddate__gt=date.today()).order_by('enddate', 'startdate'),
        'og': {
            'url': request.path,
            'title': title,
            'description': 'PostgreSQL 社区近期活动、会议和用户组聚会。',
            'type': 'website',
            'sitename': 'PostgreSQL 活动',
        },
    })


def archive(request):
    # Hardcode to the latest 100 events. Do we need paging too?
    events = Event.objects.select_related('country', 'language').filter(approved=True).filter(enddate__lte=date.today()).order_by('-enddate', '-startdate',)[:100]
    page_title = '活动归档'
    return render_pgweb(request, 'about', 'events/archive.html', {
        'title': page_title,
        'archive': True,
        'events': events,
        'og': {
            'url': request.path,
            'title': page_title,
            'description': 'PostgreSQL 社区历史活动、会议和用户组聚会归档。',
            'type': 'website',
            'sitename': 'PostgreSQL 活动',
        },
    })


def item(request, itemid, slug=None):
    event = get_object_or_404(Event, pk=itemid)
    if not event.approved:
        raise Http404

    if slug != slugify(event.title):
        return HttpResponsePermanentRedirect('/about/event/{}-{}/'.format(slugify(event.title), event.id))

    description = ''
    for source in (event.summary, event.details):
        if not source:
            continue
        description = summarize_html(
            pgmarkdown(source, allow_relative_links=True),
            max_length=180,
        )
        if description:
            break
    if not description:
        description = 'PostgreSQL 活动：{}'.format(event.title)
        startdate = getattr(event, 'startdate', None)
        enddate = getattr(event, 'enddate', startdate)
        if startdate:
            date_text = str(startdate) if enddate == startdate else '{} 至 {}'.format(startdate, enddate)
            description += '，日期 {}'.format(date_text)
        location = getattr(event, 'locationstring', '')
        if location:
            description += '，地点 {}'.format(location)
        description += '。'

    return render_pgweb(request, 'about', 'events/item.html', {
        'obj': event,
        'og': {
            'url': '/about/event/{}-{}/'.format(slugify(event.title), event.id),
            'title': event.title,
            'description': description,
            'type': 'article',
            'sitename': 'PostgreSQL 活动',
        },
    })
