"""Import independently curated Chinese biographies without changing source data."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from pgweb.hacker.models import HackerProfile


class Command(BaseCommand):
    help = 'Import a complete set of Chinese developer biographies; source snapshots remain unchanged.'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--check', action='store_true')

    @transaction.atomic
    def handle(self, **options):
        try:
            payload = json.loads(Path(options['path']).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        if not isinstance(payload, dict) or payload.get('format') != 1 or payload.get('language') != 'zh':
            raise CommandError('Expected format=1 and language=zh')
        rows = payload.get('profiles')
        if not isinstance(rows, list) or not rows:
            raise CommandError('Expected a nonempty profiles list')
        profiles = {p.source_id: p for p in HackerProfile.objects.only('source_id', 'name', 'texts')}
        fields = {'bio', 'position', 'organization', 'location', 'review_note'}
        seen, changed = set(), []
        for row in rows:
            if not isinstance(row, dict) or set(row) != fields | {'source_id', 'name'} or not all(isinstance(v, str) for v in row.values()):
                raise CommandError('Invalid translated profile fields')
            source_id = row['source_id']
            profile = profiles.get(source_id)
            if source_id in seen or not profile or profile.name != row['name']:
                raise CommandError('Duplicate, unknown or mismatched profile: ' + source_id)
            seen.add(source_id)
            zh = {key: row[key] for key in fields}
            if profile.texts.get('zh') != zh:
                profile.texts = dict(profile.texts, zh=zh)
                profile.imported_at = timezone.now()
                changed.append(profile)
        if seen != set(profiles):
            raise CommandError('Translations must cover every stored profile')
        if not options['check']:
            HackerProfile.objects.bulk_update(changed, ['texts', 'imported_at'])
        self.stdout.write(json.dumps({'profiles': len(rows), 'updated': len(changed),
                                     'unchanged': len(rows) - len(changed), 'check': options['check']}))
