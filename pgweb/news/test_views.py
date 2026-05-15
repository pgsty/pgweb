from django.http import Http404
from django.test import RequestFactory, SimpleTestCase

from pgweb.news.views import archive


class NewsArchivePaginationTests(SimpleTestCase):
    def test_invalid_paginator_raises_404(self):
        request = RequestFactory().get('/about/newsarchive/-/not-a-date/')

        with self.assertRaises(Http404):
            archive(request, paginator='not-a-date')
