from pathlib import Path
from datetime import date, datetime
from io import StringIO
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase, TestCase, override_settings
from django.core.management import call_command

from pgweb.util.versions import ParsedVersion
from pgweb.core.templatetags.pgfilters import joinzh, max_filter

from .apps import do_post_migrate
from .migrate import do_migrate
from .util import determine_release_type
from .util import CurrentRelease
from pgweb.core.models import Version, Organisation, OrganisationType
from pgweb.news.models import NewsArticle, PinnedNewsArticle
from pgweb.util.moderation import ModerationState


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

    def test_november_release_keeps_15_20_and_marks_final_pg14_release(self):
        release_path = Path(__file__).resolve().parents[2] / 'data' / 'releases' / '2026-11-12.yaml'
        with release_path.open() as release_file:
            release = yaml.safe_load(release_file)

        self.assertEqual(release['versions'], ['18.7', '17.12', '16.16', '15.20', '14.25', '19rc2'])
        self.assertEqual(release['news']['id'], 3442)
        self.assertEqual(release['end_of_life'], [14])
        self.assertEqual(ParsedVersion(release['versions'][3]).minor, 20)

    def test_pg19_release_uses_local_news_and_verified_upstream_dates(self):
        release_path = Path(__file__).resolve().parents[2] / 'data' / 'releases' / '2026-11-19.yaml'
        with release_path.open() as release_file:
            release = yaml.safe_load(release_file)

        self.assertEqual(release['versions'], ['19.0'])
        self.assertEqual(release['date'], date(2026, 11, 19))
        self.assertEqual(release['eoldate'], date(2031, 11, 19))
        self.assertEqual(release['news'], {'id': 3451, 'upstream_id': 3449})
        self.assertEqual(release['notes_url'], 'https://www.postgresql.org/docs/release/19.0/')
        self.assertIn('读己之写', release['announcetext_zh'])
        self.assertEqual(determine_release_type({'versions': [ParsedVersion('19.0')]}), 'major')

    def test_release_note_link_uses_upstream_until_translation_is_loaded(self):
        version = Version(tree=15, latestminor=20)
        with patch('pgweb.docs.models.DocPage.objects.filter') as pages:
            pages.return_value.exists.return_value = False
            self.assertEqual(version.relnotes_url, 'https://www.postgresql.org/docs/15/release-15-20.html')
            pages.return_value.exists.return_value = True
            self.assertEqual(version.relnotes_url, '/docs/15/release-15-20.html')

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


