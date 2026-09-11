import json
import os

from django.core.management.base import BaseCommand, CommandError

from pgweb.nls.service import export


class Command(BaseCommand):
    help = ('Write the review state as pgnls-human-review-v1 JSON, the format review-app/manage.py import '
            'and results.py accept. Refuses to overwrite an existing file.')

    def add_arguments(self, parser):
        parser.add_argument('path', help='Output file; must not exist yet')

    def handle(self, **options):
        path = options['path']
        if os.path.exists(path):
            raise CommandError('Refusing to overwrite ' + path)
        payload = export()
        with open(path, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        self.stdout.write(json.dumps({'file': path, 'saved': len(payload['saved_state']),
                                      'workbook_sha256': payload['workbook_sha256']}, ensure_ascii=False))
