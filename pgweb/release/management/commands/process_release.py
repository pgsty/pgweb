from django.core.management.base import BaseCommand
from django.db import transaction
from django.test.utils import override_settings

from pgweb.release.migrate import do_migrate


class Command(BaseCommand):
    help = '显式处理 data/releases 中日期最新的发布 YAML'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-email',
            action='store_true',
            help='批准新闻时同时发送发布公告邮件',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='执行完整处理并输出结果，但在结束时回滚事务',
        )

    def handle(self, *args, **options):
        with override_settings(
            RELEASE_SEND_ANNOUNCEMENT_EMAIL=options['send_email'],
        ):
            with transaction.atomic():
                do_migrate()
                if options['dry_run']:
                    transaction.set_rollback(True)

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('演练完成：所有数据库变更均已回滚。'))
