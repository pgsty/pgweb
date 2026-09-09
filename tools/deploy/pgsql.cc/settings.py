"""Domain settings to merge into the existing pgweb/settings_local.py."""

SITE_ROOT = 'https://pgsql.cc'
ALLOWED_HOSTS = ['pgsql.cc', 'www.pgsql.cc', 'localhost', '127.0.0.1']
CSRF_TRUSTED_ORIGINS = ['https://pgsql.cc', 'https://www.pgsql.cc']
SESSION_COOKIE_DOMAIN = 'pgsql.cc'
CSRF_COOKIE_DOMAIN = 'pgsql.cc'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
