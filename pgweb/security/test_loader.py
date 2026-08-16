from pathlib import Path
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase, override_settings

from .apps import do_post_migrate
from .loader import _load_all_cve_json


class SecurityLoaderTests(SimpleTestCase):
    def test_new_cves_receive_localized_text_overlay(self):
        cves = {
            cve['cveMetadata']['cveId']: cve
            for cve in _load_all_cve_json()
        }

        self.assertEqual(len(cves), 51)
        self.assertEqual(
            cves['CVE-2026-6472']['_pgcenter']['title'],
            'PostgreSQL CREATE TYPE 未检查多重范围类型所在 schema 的 CREATE 权限',
        )
        self.assertIn(
            'PostgreSQL 18.4、17.10、16.14、15.18 和 14.23',
            cves['CVE-2026-6472']['_pgcenter']['description'],
        )

    def test_current_release_cves_all_have_chinese_overlays(self):
        data_path = Path(__file__).resolve().parents[2] / 'data'
        with (data_path / 'releases' / '2026-08-13.yaml').open() as release_file:
            release = yaml.safe_load(release_file)
        with (data_path / 'security' / 'cve_zh.yaml').open() as translation_file:
            translations = yaml.safe_load(translation_file)

        current_cves = {'CVE-{}'.format(cve) for cve in release['cve']}
        self.assertEqual(len(current_cves), 28)
        self.assertTrue(current_cves.issubset(translations))

    @override_settings(SECURITY_CVE_AUTOLOAD=False)
    @patch('pgweb.security.loader.load_security_json')
    def test_post_migrate_does_not_load_cves_by_default(self, loader):
        do_post_migrate(sender=None)

        loader.assert_not_called()
