"""导入等待事件百科。本地与生产跑的是同一段逻辑。"""

import gzip
import json
import sys

from django.core.management.base import BaseCommand, CommandError

from pgweb.wiki import waitevent_importer


def load(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as handle:
        return json.load(handle)


def forget():
    """索引页缓存 5 分钟，导入后主动清掉。页面侧模块可能还没上线，缺了就算了。"""
    try:
        from pgweb.wiki import waitevent
    except ImportError:
        return
    if hasattr(waitevent, 'forget'):
        waitevent.forget()


class Command(BaseCommand):
    help = '从 pgsty/wait.pg.center 图谱（外加本站手册与上游文档）或一份快照导入等待事件百科'

    def add_arguments(self, parser):
        parser.add_argument('--root', default=waitevent_importer.DEFAULT_ROOT, help='图谱仓库路径')
        parser.add_argument('--input', help='改从快照文件加载（.json 或 .json.gz）')
        parser.add_argument('--export', help='导出快照到文件后退出，不写库')
        parser.add_argument('--check', action='store_true', help='只预览改动，不写库')
        parser.add_argument('--prune', action='store_true', help='删除快照里已经没有的事件与版本')
        parser.add_argument('--no-fetch', action='store_true', dest='no_fetch',
                            help='不联网，只用 tmp/waitevent-sources 里已有的缓存')

    def handle(self, **options):
        try:
            snapshot = load(options['input']) if options['input'] \
                else waitevent_importer.export_snapshot(options['root'],
                                                        fetch=not options['no_fetch'])
        except (OSError, ValueError) as error:
            raise CommandError(str(error))

        if options['export']:
            path = options['export']
            opener = gzip.open if path.endswith('.gz') else open
            with opener(path, 'wt', encoding='utf-8') as handle:
                json.dump(snapshot, handle, ensure_ascii=False, default=str)
            report = {'exported': path, 'versions': len(snapshot['versions']),
                      'events': len(snapshot['events']),
                      'digest': waitevent_importer.digest(snapshot)}
        elif options['check']:
            report = waitevent_importer.preview(snapshot)
        else:
            report = waitevent_importer.import_snapshot(snapshot, prune=options['prune'])
            forget()

        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write('\n')
