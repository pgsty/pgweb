import json

from django.core.management.base import BaseCommand, CommandError

from pgweb.hacker.importer import SnapshotError, load, preview, upsert


class Command(BaseCommand):
    help = 'Import one complete developer snapshot; unchanged profiles and missing records are preserved.'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Snapshot JSON or JSON.gz (avatar paths are relative to this file)')
        parser.add_argument('--check', action='store_true', help='Validate all records and avatars, write nothing')

    def handle(self, **options):
        try:
            rows = load(options['path'])
            report = preview(rows) if options['check'] else upsert(rows)
        except SnapshotError as exc:
            raise CommandError(str(exc)) from exc
        report.update({'profiles': len(rows), 'avatars': sum(bool(row['avatar']) for row in rows),
                       'check': options['check']})
        self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
