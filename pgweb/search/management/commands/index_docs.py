import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Q

from pgweb.core.models import Version
from pgweb.docs.versions import manual_major
from pgweb.search.indexer import (rebuild_catalog, rebuild_errcodes, rebuild_extensions,
                                  rebuild_guc, rebuild_version)


class Command(BaseCommand):
    help = ('Build the search index from local data: the PostgreSQL manuals in the docs table and the '
            'PGEXT catalogue in pgext.universe. No external content is fetched. Without arguments every '
            'loaded PG10+ manual, the development snapshot and the catalogue are processed.')

    def add_arguments(self, parser):
        parser.add_argument('--versions', nargs='+', type=int, help='Major versions of the manual to index')
        parser.add_argument('--extensions', action='store_true', help='Rebuild the extension catalogue entries')
        parser.add_argument('--errcodes', action='store_true', help='Rebuild the SQL 状态码 entries')
        parser.add_argument('--catalog', action='store_true', help='Rebuild the 系统目录 entries')
        parser.add_argument('--guc', action='store_true', help='Rebuild the 配置参数 entries')
        parser.add_argument('--force', action='store_true', help='Rebuild unchanged manual pages too')
        parser.add_argument('--dry-run', action='store_true', help='Extract and report without writing')

    def handle(self, **options):
        available = [manual_major(tree) for tree in Version.objects.filter(
            Q(tree__gte=10) | Q(tree=0), docpage__isnull=False).values_list('tree', flat=True).distinct()]
        everything = not any((options['versions'], options['extensions'], options['errcodes'],
                              options['catalog'], options['guc']))
        versions = options['versions'] or (sorted(available, reverse=True) if everything else [])
        if any(v not in available for v in versions):
            raise CommandError('Requested version has no locally loaded PG10+ or development manual')
        for version in versions:
            self.stdout.write('PostgreSQL {}'.format(int(version)))
            report = rebuild_version(version, force=options['force'], dry_run=options['dry_run'], progress=self.stdout.write)
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
        if options['extensions'] or everything:
            self.stdout.write('Extension catalogue')
            self.stdout.write(json.dumps(rebuild_extensions(dry_run=options['dry_run']), ensure_ascii=False))
        if options['errcodes'] or everything:
            self.stdout.write(json.dumps(rebuild_errcodes(dry_run=options['dry_run']), ensure_ascii=False))
        if options['catalog'] or everything:
            self.stdout.write(json.dumps(rebuild_catalog(dry_run=options['dry_run']), ensure_ascii=False))
        if options['guc'] or everything:
            self.stdout.write(json.dumps(rebuild_guc(dry_run=options['dry_run']), ensure_ascii=False))
        if not options['dry_run']:
            with connection.cursor() as cursor:
                cursor.execute('ANALYZE search_searchentry')
