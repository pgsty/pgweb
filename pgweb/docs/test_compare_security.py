"""Security snapshot parsing checks; no network or database needed."""

import importlib.util
from pathlib import Path
import unittest


_path = Path(__file__).resolve().parents[2] / 'tools/docs/fetch_compare_security.py'
_spec = importlib.util.spec_from_file_location('fetch_compare_security', _path)
security = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(security)


class SecuritySnapshotTests(unittest.TestCase):
    def test_explicit_introduction_and_pre_10_major(self):
        self.assertEqual(security.affected_bounds('17.3 – 17.4', '17.5'), ('17', '17.3'))
        self.assertEqual(security.affected_bounds('9.6.12 - 9.6.13', '9.6.14'), ('9.6', '9.6.12'))
        self.assertEqual(security.affected_bounds('9.6', '9.6.14'), ('9.6', None))
        self.assertEqual(security.affected_bounds('18', '18.6'), ('18', None))

    def test_bad_or_cross_branch_range_fails_instead_of_guessing(self):
        for affected, fixed in [('17.5', '17.5'), ('16.3 - 17.4', '17.5'), ('unknown', '18.6')]:
            with self.subTest(affected=affected), self.assertRaises(ValueError):
                security.affected_bounds(affected, fixed)

    def test_detail_preserves_ranges_and_base_score(self):
        record = security.parse_detail('''
          <div id="pgContentWrap">
            <h1>CVE-2026-12345 <i class="lock"></i></h1>
            <h3>Fix <code>example()</code> vulnerability</h3>
            <p>Affected only after the earlier regression.</p>
            <h2>Version Information</h2>
            <table><thead><tr><th>Affected Version</th><th>Fixed In</th><th>Fix Published</th></tr></thead>
            <tbody>
            <tr><td>17.3 – 17.4</td><td><a href="/docs/release/17.5">17.5</a></td><td>2026-01-20</td></tr>
            <tr><td>16</td><td>16.9</td><td>2026-01-20</td></tr>
            </tbody></table>
            <h2>CVSS 3.1</h2>
            <table><tbody>
            <tr><th>Overall Score</th><td><strong>8.8</strong></td></tr>
            <tr><th>Component</th><td>client</td></tr>
            <tr><th>Vector</th><td>AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H</td></tr>
            </tbody></table>
            <h2>Reporting Security Vulnerabilities</h2><p>Unrelated footer.</p>
          </div>''', security.SOURCE_URL + 'CVE-2026-12345/')
        self.assertEqual(record['id'], 'CVE-2026-12345')
        self.assertEqual(record['fixed'], {'17': '17.5', '16': '16.9'})
        self.assertEqual(record['introduced'], {'17': '17.3'})
        self.assertEqual(record['affected']['17'], '17.3 – 17.4')
        self.assertEqual(record['first_published'], '2026-01-20')
        self.assertEqual(record['description_en'], 'Affected only after the earlier regression.')
        self.assertEqual(record['score'], 8.8)
        self.assertEqual(record['cvss_version'], '3.1')
        self.assertEqual(record['component'], 'client')

    def test_registry_discovers_archives_without_non_advisory_tables(self):
        advisories, archives = security.parse_index('''
          <table><thead><tr><th>Reference</th><th>Affected</th><th>Fixed</th>
          <th>Component &amp; CVSS v3 Base Score</th><th>Description</th></tr></thead><tbody>
          <tr><td><a href="/support/security/CVE-2026-12345/">CVE-2026-12345</a></td>
          <td>17</td><td>17.5</td><td>8.8</td><td>Description</td></tr></tbody></table>
          <table><thead><tr><th>Component</th><th>Description</th></tr></thead></table>
          <a href="/support/security/18/">18</a>
          <a href="/support/security/9.6/">9.6</a>
          <a href="https://example.com/support/security/12/">unrelated</a>''')
        self.assertEqual(advisories, {'CVE-2026-12345': security.SOURCE_URL + 'CVE-2026-12345/'})
        self.assertEqual(set(archives), {'18', '9.6'})

    def test_missing_registry_fails(self):
        with self.assertRaises(ValueError):
            security.parse_index('<h1>Maintenance</h1>')

    def test_cna_ranges_retain_unsupported_branches_and_exclusive_end(self):
        record = {'id': 'CVE-2025-8715', 'introduced': {}}
        payload = {
            'cveMetadata': {'cveId': record['id']},
            'containers': {'cna': {
                'providerMetadata': {'shortName': 'PostgreSQL'},
                'affected': [{'product': 'PostgreSQL', 'defaultStatus': 'unaffected', 'versions': [
                    {'status': 'affected', 'version': '17.3', 'lessThan': '17.6'},
                    {'status': 'affected', 'version': '11.20', 'lessThan': '13.22'},
                    {'status': 'affected', 'version': '9.6.8', 'lessThan': '9.6.10'},
                ]}],
            }},
        }
        security.add_cna_ranges(record, payload)
        self.assertEqual(record['affected_ranges'], [
            {'from': '9.6.8', 'until': '9.6.10'},
            {'from': '11.20', 'until': '13.22'},
            {'from': '17.3', 'until': '17.6'},
        ])
        self.assertEqual(record['introduced'], {'17': '17.3', '9.6': '9.6.8'})
        self.assertEqual(record['cna_url'], security.CNA_URL + record['id'])

    def test_incomplete_cna_ranges_do_not_create_partial_vulnerability_matrix(self):
        record = {'id': 'CVE-2025-8715', 'introduced': {}}
        payload = {
            'cveMetadata': {'cveId': record['id']},
            'containers': {'cna': {
                'providerMetadata': {'shortName': 'PostgreSQL'},
                'affected': [{'product': 'PostgreSQL', 'defaultStatus': 'unaffected', 'versions': [
                    {'status': 'affected', 'version': '17', 'lessThan': '17.6'},
                    {'status': 'affected', 'version': '16.x'},
                ]}],
            }},
        }
        security.add_cna_ranges(record, payload)
        self.assertNotIn('affected_ranges', record)
