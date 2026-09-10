#!/usr/bin/env python3
"""Generate missing 大新闻 thumbnails with Codex's image tool (GPT Image).

    tools/info/gen_thumbs.py tmp/info/need-image.jsonl [--batch 8] [--parallel 4] [--limit N] [--workdir tmp/info/gen]

Reads the manifest written by `thumbs.py missing` (one JSON object per line
with date, key, title, summary, url, domain, tags), skips keys that already have
data/info/img/<key>.webp, and asks `codex exec` to draw one picture per item in
the column's house style. Codex saves each PNG as <workdir>/<key>.png; this
script crops it to 500 × 300 WebP via thumbs.convert. Failures are logged and
left for the next run. Stdlib only; needs `codex` and `magick` on PATH.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import thumbs  # noqa: E402

STYLE = """House style, identical for every picture: flat vector editorial illustration, clean geometric shapes, soft
two-tone shading, faintly textured off-white background (#F4F5F7). Palette: PostgreSQL slate blue (#336791), light
blue (#8FB3D9), graphite (#2F3A48), warm sand (#E9DCC5) and at most one small warm accent (#E8A33D); no other
saturated colours, no gradients, no 3D render, no photo. Landscape 3:2, one clear subject centred with breathing room
and nothing important in the top or bottom 8% (it will be cropped to 5:3). Absolutely no text, letters, digits, logos,
trademarks, brand marks, screenshots, code, or recognisable people. Say what the news is about through metaphor:
databases as stacked cylinders, tables as grids, replication as mirrored shapes with arrows, backups as boxes and
clocks, security as shields, locks and keys, performance as gauges or a rocket, cloud services as clouds over servers,
releases as wrapped packages or tags, conferences as a stage and speech bubbles, funding as coins, AI as a neural
mesh or a friendly robot. A friendly flat blue elephant (the PostgreSQL mascot) may appear when the news is about
PostgreSQL itself."""


def load_manifest(path, limit=None):
    rows = []
    with open(path, encoding='utf-8') as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if os.path.exists(thumbs.thumb_path(row['key'])):
                continue
            rows.append(row)
    return rows[:limit] if limit else rows


def prompt_for(batch, workdir):
    lines = [
        "You are illustrating items for pgsql.cc's PostgreSQL news column. For EACH item below, write one English",
        "image prompt that follows the house style exactly and depicts that item's subject, then call your image",
        "generation tool once with it at 1536x1024, and move the resulting PNG to {}/<key>.png".format(workdir),
        "(exactly that file name, no other files). Do not skip items; if a generation fails, retry once. Do not",
        "open any URL. Do not write anything except the PNG files. When every item is done, reply with one line",
        "per key: `<key> done` or `<key> failed: reason`.",
        "",
        STYLE,
        "",
        "Items:",
    ]
    for row in batch:
        summary = (row.get('summary') or '').replace('\n', ' ')
        lines.append("- key: {}\n  title: {}\n  summary: {}\n  domain: {}  tags: {}".format(
            row['key'], row['title'], summary[:400], row.get('domain', ''), ', '.join(row.get('tags') or [])))
    return "\n".join(lines)


def run_batch(batch, workdir, model, effort, timeout):
    os.makedirs(workdir, exist_ok=True)
    started = time.time()
    command = ['codex', 'exec', '--skip-git-repo-check', '-C', workdir, '--sandbox', 'danger-full-access',
               '-c', 'model_reasoning_effort="{}"'.format(effort)]
    if model:
        command += ['-m', model]
    command.append(prompt_for(batch, workdir))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        tail = (result.stdout or '')[-2000:]
    except subprocess.TimeoutExpired:
        tail = 'timeout'
    made, failed = [], []
    for row in batch:
        png = os.path.join(workdir, row['key'] + '.png')
        if os.path.exists(png) and os.path.getsize(png) > 10000:
            try:
                thumbs.convert(png, row['key'])
                os.unlink(png)
                made.append(row['key'])
                continue
            except subprocess.CalledProcessError as exc:
                tail += '\nconvert failed for {}: {}'.format(row['key'], exc.stderr.decode()[:200])
        failed.append(row['key'])
    return {'made': made, 'failed': failed, 'seconds': int(time.time() - started), 'tail': tail}


def main():
    parser = argparse.ArgumentParser(description='用 Codex 图像工具补一档缩略图')
    parser.add_argument('manifest')
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--parallel', type=int, default=4)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--workdir', default=os.path.join(thumbs.ROOT, 'tmp', 'info', 'gen'))
    parser.add_argument('--model', default='')
    parser.add_argument('--effort', default='medium')
    parser.add_argument('--timeout', type=int, default=1800, help='seconds per codex session')
    options = parser.parse_args()
    rows = load_manifest(options.manifest, options.limit)
    batches = [rows[i:i + options.batch] for i in range(0, len(rows), options.batch)]
    print('{} 条待生成，{} 批，每批 {} 张，{} 路并行'.format(len(rows), len(batches), options.batch, options.parallel), flush=True)
    made = failed = 0
    with ThreadPoolExecutor(max_workers=options.parallel) as pool:
        futures = [pool.submit(run_batch, batch, os.path.join(options.workdir, 'b{:03d}'.format(i)),
                               options.model, options.effort, options.timeout) for i, batch in enumerate(batches)]
        for i, future in enumerate(futures):
            report = future.result()
            made += len(report['made'])
            failed += len(report['failed'])
            print('batch {:03d}: made {} failed {} in {}s{}'.format(
                i, len(report['made']), len(report['failed']), report['seconds'],
                ('\n  failed: ' + ', '.join(report['failed'])) if report['failed'] else ''), flush=True)
            if report['failed']:
                print('  codex tail: ' + report['tail'][-600:].replace('\n', '\n  '), flush=True)
    print(json.dumps({'made': made, 'failed': failed}), flush=True)
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
