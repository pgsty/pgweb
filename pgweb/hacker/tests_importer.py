import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from PIL import Image

from .importer import SnapshotError, load, preview, upsert
from .models import HackerProfile


class ImporterTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        buffer = io.BytesIO()
        Image.new('RGB', (24, 24), '#336791').save(buffer, 'WEBP')
        self.avatar = buffer.getvalue()
        (self.base / 'avatar.webp').write_bytes(self.avatar)
        self.profile = {
            'source_id': '17', 'slug': 'example-hacker-17', 'name': 'Example Hacker',
            'organization': 'Example', 'country': 'GB', 'bio': 'Database developer.\nContributor.',
            'source_url': 'https://pgnexus.ai/hacker-profiles/17',
            'data': {
                'list': {'id': '17', 'name': 'Example Hacker', 'future_field': {'nested': [None, True, 3]}},
                'detail': {'research': ['Project A'], 'bio_html': '<b>Preserve original</b>'},
                'sections': {'DiscussionsSection': {'initialItems': [{'title': 'A discussion'}], 'total': 19}},
                'emails': ['developer@example.com'],
                'links': [{'label': 'Homepage', 'url': 'https://example.com/'}],
                'avatar_sources': ['https://example.com/avatar.jpg'],
            },
            'avatar': {'path': 'avatar.webp', 'sha256': hashlib.sha256(self.avatar).hexdigest(),
                       'content_type': 'image/webp', 'source_url': 'https://example.com/avatar.jpg'},
        }
        self.payload = {'format': 1, 'fetched_at': '2026-09-26T11:00:00Z',
                        'source_url': 'https://pgnexus.ai/hacker-profiles',
                        'expected_count': 1, 'profiles': [self.profile]}
        self.path = self.base / 'profiles.json'

    def write(self, payload=None):
        self.path.write_text(json.dumps(payload or self.payload), encoding='utf-8')
        return self.path

    def test_full_source_and_unknown_fields_are_preserved(self):
        self.profile['new_top_level'] = {'present': [1, '二', None]}
        rows = load(self.write())
        self.assertEqual(upsert(rows), {'new': 1, 'updated': 0, 'unchanged': 0})
        item = HackerProfile.objects.get(source_id='17')
        for key, value in self.profile['data'].items():
            self.assertEqual(item.data[key], value)
        self.assertEqual(item.data['extra'], {'new_top_level': {'present': [1, '二', None]}})
        self.assertEqual(item.data['source_url'], self.profile['source_url'])
        self.assertEqual(item.data['snapshot']['expected_count'], 1)
        self.assertEqual(item.data['avatar'], self.profile['avatar'])
        self.assertEqual(bytes(item.avatar), self.avatar)
        self.assertEqual(item.avatar_content_type, 'image/webp')
        self.assertEqual(item.avatar_url, '/developer/hacker/example-hacker-17/avatar/')
        self.assertEqual(item.get_absolute_url(), '/developer/hacker/example-hacker-17/')

    def test_gzip_snapshot_loads_identically(self):
        rows = load(self.write())
        compressed = self.base / 'profiles.json.gz'
        compressed.write_bytes(gzip.compress(self.path.read_bytes(), mtime=0))
        self.assertEqual(load(compressed), rows)

    def test_unchanged_snapshot_does_not_write_or_refresh_timestamps(self):
        upsert(load(self.write()))
        before = HackerProfile.objects.get(source_id='17')
        self.payload['fetched_at'] = '2026-09-27T11:00:00Z'
        self.payload['archive_path'] = 'another-run'
        self.profile['data']['official_sources'] = [{'retrieved_at': '2026-09-27T11:00:00Z'}]
        self.profile['data']['avatar_errors'] = [{'error': 'prior fetch retry', 'fetched_at': '2026-09-27T11:00:00Z'}]
        rows = load(self.write())
        self.assertEqual(preview(rows), {'new': 0, 'updated': 0, 'unchanged': 1})
        with patch.object(HackerProfile, 'save', side_effect=AssertionError('unchanged row was written')):
            self.assertEqual(upsert(rows), {'new': 0, 'updated': 0, 'unchanged': 1})
        after = HackerProfile.objects.get(source_id='17')
        self.assertEqual(after.imported_at, before.imported_at)
        self.assertEqual(after.source_fetched_at, before.source_fetched_at)

    def test_changed_source_updates_in_place_and_preserves_existing_url(self):
        upsert(load(self.write()))
        before = HackerProfile.objects.get(source_id='17')
        before.texts = {'zh': {'bio': '人工整理的中文简介'}}
        before.save(update_fields=['texts'])
        self.profile['name'] = 'New Name'
        self.profile['slug'] = 'new-name-17'
        self.profile['data']['detail']['new_fact'] = {'a': 'b'}
        self.payload['fetched_at'] = '2026-09-27T11:00:00Z'
        self.assertEqual(upsert(load(self.write())), {'new': 0, 'updated': 1, 'unchanged': 0})
        after = HackerProfile.objects.get(source_id='17')
        self.assertEqual(after.pk, before.pk)
        self.assertEqual(after.slug, before.slug)
        self.assertEqual(after.name, 'New Name')
        self.assertEqual(after.texts, before.texts)
        self.assertEqual(after.data['detail']['new_fact'], {'a': 'b'})
        self.assertGreater(after.imported_at, before.imported_at)

    def test_missing_profiles_are_not_deleted(self):
        upsert(load(self.write()))
        self.profile.update(source_id='18', slug='other-18')
        upsert(load(self.write()))
        self.assertEqual(HackerProfile.objects.count(), 2)

    def test_check_validates_without_writing(self):
        out = io.StringIO()
        call_command('hacker_import', str(self.write()), check=True, stdout=out)
        self.assertEqual(HackerProfile.objects.count(), 0)
        self.assertEqual(json.loads(out.getvalue())['new'], 1)

    def test_invalid_last_record_writes_nothing(self):
        bad = copy.deepcopy(self.profile)
        bad.update(source_id='18', slug='second-18')
        bad['avatar']['sha256'] = '0' * 64
        self.payload['profiles'].append(bad)
        self.payload['expected_count'] = 2
        with self.assertRaisesMessage(CommandError, 'SHA-256 mismatch'):
            call_command('hacker_import', str(self.write()), stdout=io.StringIO())
        self.assertEqual(HackerProfile.objects.count(), 0)

    def test_database_failure_rolls_back_prior_rows(self):
        second = copy.deepcopy(self.profile)
        second.update(source_id='18', slug='second-18')
        self.payload['profiles'].append(second)
        self.payload['expected_count'] = 2
        rows = load(self.write())
        original_save = HackerProfile.save

        def fail_on_second(item, *args, **kwargs):
            if item.source_id == '18':
                raise RuntimeError('simulated database failure')
            return original_save(item, *args, **kwargs)

        with patch.object(HackerProfile, 'save', fail_on_second):
            with self.assertRaisesMessage(RuntimeError, 'simulated database failure'):
                upsert(rows)
        self.assertEqual(HackerProfile.objects.count(), 0)

    def test_slug_conflict_fails_before_writing(self):
        upsert(load(self.write()))
        self.profile['source_id'] = '18'
        with self.assertRaisesMessage(SnapshotError, 'already belongs'):
            upsert(load(self.write()))
        self.assertEqual(HackerProfile.objects.count(), 1)

    def test_duplicate_ids_slugs_and_incomplete_snapshot_are_rejected(self):
        bad = copy.deepcopy(self.profile)
        bad.update(slug='another-slug')
        self.payload['profiles'].append(bad)
        self.payload['expected_count'] = 2
        with self.assertRaisesMessage(SnapshotError, 'duplicate'):
            load(self.write())
        bad.update(source_id='18', slug=self.profile['slug'])
        with self.assertRaisesMessage(SnapshotError, 'duplicate'):
            load(self.write())
        bad['slug'] = 'second-18'
        self.payload['expected_count'] = 98
        with self.assertRaisesMessage(SnapshotError, 'expected_count'):
            load(self.write())

    def test_avatar_bytes_and_content_type_are_verified(self):
        for body, content_type, expected in (
            (b'<svg onload="alert(1)"></svg>', 'image/webp', 'valid WebP'),
            (self.avatar, 'image/svg+xml', 'content type'),
        ):
            with self.subTest(content_type=content_type):
                (self.base / 'avatar.webp').write_bytes(body)
                self.profile['avatar'].update(sha256=hashlib.sha256(body).hexdigest(), content_type=content_type)
                with self.assertRaisesMessage(SnapshotError, expected):
                    load(self.write())

    def test_avatar_paths_cannot_escape_snapshot(self):
        for name in ('../avatar.webp', str(self.base / 'avatar.webp')):
            with self.subTest(path=name):
                self.profile['avatar']['path'] = name
                with self.assertRaisesMessage(SnapshotError, 'inside the snapshot directory'):
                    load(self.write())

    def test_missing_avatar_is_valid_and_has_no_image_url(self):
        self.profile['avatar'] = None
        upsert(load(self.write()))
        item = HackerProfile.objects.get(source_id='17')
        self.assertIsNone(item.avatar)
        self.assertEqual(item.avatar_sha256, '')
        self.assertEqual(item.avatar_url, '')

    def test_failed_refresh_of_same_avatar_keeps_local_copy(self):
        upsert(load(self.write()))
        self.profile['avatar'] = None
        self.profile['data']['avatar_errors'] = [{'url': 'https://example.com/avatar.jpg', 'status': 403}]
        rows = load(self.write())
        self.assertEqual(preview(rows), {'new': 0, 'updated': 0, 'unchanged': 1})
        self.assertEqual(upsert(rows), {'new': 0, 'updated': 0, 'unchanged': 1})
        self.profile['bio'] = 'Updated biography while the image server is unavailable.'
        self.assertEqual(upsert(load(self.write())), {'new': 0, 'updated': 1, 'unchanged': 0})
        item = HackerProfile.objects.get(source_id='17')
        self.assertEqual(bytes(item.avatar), self.avatar)
        self.assertEqual(item.bio, self.profile['bio'])
        self.assertEqual(item.data['avatar_errors'][0]['status'], 403)

    def test_changed_avatar_source_does_not_keep_stale_portrait(self):
        upsert(load(self.write()))
        self.profile['avatar'] = None
        self.profile['data']['avatar_errors'] = [{'status': 404}]
        self.profile['data']['avatar_sources'] = ['https://example.com/new-avatar.jpg']
        upsert(load(self.write()))
        self.assertIsNone(HackerProfile.objects.get(source_id='17').avatar)

    def test_nonstandard_json_numbers_and_naive_time_are_rejected(self):
        self.profile['data']['invalid'] = float('nan')
        with self.assertRaisesMessage(SnapshotError, 'Invalid JSON number'):
            load(self.write())
        del self.profile['data']['invalid']
        self.payload['fetched_at'] = '2026-09-26T11:00:00'
        with self.assertRaisesMessage(SnapshotError, 'timezone'):
            load(self.write())
