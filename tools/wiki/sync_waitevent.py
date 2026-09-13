#!/usr/bin/env python3
"""把 pgsty/wait.pg.center 的等待事件百科同步进本地或生产 PGWeb 库。

导出与导入分两步，好让同一份快照分别加载两端；生产机上不需要图谱仓库，也不需要本站手册
与联网——中文采集、上游英文与 19 / 20 的推导都在导出时做完了。默认只预览不写库。
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
    parser.add_argument('--root', default='~/pg.center/wait', help='图谱仓库路径')
    parser.add_argument('--input', help='改从快照加载；- 表示从标准输入读 gzip')
    parser.add_argument('--export', type=Path, metavar='FILE.json.gz', help='导出快照后退出，不写库')
    parser.add_argument('--target', choices=['local', 'production'], default='local')
    parser.add_argument('--ssh-host', default='pg')
    parser.add_argument('--remote-root', default='/data/app/pgsql.cc')
    parser.add_argument('--write', action='store_true', help='真正写库；不给就只预览')
    parser.add_argument('--prune', action='store_true', help='删除快照里已经没有的事件与版本')
    parser.add_argument('--no-fetch', action='store_true', dest='no_fetch',
                        help='不联网，只用 tmp/waitevent-sources 里已有的缓存')
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    from django.db import DatabaseError
    django.setup()
    from pgweb.wiki import waitevent_importer

    try:
        if args.input:
            payload = sys.stdin.buffer.read() if args.input == '-' else Path(args.input).read_bytes()
            snapshot = json.loads(gzip.decompress(payload))
        else:
            snapshot = waitevent_importer.export_snapshot(args.root, fetch=not args.no_fetch)
        waitevent_importer.validate(snapshot)

        if args.export:
            args.export.write_bytes(blob(snapshot))
            print('已导出 {} 个事件、{} 个版本到 {}'.format(
                len(snapshot['events']), len(snapshot['versions']), args.export))
            return 0

        if args.target == 'production':
            remote = ['.venv/bin/python', 'tools/wiki/sync_waitevent.py', '--input', '-']
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
            report = waitevent_importer.import_snapshot(snapshot, prune=args.prune)
            forget()
        else:
            report = waitevent_importer.preview(snapshot)

        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        if args.write:
            print('别忘了重建检索：.venv/bin/python manage.py index_docs --waitevents', file=sys.stderr)
        return 0
    except (OSError, ValueError, DatabaseError) as exc:
        print('等待事件同步失败：{}'.format(exc), file=sys.stderr)
        return 1


def forget():
    """索引页缓存 5 分钟，导入后主动清掉。页面侧模块可能还没上线，缺了就算了。"""
    try:
        from pgweb.wiki import waitevent
    except ImportError:
        return
    if hasattr(waitevent, 'forget'):
        waitevent.forget()


if __name__ == '__main__':
    sys.exit(main())
