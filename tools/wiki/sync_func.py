#!/usr/bin/env python3
"""把函数百科同步进本地或生产 PGWeb 库。

事实取自 postgresql.org 的英文原页，中文取自本站手册。导出与导入分两步，好让同一份
快照分别加载两端；生产机上不需要手册，也不联网——抓取、解析与中文叠加都在导出时做完了。
默认只预览不写库。
"""

import argparse
import gzip
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


def blob(snapshot):
    return gzip.compress(json.dumps(snapshot, ensure_ascii=False, default=str).encode(), mtime=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true',
                        help='只用 --cache-dir 里已有的上游页面，不联网；缺的版本跳过并写进报告')
    parser.add_argument('--cache-dir', default='tmp/func-sources')
    parser.add_argument('--input', help='改从快照加载；- 表示从标准输入读 gzip')
    parser.add_argument('--export', type=Path, metavar='FILE.json.gz', help='导出快照后退出，不写库')
    parser.add_argument('--target', choices=['local', 'production'], default='local')
    parser.add_argument('--ssh-host', default='pg')
    parser.add_argument('--remote-root', default='/data/app/pgsql.cc')
    parser.add_argument('--write', action='store_true', help='真正写库；不给就只预览')
    parser.add_argument('--prune', action='store_true', help='删除快照里已经没有的函数与版本')
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    from django.db import DatabaseError
    django.setup()
    from pgweb.wiki import func_importer

    try:
        if args.input:
            payload = sys.stdin.buffer.read() if args.input == '-' else Path(args.input).read_bytes()
            snapshot = json.loads(gzip.decompress(payload) if payload.startswith(b'\x1f\x8b')
                                  else payload)
        else:
            snapshot = func_importer.export_snapshot(offline=args.offline,
                                                     cache_dir=args.cache_dir)
        func_importer.validate(snapshot)

        if args.export:
            args.export.write_bytes(blob(snapshot))
            print('已导出 {} 个函数、{} 个版本到 {}'.format(
                len(snapshot['functions']), len(snapshot['versions']), args.export))
            return 0

        if args.target == 'production':
            remote = ['.venv/bin/python', 'tools/wiki/sync_func.py', '--input', '-']
            if args.write:
                remote.append('--write')
            if args.prune:
                remote.append('--prune')
            command = 'cd {} && {}'.format(shlex.quote(args.remote_root), shlex.join(remote))
            result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '--', args.ssh_host, command],
                                    input=blob(snapshot), capture_output=True)
            if result.returncode:
                raise ValueError('远端同步失败：' + result.stderr.decode().strip())
            report = json.loads(result.stdout)
        elif args.write:
            report = func_importer.import_snapshot(snapshot, prune=args.prune)
        else:
            report = func_importer.preview(snapshot)

        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        if args.write:
            print('别忘了重建检索：.venv/bin/python manage.py index_docs --func', file=sys.stderr)
        return 0
    except (OSError, ValueError, DatabaseError) as exc:
        print('函数百科同步失败：{}'.format(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
