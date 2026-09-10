"""博览 pages: a day-grouped stream, one page per day, archive and search."""

from datetime import datetime

from django.core.paginator import Paginator
from django.db.models import Count, Max, Min
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_safe

from pgweb.util.decorators import queryparams

from .models import InfoItem
from . import search as info_search

DAYS_PER_PAGE = 7
SIDECARD_DAYS = 30
TAGLINE = '每日精选 PostgreSQL、数据库与云计算资讯'
TITLE = 'PostgreSQL 博览'


def published():
    return InfoItem.objects.filter(status='published')


def day_counts(limit=None):
    """Days that have content, newest first, with the number of items."""
    rows = (published().values('date').annotate(count=Count('id')).order_by('-date'))
    if limit:
        rows = rows[:limit]
    return [{'date': row['date'], 'count': row['count'],
             'url': '/info/{}/'.format(row['date'].isoformat())} for row in rows]


def sidecard(current=None, query=''):
    return {'sidecard_days': day_counts(SIDECARD_DAYS), 'sidecard_current': current, 'sidecard_query': query}


def group(items):
    """One day's items split into the three tiers, in reading order."""
    tiers = {1: [], 2: [], 3: []}
    for item in items:
        tiers.get(item.tier, tiers[3]).append(item)
    return {'lead': tiers[1], 'brief': tiers[2], 'mini': tiers[3]}


def days_with_items(dates):
    """[{date, count, url, lead, brief, mini}] for the given dates, newest first."""
    items = published().filter(date__in=dates).order_by('-date', 'tier', 'position', 'id')
    buckets = {}
    for item in items:
        buckets.setdefault(item.date, []).append(item)
    days = []
    for value in sorted(buckets, reverse=True):
        entry = {'date': value, 'count': len(buckets[value]),
                 'url': '/info/{}/'.format(value.isoformat())}
        entry.update(group(buckets[value]))
        days.append(entry)
    return days


def page_url(number):
    return '/info/' if not number or number == 1 else '/info/?page={}'.format(number)


def seo(context, title, description, canonical, noindex=False):
    context['title'] = title
    context['noindex'] = noindex
    context['seo'] = {'title': title if title.startswith('PostgreSQL') else title + ' · PostgreSQL',
                      'description': description, 'canonical': canonical, 'lang': 'zh'}
    return context


@queryparams('page')
@require_safe
def stream(request):
    dates = [row['date'] for row in day_counts()]
    pager = Paginator(dates, DAYS_PER_PAGE)
    page = pager.get_page(request.GET.get('page'))
    context = {
        'days': days_with_items(list(page)),
        'page': page,
        'total': pager.count,
        'pagination': [{'label': number, 'current': number == page.number,
                        'url': page_url(number) if isinstance(number, int) else ''}
                       for number in pager.get_elided_page_range(page.number, on_each_side=1, on_ends=1)],
        'previous_url': page_url(page.previous_page_number()) if page.has_previous() else '',
        'next_url': page_url(page.next_page_number()) if page.has_next() else '',
        'tagline': TAGLINE,
    }
    context.update(sidecard())
    seo(context, TITLE, TAGLINE + '，每天 10–30 条，按日期分组。',
        page_url(page.number), noindex=page.number > 1)
    return render(request, 'info/stream.html', context)


@queryparams()
@require_safe
def day(request, datestr):
    try:
        value = datetime.strptime(datestr, '%Y-%m-%d').date()
    except ValueError:
        raise Http404('Not a 博览 date')
    items = list(published().filter(date=value).order_by('tier', 'position', 'id'))
    neighbours = published().filter(date__lt=value).aggregate(previous=Max('date'))
    following = published().filter(date__gt=value).aggregate(next=Min('date'))
    context = {
        'day': value,
        'count': len(items),
        'tagline': TAGLINE,
        'previous_day': neighbours['previous'],
        'next_day': following['next'],
    }
    context.update(group(items))
    context.update(sidecard(current=value))
    description = ('{} 的 PostgreSQL、数据库与云计算资讯，共 {} 条。'.format(value.isoformat(), len(items))
                   if items else '{} 暂无收录。'.format(value.isoformat()))
    seo(context, 'PostgreSQL 博览 · {}'.format(value.isoformat()), description,
        '/info/{}/'.format(value.isoformat()), noindex=not items)
    return render(request, 'info/day.html', context)


@queryparams()
@require_safe
def daily(request):
    latest = published().aggregate(date=Max('date'))['date']
    if latest is None:
        return HttpResponseRedirect('/info/')
    return HttpResponseRedirect('/info/{}/'.format(latest.isoformat()))


@queryparams()
@require_safe
def archive(request):
    months, total = [], 0
    for row in day_counts():
        label = '{} 年 {} 月'.format(row['date'].year, row['date'].month)
        if not months or months[-1]['label'] != label:
            months.append({'label': label, 'key': row['date'].strftime('%Y-%m'), 'days': [], 'count': 0})
        months[-1]['days'].append(row)
        months[-1]['count'] += row['count']
        total += row['count']
    context = {'months': months, 'total': total, 'day_total': sum(len(m['days']) for m in months),
               'tagline': TAGLINE}
    context.update(sidecard())
    seo(context, 'PostgreSQL 博览归档', '按月份列出博览收录过的日期与条数。', '/info/archive/', noindex=True)
    return render(request, 'info/archive.html', context)


@queryparams('q', 'page')
@require_safe
def search(request):
    query = request.GET.get('q', '')
    context = info_search.search(query, request.GET.get('page'))
    context['tagline'] = TAGLINE
    context.update(sidecard(query=context['q']))
    title = 'PostgreSQL 博览检索' if not context['q'] else 'PostgreSQL 博览检索 · {}'.format(context['q'])
    seo(context, title, '在博览中检索 PostgreSQL、数据库与云计算资讯。', '/info/search/', noindex=True)
    response = render(request, 'info/search.html', context)
    response['Cache-Control'] = 'no-cache'
    return response
