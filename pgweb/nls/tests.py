import gzip
import json
import os
import tempfile

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.test import TestCase

from .importer import load
from .models import Message
from . import service

SHA = '8b9f6d3f666b6e17a8370b07b7d3ca92cad1078c976c1c7c7f81f787b336a5b9'


def message(mid, component, msgid, suggested, original=None, plural=None, flags=('c-format',), kind='revised', human=None):
    row = {'id': mid, 'number': int(mid[-1]), 'component': component, 'msgid': msgid, 'msgid_plural': plural,
           'msgctxt': None, 'flags': list(flags), 'plural_forms': 'nplurals=1; plural=0;' if plural else '',
           'original_forms': original if original is not None else {'': ''}, 'suggested_forms': suggested,
           'suggestion_source': 'nls-v2', 'calibration': {'kind': kind, 'label': kind, 'previous_changed': False,
                                                         'previous_forms': suggested},
           'old_assessment': 'change' if original else 'empty', 'assessment_reason': '依据英文统一术语。',
           'context': {'context': 'ctx', 'parameters': '', 'locations': 'file.c:1'}, 'plural_issue': None,
           'revision': 'rev-' + mid, 'workbook_sha256': SHA,
           'human': human or {'status': 'pending', 'forms': suggested, 'note': '', 'version': 0, 'updated_at': None,
                              'reviewer': '', 'source_revision': 'rev-' + mid}}
    return row


ROWS = [
    message('m_a1', 'pltcl', 'could not open file "%s": %m', {'': '无法打开文件 "%s"：%m'}, {'': '无法打开文件 "%s": %m'}),
    message('m_a2', 'pltcl', 'out of memory\n', {'': '内存不足\n'}, {'': '内存溢出\n'}),
    message('m_a3', 'pltcl', 'unrecognized option', {'': '无法识别的选项'}, {'': '无法识别的选项'}, kind='retained',
            human={'status': 'approved', 'forms': {'': '无法识别的选项'}, 'note': '沿用', 'version': 2,
                   'updated_at': '2026-09-10T04:16:34+00:00', 'reviewer': 'alice', 'source_revision': 'rev-m_a3'}),
    message('m_b1', 'psql', '%d row', {'0': '%d 行'}, {'0': '%d 行'}, plural='%d rows', kind='retained'),
    message('m_b2', 'psql', 'could not open file "%s" for reading: %m', {'': '无法打开文件 "%s" 进行读取：%m'}, {'': '为了读取,无法打开文件 "%s": %m'}),
]


def write_bundle(rows, gz=True):
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, 'bundle.jsonl' + ('.gz' if gz else ''))
    opener = gzip.open if gz else open
    with opener(path, 'wt', encoding='utf-8') as stream:
        stream.write(json.dumps({'kind': 'header', 'schema': 'pgnls-message-bundle-v1', 'workbook_sha256': SHA,
                                 'total': len(rows)}) + '\n')
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    return path


class NlsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user('alice', 'alice@example.org', 'pw')
        cls.bob = User.objects.create_user('bob', 'bob@example.org', 'pw')
        cls.reviewer_perm = Permission.objects.get(content_type__app_label='nls', codename='review')
        cls.alice.user_permissions.add(cls.reviewer_perm)
        cls.report = load(write_bundle(ROWS))

    def post(self, path, payload):
        return self.client.post(path, data=json.dumps(payload), content_type='application/json')

    def decision(self, mid, status='pending', **overrides):
        m = Message.objects.get(pk=mid)
        return {'id': mid, 'expected_version': m.version, 'status': status, 'forms': dict(m.forms), 'note': m.note, **overrides}

    # ---- import ----
    def test_import_loads_everything_and_keeps_reviewer_state_on_reimport(self):
        self.assertEqual(self.report, {'new': 5, 'updated': 0, 'kept': 0, 'total': 5})
        m = Message.objects.get(pk='m_a3')
        self.assertEqual((m.status, m.version, m.note, m.updated_by.username), ('approved', 2, '沿用', 'alice'))
        self.assertEqual(m.history[0]['reviewer'], 'alice')
        # A newer calibration changes recommendations; local review work is never overwritten.
        rows = json.loads(json.dumps(ROWS))
        rows[0]['suggested_forms'] = {'': '打不开文件 "%s"：%m'}
        rows[2]['suggested_forms'] = rows[2]['human']['forms'] = {'': '另一种译法'}
        report = load(write_bundle(rows, gz=False))
        self.assertEqual(report, {'new': 0, 'updated': 4, 'kept': 1, 'total': 5})
        self.assertEqual(Message.objects.get(pk='m_a1').forms, {'': '打不开文件 "%s"：%m'})
        kept = Message.objects.get(pk='m_a3')
        self.assertEqual(kept.forms, {'': '无法识别的选项'})
        self.assertEqual(kept.suggested_forms, {'': '另一种译法'})
        self.assertEqual(load(write_bundle(rows), check=True)['total'], 5)

    def test_import_rejects_other_files(self):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, 'x.jsonl')
        with open(path, 'w') as stream:
            stream.write(json.dumps({'schema': 'pgnls-human-review-v1'}) + '\n')
        with self.assertRaises(ValueError):
            load(path)

    # ---- reading is public, writing needs the permission ----
    def test_anonymous_reads_but_cannot_write(self):
        page = self.client.get('/nls/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'data-can-edit="0"')
        self.assertContains(page, 'href="/nls/"')
        self.assertContains(page, '消息翻译')
        boot = self.client.get('/nls/api/bootstrap/').json()
        self.assertEqual(boot['total'], 5)
        self.assertEqual([c['name'] for c in boot['components']], ['pltcl', 'psql'])  # alphabetical, not by size
        self.assertEqual(boot['user'], {'authenticated': False, 'name': '', 'can_edit': False, 'login_url': '/account/login/?next=/nls/'})
        table = self.client.get('/nls/api/component/?name=pltcl').json()
        self.assertEqual([r['id'] for r in table['records']], ['m_a1', 'm_a2', 'm_a3'])
        self.assertEqual(table['records'][2]['reviewer'], 'alice')
        self.assertNotIn('previous_forms', table['records'][0]['calibration'])
        response = self.post('/nls/api/decide/', self.decision('m_a1', 'flagged'))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['login_url'], '/account/login/?next=/nls/')
        self.assertEqual(self.client.get('/nls/api/export/').status_code, 401)
        self.assertEqual(Message.objects.get(pk='m_a1').version, 0)

    def test_signed_in_user_without_permission_is_read_only(self):
        self.client.force_login(self.bob)
        self.assertContains(self.client.get('/nls/'), 'data-can-edit="0"')
        self.assertEqual(self.client.get('/nls/api/bootstrap/').json()['user']['can_edit'], False)
        self.assertEqual(self.post('/nls/api/decide/', self.decision('m_a1', 'flagged')).status_code, 403)
        self.assertEqual(Message.objects.get(pk='m_a1').version, 0)

    def test_reviewer_saves_and_is_recorded(self):
        self.client.force_login(self.alice)
        self.assertContains(self.client.get('/nls/'), 'data-can-edit="1"')
        response = self.post('/nls/api/decide/', self.decision('m_a2', forms={'': '内存不足了\n'}, note='试改'))
        self.assertEqual(response.status_code, 200, response.content)
        saved = response.json()
        self.assertEqual((saved['status'], saved['version'], saved['reviewer'], saved['forms']), ('pending', 1, 'alice', {'': '内存不足了\n'}))
        m = Message.objects.get(pk='m_a2')
        self.assertEqual((m.updated_by, m.note, m.source_revision), (self.alice, '试改', m.revision))
        self.assertEqual(m.history[-1]['version'], 1)

    def test_optimistic_lock_rejects_stale_versions(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.post('/nls/api/decide/', self.decision('m_a1', 'flagged')).status_code, 200)
        conflict = self.post('/nls/api/decide/', {**self.decision('m_a1', 'rejected'), 'expected_version': 0})
        self.assertEqual(conflict.status_code, 409)
        self.assertIn('被他人修改', conflict.json()['error'])
        self.assertEqual(Message.objects.get(pk='m_a1').status, 'flagged')

    def test_approval_runs_msgfmt_and_layout_checks(self):
        self.client.force_login(self.alice)
        bad = self.post('/nls/api/decide/', self.decision('m_a1', 'approved', forms={'': '无法打开文件'}))
        self.assertEqual(bad.status_code, 409)
        self.assertRegex(bad.json()['error'], 'msgfmt|占位符')
        layout = self.post('/nls/api/decide/', self.decision('m_a2', 'approved', forms={'': '内存不足'}))
        self.assertEqual(layout.status_code, 409)
        self.assertIn('换行', layout.json()['error'])
        self.assertEqual(Message.objects.filter(version__gt=0).count(), 1)  # only the imported alice row
        good = self.post('/nls/api/decide/', self.decision('m_a1', 'approved'))
        self.assertEqual(good.status_code, 200, good.content)
        self.assertEqual(Message.objects.get(pk='m_a1').status, 'approved')
        plural = self.post('/nls/api/decide/', self.decision('m_b1', 'approved'))
        self.assertEqual(plural.status_code, 200, plural.content)

    def test_component_submit_is_complete_and_atomic(self):
        self.client.force_login(self.alice)
        incomplete = self.post('/nls/api/save/', {'component': 'pltcl', 'submit': True,
                                                  'decisions': [{'id': 'm_a1', 'expected_version': 0}]})
        self.assertEqual(incomplete.status_code, 409)
        m2 = Message.objects.get(pk='m_a2')
        broken = self.post('/nls/api/save/', {'component': 'pltcl', 'submit': True, 'decisions': [
            {'id': 'm_a1', 'expected_version': 0}, {'id': 'm_a2', 'expected_version': 0, 'forms': {'': '没有换行'}},
            {'id': 'm_a3', 'expected_version': 2}]})
        self.assertEqual(broken.status_code, 409)
        self.assertIn('未保存任何记录', broken.json()['error'])
        self.assertEqual(Message.objects.get(pk='m_a1').version, 0)
        ok = self.post('/nls/api/save/', {'component': 'pltcl', 'submit': True, 'decisions': [
            {'id': 'm_a1', 'expected_version': 0}, {'id': 'm_a2', 'expected_version': 0}, {'id': 'm_a3', 'expected_version': 2}]})
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(sorted(r['status'] for r in ok.json()['results']), ['approved'] * 3)
        self.assertEqual(Message.objects.get(pk='m_a2').forms, m2.forms)  # unchanged rows keep their text
        other = self.post('/nls/api/save/', {'component': 'pltcl', 'decisions': [{'id': 'm_b1', 'expected_version': 0}]})
        self.assertEqual(other.status_code, 409)

    def test_undo_is_a_save_of_the_previous_state(self):
        self.client.force_login(self.alice)
        before = self.decision('m_a1')
        first = self.post('/nls/api/decide/', self.decision('m_a1', 'flagged', note='疑问')).json()
        undo = self.post('/nls/api/decide/', {**before, 'expected_version': first['version']})
        self.assertEqual(undo.status_code, 200)
        m = Message.objects.get(pk='m_a1')
        self.assertEqual((m.status, m.note, m.version), ('pending', '', 2))
        self.assertEqual([e['status'] for e in m.history], ['flagged', 'pending'])

    # ---- lookups ----
    def test_references_rank_identical_english_first(self):
        data = self.client.get('/nls/api/references/?id=m_a1').json()
        self.assertEqual(data['engine'], 'PostgreSQL pg_trgm')
        self.assertTrue(data['references'])
        self.assertEqual(data['references'][0]['id'], 'm_b2')
        self.assertEqual(''.join(d['text'] for d in data['references'][0]['diff']), data['references'][0]['english'])
        self.assertEqual(data['context']['locations'], 'file.c:1')
        self.assertEqual(self.client.get('/nls/api/references/?id=nope').status_code, 409)
        self.assertEqual(self.client.get('/nls/api/component/?name=nope').status_code, 409)

    # ---- round trip ----
    def test_export_matches_the_pgnls_review_format(self):
        self.client.force_login(self.alice)
        payload = self.client.get('/nls/api/export/').json()
        self.assertEqual(payload['schema'], 'pgnls-human-review-v1')
        self.assertEqual(payload['workbook_sha256'], SHA)
        self.assertEqual(list(payload['saved_state']), ['m_a3'])
        self.assertEqual(payload['saved_state']['m_a3']['reviewer'], 'alice')
        self.assertEqual(payload, json.loads(json.dumps(service.export())))

    def test_grant_command_toggles_the_permission(self):
        call_command('nls_grant', 'bob')
        self.assertTrue(User.objects.get(pk=self.bob.pk).has_perm('nls.review'))
        call_command('nls_grant', 'bob', '--revoke')
        self.assertFalse(User.objects.get(pk=self.bob.pk).has_perm('nls.review'))

    def test_components_are_listed_by_name(self):
        load(write_bundle([message('m_z9', 'zzz', 'a', {'': '甲'}), message('m_a9', 'aaa', 'b', {'': '乙'})], gz=False))
        self.assertEqual([c['name'] for c in service.component_stats()], ['aaa', 'pltcl', 'psql', 'zzz'])

    def test_crawlers_are_kept_out(self):
        page = self.client.get('/nls/')
        self.assertEqual(page['X-Robots-Tag'], 'noindex, nofollow')
        self.assertContains(page, '<meta name="robots" content="noindex,nofollow">')
        self.assertEqual(self.client.get('/nls/api/bootstrap/')['X-Robots-Tag'], 'noindex, nofollow')
        self.assertEqual(self.client.get('/nls/api/component/?name=pltcl')['X-Robots-Tag'], 'noindex, nofollow')
        robots = self.client.get('/robots.txt').content.decode()
        self.assertIn('Disallow: /nls/', robots)

    def test_developer_menu_ends_with_the_tool(self):
        from pgweb.util.contexts import sitenav, LOCAL_ONLY_SECTIONS
        self.assertEqual(sitenav['developer'][-1], {'title': '消息翻译', 'link': '/nls/'})
        self.assertIn('/nls/', LOCAL_ONLY_SECTIONS)
        self.assertContains(self.client.get('/nls/'), 'nls-row-', count=0)  # rows are rendered client-side

    # ---- all components ----
    def test_all_components_table_and_cross_component_save(self):
        table = self.client.get('/nls/api/component/?name=*').json()
        self.assertEqual((table['component'], table['total']), ('*', 5))
        self.assertEqual([r['component'] for r in table['records']], ['pltcl', 'pltcl', 'pltcl', 'psql', 'psql'])
        self.client.force_login(self.alice)
        saved = self.post('/nls/api/save/', {'component': '*', 'decisions': [self.decision('m_a1', note='跨组件'),
                                                                            self.decision('m_b2', note='跨组件')]})
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual({r['id'] for r in saved.json()['results']}, {'m_a1', 'm_b2'})
        self.assertEqual(Message.objects.get(pk='m_b2').note, '跨组件')
        denied = self.post('/nls/api/save/', {'component': '*', 'submit': True, 'decisions': [self.decision('m_a1')]})
        self.assertEqual(denied.status_code, 409)
        self.assertIn('具体组件', denied.json()['error'])
        unknown = self.post('/nls/api/save/', {'component': '*', 'decisions': [{'id': 'm_zz', 'expected_version': 0}]})
        self.assertEqual(unknown.status_code, 409)
