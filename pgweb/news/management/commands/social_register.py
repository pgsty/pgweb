#!/usr/bin/env python3
#
# Script to register with social providers
#

from django.conf import settings
from django.core.management.base import BaseCommand

from pgweb.util.socialposter import get_all_providers


allproviders, allprovidernames = get_all_providers(settings, True)


class Command(BaseCommand):
    help = 'Register with social providers'

    def add_arguments(self, parser):
        parser.add_argument('provider', choices=allprovidernames)

    def handle(self, *args, **options):
        for provider in allproviders:
            if provider.name == options['provider']:
                registered = provider.register('pgweb')
                if registered:
                    print(registered)
                else:
                    print("{} already registered.".format(provider.name))
                break
        else:
            print("Provider {} not found.".format(options['provider']))
