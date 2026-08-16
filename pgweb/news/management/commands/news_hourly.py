#!/usr/bin/env python3
#
# 每小时运行一次：发布禁发时段已经结束的新闻。
#
#

from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import datetime, date

from pgweb.util.moderation import ModerationState
from pgweb.news.models import NewsArticle, NewsPostingEmbargo
from pgweb.mailqueue.util import send_simple_mail


class Command(BaseCommand):
    help = '发布禁发时段已经结束的新闻（每次最多一篇）'

    def handle(self, *args, **options):
        self.post_embargoed_news()

    @transaction.atomic
    def post_embargoed_news(self):
        # Fetch up to 2 article, to see if there is more than one in the queue
        articles = list(NewsArticle.objects.filter(modstate=ModerationState.EMBARGOED).order_by('date')[:2])
        if articles:
            # One or more embargoed articles. Do we have an active embargo?
            if not NewsPostingEmbargo.objects.filter(duration__contains=datetime.now()):
                # No embargo! So we post *one* news item at this point. If there is more than one, we will come back
                # and post it on the next iteration.
                a = articles[0]
                a.modstate = ModerationState.APPROVED
                a.date = date.today()
                a.send_notification = False  # We'll send our own notification
                a.save(update_fields=['modstate', 'date'])
                a.on_approval(None)

                if len(articles) > 1:
                    extra = "\n禁发队列中至少还有一篇新闻，将在下一个小时继续发布，以错开发布时间。\n"
                else:
                    extra = ""

                # Send a notification to moderators only
                send_simple_mail(
                    settings.NOTIFICATION_FROM,
                    settings.NOTIFICATION_EMAIL,
                    "新闻已解除禁发并发布",
                    "标题为“{}”的新闻已解除禁发并发布。\n{}".format(a.title, extra),
                )
