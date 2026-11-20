from copy import deepcopy

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
