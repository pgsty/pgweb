from django.template.loader import render_to_string
from django.test import SimpleTestCase

from .views import _localize_book


class LocalizedBooksTests(SimpleTestCase):
    def test_localizes_book_metadata_without_changing_canonical_fields(self):
        book = {
            'title': 'Example',
            'url': 'https://example.com/book',
            'image': 'example.png',
            'author': 'Author',
            'language': 'English',
            'version': '18',
            'format': 'Paperback, eBook',
            'published': 'April 2026',
        }

        localized = _localize_book(book)

        self.assertEqual(localized['title'], 'Example')
        self.assertEqual(localized['language_zh'], '英语')
        self.assertEqual(localized['format_zh'], '平装书、电子书')
        self.assertEqual(localized['published_zh'], '2026年4月')

    def test_template_uses_each_books_own_url(self):
        books = [
            _localize_book({
                'title': 'First',
                'url': 'https://example.com/first',
                'image': 'first.png',
                'author': 'One',
                'language': 'English',
                'version': '18',
                'format': 'eBook',
                'published': 'April 2026',
            }),
            _localize_book({
                'title': 'Second',
                'url': 'https://example.com/second',
                'image': 'second.png',
                'author': 'Two',
                'language': 'German',
                'version': '17',
                'format': 'Hardback',
                'published': 'August 2003 (auf Deutsch/in German)',
            }),
        ]

        rendered = render_to_string('docs/books.html', {'books': books})

        self.assertIn('href="https://example.com/first"', rendered)
        self.assertIn('href="https://example.com/second"', rendered)
        self.assertIn('2003年8月（德语版）', rendered)
