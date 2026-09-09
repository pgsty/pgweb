from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pgweb.core.models import Version
from pgweb.docs.models import DocPage
from pgweb.docs.versions import DEVEL_MAJOR_VERSION
from . import service
from .models import IndexedPage, SearchEntry


class ManualVersionTests(TestCase):
    def setUp(self):
        service.forget_catalog()
        for tree in (0, 10, 18):
            Version.objects.bulk_create([Version(
                tree=tree, current=tree == 18, supported=tree == 18,
                testing=2 if tree == 0 else 0,
                reldate=date(2026, 9, 9), firstreldate=date(2026, 9, 9), eoldate=date(2030, 1, 1),
            )])
            DocPage.objects.create(version_id=tree, file='runtime-config-resource.html', title='资源消耗',
                content='<div class="sect1"><h2>资源消耗</h2><dl><dt id="GUC-WORK-MEM">'
                        '<code class="varname">work_mem</code></dt><dd><p>工作内存配置。'
                        '<a href="other.html">其他配置</a></p></dd></dl></div>')
        for major in (18, DEVEL_MAJOR_VERSION):
            DocPage.objects.create(version_id=0, file=f'release-{major}.html', title=f'发行说明 {major}',
                                   content=f'<h1>发行说明 {major}</h1><p>本版更新内容。</p>')

    def tearDown(self):
        service.forget_catalog()

    def test_archive_and_development_manuals_are_searchable_at_their_reader_urls(self):
        call_command('index_docs', versions=[10, DEVEL_MAJOR_VERSION], stdout=StringIO())
        archived = service.search('pg10: work_mem')['results'][0]
        self.assertEqual((archived['version'], archived['url']),
                         (10, '/docs/10/runtime-config-resource.html#GUC-WORK-MEM'))
        result = service.search(f'pg{DEVEL_MAJOR_VERSION}: work_mem')
        first = result['results'][0]
        self.assertEqual((first['version'], first['url']),
                         (DEVEL_MAJOR_VERSION, '/docs/devel/runtime-config-resource.html#GUC-WORK-MEM'))
        entry = SearchEntry.objects.select_related('document__page').get(pk=first['id'])
        self.assertIn('/docs/devel/other.html', service.preview(entry)['html'])
        self.assertEqual([v['version'] for v in result['versions']], [DEVEL_MAJOR_VERSION, 10])
        self.assertTrue(IndexedPage.objects.filter(page__version=0, page__file=f'release-{DEVEL_MAJOR_VERSION}.html').exists())
        self.assertFalse(IndexedPage.objects.filter(page__version=0, page__file='release-18.html').exists())
        legacy = self.client.get('/search/api/', {'q': 'work_mem', 'u': '/docs/devel/'}).json()
        self.assertEqual(legacy['version'], DEVEL_MAJOR_VERSION)
        page = self.client.get('/docs/devel/runtime-config-resource.html')
        self.assertContains(page, f'data-pg-palette-scope="pg{DEVEL_MAJOR_VERSION}"')
        alias = self.client.get(f'/docs/{DEVEL_MAJOR_VERSION}/runtime-config-resource.html')
        self.assertEqual(alias.status_code, 301)
        self.assertEqual(alias['Location'], '/docs/devel/runtime-config-resource.html')
