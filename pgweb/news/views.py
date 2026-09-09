from django.shortcuts import get_object_or_404
from django.http import HttpResponse, Http404, HttpResponsePermanentRedirect

from pgweb.util.contexts import render_pgweb
from pgweb.util.markup import pgmarkdown
from pgweb.util.moderation import ModerationState
from pgweb.util.seo import summarize_html

from .models import NewsArticle, NewsTag
from .util import news_slug, news_url

import datetime
import json

# Number of items per page in the news archive
NEWS_ITEMS_PER_PAGE = 10


def _news_meta_description(news):
    content = summarize_html(
        pgmarkdown(news.content or '', allow_relative_links=True),
        max_length=180,
    )
    return content or '{}。查看 PostgreSQL 中文社区新闻、公告与版本更新。'.format(news.title)


def archive(request, tag=None, paginator=None):
    if tag and tag.strip('/') != '-':
        tag = get_object_or_404(NewsTag, urlname=tag.strip('/'))
        news = NewsArticle.objects.select_related('org').filter(modstate=ModerationState.APPROVED, tags=tag)
    else:
        tag = None
        news = NewsArticle.objects.select_related('org').filter(modstate=ModerationState.APPROVED)
    cutoff_date = None
    if paginator and paginator.strip('/'):
        try:
            cutoff_date = datetime.datetime.strptime(paginator.strip('/'), '%Y%m%d').date()
            news = news.filter(date__lte=cutoff_date)
        except ValueError:
            raise Http404

    allnews = list(news.prefetch_related('tags').order_by('-date')[:NEWS_ITEMS_PER_PAGE + 1])
    paginator_date = None
    if len(allnews) == NEWS_ITEMS_PER_PAGE + 1:
        # 11 means we have a second page, so set a paginator link
        paginator_date = allnews[NEWS_ITEMS_PER_PAGE - 1].date
        paginator = paginator_date.strftime("%Y%m%d")
    else:
        paginator = None

    page_title = '新闻归档'
    page_description = '浏览 PostgreSQL 中文社区新闻、公告与版本更新。'
    if tag:
        page_title += ' - {}'.format(tag.name)
        page_description = '{}标签下的 PostgreSQL 新闻、公告与版本更新。'.format(tag.name)
    if cutoff_date:
        date_text = '{} 年 {} 月 {} 日'.format(cutoff_date.year, cutoff_date.month, cutoff_date.day)
        page_title += '（截至 {}）'.format(date_text)
        page_description += '当前页面截止日期为 {}。'.format(date_text)

    return render_pgweb(request, 'about', 'news/newsarchive.html', {
        'news': allnews[:NEWS_ITEMS_PER_PAGE],
        'paginator': paginator,
        'paginator_date': paginator_date,
        'cutoff_date': cutoff_date,
        'page_title': page_title,
        'tag': tag,
        'newstags': NewsTag.objects.all(),
        'og': {
            'url': request.path,
            'title': page_title,
            'description': page_description,
            'type': 'website',
            'sitename': 'PostgreSQL 新闻',
        },
    })


def item(request, itemid, slug=None):
    news = get_object_or_404(NewsArticle, pk=itemid)
    if news.modstate != ModerationState.APPROVED:
        raise Http404

    fullurl = news_url(news.title, news.id)
    if slug != news_slug(news.title):
        return HttpResponsePermanentRedirect(fullurl)

    return render_pgweb(request, 'about', 'news/item.html', {
        'obj': news,
        'newstags': NewsTag.objects.all(),
        'og': {
            'url': fullurl,
            'author': news.org.name if news.org.name != '_migrated' else '',
            'time': datetime.datetime.combine(news.date, datetime.datetime.min.time()),
            'title': news.title,
            'description': _news_meta_description(news),
            'noimage': news.org.mailtemplate == 'default',  # For now, control image by "using a custom logo"
            'sitename': 'PostgreSQL 新闻',
        }
    })


def taglist_json(request):
    return HttpResponse(json.dumps({
        'tags': [{
            'urlname': t.urlname,
            'name': t.name,
            'description': t.description,
            'sortkey': t.sortkey,
        } for t in NewsTag.objects.order_by('urlname').distinct('urlname')],
    }), content_type='application/json')
