from decimal import Decimal
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from .views import _release_note_neighbors, release_notes, release_notes_list


class ReleaseNotesGapTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/docs/release/')

    def test_unreleased_version_redirects_to_following_release(self):
        response = release_notes(self.request, '18.5')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/docs/release/18.6/')

    @patch('pgweb.docs.views.render_pgweb', return_value=HttpResponse())
    @patch('pgweb.docs.views.exec_to_dict')
    def test_archive_excludes_unreleased_version(self, exec_to_dict, render_pgweb):
        exec_to_dict.return_value = [
            {'major': Decimal('18'), 'minor': minor}
            for minor in range(6, -1, -1)
        ]

        release_notes_list(self.request)

        releases = render_pgweb.call_args.args[3]['releases']
        self.assertNotIn({'major': Decimal('18'), 'minor': 5}, releases)

    def test_navigation_skips_unreleased_version(self):
        versions = [{'minor': minor} for minor in (6, 4, 3)]

        self.assertEqual(
            _release_note_neighbors(versions, Decimal('6')),
            (4, None),
        )
        self.assertEqual(
            _release_note_neighbors(versions, Decimal('4')),
            (3, 6),
        )
