import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from pgweb.info.importer import reindex
from pgweb.info.models import InfoItem


class Command(BaseCommand):
    help = 'Rebuild the 博览 search vectors from the stored text. Nothing external is fetched.'

    def add_arguments(self, parser):
        parser.add_argument('--rebuild', action='store_true', help='Recompute every search_vector')
        parser.add_argument('--date', help='Limit the rebuild to one day (YYYY-MM-DD)')

    def handle(self, **options):
        if not options['rebuild']:
            raise CommandError('Nothing to do: pass --rebuild to recompute the search vectors')
        rows = InfoItem.objects.all()
        if options['date']:
            rows = rows.filter(date=options['date'])
        count = reindex(rows)
        with connection.cursor() as cursor:
            cursor.execute('ANALYZE info_item')
        self.stdout.write(json.dumps({'indexed': count}, ensure_ascii=False, sort_keys=True))
