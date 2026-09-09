from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase

from .struct import get_struct
from .views import _loaded_version_wrappers


class DocumentationSitemapTests(SimpleTestCase):
    @patch('pgweb.docs.struct.connection')
    @patch('pgweb.docs.struct.Version.objects')
    def test_only_canonical_current_urls_are_emitted(self, objects, connection):
        current = type('Version', (), {'tree': Decimal('18.0')})()
        objects.get.return_value = current
        cursor = connection.cursor.return_value
        cursor.fetchall.return_value = [
            (Decimal('18.0'), 'index.html', datetime(2026, 8, 13), 0),
            (Decimal('17.0'), 'index.html', datetime(2026, 5, 14), 0),
        ]

        urls = [item[0] for item in get_struct()]

        self.assertNotIn('docs/18/index.html', urls)
        self.assertIn('docs/current/index.html', urls)
        self.assertIn('docs/17/index.html', urls)

    @patch('pgweb.docs.views.DocPage.objects')
    def test_version_table_marks_unloaded_manuals_without_linking_them(self, objects):
        old = type('Version', (), {'tree': Decimal('13.0'), 'numtree': 13})()
        objects.filter.return_value.values_list.return_value = []

        wrapped = _loaded_version_wrappers([old])

        self.assertEqual(len(wrapped), 1)
        self.assertFalse(wrapped[0].loaded)
        self.assertEqual(wrapped[0].indexname, 'index.html')
