import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from pgweb.core.models import Version
from pgweb.search.indexer import rebuild_version


class Command(BaseCommand):
    help = 'Build the PostgreSQL manual search index from local docs rows. No external content is fetched.'

    def add_arguments(self, parser):
        parser.add_argument('--versions', nargs='+', type=int, help='Major versions (default: all loaded PG14+ manuals)')
        parser.add_argument('--force', action='store_true', help='Rebuild unchanged pages too')
        parser.add_argument('--dry-run', action='store_true', help='Extract and report without writing')

    def handle(self, **options):
        available = list(Version.objects.filter(tree__gte=14, docpage__isnull=False).values_list('tree', flat=True).distinct())
        versions = options['versions'] or sorted(available, reverse=True)
        if any(v not in available for v in versions):
            raise CommandError('Requested version has no locally loaded PG14+ manual')
        for version in versions:
            self.stdout.write('PostgreSQL {}'.format(int(version)))
            report = rebuild_version(version, force=options['force'], dry_run=options['dry_run'], progress=self.stdout.write)
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
        if not options['dry_run']:
            with connection.cursor() as cursor:
                cursor.execute('ANALYZE search_searchentry')
