import gzip
import json
from pathlib import Path
import tempfile

from django.core.management import call_command
from django.contrib.auth.models import User
from django.test import TestCase

from . import po_sync, service
from .importer import IDENTITY_FIELDS, load
from .models import Message
from .tests import message, write_bundle
from .validate import check_forms


class PoSyncTests(TestCase):
    def setUp(self):
        row = message('legacy1', 'psql', '%d row', {'0': '%d 行', '1': '%d 行'},
                      plural='%d rows', human={'status': 'approved', 'version': 3,
                      'forms': {'0': '%d 行', '1': '%d 行'}, 'note': 'Reviewed',
                      'source_revision': 'rev-legacy1'})
        row['plural_forms'] = 'nplurals=2; plural=(n != 1);'
        load(write_bundle([row]))
        self.before = Message.objects.get(pk='legacy1')

    def snapshot(self, text='%d 行'):
        m = self.before
        row = {'id': m.id, **{key: getattr(m, key) for key in IDENTITY_FIELDS},
               'expected': po_sync.digest({key: getattr(m, key) for key in po_sync.CONTENT}),
               'desired': {'forms': {'0': text}, 'plural_forms': 'nplurals=1; plural=0;', 'flags': m.flags},
               'source': {'path': 'zh_CN/master/psql.po', 'sha256': 'a' * 64}}
        return {'schema': po_sync.SCHEMA, 'messages': [row], 'sha256': po_sync.digest([row])}

    def test_normalization_preserves_approval_history_and_is_idempotent(self):
        snapshot = self.snapshot()
        self.assertEqual(po_sync.apply(snapshot)['changed'], 1)
        self.assertEqual(Message.objects.get(pk='legacy1').forms, self.before.forms)
        result = po_sync.apply(snapshot, write=True)
        after = Message.objects.get(pk='legacy1')
        self.assertEqual(result['counts']['forms'], 1)
        self.assertEqual((after.status, after.note, after.updated_by_id, after.updated_at),
                         (self.before.status, self.before.note, self.before.updated_by_id, self.before.updated_at))
        self.assertEqual(after.history[:-1], self.before.history)
        self.assertEqual(after.history[-1]['before']['forms'], self.before.forms)
        self.assertEqual(after.history[-1]['operation'], 'authoritative_po_sync')
        self.assertEqual(after.version, self.before.version + 1)
        self.assertEqual(after.suggested_forms, self.before.suggested_forms)
        check_forms(after, after.forms)
        table = service.component_table('psql')
        self.assertEqual(table['records'][0]['suggested_forms'], {'0': '%d 行'})
        self.assertEqual(service.bootstrap(None)['forms'], 1)
        self.assertEqual(po_sync.apply(snapshot, write=True)['changed'], 0)
        self.assertEqual(Message.objects.get(pk='legacy1').history, after.history)

    def test_real_translation_changes_are_not_new_human_approvals(self):
        po_sync.apply(self.snapshot('%d 条记录'), write=True)
        after = Message.objects.get(pk='legacy1')
        self.assertEqual(after.status, 'pending')
        self.assertEqual(after.history[-1]['before']['status'], 'approved')
        self.assertFalse(after.history[-1]['approval_preserved'])

    def test_content_precondition_prevents_concurrent_translation_overwrite(self):
        snapshot = self.snapshot()
        Message.objects.filter(pk='legacy1').update(forms={'0': 'new', '1': 'new'})
        with self.assertRaisesRegex(ValueError, 'changed after export'):
            po_sync.apply(snapshot, write=True)
        self.assertEqual(Message.objects.get(pk='legacy1').forms['0'], 'new')

    def test_independent_production_history_is_retained(self):
        snapshot = self.snapshot()
        history = [*self.before.history, {'operation': 'production review'}]
        Message.objects.filter(pk='legacy1').update(version=9, history=history)
        po_sync.apply(snapshot, write=True)
        after = Message.objects.get(pk='legacy1')
        self.assertEqual(after.history[:-1], history)
        self.assertEqual(after.version, 10)

    def test_normalized_message_can_be_saved_and_exported_by_a_real_reviewer(self):
        po_sync.apply(self.snapshot(), write=True)
        reviewer = User.objects.create_user('reviewer')
        current = Message.objects.get(pk='legacy1')
        sync_history = current.history
        result = service.decide({'id': current.id, 'language': 'zh_CN', 'major': 19,
                                 'expected_version': current.version, 'status': 'approved',
                                 'forms': {'0': '%d 行'}}, reviewer)
        self.assertEqual(result['stored_status'], 'approved')
        self.assertEqual(result['reviewer'], 'reviewer')
        current.refresh_from_db()
        self.assertEqual(current.history[:-1], sync_history)
        self.assertEqual(current.history[-1]['reviewer'], 'reviewer')
        self.assertEqual(service.export(19, 'zh_CN')['saved_state'][current.id]['forms'], {'0': '%d 行'})
        self.assertEqual(service.component_table('psql')['records'][0]['suggested_forms'], {'0': '%d 行'})

    def test_later_precondition_failure_rolls_back_the_whole_batch(self):
        snapshot = self.snapshot()
        source = Message.objects.get(pk='legacy1')
        source.id = 'another2'
        source.msgctxt = 'distinct context'
        source.save(force_insert=True)
        row = dict(snapshot['messages'][0], id=source.id, msgctxt=source.msgctxt,
                   expected='0' * 64)
        snapshot['messages'].append(row)
        snapshot['sha256'] = po_sync.digest(snapshot['messages'])
        with self.assertRaisesRegex(ValueError, 'changed after export'):
            po_sync.apply(snapshot, write=True)
        self.assertEqual(Message.objects.get(pk='legacy1').forms, self.before.forms)
        self.assertEqual(Message.objects.get(pk='legacy1').history, self.before.history)

    def test_snapshot_integrity_shape_and_existing_id_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.json'
            value = self.snapshot()
            path.write_text(json.dumps(value))
            self.assertEqual(po_sync.read(path), value)
            value['messages'][0]['desired']['forms']['1'] = '%d 行'
            value['sha256'] = po_sync.digest(value['messages'])
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                po_sync.read(path)
            identities = Path(folder) / 'ids.json.gz'
            call_command('nls_export_ids', str(identities))
            with gzip.open(identities, 'rt') as stream:
                exported = json.load(stream)
            self.assertEqual(exported['messages'][0]['id'], 'legacy1')
