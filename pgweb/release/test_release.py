from pathlib import Path
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase, override_settings

from pgweb.util.versions import ParsedVersion
from pgweb.core.templatetags.pgfilters import joinzh, max_filter

from .apps import do_post_migrate
from .util import determine_release_type


class ReleaseDataTests(SimpleTestCase):
    def test_minor_release_versions_preserve_two_digit_minors(self):
        release_path = Path(__file__).resolve().parents[2] / 'data' / 'releases' / '2026-05-14.yaml'
        with release_path.open() as release_file:
            release = yaml.safe_load(release_file)

        self.assertEqual(release['versions'], ['18.4', '17.10', '16.14', '15.18', '14.23'])
        self.assertEqual(
            [(version.major, version.minor) for version in map(ParsedVersion, release['versions'])],
            [(18, 4), (17, 10), (16, 14), (15, 18), (14, 23)],
        )

    def test_local_current_release_targets_translated_news(self):
        release_path = Path(__file__).resolve().parents[2] / 'data' / 'releases' / '2026-08-13.yaml'
        with release_path.open() as release_file:
            release = yaml.safe_load(release_file)

        self.assertEqual(
            release['versions'],
            ['18.6', '17.11', '16.15', '15.19', '14.24', '19beta3'],
        )
        self.assertEqual(release['news']['id'], 3365)

    def test_prerelease_type_and_chinese_display_value(self):
        version = ParsedVersion('19beta3')

        self.assertEqual(determine_release_type({'versions': [version]}), 'beta')
        self.assertEqual(str(version), '19 Beta 3')

    def test_chinese_release_list_uses_conjunction_before_last_item(self):
        versions = [
            ParsedVersion(version)
            for version in ('18.6', '17.11', '16.15', '15.19', '14.24', '19beta3')
        ]

        self.assertEqual(
            joinzh(versions),
            '18.6、17.11、16.15、15.19、14.24 与 19 Beta 3',
        )

    def test_mixed_release_selects_pg19_for_press_kit(self):
        versions = [
            ParsedVersion(version)
            for version in ('18.6', '17.11', '16.15', '15.19', '14.24', '19beta3')
        ]

        self.assertEqual(max_filter(versions).major, 19)

    @override_settings(RELEASE_AUTO_PROCESS=False)
    @patch('pgweb.release.migrate.do_migrate')
    def test_post_migrate_does_not_process_release_by_default(self, migrate):
        do_post_migrate(sender=None)

        migrate.assert_not_called()
