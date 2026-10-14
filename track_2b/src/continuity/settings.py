"""On-premise application settings. SQLite is an explicit local-test option."""
import os
from pathlib import Path
from urllib.parse import urlsplit, unquote

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEMO_MODE = os.getenv('DEMO_MODE', '0') == '1'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    raise ImproperlyConfigured('Set DJANGO_SECRET_KEY; make run initializes local demo secrets.')
DEBUG = False
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
INSTALLED_APPS = [
    'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions',
    'django.contrib.staticfiles', 'identity', 'records',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'identity.middleware.AuthenticationLifetimeMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'continuity.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
    ]},
}]
WSGI_APPLICATION = 'continuity.wsgi.application'
if os.getenv('USE_SQLITE', '0') == '1':
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'local.sqlite3'}}
else:
    db = urlsplit(os.getenv('DATABASE_URL', ''))
    if db.scheme not in ('postgres', 'postgresql') or not db.hostname or not db.path.strip('/'):
        raise ImproperlyConfigured('DATABASE_URL must name a PostgreSQL database.')
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql', 'NAME': unquote(db.path.strip('/')),
        'USER': unquote(db.username or ''), 'PASSWORD': unquote(db.password or ''),
        'HOST': db.hostname, 'PORT': db.port or 5432, 'CONN_MAX_AGE': 0,
        'OPTIONS': {'connect_timeout': 5},
    }}
    if os.getenv('DATABASE_TEST_NAME'):
        DATABASES['default']['TEST'] = {'NAME': os.environ['DATABASE_TEST_NAME']}
AUTH_USER_MODEL = 'identity.User'
AUTHENTICATION_BACKENDS = ['identity.backends.OIDCSessionBackend']
LOGIN_URL = '/'
APP_BASE_URL = os.getenv('APP_BASE_URL', 'http://localhost:8000').rstrip('/')
OIDC_ISSUER = os.getenv('OIDC_ISSUER', 'http://localhost:8081/realms/continuity').rstrip('/')
OIDC_INTERNAL_ISSUER = os.getenv('OIDC_INTERNAL_ISSUER', OIDC_ISSUER).rstrip('/')
OIDC_CLIENT_ID = os.getenv('OIDC_CLIENT_ID', 'continuity-web')
OIDC_CLIENT_SECRET = os.getenv('OIDC_CLIENT_SECRET', '')
if not DEMO_MODE and not OIDC_CLIENT_SECRET:
    raise ImproperlyConfigured('Set the confidential OIDC client secret.')
if not DEMO_MODE and any(urlsplit(url).scheme != 'https' for url in (APP_BASE_URL, OIDC_ISSUER, OIDC_INTERNAL_ISSUER)):
    raise ImproperlyConfigured('HTTPS is required outside the local demo.')
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEMO_MODE
CSRF_COOKIE_SECURE = not DEMO_MODE
CSRF_TRUSTED_ORIGINS = [APP_BASE_URL]
SESSION_COOKIE_AGE = 900
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SECURE_SSL_REDIRECT = not DEMO_MODE
SECURE_HSTS_SECONDS = 0 if DEMO_MODE else 31536000
SECURE_CONTENT_TYPE_NOSNIFF = True
# Preserve the origin on local forms for CSRF; send no referrer to other sites.
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
USE_TZ = True
TIME_ZONE = 'UTC'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# Small explicit hospital searches only; use a self-hosted endpoint for sovereign operation.
FACILITY_SEARCH_URL = os.getenv('FACILITY_SEARCH_URL','https://nominatim.openstreetmap.org')
ASSISTANT_SEARCH_SOURCE_LIMIT = int(os.getenv('ASSISTANT_SEARCH_SOURCE_LIMIT','30'))
if not 1 <= ASSISTANT_SEARCH_SOURCE_LIMIT <= 30:
    raise ImproperlyConfigured('ASSISTANT_SEARCH_SOURCE_LIMIT must be between 1 and 30.')
PRIVATE_STORAGE_ROOT = Path(os.getenv('PRIVATE_STORAGE_ROOT', str(BASE_DIR.parent / '.runtime' / 'documents')))
DATA_UPLOAD_MAX_MEMORY_SIZE = 262144
FILE_UPLOAD_MAX_MEMORY_SIZE = 1048576
FILE_UPLOAD_HANDLERS = ['records.storage.LimitedUploadHandler', 'django.core.files.uploadhandler.MemoryFileUploadHandler', 'django.core.files.uploadhandler.TemporaryFileUploadHandler']
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'security_console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'authlib': {'level': 'WARNING'}, 'django.server': {'level': 'WARNING'},
        # Django's CSRF reasons contain no submitted token/password values.
        'django.security.csrf': {
            'handlers': ['security_console'], 'level': 'WARNING', 'propagate': False,
        },
    },
}
