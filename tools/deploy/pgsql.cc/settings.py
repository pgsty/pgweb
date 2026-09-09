"""Overrides for /data/app/pgsql.cc/pgweb/settings_local.py.

Copy the existing production configuration first to retain its database,
search connection, secret key and mail settings, then append these overrides.
"""

DEBUG = False
SITE_ROOT = 'https://pgsql.cc'
ALLOWED_HOSTS = ['pgsql.cc', 'localhost', '127.0.0.1']
CSRF_TRUSTED_ORIGINS = ['https://pgsql.cc']
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_REAL_SCHEME', 'https')
STATIC_ROOT = '/data/app/pgsql.cc/static_collected'
STATIC_CHECKOUT = '/data/app/pgsql.cc/static'
FTP_PICKLE = '/data/app/pgsql.cc/data/ftpsite.pickle'
YUM_JSON = '/data/app/pgsql.cc/data/yum.json'
