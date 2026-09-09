from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from .views import _doc_page_title, docpage


class DocPageSeoTests(SimpleTestCase):
    def test_ecpg_file_family_is_distinguished_from_sql_command(self):
        ecpg = SimpleNamespace(
            file='ecpg-sql-declare.html',
            title='DECLARE',
            display_version=lambda: '18',
        )
        sql = SimpleNamespace(
            file='sql-declare.html',
            title='DECLARE',
            display_version=lambda: '18',
        )

        self.assertEqual(
            _doc_page_title(ecpg),
            'PostgreSQL 18 文档 · ECPG DECLARE',
        )
        self.assertEqual(
            _doc_page_title(sql),
            'PostgreSQL 18 文档 · DECLARE',
        )

    @patch('pgweb.docs.views.render', return_value=HttpResponse())
    @patch('pgweb.docs.views.DocPage.objects')
    def test_docpage_uses_same_ecpg_title_for_html_and_og(self, objects, render):
        loaded_at = datetime(2026, 9, 8, 12, 34, 56)
        version = SimpleNamespace(
            current=False,
            supported=True,
            testing=0,
            docsloaded=loaded_at,
        )
        page = SimpleNamespace(
            file='ecpg-sql-prepare.html',
            title='PREPARE',
            content='<p>准备一个用于执行的语句。</p>',
            version=version,
            display_version=lambda: '18',
        )
        query = objects.select_related.return_value
        query.get.return_value = page
        query.extra.return_value.order_by.return_value.only.return_value = [page]

        docpage(RequestFactory().get('/docs/18/ecpg-sql-prepare.html'), '18', 'ecpg-sql-prepare')

        context = render.call_args.args[2]
        self.assertEqual(context['seo']['title'], 'PostgreSQL 18 文档 · ECPG PREPARE')
        self.assertEqual(context['og']['title'], context['seo']['title'])
        self.assertEqual(context['og']['modified_time'], loaded_at)
        self.assertNotIn('time', context['og'])

    def test_document_modified_time_is_not_published_time(self):
        source = render_to_string('base/base.html', {
            'link_root': 'https://pg.center',
            'seo': {'title': 'PostgreSQL 18 文档 · ECPG PREPARE'},
            'og': {
                'url': '/docs/18/ecpg-sql-prepare.html',
                'title': 'PostgreSQL 18 文档 · ECPG PREPARE',
                'modified_time': datetime(2026, 9, 8, 12, 34, 56),
            },
        })

        self.assertIn('property="article:modified_time"', source)
        self.assertNotIn('property="article:published_time"', source)
