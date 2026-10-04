import datetime
import smtplib
import ssl
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from .models import QueuedMail


@override_settings(
    EMAIL_HOST='smtp.example.test', EMAIL_PORT=80,
    EMAIL_HOST_USER='noreply@example.test', EMAIL_HOST_PASSWORD='test-password',
    EMAIL_USE_TLS=True, EMAIL_USE_SSL=False, EMAIL_TIMEOUT=15,
    FRONTEND_SMTP_RELAY='frontend.example.test',
)
class SendQueuedMailTests(TestCase):
    def setUp(self):
        self.smtp_patch = patch('smtplib.SMTP')
        self.smtp_class = self.smtp_patch.start()
        self.addCleanup(self.smtp_patch.stop)
        self.smtp = self.smtp_class.return_value
        self.mail = QueuedMail.objects.create(
            sender='noreply@example.test', receiver='reader@example.test',
            fullmsg='Subject: PGSQL.CC\n\n中文注册邮件',
            sendat=datetime.datetime.now(),
        )

    def test_authenticated_tls_delivery_preserves_message(self):
        call_command('send_queued_mail')
        args, kwargs = self.smtp_class.call_args
        self.assertEqual(args, ('smtp.example.test', 80))
        self.assertEqual(kwargs['timeout'], 15)
        context = self.smtp.starttls.call_args.kwargs['context']
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.smtp.login.assert_called_once_with('noreply@example.test', 'test-password')
        self.smtp.sendmail.assert_called_once_with(
            self.mail.sender, self.mail.receiver, self.mail.fullmsg.encode('utf-8'),
        )
        self.smtp.close.assert_called_once()
        self.assertFalse(QueuedMail.objects.exists())

    def test_excluded_and_future_messages_are_not_sent(self):
        QueuedMail.objects.create(
            sender=self.mail.sender, receiver=self.mail.receiver, fullmsg='future',
            sendat=datetime.datetime.now() + datetime.timedelta(days=1),
        )
        call_command('send_queued_mail', exclude_ids=[self.mail.pk])
        self.smtp_class.assert_not_called()
        self.assertEqual(QueuedMail.objects.count(), 2)

    def test_authentication_failure_keeps_mail(self):
        self.smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b'Authentication failed')
        with self.assertRaises(smtplib.SMTPAuthenticationError):
            call_command('send_queued_mail')
        self.smtp.sendmail.assert_not_called()
        self.assertTrue(QueuedMail.objects.filter(pk=self.mail.pk).exists())

    def test_tls_failure_never_authenticates_or_sends(self):
        self.smtp.starttls.side_effect = ssl.SSLCertVerificationError('certificate rejected')
        with self.assertRaises(ssl.SSLCertVerificationError):
            call_command('send_queued_mail')
        self.smtp.login.assert_not_called()
        self.smtp.sendmail.assert_not_called()
        self.assertTrue(QueuedMail.objects.filter(pk=self.mail.pk).exists())

    def test_rejected_account_mail_stays_queued(self):
        self.smtp.sendmail.side_effect = smtplib.SMTPDataError(554, b'Rejected')
        with self.assertRaises(smtplib.SMTPDataError):
            call_command('send_queued_mail')
        self.smtp.close.assert_called_once()
        self.assertTrue(QueuedMail.objects.filter(pk=self.mail.pk).exists())

    def test_user_generated_mail_keeps_separate_relay_without_credentials(self):
        self.mail.usergenerated = True
        self.mail.save(update_fields=['usergenerated'])
        call_command('send_queued_mail')
        self.smtp_class.assert_called_once_with('frontend.example.test', timeout=15)
        self.smtp.login.assert_not_called()
        self.smtp.starttls.assert_not_called()
        self.assertFalse(QueuedMail.objects.exists())

    def test_rejected_user_generated_mail_preserves_antispam_behavior(self):
        self.mail.usergenerated = True
        self.mail.save(update_fields=['usergenerated'])
        self.smtp.sendmail.side_effect = smtplib.SMTPDataError(554, b'Spam rejected')
        call_command('send_queued_mail')
        self.smtp.close.assert_called_once()
        self.assertFalse(QueuedMail.objects.exists())
