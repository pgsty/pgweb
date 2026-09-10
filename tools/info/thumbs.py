#!/usr/bin/env python3
"""Local 500 × 300 WebP thumbnails for 大新闻 items.

    tools/info/thumbs.py fetch  [DATE|file ...]          # download each tier-1 `image`, crop 5:3, write data/info/img/<key>.webp
    tools/info/thumbs.py missing [DATE|file ...] [--out tmp/info/need-image.jsonl]
    tools/info/thumbs.py convert PNG [PNG ...]            # crop/resize any picture files into data/info/img/<key>.webp (name = key)
    tools/info/thumbs.py orphans [--delete]               # thumbnails whose key no longer appears in any batch file

The thumbnail is the picture the site serves (stored in the info_item.thumb
column by the importer); the batch file's `image` field only records where the
source picture came from. Needs ImageMagick (`magick`) on PATH; stdlib only.
"""

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, 'data', 'info')
IMG = os.path.join(DATA, 'img')
WIDTH, HEIGHT, QUALITY = 500, 300, 82
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36 pgsql.cc-info'


def item_key(day, url, title):
    return hashlib.sha1('{}|{}'.format(day, url or title).encode('utf-8')).hexdigest()[:16]


def batches(args):
    if not args:
        return sorted(glob.glob(os.path.join(DATA, '*.json')))
    return [os.path.join(DATA, a + '.json') if len(a) == 10 and a[4] == '-' else a for a in args]


def leads(paths):
    for path in paths:
        with open(path, encoding='utf-8') as stream:
            payload = json.load(stream)
        for item in payload['items']:
            if item['tier'] == 1:
                yield payload['date'], item_key(payload['date'], item.get('url', ''), item['title']), item


def thumb_path(key):
    return os.path.join(IMG, key + '.webp')


def convert(source, key):
    """Centre-crop to 5:3, resize to 500 × 300, write WebP. Returns the output path."""
    os.makedirs(IMG, exist_ok=True)
    out = thumb_path(key)
    subprocess.run(['magick', source + '[0]', '-auto-orient', '-strip', '-resize', '{}x{}^'.format(WIDTH, HEIGHT),
                    '-gravity', 'center', '-extent', '{}x{}'.format(WIDTH, HEIGHT),
                    '-quality', str(QUALITY), '-define', 'webp:method=6', out], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return out


def download(url, timeout=30):
    request = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'image/*,*/*;q=0.8'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        kind = response.headers.get('Content-Type', '')
        if not kind.startswith('image/') and 'octet-stream' not in kind:
            raise ValueError('not an image: ' + kind)
        data = response.read(15 * 1024 * 1024)
    if len(data) < 1024:
        raise ValueError('too small ({} bytes)'.format(len(data)))
    return data


def fetch_one(day, key, item, force=False):
    if not item.get('image'):
        return day, key, 'noimage', ''
    if os.path.exists(thumb_path(key)) and not force:
        return day, key, 'exists', ''
    try:
        data = download(item['image'])
        with tempfile.NamedTemporaryFile(suffix='.img', delete=False) as tmp:
            tmp.write(data)
        try:
            convert(tmp.name, key)
        finally:
            os.unlink(tmp.name)
        return day, key, 'made', ''
    except Exception as exc:  # noqa: BLE001 - report, never abort the batch
        return day, key, 'failed', '{}: {}'.format(type(exc).__name__, str(exc)[:120])


def cmd_fetch(options):
    rows = list(leads(batches(options.files)))
    counts = {'made': 0, 'exists': 0, 'noimage': 0, 'failed': 0}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for day, key, state, note in pool.map(lambda r: fetch_one(*r, force=options.force), rows):
            counts[state] += 1
            if state == 'failed':
                print('{} {}: {}'.format(day, key, note))
    print(json.dumps(counts))


def cmd_missing(options):
    out = open(options.out, 'w', encoding='utf-8') if options.out else sys.stdout
    n = 0
    for day, key, item in leads(batches(options.files)):
        if os.path.exists(thumb_path(key)):
            continue
        n += 1
        out.write(json.dumps({'date': day, 'key': key, 'title': item['title'], 'summary': item.get('summary', ''),
                              'url': item.get('url', ''), 'domain': item.get('domain', ''), 'tags': item.get('tags', [])},
                             ensure_ascii=False) + '\n')
    if options.out:
        out.close()
        print('{} 条一档缺缩略图 -> {}'.format(n, options.out), file=sys.stderr)


def cmd_convert(options):
    for path in options.files:
        key = os.path.splitext(os.path.basename(path))[0]
        print(convert(path, key))


def cmd_orphans(options):
    keys = {key for _, key, _ in leads(batches([]))}
    orphans = [p for p in glob.glob(os.path.join(IMG, '*.webp')) if os.path.splitext(os.path.basename(p))[0] not in keys]
    for path in orphans:
        print(path)
        if options.delete:
            os.unlink(path)
    print('{} 张缩略图没有对应条目{}'.format(len(orphans), '，已删除' if options.delete else ''), file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='博览一档缩略图')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('fetch'); p.add_argument('files', nargs='*'); p.add_argument('--force', action='store_true')
    p = sub.add_parser('missing'); p.add_argument('files', nargs='*'); p.add_argument('--out')
    p = sub.add_parser('convert'); p.add_argument('files', nargs='+')
    p = sub.add_parser('orphans'); p.add_argument('--delete', action='store_true')
    options = parser.parse_args()
    {'fetch': cmd_fetch, 'missing': cmd_missing, 'convert': cmd_convert, 'orphans': cmd_orphans}[options.command](options)
    return 0


if __name__ == '__main__':
    sys.exit(main())
