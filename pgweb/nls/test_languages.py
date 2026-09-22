"""Catalog identity and review state must stay isolated across language/version."""

from copy import deepcopy
import json
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from . import service
from .importer import BundleError, load
from .models import Message
from .tests import message, write_bundle
from .validate import candidate_po


class LanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reviewer = User.objects.create_user('reviewer')
        cls.reviewer.user_permissions.add(Permission.objects.get(content_type__app_label='nls', codename='review'))
        english = 'could not open file "%s": %m'
        cls.cn = message('cn1', 'psql', english, {'': '不能打开文件 "%s": %m'})
        cls.tw = message('tw1', 'psql', english, {'': '不能開啟檔案 "%s": %m'})
        cls.tw_other = message('tw2', 'postgres', english, {'': '不能開啟檔案 "%s": %m'})
        cls.tw14 = message('tw3', 'psql', english, {'': '不能開啟檔案 "%s": %m'})
        cls.tw14['pg_major'] = 14
        load(write_bundle([cls.cn]))
        cls.import_tw([cls.tw, cls.tw_other, cls.tw14])

    @staticmethod
    def import_tw(rows, check=False):
        path = Path(write_bundle(rows, gz=False))
        lines = path.read_text().splitlines()
        header = json.loads(lines[0]); header['language'] = 'zh_TW'
        path.write_text('\n'.join([json.dumps(header), *lines[1:]]) + '\n')
        return load(path, check=check)

    def post(self, path, data):
        self.client.force_login(self.reviewer)
        return self.client.post(path, json.dumps(data), content_type='application/json')

    def test_old_bundles_and_urls_remain_simplified(self):
        self.assertEqual(Message.objects.get(pk='cn1').language, 'zh_CN')
        data = self.client.get('/nls/api/bootstrap/').json()
        self.assertEqual((data['language'], data['total'], data['majors']), ('zh_CN', 1, [19]))
        self.assertEqual([row['id'] for row in self.client.get('/nls/api/component/?name=*').json()['records']], ['cn1'])
        self.assertContains(self.client.get('/nls/?lang=zh_TW&v=14'), 'id="nls-language"')

    def test_lists_counts_and_versions_are_scoped(self):
        data = self.client.get('/nls/api/bootstrap/?lang=zh_TW').json()
        self.assertEqual((data['total'], data['majors']), (2, [19, 14]))
        self.assertEqual({row['code'] for row in data['languages']}, {'zh_CN', 'zh_TW'})
        table = self.client.get('/nls/api/component/?name=*&lang=zh_TW&major=14').json()
        self.assertEqual([row['id'] for row in table['records']], ['tw3'])
        self.assertEqual(table['records'][0]['language'], 'zh_TW')
        self.assertEqual(self.client.get('/nls/api/bootstrap/?major=14').status_code, 409)
        login = self.client.get('/nls/api/bootstrap/?lang=zh_TW&major=14').json()['user']['login_url']
        self.assertEqual(parse_qs(urlparse(login).query)['next'], ['/nls/?lang=zh_TW&v=14'])

    def test_empty_language_has_a_valid_empty_state(self):
        Message.objects.filter(language='zh_TW').delete()
        data = self.client.get('/nls/api/bootstrap/?lang=zh_TW').json()
        self.assertEqual((data['total'], data['components']), (0, []))
        self.assertEqual(data['counts'], dict.fromkeys(service.STATUS_KEYS, 0))

    def test_unknown_language_is_rejected_at_every_boundary(self):
        for path in ('bootstrap/', 'component/?name=*&', 'references/?id=cn1&', 'export/'):
            self.client.force_login(self.reviewer)
            url = '/nls/api/' + path + ('?' if '?' not in path else '') + 'lang=xx'
            self.assertEqual(self.client.get(url).status_code, 409, url)
        for language in ('xx', [], {'code': 'zh_TW'}):
            response = self.post('/nls/api/decide/', {'id': 'cn1', 'language': language, 'expected_version': 0})
            self.assertEqual(response.status_code, 409)
        self.assertEqual(Message.objects.get(pk='cn1').version, 0)

    def test_same_language_references_only(self):
        data = self.client.get('/nls/api/references/?id=tw1&lang=zh_TW&major=19').json()
        self.assertEqual({row['id'] for row in data['references']}, {'tw2'})
        self.assertEqual(self.client.get('/nls/api/references/?id=tw1').status_code, 409)
        self.assertEqual(self.client.get('/nls/api/references/?id=tw1&lang=zh_TW&major=14').status_code, 409)

    def test_single_save_requires_matching_language_and_explicit_version(self):
        for payload in ({}, {'language': 'zh_CN'}, {'language': 'zh_TW', 'major': 14}):
            response = self.post('/nls/api/decide/', {'id': 'tw1', 'expected_version': 0, **payload})
            self.assertEqual(response.status_code, 409)
        saved = self.post('/nls/api/decide/', {'id': 'tw1', 'language': 'zh_TW', 'major': 19,
                                             'expected_version': 0, 'status': 'approved'})
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual((saved.json()['language'], saved.json()['version']), ('zh_TW', 1))
        self.assertEqual(Message.objects.get(pk='cn1').version, 0)

    def test_bulk_all_and_component_reject_mixed_scopes_atomically(self):
        for component in ('*', 'psql'):
            for foreign in ('cn1', 'tw3'):
                response = self.post('/nls/api/save/', {'component': component, 'language': 'zh_TW', 'major': 19,
                    'decisions': [{'id': 'tw1', 'expected_version': 0, 'note': 'must roll back'},
                                  {'id': foreign, 'expected_version': 0}]})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(Message.objects.get(pk='tw1').version, 0)
        saved = self.post('/nls/api/save/', {'component': 'psql', 'language': 'zh_TW', 'major': 19,
                                           'submit': True, 'decisions': [{'id': 'tw1', 'expected_version': 0}]})
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual(Message.objects.get(pk='tw1').status, 'approved')
        self.assertEqual(Message.objects.get(pk='tw3').version, 0)

    def test_import_cannot_rebind_ids_or_override_review_history(self):
        with self.assertRaises(BundleError):
            self.import_tw([self.tw, self.cn])
        self.assertEqual(Message.objects.get(pk='cn1').language, 'zh_CN')
        with self.assertRaises(BundleError):
            self.import_tw([self.tw, self.tw])
        alias = deepcopy(self.cn); alias['id'] = 'new_hash_for_legacy_cn'
        with self.assertRaisesRegex(BundleError, 'preserve its existing ID'):
            load(write_bundle([alias]))
        wrong = deepcopy(self.tw); wrong['language'] = 'zh_CN'
        with self.assertRaises(BundleError):
            self.import_tw([wrong])
        service.decide({'id': 'tw1', 'language': 'zh_TW', 'expected_version': 0, 'status': 'approved'}, self.reviewer)
        before = Message.objects.get(pk='tw1')
        new = deepcopy(self.tw); new['suggested_forms'] = {'': '無法開啟檔案 "%s": %m'}; new['revision'] = 'new'
        self.import_tw([new])
        after = Message.objects.get(pk='tw1')
        self.assertEqual((after.forms, after.version, after.history), (before.forms, before.version, before.history))
        self.assertTrue(after.stale)
        self.assertEqual(Message.objects.get(pk='cn1').forms, self.cn['suggested_forms'])

    def test_check_import_does_not_create_messages(self):
        new = deepcopy(self.tw); new['id'] = 'new_tw'; new['msgctxt'] = 'different context'
        self.assertEqual(self.import_tw([new], check=True)['new'], 1)
        self.assertFalse(Message.objects.filter(pk='new_tw').exists())

    def test_export_and_command_include_language_and_version(self):
        for mid, language in [('cn1', 'zh_CN'), ('tw1', 'zh_TW'), ('tw3', 'zh_TW')]:
            service.decide({'id': mid, 'language': language, 'expected_version': 0, 'status': 'approved'}, self.reviewer)
        self.client.force_login(self.reviewer)
        response = self.client.get('/nls/api/export/?lang=zh_TW&major=14')
        data = response.json()
        self.assertEqual((data['language'], data['pg_major'], set(data['saved_state'])), ('zh_TW', 14, {'tw3'}))
        self.assertIn('pg14-zh_TW-human-review.json', response['Content-Disposition'])
        self.assertEqual(set(self.client.get('/nls/api/export/').json()['saved_state']), {'cn1'})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'review.json'
            call_command('nls_export', str(path), language='zh_TW', major=14)
            self.assertEqual(set(json.loads(path.read_text())['saved_state']), {'tw3'})

    def test_po_validator_uses_message_language(self):
        row = Message.objects.get(pk='tw1')
        self.assertIn('Language: zh_TW', candidate_po(row, row.forms))
        self.assertNotIn('Language: zh_CN', candidate_po(row, row.forms))

    def test_database_rejects_unsupported_language(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Message.objects.filter(pk='cn1').update(language='xx')
