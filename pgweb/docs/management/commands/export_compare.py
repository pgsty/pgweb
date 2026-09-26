import gzip
import json
import os
from pathlib import Path
import tempfile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from pgweb.docs.compare_store import export_database_archive, export_database_snapshot


class Command(BaseCommand):
    help = 'Export active source JSON, or a complete comparison database archive'

    def add_arguments(self, parser):
        parser.add_argument('output', type=Path)
        parser.add_argument('--kind', choices=('releases', 'security'), default='releases')
        parser.add_argument('--language', choices=('zh', 'en'), default=getattr(settings, 'COMPARE_LANGUAGE', 'zh'))
        parser.add_argument('--database', default='default')
        parser.add_argument('--archive', action='store_true', help='Include IDs, retired rows and all revisions from four tables')

    def handle(self, *args, **options):
        destination = options['output']
        temporary = None
        try:
            data = (export_database_archive(options['database']) if options['archive'] else
                    export_database_snapshot(options['kind'], options['language'], options['database']))
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix='.compare-export-', dir=destination.parent)
            raw = (json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
            with os.fdopen(descriptor, 'wb') as stream:
                if str(destination).endswith('.gz'):
                    with gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0) as compressed:
                        compressed.write(raw)
                else:
                    stream.write(raw)
            os.chmod(temporary, 0o644)
            os.replace(temporary, destination)
        except (ValueError, OSError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        self.stdout.write(self.style.SUCCESS('Exported database comparison data to ' + str(destination)))
