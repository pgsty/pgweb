#!/usr/bin/env python3
"""Refresh Wiki pages in the site's full-text index without pruning other URLs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from configparser import ConfigParser
import json
import os
from pathlib import Path
import sys

import psycopg2
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools/search/crawler'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    cfg = ConfigParser()
    cfg.read(ROOT / 'tools/search/crawler/search.ini')
    assert cfg.get('search', 'web') == 'pgsql.cc'
    assert cfg.get('search', 'local_baseurl').rstrip('/') == args.base.rstrip('/')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    django.setup()
    from pgweb.wiki.struct import get_struct
    from lib.basecrawler import BaseSiteCrawler
    paths = sorted({'/' + row[0].lstrip('/') for row in get_struct()})
    assert len(paths) > 4500, len(paths)
    conn = psycopg2.connect(cfg.get('search', 'db'))
    with conn.cursor() as cursor:
        cursor.execute('SELECT current_database(),current_user')
        assert cursor.fetchone() == ('pgweb', 'pgweb')
        cursor.execute('SELECT hostname FROM sites WHERE id=1')
        assert cursor.fetchone()[0] == 'pgsql.cc'
    crawler = BaseSiteCrawler('pgsql.cc', conn, 1, local_baseurl=args.base)
    def fetch(path):
        response = requests.get(args.base + path, timeout=60)
        response.raise_for_status()
        assert 'text/html' in response.headers.get('content-type', ''), path
        return path, response.text, crawler.get_date(response.headers.get('last-modified'))
    with ThreadPoolExecutor(max_workers=3) as pool:
        count = 0
        # Bound pending HTML results; Executor.map otherwise queues the entire site.
        for start in range(0, len(paths), 12):
            for path, html, lastmod in pool.map(fetch, paths[start:start + 12]):
                crawler.page = crawler.parse_html(html)
                crawler.save_page(path, lastmod, 0.8, False)
                count += 1
                if count % 200 == 0:
                    conn.commit()
                    print('Indexed', count, 'of', len(paths), flush=True)
    conn.commit()
    with conn.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM webpages WHERE site=1 AND suburl=ANY(%s)', [paths])
        assert cursor.fetchone()[0] == len(paths)
        cursor.execute('UPDATE sites SET pagecount=(SELECT count(*) FROM webpages WHERE site=1) WHERE id=1')
    conn.commit()
    receipt = dict(count=len(paths), updated=crawler.pages_updated, added=crawler.pages_new, deleted=0, paths=paths)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print({k: v for k, v in receipt.items() if k != 'paths'})
    conn.close()


if __name__ == '__main__':
    main()
