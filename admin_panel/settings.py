import os
import sys
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

# Environment-based configuration
DEBUG = config('DEBUG', default=True, cast=bool)
SECRET_KEY = config('SECRET_KEY', default='admin-dev-key-only-for-local')
ENVIRONMENT = config('ENVIRONMENT', default='local')

# Allowed hosts
if ENVIRONMENT == 'local':
    ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '0.0.0.0', '*']
else:
    ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='admin.renditefuchs.de', cast=lambda v: [s.strip() for s in v.split(',')])

# HTTPS Configuration for production
if ENVIRONMENT == 'production':
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='https://admin.renditefuchs.de', cast=lambda v: [s.strip() for s in v.split(',')])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'monitoring',
    'business',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'admin_panel.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'admin_panel.wsgi.application'

# Database Configuration - Connect to RenditeFuchs Databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'admin_db.sqlite3',
    }
}

# Multi-Database Setup für Server (gleiche DBs wie Main)
if ENVIRONMENT in ['test', 'live']:
    import dj_database_url
    
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'admin_db.sqlite3',
        },
        'main_db': dj_database_url.parse(config(
            'DATABASE_URL_TEST' if ENVIRONMENT == 'test' else 'DATABASE_URL_LIVE'
        )),
        'shared_db': dj_database_url.parse(config('DATABASE_URL_SHARED')),
        'test_db': dj_database_url.parse(config('DATABASE_URL_TEST')),
        'live_db': dj_database_url.parse(config('DATABASE_URL_LIVE')),
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'de-de'
TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Admin Dashboard Settings
ADMIN_DASHBOARD_TITLE = 'RenditeFuchs Admin Dashboard'
ADMIN_SITE_HEADER = 'RenditeFuchs Platform Administration'

# Monitoring Settings - Test vs Live Environment Support
MONITORED_PLATFORMS = {
    # Test Environment Platforms
    'main_test': {
        'name': 'Main Website (Test)',
        'url': 'http://127.0.0.1:8001' if ENVIRONMENT == 'local' else 'https://test.renditefuchs.de',
        'health_endpoint': '/health/',
        'environment': 'test',
        'color': 'warning',  # Orange for test
    },
    'focus_test': {
        'name': 'Focus App (Test)',
        'url': 'http://127.0.0.1:8002' if ENVIRONMENT == 'local' else 'https://focus.test.renditefuchs.de',
        'health_endpoint': '/health/',
        'environment': 'test',
        'color': 'warning',
    },
    'blog_test': {
        'name': 'Blog (Test)',
        'url': 'http://127.0.0.1:8004' if ENVIRONMENT == 'local' else 'https://blog.test.renditefuchs.de',
        'health_endpoint': '/health/',
        'environment': 'test',
        'color': 'warning',
    },
    'academy_test': {
        'name': 'Academy (Test)',
        'url': 'http://127.0.0.1:8005' if ENVIRONMENT == 'local' else 'https://academy.test.renditefuchs.de',
        'health_endpoint': '/health/',
        'environment': 'test',
        'color': 'warning',
    },
    
    # Live Environment Platforms
    'main_live': {
        'name': 'Main Website (Live)',
        'url': 'https://renditefuchs.de',
        'health_endpoint': '/health/',
        'environment': 'live',
        'color': 'success',  # Green for live
    },
    'focus_live': {
        'name': 'Focus App (Live)',
        'url': 'https://focus.renditefuchs.de',
        'health_endpoint': '/health/',
        'environment': 'live',
        'color': 'success',
    },
    'blog_live': {
        'name': 'Blog (Live)',
        'url': 'https://blog.renditefuchs.de',
        'health_endpoint': '/health/',
        'environment': 'live',
        'color': 'success',
    },
    'academy_live': {
        'name': 'Academy (Live)',
        'url': 'https://academy.renditefuchs.de',
        'health_endpoint': '/health/',
        'environment': 'live',
        'color': 'success',
    },
}

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs/admin_dashboard.log',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'monitoring': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Ensure logs directory exists
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

# Environment status
if ENVIRONMENT == 'local':
    print(f"🔧 ADMIN DASHBOARD - LOCAL DEVELOPMENT MODE")
else:
    print(f"🚀 ADMIN DASHBOARD - {ENVIRONMENT.upper()} ENVIRONMENT")
print(f"🎛️  Admin Panel: Port 8003")
print(f"📊 Monitoring: {len(MONITORED_PLATFORMS)} Platforms")