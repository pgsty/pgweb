from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from pgweb.core.models import Version

from .models import SecurityPatch
from .struct import get_struct
from .views import _list_patches, details


class SecuritySeoTests(SimpleTestCase):
    def test_sitemap_has_version_and_trailing_slash_cve_urls(self):
        version = SimpleNamespace(numtree='18')
        patch_row = SimpleNamespace(cve='2026-1234')

        versions = Mock()
        versions.filter.return_value.order_by.return_value = [version]
        patches = Mock()
        patches.filter.return_value.exclude.return_value.order_by.return_value = [patch_row]
        with patch.object(Version, 'objects', versions), patch.object(SecurityPatch, 'objects', patches):
            entries = list(get_struct())

        self.assertEqual(
            entries,
            [
                ('support/security/', None),
                ('support/security/18/', None),
                ('support/security/CVE-2026-1234/', None),
            ],
        )

    @patch('pgweb.security.views.render_pgweb', return_value=HttpResponse())
    @patch('pgweb.security.views.GetPatchesList', return_value=[])
    @patch('pgweb.security.views.Version.objects')
    def test_version_list_title_identifies_major_version(self, versions, get_patches, render_pgweb):
        versions.filter.return_value = versions
        versions.extra.return_value = versions
        version = SimpleNamespace(numtree='18')
        _list_patches(RequestFactory().get('/support/security/18/'), 'v.supported', version)

        context = render_pgweb.call_args.args[3]
        self.assertEqual(context['page_title'], '安全信息：版本 18')
        self.assertIn('PostgreSQL 18', context['og']['description'])
        self.assertEqual(context['og']['url'], '/support/security/18/')

    @patch('pgweb.security.views.render_pgweb', return_value=HttpResponse())
    @patch('pgweb.security.views.get_object_or_404')
    def test_cve_metadata_keeps_identifier_and_description(self, get_patch, render_pgweb):
        security_patch = SimpleNamespace(
            cve='2026-1234',
            description='权限检查错误',
            details='修复了受影响版本中的权限检查。',
            securitypatchversion_set=Mock(),
        )
        security_patch.securitypatchversion_set.select_related.return_value.order_by.return_value.all.return_value = []
        get_patch.return_value = security_patch

        details(RequestFactory().get('/support/security/CVE-2026-1234/'), 'CVE', '2026-1234')

        context = render_pgweb.call_args.args[3]
        self.assertEqual(context['page_title'], 'CVE-2026-1234: 权限检查错误')
        self.assertEqual(context['og']['url'], '/support/security/CVE-2026-1234/')
        self.assertIn('权限检查', context['og']['description'])
