import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

# Load environment variables from .env
load_dotenv()

# ----------------------
# BASE DIR
# ----------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ----------------------
# SECRET KEY
# ----------------------
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-your-secret-key-here')

# ----------------------
# DEBUG
# ----------------------
DEBUG = os.getenv('DEBUG', 'True') == 'True'

# ----------------------
# ALLOWED HOSTS
# ----------------------
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
if not DEBUG:
    ALLOWED_HOSTS = ['.onrender.com']

# ----------------------
# STATIC FILES
# ----------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ----------------------
# MEDIA FILES
# ----------------------
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ----------------------
# APPLICATIONS
# ----------------------
INSTALLED_APPS = [
    # Django default apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    'django.contrib.sites',

    # Third-party apps
    'rest_framework',
    'corsheaders',
    'channels',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'widget_tweaks',

    # Local apps
    'apps.users',
    'apps.consultations',
    'apps.agents',
    'apps.blackboard',
    'apps.rag',
]

# ----------------------
# MIDDLEWARE
# ----------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

# ----------------------
# URLS
# ----------------------
ROOT_URLCONF = 'core.urls'
WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'

# ----------------------
# DATABASE CONFIG
# ----------------------
# Local SQLite fallback, Postgres for production via DATABASE_URL
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600
    )
}

# ----------------------
# SECURITY & SSL (Render)
# ----------------------
if not DEBUG:
    CSRF_TRUSTED_ORIGINS = ["https://*.onrender.com"]
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True

# ----------------------
# REDIS / CACHE / CHANNELS
# ----------------------
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
    }
}

try:
    import channels_redis  # noqa: F401
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [REDIS_URL]},
        }
    }
except ImportError:
    CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}

# ----------------------
# CELERY
# ----------------------
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

# ----------------------
# REST Framework
# ----------------------
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20
}

# ----------------------
# CORS
# ----------------------
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8000',
]

# ----------------------
# AUTHENTICATION
# ----------------------
AUTH_USER_MODEL = 'users.User'
LOGIN_URL = 'account_login'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'
SITE_ID = 1

# ----------------------
# EMAIL
# ----------------------
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@mediai.local')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False') == 'True'

# Notification inboxes
LAB_INBOX_EMAIL = os.getenv('LAB_INBOX_EMAIL', '')
PHARMACY_INBOX_EMAIL = os.getenv('PHARMACY_INBOX_EMAIL', '')

# ----------------------
# LLM / AI CONFIG
# ----------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.2"))
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1024"))

if not OPENAI_API_KEY and not os.getenv("DEEPSEEK_API_KEY", "") and not GROQ_API_KEY:
    print("⚠️ WARNING: No LLM API key set. Set GROQ_API_KEY, DEEPSEEK_API_KEY, or OPENAI_API_KEY.")

# ----------------------
# AGENT SETTINGS
# ----------------------
AGENT_CHECK_INTERVAL = 5  # seconds
AGENT_MAX_RETRIES = 3
LAB_RESULTS_MODE = os.getenv('LAB_RESULTS_MODE', 'mock').lower()

# ----------------------
# LOGGING
# ----------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'simple': {'format': '[{levelname}] {name}: {message}', 'style': '{'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'}},
    'loggers': {
        'apps.agents': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'apps.blackboard': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'apps.consultations': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'django': {'handlers': ['console'], 'level': 'WARNING', 'propagate': True},
    },
}

# ----------------------
# DEFAULT PRIMARY KEY
# ----------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'