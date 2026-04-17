#!/usr/bin/env python3
#
# Script to post previously unposted news to social media providers
#

import time
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.template.defaultfilters import slugify

from pgweb.news.models import NewsArticle, PinnedNewsArticle
from pgweb.util.moderation import ModerationState
from pgweb.util.socialposter import get_all_providers


allproviders, allprovidernames = get_all_providers(settings)


class Command(BaseCommand):
    help = 'Post to social media'

    def handle(self, *args, **options):
        if not allprovidernames:
            # If we have no providers, there is no posting.
            return

        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(62387372)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing social_post process stuck?")

        articles = list(
            NewsArticle.objects.filter(
                modstate=ModerationState.APPROVED,
                date__gt=datetime.now() - timedelta(days=7),
            ).exclude(postedto__has_keys=allprovidernames).order_by('date')
        )

        for i, article in enumerate(articles):
            if i != 0:
                # Don't post more often than once / 30 seconds, to not trigger flooding.
                time.sleep(30)

            statusstr = "News: {0}\n\n{1}/about/news/{2}-{3}/\n\n#postgresql".format(
                article.title[:100],
                settings.SITE_ROOT,
                slugify(article.title),
                article.id,
            )

            for provider in allproviders:
                if provider.name not in article.postedto:
                    postid = provider.post(statusstr)
                    if postid is not None:
                        article.postedto[provider.name] = postid
                        article.save(update_fields=['postedto'])

        # Pin or unpin any articles as needed.
        pinned = (
            PinnedNewsArticle.objects.select_related('pinnedarticle')
            .only('pinnedarticle', 'pinnedtoproviders', 'pinnedarticle__postedto')
            .first()
        )
        if not pinned:
            return

        for provider in allproviders:
            pinnedid = pinned.pinnedarticle.postedto.get(provider.name) if pinned.pinnedarticle else None
            if pinned.pinnedtoproviders.get(provider.name) != pinnedid:
                if provider.set_pin(pinnedid):
                    pinned.pinnedtoproviders[provider.name] = pinnedid
                    pinned.save(update_fields=['pinnedtoproviders'])
