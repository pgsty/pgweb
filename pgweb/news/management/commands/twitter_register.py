#!/usr/bin/env python3
#
# Backward-compatible wrapper for the removed twitter_register command.
#

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Compatibility shim for the removed twitter_register command'

    def handle(self, *args, **options):
        raise CommandError(
            "Twitter support has been removed. Use 'manage.py social_register mastodon' "
            "or 'manage.py social_register bluesky' instead."
        )
