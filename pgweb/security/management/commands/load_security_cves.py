from django.core.management.base import BaseCommand

from pgweb.security.loader import load_security_json


class Command(BaseCommand):
    help = '从 data/security/cve 显式同步 PostgreSQL CNA 数据'

    def add_arguments(self, parser):
        parser.add_argument(
            '--overwrite-text',
            action='store_true',
            help='用本地中文映射覆盖已有标题和详情；无映射时回退到英文 CNA 原文',
        )
        parser.add_argument(
            '--prune-missing',
            action='store_true',
            help='删除 JSON 集合中不存在的 2025 年以后 CVE 及版本关联',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='执行完整同步并输出结果，但在结束时回滚事务',
        )

    def handle(self, *args, **options):
        load_security_json(
            overwrite_text=options['overwrite_text'],
            prune_missing=options['prune_missing'],
            dry_run=options['dry_run'],
        )
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('演练完成：所有数据库变更均已回滚。'))
