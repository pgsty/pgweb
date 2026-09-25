"""Exercise the real historical models, including a populated contraction and rollback."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from .migrations._reference_documents import legacy_document


class ReferenceMigrationTests(TransactionTestCase):
    def _fixture_teardown(self):
        # Historical unmanaged account tables retain FKs to managed tables.
        # The isolated test database needs CASCADE when Django flushes it.
        from django.core.management import call_command
        call_command('flush', verbosity=0, interactive=False, database='default',
                     reset_sequences=False, allow_cascade=True)

    def migrate(self, name):
        executor = MigrationExecutor(connection)
        executor.migrate([('wiki', name), ('search', '0005_catalog_entry_identity')])
        return executor.loader.project_state([('wiki', name), ('search', '0005_catalog_entry_identity')]).apps

    def test_populated_forward_and_reverse(self):
        old = self.migrate('0006_func')
        try:
            old.get_model('wiki', 'ErrorCodeClass').objects.create(code='23', name='Integrity')
            code = old.get_model('wiki', 'ErrorCode').objects.create(
                sqlstate='23505', klass_id='23', known_present_by='7.4', case_count=1, snippet_count=1,
                facts={'presence_intervals': [{'start': '18.0', 'proof': {'keep': True}}]})
            old.get_model('wiki', 'ErrorCodePresence').objects.create(
                errcode=code, start='18.0', position=0, evidence_count=19)
            old.get_model('wiki', 'ErrorCodeText').objects.create(
                errcode=code, lang='fr', summary='original', is_stale=True, translation_source_rev='kept')
            old.get_model('wiki', 'ErrorCodeSource').objects.create(errcode=code, source_id='s', sha256='a'*64)
            old.get_model('wiki', 'ErrorCodeClaim').objects.create(
                errcode=code, claim_id='claim', statement='kept', sources=['s', 'run'], runtime=['run'])
            old.get_model('wiki', 'ErrorCodeRuntime').objects.create(
                errcode=code, runtime_id='run', cases=['case'], raw={'nested': [1, 2]})
            old.get_model('wiki', 'ErrorCodeCase').objects.create(
                errcode=code, case_id='case', assertions=['kept'], has_snippet=True)
            message = old.get_model('wiki', 'ErrorCodeMessage').objects.create(
                errcode=code, message_id='message', raw={'primary_variants': ['kept']})
            old.get_model('wiki', 'ErrorCodeTemplate').objects.create(
                errcode=code, message=message, kind='hint', role='variant', template='try %s', literal='try')
            before = legacy_document(old, connection.alias, code)
            current = self.migrate('0010_retire_errcode_children')
            row = current.get_model('wiki', 'ErrorCode').objects.get(pk='23505')
            self.assertEqual(row.texts, before['texts'])
            self.assertEqual(row.evidence, before['evidence'])
            self.assertEqual(row.facts, before['facts'])
            self.assertEqual(row.imported_at, code.imported_at)
            self.assertNotIn('wiki_errcode_text', connection.introspection.table_names())
            # Reverse must restore a post-migration edit, not a stale shadow copy.
            row.texts['fr']['summary'] = 'updated after migration'
            row.save(update_fields=['texts'])
            before['texts']['fr']['summary'] = 'updated after migration'
            reverted = self.migrate('0006_func')
            row = reverted.get_model('wiki', 'ErrorCode').objects.get(pk='23505')
            self.assertEqual(legacy_document(reverted, connection.alias, row), before)
        finally:
            self.migrate('0010_retire_errcode_children')
