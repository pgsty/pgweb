import io
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from .models import HackerProfile


class LocalizationTests(TestCase):
    def setUp(self):
        self.profile = HackerProfile.objects.create(
            source_id='1', slug='person-1', name='Person', bio='Original biography',
            data={'original': True}, content_hash='a' * 64, source_fetched_at=timezone.now(),
            texts={'en': {'bio': 'English biography'}},
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'zh.json'
        self.payload = {'format': 1, 'language': 'zh', 'profiles': [
            {'source_id': '1', 'name': 'Person', 'bio': '开发者中文简介', 'position': '',
             'organization': '', 'location': '', 'review_note': ''},
        ]}

    def run_import(self, check=False):
        self.path.write_text(json.dumps(self.payload), encoding='utf-8')
        output = io.StringIO()
        call_command('hacker_localize', str(self.path), check=check, stdout=output)
        return json.loads(output.getvalue())

    def test_check_import_and_idempotence_preserve_sources_and_other_languages(self):
        self.assertEqual(self.run_import(check=True)['updated'], 1)
        self.profile.refresh_from_db()
        self.assertNotIn('zh', self.profile.texts)
        self.assertEqual(self.run_import()['updated'], 1)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.zh['bio'], '开发者中文简介')
        self.assertEqual(self.profile.bio, 'Original biography')
        self.assertEqual(self.profile.data, {'original': True})
        self.assertEqual(self.profile.content_hash, 'a' * 64)
        self.assertEqual(self.profile.texts['en']['bio'], 'English biography')
        imported_at = self.profile.imported_at
        self.assertEqual(self.run_import()['unchanged'], 1)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.imported_at, imported_at)

    def test_invalid_later_row_does_not_partially_write(self):
        self.payload['profiles'].append(dict(self.payload['profiles'][0], source_id='2'))
        with self.assertRaises(CommandError):
            self.run_import()
        self.profile.refresh_from_db()
        self.assertNotIn('zh', self.profile.texts)

    def test_missing_profile_prevents_partial_translation_set(self):
        HackerProfile.objects.create(source_id='2', slug='other-2', name='Other', content_hash='b' * 64,
                                     source_fetched_at=timezone.now())
        with self.assertRaisesMessage(CommandError, 'every stored profile'):
            self.run_import()
        self.profile.refresh_from_db()
        self.assertNotIn('zh', self.profile.texts)
