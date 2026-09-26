import gzip
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from pgweb.docs.compare_store import import_snapshot, restore_database_archive


class Command(BaseCommand):
    help = 'Validate or atomically import comparison snapshots into this database'

    def add_arguments(self, parser):
        parser.add_argument('input', type=Path)
        parser.add_argument('--kind', choices=('releases', 'security'), help='Inferred from the snapshot when omitted')
        parser.add_argument('--language', choices=('zh', 'en'), default=getattr(settings, 'COMPARE_LANGUAGE', 'zh'))
        parser.add_argument('--database', default='default')
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--write', action='store_true', help='Commit the validated import')
        mode.add_argument('--check', action='store_true', help='Validate using a rolled-back transaction (default)')
        parser.add_argument('--complete', action='store_true', help='Input is the intended complete active source set')
        parser.add_argument('--prune', action='store_true', help='Retire missing occurrences; requires --complete')

    def handle(self, *args, **options):
        try:
            opener = gzip.open if str(options['input']).endswith('.gz') else open
            with opener(options['input'], 'rt', encoding='utf-8') as stream:
                source = json.load(stream)
            if 'storage_format' in source:
                counts = restore_database_archive(source, check=not options['write'], using=options['database'])
            else:
                kind = options['kind'] or ('security' if 'cves' in source else 'releases')
                counts = import_snapshot(source, kind=kind, language=options['language'],
                                         complete=options['complete'], prune=options['prune'],
                                         check=not options['write'], using=options['database'])
        except (ValueError, OSError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(('Imported ' if options['write'] else 'Validated (rolled back) ') +
                                             json.dumps(counts, ensure_ascii=False, sort_keys=True)))
