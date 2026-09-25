"""导入错误码大全。本地与生产跑的是同一段逻辑。"""

import gzip
import json
import sys

from django.core.management.base import BaseCommand, CommandError

from pgweb.wiki import errcode, importer


def load(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as handle:
        return json.load(handle)


class Command(BaseCommand):
    help = '从 pgsty/err.pg.center 仓库或一份快照导入错误码大全'

    def add_arguments(self, parser):
        parser.add_argument('--root', default=importer.DEFAULT_ROOT, help='源仓库路径')
        parser.add_argument('--input', help='改从快照文件加载（.json 或 .json.gz）')
        parser.add_argument('--export', help='导出快照到文件后退出，不写库')
        parser.add_argument('--check', action='store_true', help='只预览改动，不写库')
        parser.add_argument('--prune', action='store_true', help='删除快照里已经没有的码')

    def handle(self, **options):
        try:
            snapshot = load(options['input']) if options['input'] \
                else importer.export_snapshot(options['root'])
        except (OSError, ValueError) as error:
            raise CommandError(str(error))

        snapshot = importer.prepare(snapshot)
        if options['export']:
            path = options['export']
            opener = gzip.open if path.endswith('.gz') else open
            with opener(path, 'wt', encoding='utf-8') as handle:
                json.dump(snapshot, handle, ensure_ascii=False, default=str)
            report = {'exported': path, 'codes': len(snapshot['codes'])}
        elif options['check']:
            report = importer.preview(snapshot)
        else:
            report = importer.import_snapshot(snapshot, prune=options['prune'])
            # 索引页缓存 5 分钟，导入后主动清掉，改动立刻可见。
            errcode.forget()

        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write('\n')
