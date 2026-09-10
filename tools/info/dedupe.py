#!/usr/bin/env python3
"""Drop cross-day duplicate links in data/info/*.json, keeping the earliest day.

    tools/info/dedupe.py [--dry-run] [data/info/*.json]

Two editors working on neighbouring ranges can both pick the same link; the
column wants one entry per event. The copy with the higher tier wins (a story
that matured into 大新闻 keeps that entry); at equal tier the earliest day
wins. Losing days are renumbered. Files are rewritten in the same format (2-space indent,
ensure_ascii=False, trailing newline). Stdlib only.
"""

import argparse
import glob
import json
import os
import sys
from urllib.parse import urlsplit, urlunsplit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def normalise(url):
    parts = urlsplit(url.strip())
    path = parts.path.rstrip('/') or '/'
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ''))


def load(path):
    with open(path, encoding='utf-8') as stream:
        return json.load(stream)


def main():
    parser = argparse.ArgumentParser(description='去掉跨天重复链接：保留档位更高的一条，同档保留最早的一天')
    parser.add_argument('files', nargs='*')
    parser.add_argument('--dry-run', action='store_true')
    options = parser.parse_args()
    files = sorted(options.files or glob.glob(os.path.join(ROOT, 'data', 'info', '*.json')))
    payloads = {path: load(path) for path in files}
    # Winner per link: lowest tier number, then earliest date (files are date-sorted).
    winner = {}
    for path in files:
        for item in payloads[path]['items']:
            url = item.get('url') or ''
            if not url:
                continue
            key = normalise(url)
            if key not in winner or item['tier'] < winner[key][1]:
                winner[key] = (path, item['tier'])
    removed = 0
    for path in files:
        payload = payloads[path]
        keep, dropped = [], []
        for item in payload['items']:
            url = item.get('url') or ''
            if url and winner[normalise(url)][0] != path:
                dropped.append((item['tier'], item['title'], payloads[winner[normalise(url)][0]]['date']))
            else:
                keep.append(item)
        if not dropped:
            continue
        removed += len(dropped)
        for tier, title, other in dropped:
            print('{}: 删去 {} 档「{}」（{} 保留）'.format(payload['date'], tier, title, other))
        for index, item in enumerate(keep, start=1):
            item['position'] = index
        payload['items'] = keep
        if not options.dry_run:
            with open(path, 'w', encoding='utf-8') as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
    print('{} 个文件，删去 {} 条重复'.format(len(files), removed), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
