"""导入函数百科。本地与生产跑的是同一段逻辑。"""

import gzip
import json
import sys

from django.core.management.base import BaseCommand, CommandError

from pgweb.wiki import func_importer


def load(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as handle:
        return json.load(handle)


class Command(BaseCommand):
    help = '从上游英文原页（事实）加本站手册（中文）或一份自包含快照导入函数百科'

    def add_arguments(self, parser):
        parser.add_argument('--offline', action='store_true',
                            help='只用 --cache-dir 里已有的上游页面，不联网；缺的版本跳过并写进报告')
        parser.add_argument('--cache-dir', default=func_importer.CACHE_DIR)
        parser.add_argument('--input', help='改从快照文件加载（.json 或 .json.gz）')
        parser.add_argument('--export', help='导出快照到文件后退出，不写库')
        parser.add_argument('--check', action='store_true', help='只预览改动，不写库')
        parser.add_argument('--prune', action='store_true', help='删除快照里已经没有的函数与版本')

    def handle(self, **options):
        try:
            snapshot = load(options['input']) if options['input'] \
                else func_importer.export_snapshot(options['offline'], options['cache_dir'])
        except (OSError, ValueError) as error:
            raise CommandError(str(error))

        if options['export']:
            path = options['export']
            opener = gzip.open if path.endswith('.gz') else open
            with opener(path, 'wt', encoding='utf-8') as handle:
                json.dump(snapshot, handle, ensure_ascii=False, default=str)
            report = {'exported': path, 'versions': len(snapshot['versions']),
                      'functions': len(snapshot['functions']),
                      'digest': func_importer.digest(snapshot)}
        elif options['check']:
            report = func_importer.preview(snapshot)
        else:
            report = func_importer.import_snapshot(snapshot, prune=options['prune'])

        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write('\n')
