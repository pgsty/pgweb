#!/usr/bin/env python3
"""Point third-party announcements away from postgresql.org news pages.

    .venv/bin/python tools/info/relink.py [--dry-run] [data/info/*.json]

A postgresql.org news page is the final content only for PostgreSQL's own
releases and security advisories (org = PostgreSQL Global Development Group /
Core Team / Security Team). For every other item whose url is such a page,
switch to our translated copy on pgsql.cc, found in the local news table by
date and slug tokens. Items that already point elsewhere are untouched.
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
UPSTREAM = re.compile(r'^https?://www\.postgresql\.org/about/news/(?:([a-z0-9-]*?)-)?(\d+)/?$')
OWN_ORGS = ('postgresql global development group', 'postgresql core team', 'postgresql security team',
            'postgresql project', 'pgdg')
STOP = {'released', 'release', 'postgresql', 'postgres', 'for', 'and', 'the', 'of', 'with', 'is', 'now',
        'available', 'new', 'version', 'announcement', 'announcing', 'call', 'papers', 'out', 'ai', 'open',
        'source', 'data', 'cloud', 'update', 'updates'}


def setup_django():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    django.setup()


def tokens(slug):
    return {t for t in slug.split('-') if t and t not in STOP and not t.isdigit()}


def main():
    parser = argparse.ArgumentParser(description='把第三方公告从 postgresql.org 新闻页改到本站译文页')
    parser.add_argument('files', nargs='*')
    parser.add_argument('--dry-run', action='store_true')
    options = parser.parse_args()
    files = sorted(options.files or glob.glob(os.path.join(ROOT, 'data', 'info', '*.json')))
    setup_django()
    from pgweb.news.models import NewsArticle
    from pgweb.news.util import news_url
    changed = kept = unmatched = 0
    for path in files:
        with open(path, encoding='utf-8') as stream:
            payload = json.load(stream)
        day = date.fromisoformat(payload['date'])
        dirty = False
        for item in payload['items']:
            m = UPSTREAM.match((item.get('url') or '').strip())
            if not m:
                continue
            slug = m.group(1) or ''
            when = date.fromisoformat(item['source_date']) if item.get('source_date') else day
            rows = list(NewsArticle.objects.filter(modstate=2, date__gte=when - timedelta(days=4),
                                                   date__lte=when + timedelta(days=2)).select_related('org'))
            want = tokens(slug)
            best, score = None, 0
            for row in rows:
                local = news_url(row.title, row.id)
                shared = want & tokens(local.split('/')[3].rsplit('-', 1)[0])
                # One shared token is enough only when it is a distinctive name.
                overlap = len(shared) if len(shared) > 1 or any(len(t) >= 5 for t in shared) else 0
                if overlap > score:
                    best, score = row, overlap
            if best is None:
                unmatched += 1
                print('{}: 未找到本站对应新闻 {}'.format(payload['date'], item['url']))
                continue
            if (best.org.name if best.org_id else '').lower() in OWN_ORGS:
                kept += 1
                continue
            new = 'https://pgsql.cc' + news_url(best.title, best.id)
            print('{}: {} 档「{}」 -> {}'.format(payload['date'], item['tier'], item['title'], new))
            item['url'] = new
            dirty = True
            changed += 1
        if dirty and not options.dry_run:
            with open(path, 'w', encoding='utf-8') as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
    print('改链 {}，保留官方公告 {}，未匹配 {}'.format(changed, kept, unmatched), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
