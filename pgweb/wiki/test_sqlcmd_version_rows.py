"""Release status and loaded manual builds remain independent in wiki readers."""

from copy import deepcopy
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from pgweb.core.models import Version
from pgweb.util.versions import ParsedVersion
from pgweb.wiki import lock, sqlcmd, topics
from pgweb.wiki.sqlcmd_common import version_rows


class WikiManualBuildTests(SimpleTestCase):
    def setUp(self):
        self.final = Version(tree=19, testing=0, latestminor=0,
                             current=True, supported=True)
        self.older = Version(tree=18, testing=0, latestminor=7,
                             current=False, supported=True)
        self.enterContext(patch('pgweb.wiki.sqlcmd_common.Version.objects.all',
                                return_value=[self.older, self.final]))
        self.build = self.enterContext(patch(
            'pgweb.wiki.sqlcmd_common.manual_prerelease',
            side_effect=lambda version: ParsedVersion('19rc2') if version.tree == 19 else None))

    def test_final_release_retains_rc_manual_label_and_supported_state(self):
        rows = version_rows(['18', '19'])
        self.assertEqual([row['major'] for row in rows if row['status'] == 'stable'], ['19'])
        self.assertEqual(rows[0]['label'], '18')
        self.assertEqual(rows[1]['label'], '19（当前手册：19 RC 2）')
        self.assertEqual(rows[1]['support_status'], 'supported')

        version = dict(rows[1], preview=False, devel=False)
        notice = sqlcmd.notice_of(version)
        self.assertEqual(notice, '')
        html = render_to_string('wiki/sqlcmd_preview.html', {
            'version': version, 'notice': notice,
            'manual_url': '/docs/19/sql-select.html',
            'snapshot': {'name': 'SELECT'}, 'command': {'group_label': '查询'},
        })
        self.assertIn('当前手册：19 RC 2', html)
        self.assertNotIn('尚未正式发布', html)

    def test_formal_manual_removes_only_the_build_annotation(self):
        self.build.side_effect = None
        self.build.return_value = None
        row = version_rows(['19'])[0]
        self.assertEqual(row['label'], '19')
        self.assertEqual(row['status'], 'stable')
        self.assertEqual(row['support_status'], 'supported')

    def test_preview_and_development_release_states_stay_unchanged(self):
        self.final.testing = 1
        self.final.latestminor = 2
        self.final.supported = False
        self.final.current = False
        self.older.current = True
        rows = version_rows(['18', '19', '20'])
        self.assertEqual([row['status'] for row in rows], ['stable', 'preview', 'devel'])
        self.assertEqual([row['label'] for row in rows], ['18', '19 rc 2', '20 devel'])

    def test_topic_source_build_is_not_relabelled(self):
        source = {'label': '19beta4', 'ref': 'REL_19_BETA4',
                  'revision': 'original-source', 'channel': 'preview'}
        rows = [{'versions': {'19': {'release': source}}}]
        before = deepcopy(rows)
        versions = topics.releases(rows, '/wiki/role/')
        self.assertEqual(rows, before)
        self.assertEqual(versions[0]['source'], source)
        self.assertEqual(versions[0]['status'], 'stable')
        html = render_to_string('wiki/topic_versions.html', {
            'versions': versions, 'version': versions[0],
        })
        self.assertIn('当前手册：19 RC 2', html)
        self.assertIn('本页依据预发行或开发快照', html)
        self.assertNotIn('尚未正式发布', html)

    def test_lock_source_build_stays_separate_from_release_and_manual(self):
        rows = [{'versions': {'19': {'provenance': {
            'ref': 'REL_19_BETA4', 'revision': 'original-source',
        }}}}]
        before = deepcopy(rows)
        version = lock.versions(rows)[0]
        self.assertEqual(rows, before)
        self.assertEqual(version['status_label'], '当前稳定版')
        self.assertEqual(version['support_status'], 'supported')
        html = render_to_string('wiki/lock_sources.html', {
            'version': version, 'snapshot_label': '采样构建 REL_19_BETA4 · original-source',
            'manual_base': '/docs/19/',
        })
        self.assertIn('当前手册：19 RC 2', html)
        self.assertIn('采样构建 REL_19_BETA4', html)
        self.assertNotIn('尚未正式发布', html)
