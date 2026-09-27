"""Import the same self-contained lock snapshot locally or on production."""

import gzip
import json

from django.core.management.base import BaseCommand, CommandError

from pgweb.wiki import lock_importer


class Command(BaseCommand):
    help = '导入完整的 PostgreSQL 锁百科快照（默认 data/wiki/locks.json）'

    def add_arguments(self, parser):
        parser.add_argument('--input', default='data/wiki/locks.json',
                            help='自包含快照文件（.json 或 .json.gz）')
        parser.add_argument('--check', '--dry-run', action='store_true',
                            help='校验并预览变更，不写入数据库')
        parser.add_argument('--prune', action='store_true', help='删除不在完整快照中的旧模式')

    def handle(self, **options):
        try:
            path = options['input']
            opener = gzip.open if path.endswith('.gz') else open
            with opener(path, 'rt', encoding='utf-8') as handle:
                snapshot = json.load(handle)
            report = (lock_importer.preview(snapshot) if options['check'] else
                      lock_importer.import_snapshot(snapshot, prune=options['prune']))
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
