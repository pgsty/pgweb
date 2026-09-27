"""Build identity and development-manual prose must not cross release boundaries."""
import hashlib
import json
import tempfile
from datetime import date
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from pgweb.core.models import Version
from .catalog import notice_of
from .catalog_importer import ArchivedEnglishManual, harvest_english, require_matching_preview


PAGE = '''<div class="sect1"><h2>pg_class</h2><p>Current release catalog.</p>
<div class="table"><p class="title"><code class="structname">pg_class</code></p>
<table><tbody><tr><td class="catalog_table_entry"><p class="column_definition">
<code class="structfield">relkind</code> <code class="type">char</code></p>
<p>r = ordinary table, I = partitioned index</p></td></tr></tbody></table></div></div>'''


def relation(name='pg_class', base=None):
    snapshot = {'doc': {'file': 'catalog-pg-class.html', 'anchor': '', 'slug': 'devel'},
                'description': 'Old release catalog.', 'columns': [
                    {'name': 'relkind', 'description': 'r = ordinary table, g = property graph',
                     'description_zh': 'r = 普通表，I = 分区索引'}]}
    if base:
        snapshot['derived_from'] = base
    return {'name': name, 'versions': {'20': snapshot}}


class CatalogEnglishBuildTests(SimpleTestCase):
    def archive(self, root):
        path = Path(root) / 'sources/postgresql/devel'
        path.mkdir(parents=True)
        raw = PAGE.encode()
        (path / 'catalog-pg-class.html').write_bytes(raw)
        (path / 'build.json').write_text(json.dumps({
            'release': '20devel', 'source_archive_sha256': 'fixed-source',
            'files': {'catalog-pg-class.html': hashlib.sha256(raw).hexdigest()}}))
        return path

    def test_missing_archive_does_not_keep_old_enum_prose(self):
        rows = [relation()]
        with tempfile.TemporaryDirectory() as root:
            report = {'devel': {}}
            harvest_english(ArchivedEnglishManual(root, 'devel'), rows, '20', report)
        snap = rows[0]['versions']['20']
        self.assertEqual(snap['description'], '')
        self.assertEqual(snap['columns'][0]['description'], '')
        self.assertIn('分区索引', snap['columns'][0]['description_zh'])
        self.assertFalse(report['devel']['english']['available'])

    def test_matching_archive_replaces_old_enum_and_resolves_alias_chain(self):
        rows = [relation(), relation('pg_alias', 'pg_class'), relation('pg_alias2', 'pg_alias')]
        with tempfile.TemporaryDirectory() as root:
            self.archive(root)
            report = {'devel': {}}
            harvest_english(ArchivedEnglishManual(root, 'devel'), rows, '20', report)
        for row in rows:
            snap = row['versions']['20']
            self.assertEqual(snap['columns'][0]['description'], 'r = ordinary table, I = partitioned index')
            self.assertEqual(snap['english_build']['release'], '20devel')
        self.assertEqual(rows[0]['versions']['20']['description'], 'Current release catalog.')
        self.assertEqual(report['devel']['english']['columns'], 3)

    def test_changed_archive_fails_instead_of_mixing_builds(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.archive(root)
            (path / 'catalog-pg-class.html').write_text(PAGE + 'changed')
            with self.assertRaisesMessage(ValueError, '英文手册归档指纹不匹配'):
                harvest_english(ArchivedEnglishManual(root, 'devel'), [relation()], '20', {'devel': {}})

    def test_preview_notice_uses_its_actual_build(self):
        self.assertTrue(notice_of({'preview': True, 'label': '19 beta 4'}).startswith('19 beta 4'))


class CatalogPreviewAlignmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Version.objects.bulk_create([Version(tree=19, latestminor=4, testing=2, reldate=date(2026, 9, 1),
                               firstreldate=date(2026, 9, 1), eoldate=date(2031, 9, 1))])

    def test_beta3_facts_cannot_be_overlaid_with_beta4_translation(self):
        with self.assertRaisesMessage(ValueError, '请先刷新同构建事实源'):
            require_matching_preview({'status': 'preview', 'major': '19', 'documentation_version': '19beta3'})

    def test_matching_beta4_is_accepted(self):
        require_matching_preview({'status': 'preview', 'major': '19', 'documentation_version': '19beta4'})
