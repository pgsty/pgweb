from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate


def do_post_migrate(sender, **kwargs):
    if not settings.RELEASE_AUTO_PROCESS:
        return

    from .migrate import do_migrate
    do_migrate()


class ReleaseAppConfig(AppConfig):
    name = "pgweb.release"

    def ready(self):
        post_migrate.connect(
            do_post_migrate,
            sender=self,
            dispatch_uid='pgweb.release.process_current_release',
        )
