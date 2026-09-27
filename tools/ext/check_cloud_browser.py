#!/usr/bin/env python3
"""Exercise cloud matrices in an already running local PGSQL.CC instance.

Run with a Python environment containing Playwright and Chromium. This tool
reads application pages, downloads CSVs and saves screenshots; it does not
modify application data. Results are written even when a scenario fails.
"""

import argparse
import csv
import io
import json
import re
import traceback
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from playwright.sync_api import sync_playwright


class Review:
    def __init__(self, browser, base_url, output, source_check=None):
        self.browser = browser
        self.base_url = base_url.rstrip("/")
        self.output = output
        self.source_check = source_check
        self.results = []
        self.errors = []
        self.console_errors = []
        self.csp_errors = []
        self.context = browser.new_context(
            viewport={"width": 1440, "height": 1080}, accept_downloads=True
        )
        self.page = self.new_page(self.context)

    def new_page(self, context):
        page = context.new_page()
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.on("console", self.console)
        page.add_init_script("""document.addEventListener('securitypolicyviolation',
            event => console.error('CSP:' + event.violatedDirective + ':' + event.blockedURI));""")
        return page

    def console(self, message):
        if message.type == "error":
            self.console_errors.append(message.text)
            if "CSP:" in message.text or "Content Security Policy" in message.text:
                self.csp_errors.append(message.text)

    def record(self, name, passed, **detail):
        self.results.append({"name": name, "passed": bool(passed), **detail})
        print(("PASS " if passed else "FAIL ") + name, flush=True)

    def require(self, name, condition, **detail):
        self.record(name, condition, **detail)
        if not condition:
            raise AssertionError(name)

    def run(self, name, operation):
        try:
            operation()
        except Exception as error:
            self.record(name + " completed", False, error=str(error), traceback=traceback.format_exc())

    def goto(self, path, page=None):
        page = page or self.page
        response = page.goto(self.base_url + path, wait_until="networkidle")
        self.require("GET " + path, response is not None and response.status == 200,
                     status=response.status if response else None)
        return page

    def screenshot(self, name, page=None):
        (page or self.page).screenshot(path=str(self.output / (name + ".png")), full_page=True)

    def no_overflow(self, page, name):
        widths = page.evaluate("({viewport:innerWidth, document:document.documentElement.scrollWidth})")
        self.require(name + " contains horizontal scrolling within matrix",
                     widths["document"] <= widths["viewport"] + 1, **widths)

    @staticmethod
    def query(page):
        return parse_qs(urlsplit(page.url).query)

    @staticmethod
    def settle(page):
        page.wait_for_function("!document.querySelector('[aria-busy=true]')")

    def baseline(self):
        page = self.goto("/ext/")
        self.require("Existing extension directory title", page.locator("h1").inner_text() == "PostgreSQL 扩展目录")
        self.require("Directory links to cloud comparison", page.locator('a[href="/ext/cloud/"]').count() > 0)
        self.no_overflow(page, "Existing directory")
        self.screenshot("directory-desktop")

    def comparison(self):
        page = self.goto("/ext/cloud/")
        services = page.locator('input[name="service"]')
        self.require("Comparison defaults to PG18", page.locator('#cloud-pg').input_value() == '18')
        self.require("All cloud services selected by default", services.count() >= 33 and
                     services.count() == page.locator('input[name="service"]:checked').count(),
                     service_count=services.count())
        headers = page.locator('.cloud-table thead th')
        self.require("Pigsty is first comparison column", 'Pigsty' in headers.nth(1).inner_text())
        self.require("A column per selected service", headers.count() == services.count() + 2,
                     column_count=headers.count())
        self.require("Matrix pagination bounds the first screen", 0 < page.locator('.cloud-table tbody tr').count() <= 100)
        self.no_overflow(page, "Comparison desktop")
        self.screenshot("compare-desktop")
        scroller = page.locator('#cloud-table-scroll')
        before = page.locator('.cloud-table tbody th').first.bounding_box()['x']
        anchor_before = page.locator('.cloud-table tbody .cloud-anchor').first.bounding_box()['x']
        scroller.evaluate('(element) => {element.scrollLeft = 700;}')
        page.wait_for_timeout(100)
        after = page.locator('.cloud-table tbody th').first.bounding_box()['x']
        anchor_after = page.locator('.cloud-table tbody .cloud-anchor').first.bounding_box()['x']
        self.require("Extension names remain pinned while scrolling", abs(before - after) <= 1)
        self.require("Pigsty remains pinned while scrolling", abs(anchor_before - anchor_after) <= 1)
        self.screenshot("compare-scrolled")

    def service(self):
        page = self.goto('/ext/cloud/aws_rds/')
        headers = page.locator('.cloud-table thead th').all_inner_texts()
        self.require("Service has five PG-major columns", len(headers) == 6 and
                     all('PG ' + str(major) in headers[index + 1] for index, major in enumerate(range(18, 13, -1))),
                     headers=headers)
        self.require("Service can show packaged and all indexed extensions",
                     {'packaged', 'all'}.issubset(set(page.locator('#cloud-scope option').evaluate_all('(nodes) => nodes.map(n => n.value)'))))
        self.no_overflow(page, 'Service desktop')
        self.screenshot('aws-rds-desktop')

    def service_routes(self):
        page = self.goto('/ext/cloud/')
        services = page.locator('input[name="service"]').evaluate_all('(inputs) => inputs.map(i => i.value)')
        routes = []
        for service in services:
            response = self.context.request.get(self.base_url + '/ext/cloud/' + service + '/?scope=packaged')
            body = response.text()
            table_head = re.search(r'<table class="cloud-table">.*?<thead>(.*?)</thead>', body, re.S)
            routes.append({'service': service, 'status': response.status,
                           'five_major_columns': bool(table_head) and all('PG ' + str(major) in table_head[1] for major in range(14, 19)),
                           'filter_form': 'id="cloud-form"' in body})
        self.require('Every selected cloud service has a rendered matrix route',
                     all(item['status'] == 200 and item['five_major_columns'] and item['filter_form'] for item in routes),
                     routes=routes)
        response = self.context.request.get(self.base_url + '/ext/cloud/this_service_does_not_exist/')
        self.require('Unknown service returns 404', response.status == 404)
        page = self.goto('/ext/cloud/vultr/')
        self.require('Missing provider data has a specific evidence state',
                     '尚无可核验' in page.locator('.cloud-empty').inner_text())
        page.get_by_role('link', name='查看 Pigsty 打包范围').click()
        page.wait_for_function("new URL(location.href).searchParams.get('scope') === 'packaged'")
        self.settle(page)
        self.require('Missing-data service can expose five-column evidence gaps',
                     page.locator('.cloud-table thead th').count() == 6 and
                     page.locator('tbody td').count() == page.locator('tbody td.cloud-state-UNKNOWN').count())

    def filtering(self):
        page = self.goto('/ext/cloud/')
        # In-place interaction must preserve the page, not quietly reload it.
        page.evaluate('window.cloudReviewSentinel = 42')
        page.locator('#cloud-query').fill('postgis')
        page.wait_for_function("new URL(location.href).searchParams.get('q') === 'postgis'")
        self.settle(page)
        self.require('Search keeps page and focus', page.evaluate('window.cloudReviewSentinel') == 42 and
                     page.locator('#cloud-query').evaluate('(input) => document.activeElement === input'))
        self.require('Search actually limits results', 0 < page.locator('.cloud-table tbody tr').count() < 50)
        page.locator('#cloud-pg').select_option('17')
        page.wait_for_function("new URL(location.href).searchParams.get('pg') === '17'")
        self.settle(page)
        page.locator('#cloud-pg').select_option('16')
        page.wait_for_function("new URL(location.href).searchParams.get('pg') === '16'")
        self.settle(page)
        page.go_back()
        page.wait_for_function("document.querySelector('#cloud-pg').value === '17'")
        self.settle(page)
        self.require('Back restores filters and keyword', page.locator('#cloud-query').input_value() == 'postgis')
        page.go_forward()
        page.wait_for_function("document.querySelector('#cloud-pg').value === '16'")
        self.settle(page)
        self.require('Forward restores PG version', self.query(page).get('pg') == ['16'])
        page.locator('#cloud-services summary').click()
        page.locator('[data-cloud-select="none"]').click()
        page.wait_for_function("document.querySelectorAll('.cloud-table thead th').length === 2")
        self.settle(page)
        self.require('No cloud selections retains only Pigsty', self.query(page).get('selection') == ['1'] and
                     'service' not in self.query(page) and
                     page.locator('input[name="service"]:checked').count() == 0)
        for service in ('aws_rds', 'google_cloud_sql'):
            page.locator('#cloud-service-' + service).check()
            page.wait_for_function('(service) => new URL(location.href).searchParams.getAll("service").includes(service)', arg=service)
            self.settle(page)
        self.require('Repeated service parameters retain both selected columns',
                     set(self.query(page).get('service', [])) == {'aws_rds', 'google_cloud_sql'} and
                     page.locator('.cloud-table thead th').count() == 4)
        page.reload(wait_until='networkidle')
        self.require('Reload retains selected services', page.locator('input[name="service"]:checked').count() == 2)
        page.locator('#cloud-services summary').click()
        page.locator('#cloud-services a[href="/ext/cloud/google_cloud_sql/"]').click()
        page.wait_for_url('**/ext/cloud/google_cloud_sql/')
        self.require('Chooser details link opens provider page', page.locator('.cloud-table thead th').count() == 6)
        page.go_back()
        page.wait_for_function("document.querySelector('#cloud-pg') !== null")
        self.require('Provider detail navigation preserves previous service selections',
                     page.locator('input[name="service"]:checked').count() == 2)

    def input_and_races(self):
        page = self.goto('/ext/cloud/?selection=1&service=aws_rds')
        requested = []
        page.on('request', lambda request: requested.append(request.url)
                if request.resource_type == 'fetch' and request.url.startswith(self.base_url + '/ext/cloud/') else None)
        query = page.locator('#cloud-query')
        query.dispatch_event('compositionstart')
        query.fill('向量')
        page.wait_for_timeout(500)
        self.require('IME composition does not fetch incomplete input', not requested)
        query.dispatch_event('compositionend')
        page.wait_for_function("new URL(location.href).searchParams.get('q') === '向量'")
        self.settle(page)
        page.wait_for_timeout(400)
        self.require('IME completion applies search once', len(requested) == 1, requests=requested)
        page.evaluate("""(() => {
            const original = window.fetch;
            window.fetch = async (...args) => {
                const response = await original(...args);
                if (new URL(args[0], location.href).searchParams.get('q') === 'pg_cron') {
                    await new Promise(resolve => setTimeout(resolve, 900));
                }
                return response;
            };
        })()""")
        page.locator('#cloud-query').fill('pg_cron')
        page.wait_for_timeout(350)
        page.locator('#cloud-query').fill('postgis')
        page.wait_for_function("new URL(location.href).searchParams.get('q') === 'postgis'")
        page.wait_for_timeout(1100)
        self.settle(page)
        self.require('Older slow responses cannot replace latest search',
                     self.query(page).get('q') == ['postgis'] and page.locator('#cloud-query').input_value() == 'postgis')

    def pagination_and_export(self):
        page = self.goto('/ext/cloud/?scope=packaged&selection=1&service=aws_rds')
        count = int(page.locator('.cloud-results-bar strong').inner_text())
        visible = page.locator('.cloud-table tbody tr').count()
        columns = page.locator('.cloud-table thead th').count() - 1
        page.locator('.cloud-pager a[rel="next"]').click()
        page.wait_for_function("new URL(location.href).searchParams.get('page') === '2'")
        self.settle(page)
        self.require('Pagination preserves filters and service selection', self.query(page).get('scope') == ['packaged'] and
                     self.query(page).get('service') == ['aws_rds'])
        with page.expect_download() as pending:
            page.get_by_role('link', name='导出 CSV', exact=True).click()
        download = pending.value
        path = self.output / 'packaged-aws-rds.csv'
        download.save_as(path)
        reader = csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig')))
        rows = list(reader)
        self.require('CSV contains all filtered cells, beyond current page', len(rows) == count * columns and count > visible,
                     result_count=count, visible_rows=visible, exported_cells=len(rows), header=reader.fieldnames)
        self.require('CSV retains the selected cloud and fixed anchor',
                     {row['service'] for row in rows} == {'pigsty', 'aws_rds'})

    def evidence(self):
        page = self.goto('/ext/cloud/?q=postgis&selection=1&service=aws_rds')
        trigger = page.locator('td:not(.cloud-anchor) a[data-cloud-evidence]').first
        href = trigger.get_attribute('href')
        trigger.focus()
        page.keyboard.press('Enter')
        page.locator('#cloud-dialog[open] #cloud-evidence-content').wait_for()
        self.require('Keyboard opens source modal with official links',
                     page.locator('#cloud-dialog a[href^="https://"]').count() > 0)
        self.require('Source modal title names the PostgreSQL major', 'PG 18' in page.locator('#cloud-dialog-title').inner_text())
        self.require('Source modal retains raw name and capture date',
                     'PostGIS' in page.locator('#cloud-dialog-content').inner_text() and
                     bool(re.search(r'\d{4}-\d{2}-\d{2}', page.locator('#cloud-dialog-content').inner_text())))
        self.screenshot('evidence-desktop')
        page.keyboard.press('Escape')
        self.require('Escape closes modal and restores triggering focus', not page.locator('#cloud-dialog').is_visible() and
                     trigger.evaluate('(node) => document.activeElement === node'))
        self.require('Evidence has an ordinary shareable URL', '/ext/cloud/evidence/' in href)

    def responsive(self):
        for name, width, height, scheme in [('mobile', 390, 844, 'light'),
                                             ('mobile-small', 320, 740, 'light'),
                                             ('tablet', 768, 1024, 'light'),
                                             ('dark', 1440, 1080, 'dark')]:
            context = self.browser.new_context(viewport={'width': width, 'height': height}, color_scheme=scheme)
            page = self.new_page(context)
            for mode, path in [('compare', '/ext/cloud/'), ('aws-rds', '/ext/cloud/aws_rds/')]:
                self.goto(path, page)
                self.no_overflow(page, mode + ' ' + name)
                self.screenshot(mode + '-' + name, page)
            context.close()

    def no_javascript(self):
        context = self.browser.new_context(java_script_enabled=False, viewport={'width': 1280, 'height': 900})
        page = context.new_page()
        self.goto('/ext/cloud/', page)
        self.require('No-JS comparison contains matrix and submit control',
                     page.locator('.cloud-table tbody tr').count() > 0 and
                     page.get_by_role('button', name='应用筛选').is_visible())
        page.locator('#cloud-query').fill('postgis')
        page.locator('#cloud-pg').select_option('17')
        page.get_by_role('button', name='应用筛选').click()
        page.wait_for_load_state('networkidle')
        self.require('No-JS GET filtering renders useful results', self.query(page).get('q') == ['postgis'] and
                     self.query(page).get('pg') == ['17'] and 0 < page.locator('.cloud-table tbody tr').count() < 50)
        page.locator('td:not(.cloud-anchor) a[data-cloud-evidence]').first.click()
        page.wait_for_load_state('networkidle')
        self.require('No-JS cell navigation shows source evidence', page.locator('#cloud-evidence-content').is_visible() and
                     page.locator('#cloud-evidence-content a[href^="https://"]').count() > 0)
        self.screenshot('evidence-no-js', page)
        self.goto('/ext/cloud/aws_rds/', page)
        self.require('No-JS provider matrix has all five major versions', page.locator('.cloud-table thead th').count() == 6)
        context.close()

    def source_fidelity(self):
        if not self.source_check:
            return
        source = json.loads(self.source_check.read_text(encoding='utf-8'))
        labels = {'SUPPORTED': '支持', 'UNSUPPORTED': '不支持', 'OTHER': '条件支持'}
        for sample in source['samples']:
            path = '/ext/cloud/evidence/?' + urlencode({
                'service': sample['service'], 'pg': sample['pg_major'], 'entry': sample['extension']})
            page = self.goto(path)
            fields = page.locator('#cloud-evidence-content dl').evaluate('''element =>
                Object.fromEntries([...element.querySelectorAll('dt')].map(dt =>
                    [dt.textContent.trim(), dt.nextElementSibling.textContent.trim()]))''')
            self.require('Source fact preserved: ' + sample['service'] + '/' + sample['extension'],
                         fields.get('支持状态') == labels[sample['status']] and
                         fields.get('扩展版本', '') == (sample['version'] or '') and
                         fields.get('厂商原始名称') == sample['raw_name'], fields=fields)
            self.require('Evidence identifies its PostgreSQL major',
                         str(sample['pg_major']) in page.locator('.cloud-intro').inner_text())
            if sample['note']:
                self.require('Source note preserved: ' + sample['service'] + '/' + sample['extension'],
                             sample['note'] in page.locator('#cloud-evidence-content').inner_text())
        for meta in source['coverage']:
            if meta['engine_status'] != 'UNAVAILABLE' and meta['data_status'] != 'MISSING':
                continue
            path = '/ext/cloud/evidence/?' + urlencode({'service': meta['service'], 'pg': meta['pg_major'], 'entry': 'postgis'})
            page = self.goto(path)
            expected = '未提供此 PG 版本' if meta['engine_status'] == 'UNAVAILABLE' else '资料不足'
            self.require('Missing evidence is distinct from unsupported: ' + meta['service'],
                         page.locator('#cloud-evidence-content dd').first.inner_text() == expected)
        page = self.goto('/ext/cloud/?q=ICU+module&scope=raw&selection=1&service=aws_rds&service=aws_aurora')
        rows = page.locator('.cloud-table tbody tr')
        self.require('Identical unresolved labels remain separate provider identities', rows.count() == 2)
        entry_sets = [set(parse_qs(urlsplit(href).query)['entry'][0]
                          for href in row.locator('[data-cloud-evidence]').evaluate_all('(links) => links.map(link => link.href)'))
                      for row in rows.all()]
        self.require('Unresolved row links use service-qualified keys',
                     {next(iter(keys)) for keys in entry_sets} == {'raw:aws_rds:ICU module', 'raw:aws_aurora:ICU module'} and
                     all(len(keys) == 1 for keys in entry_sets), keys=[sorted(keys) for keys in entry_sets])
        self.screenshot('raw-provider-identities')
        with page.expect_download() as pending:
            page.get_by_role('link', name='导出 CSV', exact=True).click()
        path = self.output / 'raw-provider-identities.csv'
        pending.value.save_as(path)
        exported = list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
        self.require('CSV preserves unresolved row identities without ambiguous duplicates',
                     {row['entry_key'] for row in exported} == {'raw:aws_rds:ICU module', 'raw:aws_aurora:ICU module'} and
                     len({(row['entry_key'], row['service'], row['pg_major']) for row in exported}) == len(exported))

    def finish(self):
        self.record("No browser JavaScript errors", not self.errors, errors=self.errors)
        self.record("No CSP violations", not self.csp_errors, errors=self.csp_errors)
        report = {"base_url": self.base_url, "results": self.results,
                  "console_errors": self.console_errors}
        (self.output / "browser-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return all(item["passed"] for item in self.results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("tmp/ext-cloud-review"))
    parser.add_argument("--source-check", type=Path,
                        help="Optional independently exported JSON with source samples and coverage")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        review = Review(browser, args.base_url, args.output, args.source_check)
        for name, operation in [('Existing directory', review.baseline), ('Comparison', review.comparison),
                                ('Service', review.service), ('All provider routes', review.service_routes),
                                ('Filters and history', review.filtering),
                                ('IME and request races', review.input_and_races),
                                ('Pagination and CSV', review.pagination_and_export),
                                ('Source evidence', review.evidence), ('Responsive layout', review.responsive),
                                ('No JavaScript', review.no_javascript), ('Independent source evidence', review.source_fidelity)]:
            review.run(name, operation)
        passed = review.finish()
        browser.close()
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
