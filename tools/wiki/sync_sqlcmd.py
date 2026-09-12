#!/usr/bin/env python3
"""把本站手册的 SQL 命令百科同步进本地或生产 PGWeb 库。

导出与导入分两步，好让同一份快照分别加载两端；生产机上不需要源仓库，也不需要
本站手册——手册译文采集与 SQL 参考页解析都在导出时做完了。默认只预览不写库。
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


def forget():
    """页面缓存 5 分钟，导入后主动清掉；页面模块还没落地时不拦着导入。"""
    try:
        from pgweb.wiki import sqlcmd
    except ImportError:
        return
    getattr(sqlcmd, 'forget', lambda: None)()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true', help='预留：二期抓取 9.x 英文层')
    parser.add_argument('--cache-dir', default='tmp/sqlcmd-sources')
    parser.add_argument('--input', help='改从快照加载；- 表示从标准输入读 gzip')
    parser.add_argument('--export', type=Path, metavar='FILE.json.gz', help='导出快照后退出，不写库')
    parser.add_argument('--target', choices=['local', 'production'], default='local')
    parser.add_argument('--ssh-host', default='pg')
    parser.add_argument('--remote-root', default='/data/app/pgsql.cc')
    parser.add_argument('--write', action='store_true', help='真正写库；不给就只预览')
    parser.add_argument('--prune', action='store_true', help='删除快照里已经没有的命令')
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    from django.db import DatabaseError
    django.setup()
    from pgweb.wiki import sqlcmd_importer

    try:
        if args.input:
            payload = sys.stdin.buffer.read() if args.input == '-' else Path(args.input).read_bytes()
            snapshot = json.loads(gzip.decompress(payload) if payload.startswith(b'\x1f\x8b') else payload)
        else:
            snapshot = sqlcmd_importer.export_snapshot(fetch=args.fetch, cache_dir=args.cache_dir)
        sqlcmd_importer.validate(snapshot)

        if args.export:
            args.export.write_bytes(blob(snapshot))
            print('已导出 {} 条命令、{} 个版本到 {}'.format(
                len(snapshot['commands']), len(snapshot['versions']), args.export))
            return 0

        if args.target == 'production':
            remote = ['.venv/bin/python', 'tools/wiki/sync_sqlcmd.py', '--input', '-']
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
            report = sqlcmd_importer.import_snapshot(snapshot, prune=args.prune)
            forget()
        else:
            report = sqlcmd_importer.preview(snapshot)

        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        if args.write:
            print('别忘了重建检索：.venv/bin/python manage.py index_docs --sqlcmd', file=sys.stderr)
        return 0
    except (OSError, ValueError, DatabaseError) as exc:
        print('SQL 命令同步失败：{}'.format(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
