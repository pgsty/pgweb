import json

from django.core.management.base import BaseCommand, CommandError

from pgweb.wiki import topic_importer


class Command(BaseCommand):
    help = 'Import fixed hook, relopts, role and oid snapshots into their own reference tables.'

    def add_arguments(self, parser):
        parser.add_argument('files', nargs='+')
        parser.add_argument('--check', action='store_true', help='Validate and report without writing')
        parser.add_argument('--prune', action='store_true', help='Remove absent entities in the supplied domains')

    def handle(self, **options):
        try:
            prepared = [topic_importer.load(path) for path in options['files']]
            if len({kind for kind, _ in prepared}) != len(prepared):
                raise ValueError('Supply at most one snapshot per domain')
            # Validate every input before performing any writes.
            from django.db import transaction
            with transaction.atomic():
                for kind, rows in prepared:
                    report = topic_importer.apply(kind, rows, check=options['check'], prune=options['prune'])
                    self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
        except (ValueError, OSError, TypeError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        if not options['check']:
            self.stdout.write('Rebuild search entries: manage.py index_docs --topics')
