from datetime import date, timedelta
from .models import NewsArticle
from .util import news_url

from pgweb.util.moderation import ModerationState


def get_struct():
    now = date.today()
    fouryearsago = date.today() - timedelta(4 * 365, 0, 0)

    # We intentionally don't put /about/newsarchive/ in the sitemap,
    # since we don't care about getting it indexed.
    # Also, don't bother indexing anything > 4 years old

    for n in NewsArticle.objects.filter(modstate=ModerationState.APPROVED, date__gt=fouryearsago):
        yearsold = (now - n.date).days / 365
        if yearsold > 4:
            yearsold = 4
        yield (news_url(n.title, n.id).lstrip('/'),
               0.5 - (yearsold / 10.0))
