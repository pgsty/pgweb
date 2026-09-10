import json

from django.core.management.base import BaseCommand, CommandError

from pgweb.info.highlights import forget_highlights
from pgweb.info.importer import BatchError, load, preview, upsert


class Command(BaseCommand):
    help = ('Import 博览 batch files (data/info/YYYY-MM-DD.json). Rows are written by key, so '
            'importing the same file twice changes nothing. Reports new / updated / unchanged as JSON.')

    def add_arguments(self, parser):
        parser.add_argument('files', nargs='+', help='Batch files in the tools/info/CURATION.md format')
        parser.add_argument('--hide-missing', action='store_true',
                            help="Set status='hidden' on that day's rows that the file no longer lists")
        parser.add_argument('--check', action='store_true', help='Validate only, write nothing')

    def handle(self, **options):
        batches = []
        for path in options['files']:
            try:
                batches.append((path, *load(path)))
            except BatchError as exc:
                raise CommandError(str(exc))
        totals = {'new': 0, 'updated': 0, 'unchanged': 0, 'hidden': 0}
        for path, day, _origin, rows in batches:
            if options['check']:
                report = preview(rows)
            else:
                report = upsert(rows, day, hide_missing=options['hide_missing'])
            report.update({'file': path, 'date': day.isoformat(), 'items': len(rows)})
            for field in totals:
                totals[field] += report[field]
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
        if not options['check']:
            forget_highlights()
        if len(batches) > 1:
            totals['files'] = len(batches)
            self.stdout.write(json.dumps(totals, ensure_ascii=False, sort_keys=True))
