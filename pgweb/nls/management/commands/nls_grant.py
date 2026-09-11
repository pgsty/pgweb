from django.contrib.auth.models import Permission, User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Grant (or --revoke) the nls.review permission that lets a user save on /nls/. Same as the admin checkbox.'

    def add_arguments(self, parser):
        parser.add_argument('usernames', nargs='+')
        parser.add_argument('--revoke', action='store_true')

    def handle(self, **options):
        permission = Permission.objects.get(content_type__app_label='nls', codename='review')
        for name in options['usernames']:
            try:
                user = User.objects.get(username=name.lower())
            except User.DoesNotExist:
                raise CommandError('No such user: ' + name)
            if options['revoke']:
                user.user_permissions.remove(permission)
            else:
                user.user_permissions.add(permission)
            self.stdout.write('{} {} nls.review'.format(user.username, 'lost' if options['revoke'] else 'has'))
