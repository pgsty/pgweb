from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate


def do_post_migrate(sender, **kwargs):
    if not settings.SECURITY_CVE_AUTOLOAD:
        return

    from .loader import load_security_json
    load_security_json()


class SecurityAppConfig(AppConfig):
    name = "pgweb.security"

    def ready(self):
        post_migrate.connect(
            do_post_migrate,
            sender=self,
            dispatch_uid='pgweb.security.load_cve_json',
        )
