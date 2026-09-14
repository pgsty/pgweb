"""导入 SQL 命令百科。本地与生产跑的是同一段逻辑。"""

import gzip
import json
import sys

from django.core.management.base import BaseCommand, CommandError

from pgweb.wiki import sqlcmd_importer


def load(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as handle:
        return json.load(handle)


def forget():
    """页面缓存 5 分钟，导入后主动清掉；页面模块还没落地时不拦着导入。"""
    try:
        from pgweb.wiki import sqlcmd
    except ImportError:
        return
    getattr(sqlcmd, 'forget', lambda: None)()


class Command(BaseCommand):
    help = '从本站手册或自包含快照导入 SQL 命令百科'

    def add_arguments(self, parser):
        parser.add_argument('--fetch', action='store_true', help='预留：二期抓取 9.x 英文层')
        parser.add_argument('--cache-dir', default=sqlcmd_importer.CACHE_DIR)
        parser.add_argument('--input', help='改从快照文件加载（.json 或 .json.gz）')
        parser.add_argument('--export', help='导出快照到文件后退出，不写库')
        parser.add_argument('--check', action='store_true', help='只预览改动，不写库')
        parser.add_argument('--prune', action='store_true', help='删除快照里已经没有的命令')

    def handle(self, **options):
        try:
            snapshot = load(options['input']) if options['input'] \
                else sqlcmd_importer.export_snapshot(options['fetch'], options['cache_dir'])
        except (OSError, ValueError) as error:
            raise CommandError(str(error))

        if options['export']:
            path = options['export']
            opener = gzip.open if path.endswith('.gz') else open
            with opener(path, 'wt', encoding='utf-8') as handle:
                json.dump(snapshot, handle, ensure_ascii=False, default=str)
            report = {'exported': path, 'versions': len(snapshot['versions']),
                      'commands': len(snapshot['commands'])}
        elif options['check']:
            report = sqlcmd_importer.preview(snapshot)
        else:
            report = sqlcmd_importer.import_snapshot(snapshot, prune=options['prune'])
            forget()

        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write('\n')