@override_settings(RELEASE_SEND_ANNOUNCEMENT_EMAIL=False)
class MajorReleaseProcessingTests(SimpleTestCase):
    def setUp(self):
        release_path = Path(__file__).resolve().parents[2] / 'data' / 'releases' / '2026-11-19.yaml'
        with release_path.open() as release_file:
            self.release = yaml.safe_load(release_file)
        self.release['versions'] = [ParsedVersion(value) for value in self.release['versions']]
        self.release['type'] = determine_release_type(self.release)
        self.version = Version(
            id=19, tree=19, latestminor=2, testing=1, supported=False, current=False,
            reldate=date(2026, 11, 12), firstreldate=date(2026, 6, 4),
            eoldate=date(2031, 11, 13), docsloaded=datetime(2026, 11, 13, 9), docsgit='a' * 40,
        )
        self.news = NewsArticle(id=3451, title='PostgreSQL 19 发布', modstate=ModerationState.CREATED,
                                postedto={'upstream_sync': {'id': 3449}})
        self.pinned = PinnedNewsArticle(id=1, pinnedarticle=NewsArticle(id=3442))
        self.enterContext(patch.object(CurrentRelease, 'get', return_value=self.release))
        self.versions = self.enterContext(patch.object(Version.objects, 'only'))
        self.versions.return_value.get.return_value = self.version
        self.news_get = self.enterContext(patch.object(NewsArticle.objects, 'get', return_value=self.news))
        self.enterContext(patch.object(PinnedNewsArticle.objects, 'first', return_value=self.pinned))
        self.version_save = self.enterContext(patch.object(self.version, 'save'))
        self.news_save = self.enterContext(patch.object(self.news, 'save'))
        self.enterContext(patch.object(self.pinned, 'save'))
        self.email = self.enterContext(patch.object(self.news, 'on_approval'))
        self.enterContext(patch('sys.stdout', new=StringIO()))

    def process(self):
        # Exercise the processing logic without opening the atomic DB transaction.
        # SimpleTestCase rejects any unexpected database access by these mocks.
        do_migrate.__wrapped__()

    def test_rc_to_major_sets_ga_dates_preserves_manual_and_sends_no_email(self):
        self.process()
        self.assertEqual((self.version.testing, self.version.latestminor), (0, 0))
        self.assertTrue(self.version.current and self.version.supported)
        self.assertEqual(self.version.reldate, date(2026, 11, 19))
        self.assertEqual(self.version.firstreldate, date(2026, 11, 19))
        self.assertEqual(self.version.eoldate, date(2031, 11, 19))
        self.assertEqual(self.version.docsloaded, datetime(2026, 11, 13, 9))
        self.assertEqual(self.version.docsgit, 'a' * 40)
        self.assertTrue({'docsloaded', 'docsgit'}.isdisjoint(self.version_save.call_args.kwargs['update_fields']))
        self.news_get.assert_called_once_with(pk=3451)
        self.assertEqual(self.news.modstate, ModerationState.APPROVED)
        self.assertIs(self.pinned.pinnedarticle, self.news)
        self.email.assert_not_called()
        self.process()
        self.version_save.assert_called_once()
        self.news_save.assert_called_once()
        self.email.assert_not_called()

    def test_already_released_version_can_correct_lifecycle_dates(self):
        self.version.testing = self.version.latestminor = 0
        self.version.current = self.version.supported = True
        self.version.reldate = date(2026, 11, 19)
        self.process()
        self.assertEqual(self.version.firstreldate, date(2026, 11, 19))
        self.assertEqual(self.version.eoldate, date(2031, 11, 19))
        self.assertEqual(set(self.version_save.call_args.kwargs['update_fields']), {'firstreldate', 'eoldate'})

    def test_wrong_news_mapping_is_rejected_before_version_changes(self):
        self.news.postedto = {'upstream_sync': {'id': 3444}}
        with self.assertRaisesMessage(ValueError, 'expected upstream article 3449'):
            self.process()
        self.versions.assert_not_called()
        self.email.assert_not_called()

    def test_major_release_does_not_infer_end_of_life(self):
        del self.release['eoldate']
        self.process()
        self.assertEqual(self.version.eoldate, date(2031, 11, 13))
        self.assertNotIn('eoldate', self.version_save.call_args.kwargs['update_fields'])

    def test_invalid_end_of_life_is_rejected_before_any_processing(self):
        for value in ('2031-11-19', None, datetime(2031, 11, 19), date(2026, 11, 19), date(2026, 11, 18)):
            with self.subTest(eoldate=value):
                self.release['eoldate'] = value
                with self.assertRaisesMessage(ValueError, 'eoldate must be a date after the release date'):
                    self.process()
                self.versions.assert_not_called()
                self.news_get.assert_not_called()

    def test_explicit_end_of_life_requires_a_single_major_release(self):
        for versions in (['19rc2'], ['19.1'], ['19.0', '18.7']):
            with self.subTest(versions=versions):
                self.release['versions'] = [ParsedVersion(value) for value in versions]
                self.release['type'] = 'major' if versions[0] == '19.0' else self.release['versions'][0].type
                with self.assertRaisesMessage(ValueError, 'eoldate requires a single major release'):
                    self.process()
                self.versions.assert_not_called()
                self.news_get.assert_not_called()

    def test_minor_release_preserves_first_release_and_support_deadline(self):
        self.release.update(date=date(2027, 2, 11), versions=[ParsedVersion('19.1')], type='minor')
        del self.release['eoldate']
        self.version.testing = self.version.latestminor = 0
        self.version.current = self.version.supported = True
        self.version.firstreldate = date(2026, 11, 19)
        self.version.eoldate = date(2031, 11, 19)
        self.process()
        self.assertEqual(self.version.latestminor, 1)
        self.assertEqual(self.version.reldate, date(2027, 2, 11))
        self.assertEqual(self.version.firstreldate, date(2026, 11, 19))
        self.assertEqual(self.version.eoldate, date(2031, 11, 19))
        self.assertEqual(set(self.version_save.call_args.kwargs['update_fields']), {'latestminor', 'reldate'})


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

    def test_final_minor_release_rolls_back_then_ends_support_idempotently(self):
        version = Version(
            tree=14, latestminor=24, testing=0, supported=True,
            reldate=date(2026, 8, 13), firstreldate=date(2021, 9, 30),
            eoldate=date(2026, 11, 12),
        )
        version.save()
        release = {
            'date': date(2026, 11, 12), 'type': 'minor',
            'versions': [ParsedVersion('14.25')], 'end_of_life': [14],
        }
        with patch.object(CurrentRelease, 'get', return_value=release):
            call_command('process_release', dry_run=True, stdout=StringIO())
            version.refresh_from_db()
            self.assertEqual(version.latestminor, 24)
            self.assertTrue(version.supported)
            for _ in range(2):
                call_command('process_release', stdout=StringIO())
        version.refresh_from_db()
        self.assertEqual(version.latestminor, 25)
        self.assertFalse(version.supported or version.current)

    def test_end_of_life_before_scheduled_date_is_rejected_and_rolled_back(self):
        version = Version(
            tree=14, latestminor=24, testing=0, supported=True,
            reldate=date(2026, 8, 13), firstreldate=date(2021, 9, 30),
            eoldate=date(2026, 11, 12),
        )
        version.save()
        release = {
            'date': date(2026, 11, 11), 'type': 'minor',
            'versions': [ParsedVersion('14.25')], 'end_of_life': [14],
        }
        with patch.object(CurrentRelease, 'get', return_value=release):
            with self.assertRaisesMessage(ValueError, 'has not reached its end-of-life date'):
                call_command('process_release', stdout=StringIO())
        version.refresh_from_db()
        self.assertEqual(version.latestminor, 24)
        self.assertTrue(version.supported)
