from copy import deepcopy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, TestCase

from .models import ExtensionHook
from .snapshot import guard_calibration


class CalibrationGuardTests(TestCase):
    def test_legacy_import_cannot_discard_release_proof(self):
        versions = {'19': {'signature': 'void f(void)', 'calibration': {'release': '19.0', 'commit': 'fixed'}},
                    '20': {'signature': 'void f(void)', 'release': {'label': '20 devel'}}}
        ExtensionHook.objects.create(slug='hook', name='hook', versions=versions)
        item = {'slug': 'hook', 'versions': deepcopy(versions)}
        guard_calibration(ExtensionHook, item)
        item['versions']['19'].pop('calibration')
        with self.assertRaisesMessage(ValueError, 'pinned release calibration'):
            guard_calibration(ExtensionHook, item)
        self.assertEqual(ExtensionHook.objects.get(pk='hook').versions, versions)


class DefaultHistoryTests(SimpleTestCase):
    def test_unsampled_documentation_is_not_an_unset_default(self):
        from tools.wiki.build_release_delta import refine_guc_history
        row = {'name': 'sample', 'versions': {
            '17': {'boot_val': '64', 'unit': None, 'human': '64'},
            '18': {'boot_val': '64', 'unit': '', 'human': '64'},
            '19': {'boot_val': '128', 'unit': None, 'human': '128'},
            '20': {'boot_val': None, 'facts_source': 'documentation'}}}
        original = deepcopy(row['versions']['20'])
        refine_guc_history([row], ['17', '18', '19', '20'])
        self.assertEqual([(h['from'], h['to'], h['boot_val']) for h in row['default_history']],
                         [('17', '18', '64'), ('19', '19', '128')])
        self.assertEqual(row['versions']['20'], original)


class OrderedDeltaTests(SimpleTestCase):
    def test_streaming_refuses_membership_order_and_duplicate_identity_changes(self):
        from tools.docs.apply_reference_delta import iter_pairs
        with TemporaryDirectory() as directory:
            old, new = Path(directory) / 'old.gz', Path(directory) / 'new.gz'
            rows = [{'id': 'a', 'value': 1}, {'id': 'b', 'value': 2}]
            def write(path, values):
                path.write_bytes(gzip.compress(''.join(json.dumps(r) + '\n' for r in values).encode()))
            write(old, rows)
            write(new, [dict(r, value=r['value'] + 1) for r in rows])
            self.assertEqual(list(iter_pairs(old, new, 'id', True)), list(iter_pairs(old, new, 'id')))
            for invalid in (rows[:1], rows + [{'id': 'c'}], list(reversed(rows)), [rows[0], rows[0]]):
                write(new, invalid)
                with self.assertRaises(ValueError):
                    list(iter_pairs(old, new, 'id', True))
