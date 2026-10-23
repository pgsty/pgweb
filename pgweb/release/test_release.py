from pathlib import Path
from datetime import date
from io import StringIO
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase, TestCase, override_settings
from django.core.management import call_command

from pgweb.util.versions import ParsedVersion
from pgweb.core.templatetags.pgfilters import joinzh, max_filter

from .apps import do_post_migrate
from .util import determine_release_type
from .util import CurrentRelease
from pgweb.core.models import Version, Organisation, OrganisationType
from pgweb.news.models import NewsArticle, PinnedNewsArticle


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

    def test_rc_display_is_uppercase_but_download_version_stays_compact(self):
        self.assertEqual(str(ParsedVersion('19rc1')), '19 RC 1')
        version = Version(tree=19, latestminor=1, testing=1)
        self.assertEqual(version.versionstring_spaced, '19 RC 1')
        self.assertEqual(version.versionstring, '19rc1')

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


class ReleaseProcessingTests(TestCase):
    def setUp(self):
        self.enterContext(patch('pgweb.util.signals.varnish_purge'))
        self.enterContext(patch('pgweb.util.signals.varnish_purge_xkey'))
        self.enterContext(patch('pgweb.util.signals.send_simple_mail'))

    def test_beta_to_rc_dry_run_then_idempotent_apply_without_email(self):
        dates = dict(reldate=date(2026, 9, 24), firstreldate=date(2026, 6, 4), eoldate=date(2031, 11, 13))
        preview = Version(tree=19, latestminor=4, testing=2, supported=False, **dates)
        preview.save()
        stable = Version(tree=18, latestminor=6, testing=0, supported=True, current=True, **dates)
        stable.save()
        orgtype = OrganisationType.objects.create(typename='项目')
        org = Organisation.objects.create(name='PostgreSQL', orgtype=orgtype, url='https://postgresql.org')
        news = NewsArticle.objects.create(org=org, title='PostgreSQL 19 RC 1 发布', content='已审核的中文公告', modstate=2)
        pinned = PinnedNewsArticle.objects.get()
        release = {'date': date(2026, 10, 15), 'type': 'rc', 'versions': [ParsedVersion('19rc1')], 'news': {'id': news.pk}}
        with patch.object(CurrentRelease, 'get', return_value=release), patch.object(NewsArticle, 'on_approval') as email:
            call_command('process_release', dry_run=True, stdout=StringIO())
            preview.refresh_from_db()
            pinned.refresh_from_db()
            self.assertEqual((preview.testing, preview.latestminor), (2, 4))
            self.assertIsNone(pinned.pinnedarticle_id)
            for _ in range(2):
                call_command('process_release', stdout=StringIO())
            email.assert_not_called()
        preview.refresh_from_db()
        stable.refresh_from_db()
        pinned.refresh_from_db()
        self.assertEqual((preview.testing, preview.latestminor, preview.reldate), (1, 1, date(2026, 10, 15)))
        self.assertFalse(preview.current or preview.supported)
        self.assertTrue(stable.current and stable.supported)
        self.assertEqual(pinned.pinnedarticle_id, news.pk)
        self.assertEqual(NewsArticle.objects.count(), 1)
