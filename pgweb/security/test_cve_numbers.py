from datetime import date
from unittest.mock import patch

from django.db import connection
from django.http import HttpResponse
from django.test import TestCase

from pgweb.core.models import Version
from pgweb.security.loader import _load_all_cve_json, load_security_json
from pgweb.security.models import SecurityPatch, SecurityPatchVersion


class CveNumberTests(TestCase):
    def setUp(self):
        self.enterContext(patch('pgweb.util.signals.varnish_purge'))
        self.enterContext(patch('pgweb.util.signals.varnish_purge_xkey'))
        self.enterContext(patch('pgweb.util.signals.send_simple_mail'))

    def create_patch(self, cve):
        return SecurityPatch.objects.create(
            cve=cve, public=True, component='core server',
            description='已有中文标题', details='已有中文详情',
        )

    def test_four_to_seven_digit_cves_keep_year_order_and_resolve(self):
        identifiers = ['2025-9999999', '2026-6460', '2026-14661', '2026-116303']
        for cve in identifiers:
            self.create_patch(cve)
        self.assertEqual(
            list(SecurityPatch.objects.values_list('cve', flat=True)),
            list(reversed(identifiers)),
        )
        with patch('pgweb.security.views.render_pgweb', return_value=HttpResponse()) as render:
            for cve in identifiers:
                response = self.client.get('/support/security/CVE-{}/'.format(cve))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(render.call_args.args[3]['security_patch'].cve, cve)

    def test_import_preserves_translation_and_old_cve_when_pruning(self):
        version = Version(
            tree=18, latestminor=7, supported=True, reldate=date(2026, 11, 12),
            firstreldate=date(2025, 9, 25), eoldate=date(2030, 11, 14),
        )
        version.save()
        legacy = self.create_patch('2024-9999')
        SecurityPatchVersion.objects.create(patch=legacy, version=version, fixed_minor=0)
        missing = self.create_patch('2025-9999')
        SecurityPatchVersion.objects.create(patch=missing, version=version, fixed_minor=1)
        existing = self.create_patch('2026-116303')
        record = next(cve for cve in _load_all_cve_json() if cve['cveMetadata']['cveId'] == 'CVE-2026-116303')
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regprocedure('varnish_purge(text)')")
            if cursor.fetchone()[0] is None:
                cursor.execute("CREATE FUNCTION varnish_purge(text) RETURNS text LANGUAGE sql AS 'SELECT $1'")
        with patch('pgweb.security.loader._load_all_cve_json', return_value=iter([record])):
            load_security_json(prune_missing=True, overwrite_text=False, dry_run=True)
        self.assertTrue(SecurityPatch.objects.filter(pk=missing.pk).exists())
        for _ in range(2):
            with patch('pgweb.security.loader._load_all_cve_json', return_value=iter([record])):
                load_security_json(prune_missing=True, overwrite_text=False)
        existing.refresh_from_db()
        self.assertEqual(existing.description, '已有中文标题')
        self.assertEqual(existing.details, '已有中文详情')
        self.assertTrue(SecurityPatch.objects.filter(pk=legacy.pk).exists())
        self.assertTrue(SecurityPatchVersion.objects.filter(patch=legacy).exists())
        self.assertFalse(SecurityPatch.objects.filter(pk=missing.pk).exists())
        self.assertEqual(SecurityPatchVersion.objects.get(patch=existing, version=version).fixed_minor, 7)
