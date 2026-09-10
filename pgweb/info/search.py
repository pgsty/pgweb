"""博览 full-text search: its own index, never the document search or palette."""

from urllib.parse import urlencode

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.core.paginator import Paginator
from django.db.models import F, Value

from pgweb.search.lexicon import index_text, query_text
from pgweb.search.service import highlight

from .models import InfoItem

PAGE_SIZE = 20
MAX_QUERY = 255


def vector(item):
    """Title A, summary B, author/source/tags C, all pre-tokenised."""
    meta = ' '.join(filter(None, [item.author, item.source, *(item.tags or ())]))
    return (SearchVector(Value(index_text(item.title)), config='simple', weight='A') +
            SearchVector(Value(index_text(item.summary)), config='simple', weight='B') +
            SearchVector(Value(index_text(meta)), config='simple', weight='C'))


def result(item, term):
    return {
        'item': item,
        'key': item.key,
        'date': item.date,
        'tier': item.tier,
        'title': item.title,
        'title_html': highlight(item.title, term, 300),
        'snippet': highlight(item.summary, term) if item.summary else '',
        'url': item.url,
        'author': item.author,
        'source': item.source,
        'anchor_url': item.anchor_url,
    }


def search(q='', page=1):
    """Ranked published items. An empty or unusable query returns no results."""
    raw = (q or '').strip()[:MAX_QUERY]
    payload = {'q': raw, 'results': [], 'total': 0, 'page': None, 'pagination': [],
               'previous_url': '', 'next_url': '', 'searched': False}
    tokens = query_text(raw) if raw else ''
    if not tokens:
        return payload
    payload['searched'] = True
    query = SearchQuery(tokens, config='simple', search_type='plain')
    rows = (InfoItem.objects.filter(status='published', search_vector=query)
            .annotate(rank=SearchRank(F('search_vector'), query, cover_density=True))
            .order_by('-rank', '-date', 'tier', 'position', 'id'))
    pager = Paginator(rows, PAGE_SIZE)
    current = pager.get_page(page)
    payload.update({
        'total': pager.count,
        'page': current,
        'results': [result(item, raw) for item in current],
        'pagination': [{'label': number, 'current': number == current.number,
                        'url': page_url(raw, number) if isinstance(number, int) else ''}
                       for number in pager.get_elided_page_range(current.number, on_each_side=1, on_ends=1)],
        'previous_url': page_url(raw, current.previous_page_number()) if current.has_previous() else '',
        'next_url': page_url(raw, current.next_page_number()) if current.has_next() else '',
    })
    return payload


def page_url(q, number):
    params = {'q': q}
    if number and number > 1:
        params['page'] = number
    return '/info/search/?' + urlencode(params)
