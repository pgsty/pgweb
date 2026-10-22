"""Freeze the related release labels and verify already-current Chinese manuals."""
import argparse
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys


def write_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    path.write_bytes(gzip.compress(data, mtime=0) if path.suffix == '.gz' else data)
    return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}


def build(root, repair_root):
    from bs4 import BeautifulSoup
    from django.db import connection, transaction
    from pgweb.docs.models import DocPage
    from pgweb.docs.compare_store import export_database_snapshot, digest
    root.mkdir(parents=True, exist_ok=False)
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            cur.execute('SELECT current_database(),current_user')
            assert cur.fetchone() == ('pgweb', 'pgweb')
        manual_checks = []
        receipts = json.loads((repair_root/'catalog/manual-patch-receipts.json').read_text())
        for item in receipts:
            page = DocPage.objects.get(version=item['version'], file=item['page_key'])
            soup = BeautifulSoup(page.content, 'html.parser')
            found = []
            for tr in soup.find_all('tr'):
                cells = tr.find_all('td', recursive=False)
                if len(cells) > 1 and cells[0].get_text(' ', strip=True) == item['column']:
                    found.append(cells[1].get_text(' ', strip=True))
            assert len(found) == 1 and found[0] in {item['english_type'], item['after_type']}, item
            manual_checks.append(dict(item, target_type=found[0], target_id=page.pk,
                                      content_sha256=hashlib.sha256(page.content.encode()).hexdigest(),
                                      action='already-correct; preserved'))
        page = DocPage.objects.get(version='9.4', file='runtime-config-connection.html')
        soup = BeautifulSoup(page.content, 'html.parser')
        dt = soup.find(id='GUC-SSL-CIPHERS')
        dd = dt.find_next_sibling('dd')
        assert 'TLS 1.3' not in dd.get_text() and 'HIGH:MEDIUM:+3DES:!aNULL' in dd.get_text()
        assert dd.find_next_sibling('dt').get('id') == 'GUC-SSL-PREFER-SERVER-CIPHERS'
        assert dt.parent == soup.find(id='GUC-SSL-RENEGOTIATION-LIMIT').parent
        manual_checks.append({'version':'9.4','page_key':page.file,'target_id':page.pk,
                              'content_sha256':hashlib.sha256(page.content.encode()).hexdigest(),
                              'action':'already-correct TLS version and nesting; preserved'})
        before = export_database_snapshot(language='zh')
        after = copy.deepcopy(before)
        release = next(r for r in after['releases'] if r['version'] == '19.0')
        changes = []
        for field in ('build', 'manual_build'):
            assert release[field] == '19beta4'
            changes.append({'version':'19.0','field':field,'before':release[field],'after':'19rc1'})
            release[field] = '19rc1'
        files = {}
        for name, value in [('releases-before.json.gz', before), ('releases-after.json.gz', after),
                            ('manual-checks.json', manual_checks)]:
            files[name] = write_json(root/name, value)
        result = {'format':1,'files':files,'changes':changes,'before_release_hash':digest(before),
                  'after_release_hash':digest(after),'manual_checks':len(manual_checks),
                  'manual_pages':len({(r['version'],r['page_key']) for r in manual_checks}),
                  'manual_writes':0,'release_entries_preserved':sum(len(r['entries']) for r in after['releases'])}
        write_json(root/'manifest.json', result)
        return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--repair-root', type=Path, required=True)
    args=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','pgweb.settings')
    import django
    django.setup()
    print(json.dumps(build(args.output,args.repair_root),ensure_ascii=False))
