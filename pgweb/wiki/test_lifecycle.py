from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase

from pgweb.core.models import Version
from pgweb.wiki import catalog, func, guc, waitevent
from pgweb.wiki.lifecycle import release_versions


class WikiReleaseLifecycleTests(SimpleTestCase):
    def setUp(self):
        self.releases = [Version(tree=14, latestminor=25, supported=False),
                         Version(tree=18, latestminor=7, supported=True),
                         Version(tree=19, latestminor=0, supported=True, current=True)]
        self.enterContext(patch('pgweb.wiki.lifecycle.Version.objects.all', return_value=self.releases))
        self.rows = [
            {'major': '14', 'label': '14.25', 'status': 'historical', 'release': '14.24', 'is_default': False},
            {'major': '18', 'label': '18.7', 'status': 'stable', 'release': '18.6', 'is_default': True},
            {'major': '19', 'label': '19rc2', 'status': 'preview', 'release': '19beta4',
             'documentation_version': '19rc1', 'is_default': False},
            {'major': '20', 'label': '20 devel', 'status': 'devel', 'is_default': False},
        ]

    def test_current_navigation_preserves_pinned_evidence_and_devel(self):
        before = deepcopy(self.rows)
        rows = release_versions(self.rows)
        self.assertEqual(self.rows, before)
        self.assertEqual([v['major'] for v in rows if v['is_default']], ['19'])
        self.assertEqual(rows[2]['label'], '19')
        self.assertEqual(rows[2]['status'], 'stable')
        self.assertEqual(rows[2]['release'], '19beta4')
        self.assertEqual(rows[2]['documentation_version'], '19rc1')
        self.assertEqual(rows[2]['sample_label'], '19rc2')
        self.assertEqual(rows[0]['support_status'], 'end-of-life')
        self.assertEqual(rows[1]['status_label'], '受支持版本')
        self.assertEqual(rows[3], before[3])
        for reader in (catalog, guc, waitevent, func):
            notice = reader.notice_of(rows[2])
            self.assertIn('19beta4', notice)
            self.assertIn('尚未完成 19.0 校准', notice)
            self.assertNotIn('正式发布前', notice)

    def test_minor_release_lag_is_visible(self):
        self.assertIn('14.24', release_versions(self.rows)[0]['source_notice'])
        self.assertIn('18.6', release_versions(self.rows)[1]['source_notice'])

    def test_verified_final_source_needs_no_lag_notice(self):
        self.rows[2]['release'] = '19.0'
        self.assertNotIn('source_notice', release_versions(self.rows)[2])

    def test_absent_current_release_keeps_available_default(self):
        rows = release_versions(self.rows[:2])
        self.assertEqual([v['major'] for v in rows if v['is_default']], ['18'])

    def test_unregistered_versions_keep_their_original_metadata(self):
        self.assertEqual(release_versions([self.rows[3]]), [self.rows[3]])
