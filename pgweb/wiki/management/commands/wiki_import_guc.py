"""导入配置参数百科。本地与生产跑的是同一段逻辑。"""

import gzip
import json
import sys

from django.core.management.base import BaseCommand, CommandError

from pgweb.wiki import guc_importer


def load(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as handle:
        return json.load(handle)


def forget():
    """页面缓存 5 分钟，导入后主动清掉；页面模块还没落地时不拦着导入。"""
    try:
        from pgweb.wiki import guc
    except ImportError:
        return
    getattr(guc, 'forget', lambda: None)()


class Command(BaseCommand):
    help = '从 pgsty/guc.pg.center 仓库（外加本站手册译文）或一份快照导入配置参数百科'

    def add_arguments(self, parser):
        parser.add_argument('--root', default=guc_importer.DEFAULT_ROOT, help='源仓库路径')
        parser.add_argument('--input', help='改从快照文件加载（.json 或 .json.gz）')
        parser.add_argument('--export', help='导出快照到文件后退出，不写库')
        parser.add_argument('--check', action='store_true', help='只预览改动，不写库')
        parser.add_argument('--prune', action='store_true', help='删除快照里已经没有的参数与版本')

    def handle(self, **options):
        try:
            snapshot = load(options['input']) if options['input'] \
                else guc_importer.export_snapshot(options['root'])
        except (OSError, ValueError) as error:
            raise CommandError(str(error))

        if options['export']:
            path = options['export']
            opener = gzip.open if path.endswith('.gz') else open
            with opener(path, 'wt', encoding='utf-8') as handle:
                json.dump(snapshot, handle, ensure_ascii=False, default=str)
            report = {'exported': path, 'versions': len(snapshot['versions']),
                      'parameters': len(snapshot['parameters'])}
        elif options['check']:
            report = guc_importer.preview(snapshot)
        else:
            report = guc_importer.import_snapshot(snapshot, prune=options['prune'])
            forget()

        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write('\n')
