from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.template.defaultfilters import slugify

from .views import item, main


class EventSeoTests(SimpleTestCase):
    @patch('pgweb.events.views.render_pgweb', return_value=HttpResponse())
    @patch('pgweb.events.views.get_object_or_404')
    def test_event_metadata_uses_summary_and_preserves_event_title(self, get_event, render_pgweb):
        event = SimpleNamespace(
            id=7,
            title='SQL UPDATE 2026',
            approved=True,
            summary='TLSPUG PostgreSQL 聚会，欢迎社区成员参加。',
            details='更完整的活动说明。',
            startdate=date(2026, 4, 7),
        )
        get_event.return_value = event

        item(RequestFactory().get('/about/event/sql-update-2026-7/'), 7, slugify(event.title))

        context = render_pgweb.call_args.args[3]
        self.assertEqual(context['og']['title'], 'SQL UPDATE 2026')
        self.assertEqual(context['og']['url'], '/about/event/sql-update-2026-7/')
        self.assertIn('TLSPUG PostgreSQL', context['og']['description'])
        self.assertNotIn('time', context['og'])

    @patch('pgweb.events.views.render_pgweb', return_value=HttpResponse())
    @patch('pgweb.events.views.Event.objects')
    def test_event_listing_title_is_localized(self, events, render_pgweb):
        events.select_related.return_value.filter.return_value.order_by.return_value = []

        main(RequestFactory().get('/about/events/'))

        context = render_pgweb.call_args.args[3]
        self.assertEqual(context['title'], '近期活动')
        self.assertEqual(context['og']['url'], '/about/events/')
