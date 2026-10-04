# Script to send off all queued email.
#
# This script is intended to be run frequently from cron. We queue things
# up in the db so that they get automatically rolled back as necessary,
# but once we reach this point we're just going to send all of them one
# by one.
#
from django.core.management.base import BaseCommand, CommandError
from django.core.mail.backends.smtp import EmailBackend
from django.db import connection
from django.conf import settings

import datetime
import smtplib

from pgweb.mailqueue.models import QueuedMail


class Command(BaseCommand):
    help = 'Send queued mail'

    def add_arguments(self, parser):
        parser.add_argument('--exclude-ids', nargs='+', type=int, default=[],
                            help='Keep these messages queued without sending them')

    def handle(self, *args, **options):
        # Grab advisory lock, if available. Lock id is just a random number
        # since we only need to interlock against ourselves. The lock is
        # automatically released when we're done.
        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(72181372)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing send_queued_mail process stuck?")

        messages = QueuedMail.objects.filter(sendat__lte=datetime.datetime.now()).exclude(pk__in=options['exclude_ids'])
        for m in messages:
            # Yes, we do a new connection for each run. Just because we can.
            # If it fails we'll throw an exception and just come back on the
            # next cron job. And local delivery should never fail...
            if m.usergenerated:
                # User generated email gets relayed directly over a frontend
                smtp = smtplib.SMTP(settings.FRONTEND_SMTP_RELAY, timeout=settings.EMAIL_TIMEOUT)
            else:
                # Use Django's SMTP settings for TLS and authentication, while
                # preserving the MIME message and envelope stored in the queue.
                backend = EmailBackend()
                try:
                    backend.open()
                except Exception:
                    backend.close()
                    raise
                smtp = backend.connection
            try:
                smtp.sendmail(m.sender, m.receiver, m.fullmsg.encode('utf-8'))
            except (smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError):
                # If this was user generated, this indicates the antispam
                # kicking in, so we just ignore it. If it's anything else,
                # we want to let the exception through.
                if not m.usergenerated:
                    raise
            finally:
                smtp.close()

            m.delete()
