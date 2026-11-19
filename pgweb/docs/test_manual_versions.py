from datetime import date
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from pgweb.core.models import Version
from .models import DocPage
from .versions import manual_groups, manual_prerelease


@override_settings(ALLOWED_HOSTS=['testserver'])
class ManualBuildTests(TestCase):
    def setUp(self):
        self.enterContext(patch('pgweb.util.signals.varnish_purge'))
        self.enterContext(patch('pgweb.util.signals.varnish_purge_xkey'))
        cache.clear()
        self.addCleanup(cache.clear)
        self.version = Version(tree=19, latestminor=1, testing=1, supported=False,
                               reldate=date(2026, 10, 15), firstreldate=date(2026, 6, 4),
                               eoldate=date(2031, 11, 13))
        self.version.save()
        self.page = DocPage.objects.create(version=self.version, file='index.html',
                                           title='PostgreSQL 19beta4 手册', content='<p>Beta 4 手册</p>')

    def test_new_release_does_not_relabel_loaded_manual(self):
        self.assertEqual(str(manual_prerelease(self.version)), '19 Beta 4')
        self.assertEqual(manual_groups()['testing'], [{'major': 19, 'label': 'beta'}])
        response = self.client.get('/docs/19/index.html')
        self.assertContains(response, 'PostgreSQL 19 Beta 4')
        self.assertNotContains(response, 'PostgreSQL 19 RC 1')

    def test_rc_manual_updates_label_after_import(self):
        self.page.title = 'PostgreSQL 19rc1 手册'
        self.page.save()
        cache.clear()
        self.assertEqual(str(manual_prerelease(self.version)), '19 RC 1')
        self.assertEqual(manual_groups()['testing'], [{'major': 19, 'label': 'rc'}])

    def test_unknown_manual_build_does_not_guess_latest_release(self):
        self.page.title = 'PostgreSQL 19 手册'
        self.page.save()
        cache.clear()
        self.assertIsNone(manual_prerelease(self.version))
        self.assertContains(self.client.get('/docs/19/index.html'), 'PostgreSQL 19 预发布版')

    def test_final_release_keeps_preview_manual_and_pdf_labels(self):
        self.version.testing = 0
        self.version.latestminor = 0
        self.version.supported = True
        self.version.current = True
        self.version.save()
        self.page.title = 'PostgreSQL 19rc2 手册'
        self.page.save()
        DocPage.objects.create(version=self.version, file='release-19.html', title='19 RC 2 发行说明', content='<p>RC 2</p>')

        self.assertEqual(manual_groups()['testing'], [{'major': 19, 'label': 'rc'}])
        self.assertNotIn(19, manual_groups()['supported'])
        response = self.client.get('/docs/current/index.html')
        self.assertContains(response, '已正式发布，本页中文译文仍基于 PostgreSQL 19 RC 2')
        self.assertNotContains(response, '尚未正式发布')
        self.assertContains(response, '上游文档表单')
        self.assertContains(self.client.get('/docs/'), '当前译文：PostgreSQL 19 RC 2')
        self.assertEqual(self.version.relnotes_url, 'https://www.postgresql.org/docs/19/release-19.html')

    def test_final_manual_import_removes_preview_notice(self):
        self.version.testing = 0
        self.version.latestminor = 0
        self.version.supported = True
        self.version.save()
        self.page.title = 'PostgreSQL 19.0 手册'
        self.page.save()
        DocPage.objects.create(version=self.version, file='release-19.html', title='19.0 发行说明', content='<p>19.0</p>')

        self.assertEqual(manual_groups()['supported'], [19])
        self.assertEqual(manual_groups()['testing'], [])
        response = self.client.get('/docs/19/index.html')
        self.assertNotContains(response, '译文构建</strong>')
        self.assertEqual(self.version.relnotes_url, '/docs/19/release-19.html')
