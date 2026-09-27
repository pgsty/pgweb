"""Regressions for same-version manual coordinates and SQLSTATE labels."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from pgweb.core.models import Version
from pgweb.docs.models import DocPage
from . import errcode, importer
from .manuals import manual_slug
from .models import ErrorCode, ErrorCodeRelease


class ManualIdentityTests(SimpleTestCase):
    def test_decimal_major_identity_keeps_legacy_minor_and_devel(self):
        for tree, expected in [('0.0', 'devel'), ('9.0', '9.0'), ('9.6', '9.6'),
                               ('9.60', '9.6'), ('10.0', '10'), ('1E+1', '10'), ('19.0', '19')]:
            self.assertEqual(manual_slug(Decimal(tree)), expected)


class SQLStateManualTests(TestCase):
    def setUp(self):
        cache.clear()
        Version.objects.bulk_create([
            Version(tree=Decimal(tree), reldate=date(2026, 1, 1),
                    firstreldate=date(2026, 1, 1), eoldate=date(2030, 1, 1))
            for tree in ('0.0', '9.0', '9.6', '18.0')])

    def page(self, tree, filename, content):
        return DocPage.objects.create(version_id=Decimal(tree), file=filename,
                                      title=filename, content=content)

    def test_pinned_link_repair_requires_same_version_target_anchor(self):
        self.page('18', 'fdw-callbacks.html', '<h2 id="FDW-CALLBACKS-SCAN">扫描回调</h2>')
        source = 'https://www.postgresql.org/docs/18/fdwhandler.html#FDW-CALLBACKS-SCAN'
        self.assertEqual(importer.rewrite_links(source, importer.doc_checker()),
                         '/docs/18/fdw-callbacks.html#FDW-CALLBACKS-SCAN')
        self.assertEqual(importer.rewrite_links(source.replace('/18/', '/9.6/'), importer.doc_checker()),
                         source.replace('/18/', '/9.6/'))
        self.assertEqual(importer.rewrite_links(source.replace('SCAN', 'UNKNOWN'), importer.doc_checker()),
                         source.replace('SCAN', 'UNKNOWN'))

    def test_stacked_diagnostics_repair_preserves_pin_and_requires_evidence(self):
        source = 'https://www.postgresql.org/docs/18/plpgsql-control-structures.html#PLPGSQL-GET-DIAGNOSTICS'
        self.assertEqual(importer.rewrite_links(source, importer.doc_checker()), source)
        self.page('18', 'plpgsql-control-structures.html',
                  '<h3 id="PLPGSQL-EXCEPTION-DIAGNOSTICS">获取有关错误的信息</h3>')
        self.assertEqual(importer.rewrite_links(source, importer.doc_checker()),
                         '/docs/18/plpgsql-control-structures.html#PLPGSQL-EXCEPTION-DIAGNOSTICS')

    def test_labels_use_latest_manual_without_erasing_historical_class(self):
        self.page('18', errcode.DOC_FILE,
                  '<table><tr><td colspan="2">类 23 — 旧标题</td></tr>'
                  '<tr><td colspan="2">类 72 — 快照失败</td></tr></table>')
        self.page('0', errcode.DOC_FILE,
                  '<table><tr><td colspan="2"><strong>类 23 — 完整性约束违反</strong></td></tr>'
                  '<tr><td>23505</td><td>unique_violation</td></tr></table>')
        self.assertEqual(importer.manual_class_names(), {'23': '完整性约束违反', '72': '快照失败'})

    def test_legacy_options_and_groups_do_not_claim_devel_source_sampling(self):
        for tree in ('9.0', '9.6', '18', '0'):
            self.page(tree, errcode.DOC_FILE, '<html>附录</html>')
        for major in ('9.0', '9.6', '18'):
            ErrorCodeRelease.objects.create(major=major, release=major + '.1')
        code = ErrorCode(sqlstate='23505', present_in=['9.0', '9.6', '18'], preview_in=[])
        self.assertEqual(errcode.doc_majors(), ['0', '18', '9.0', '9.6'])
        self.assertTrue(all(option['has_doc'] for option in errcode.version_options(code)))
        self.assertEqual(errcode.pick_version(code, '9.6')['value'], '9.6')
        with patch('pgweb.docs.versions.manual_groups', return_value={
                'supported': [18], 'historical': [], 'testing': [], 'devel': 20}):
            groups = errcode.version_groups(code)
        historical = next(g for g in groups if g['kind'] == 'historical')['items']
        self.assertEqual([r['major'] for r in historical], ['9.6', '9.0'])
        self.assertEqual(historical[0]['url'], '/docs/9.6/errcodes-appendix.html')
        self.assertEqual(groups[-1]['items'][0]['state'], 'unknown')
