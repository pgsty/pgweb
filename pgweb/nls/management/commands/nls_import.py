import json

from django.core.management.base import BaseCommand, CommandError

from pgweb.nls.importer import BundleError, load


class Command(BaseCommand):
    help = ('Import a pgnls message bundle (review-app/manage.py bundle → *.jsonl.gz) into nls_message. '
            'Source fields are refreshed; rows already saved by a reviewer keep their review state.')

    def add_arguments(self, parser):
        parser.add_argument('bundle', help='Path to the .jsonl or .jsonl.gz bundle')
        parser.add_argument('--check', action='store_true', help='Validate and report only, write nothing')

    def handle(self, **options):
        try:
            report = load(options['bundle'], check=options['check'])
        except (BundleError, OSError, ValueError) as exc:
            raise CommandError(str(exc))
        report['file'] = options['bundle']
        report['written'] = not options['check']
        self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
