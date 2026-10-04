# email tools

## PGSQL.CC production delivery

Account and other system mail is queued in `mailqueue_queuedmail`. The management
command `send_queued_mail` uses Django's `EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, and
`EMAIL_TIMEOUT` settings for these messages. It preserves the stored MIME body
and envelope; failed system messages remain queued. User-generated submissions
continue to use the separate `FRONTEND_SMTP_RELAY` anti-spam relay.

The current account sender is `noreply@pg.center`, using Alibaba Cloud DirectMail
at `smtpdm.aliyun.com:80` with STARTTLS and a 15-second socket timeout. Credentials
belong only in the ignored `pgweb/settings_local.py` (mode `0600`), never in this
repository. `ACCOUNTS_NOREPLY_FROM` and `DEFAULT_FROM_EMAIL` use that sender;
account links use `SITE_ROOT = 'https://pgsql.cc'`.

The service and timer in this directory run the production queue every minute:

```sh
install -m 0644 tools/email/pgsql.cc-mailqueue.service /etc/systemd/system/
install -m 0644 tools/email/pgsql.cc-mailqueue.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pgsql.cc-mailqueue.timer
```

The service excludes IDs **13, 14, 15, 16**: these are the four expired
registration messages inspected on 2026-10-01, retained in the production queue
for separate recovery. Their 72-hour tokens have expired and ID 13 also points
to the historical `pg.center` site. Do not replay them or remove the exclusion
without explicitly resolving these messages. The exclusion only applies to the
named production database; other databases may have unrelated rows with those
IDs. A bare `send_queued_mail` command has no exclusions.

Connection and authentication can be verified without sending a message:

```sh
.venv/bin/python manage.py shell -c 'from django.core.mail.backends.smtp import EmailBackend; c = EmailBackend(); c.open(); print("SMTP authentication OK"); c.close()'
systemctl status pgsql.cc-mailqueue.timer
journalctl -u pgsql.cc-mailqueue.service --since today
```

SMTP authentication and a successful empty queue run do not prove inbox
delivery. Only send an end-to-end test to a recipient explicitly provided for
that purpose. Initial configuration backups are in `tmp/smtp-20261001/` on both
hosts. Stop the timer with `systemctl disable --now pgsql.cc-mailqueue.timer`
before rollback; restore the private configuration and backed-up command, then
restart `pgsql.cc`.

Regression tests use an isolated database and mocked SMTP connections:

```sh
PGWEB_TEST_DB=test_pgweb_mailqueue .venv/bin/python manage.py test pgweb.mailqueue --noinput
```

## Message inspection tools

This directory holds a few trivial email testing tools. They work on emails
that are in the `mailqueue` app, so they first have to be generated (with pgweb
that's typically done by approving news or using the `news_send_email` command),
and then referenced by their id number. They are used to test formats and markups.

## parse_email.py

This tool will simply parse and print the MIME structure of the email in question.

## send_email.py

This tools will take the email and send it out using SMTP/AUTH (hardcoded to always
have STARTTLS) according to the settings in `config.yaml` for end-to-end testing.

Note that emails are *not* removed from the queue when sent this way! This way they
can be sent to multiple addresses for testing.

## config.yaml

Used for both tools to find their database, and for `send_email.py` to know how to
connect to the server. See the `config.yaml.sample` file for example/docs.
