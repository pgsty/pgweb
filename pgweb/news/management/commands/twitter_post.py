#!/usr/bin/env python3
#
# Backward-compatible wrapper for the renamed social_post command.
#

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Backward-compatible alias for social_post'

    def handle(self, *args, **options):
        call_command('social_post')
