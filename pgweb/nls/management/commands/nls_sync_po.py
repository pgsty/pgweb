import json

from django.core.management.base import BaseCommand, CommandError

from pgweb.nls import po_sync


class Command(BaseCommand):
    help = 'Export a full PO reconciliation snapshot, or check/apply a fixed snapshot to existing messages.'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Self-contained .json or .json.gz snapshot')
        parser.add_argument('--source-root', help='pgnls checkout; export only, never write the database')
        parser.add_argument('--write', action='store_true', help='Apply a reviewed snapshot; default is read-only comparison')
        parser.add_argument('--report', help='Write detailed before/after differences as JSON')

    def handle(self, **options):
        try:
            if options['source_root']:
                if options['write'] or options['report']:
                    raise ValueError('--source-root exports only; compare the exported snapshot separately')
                result = po_sync.export(options['source_root'], options['path'])
            else:
                result = po_sync.apply(po_sync.read(options['path']), write=options['write'], report_path=options['report'])
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
