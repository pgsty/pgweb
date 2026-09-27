"""Export stable message IDs for source-side bundle generation."""
import gzip
import json

from django.core.management.base import BaseCommand

from pgweb.nls.importer import IDENTITY_FIELDS
from pgweb.nls.models import Message


class Command(BaseCommand):
    help = 'Export existing natural message identities and IDs without review state.'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, **options):
        rows = list(Message.objects.order_by('id').values('id', *IDENTITY_FIELDS))
        opener = gzip.open if options['path'].endswith('.gz') else open
        with opener(options['path'], 'xt', encoding='utf-8') as stream:
            json.dump({'schema': 'pgnls-message-identities-v1', 'messages': rows}, stream,
                      ensure_ascii=False, separators=(',', ':'))
        self.stdout.write('{} identities exported'.format(len(rows)))
