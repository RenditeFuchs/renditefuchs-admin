"""
Production Settings für RenditeFuchs Admin Dashboard
Sichere Einstellungen für den Server
"""

from .settings_base import *
from decouple import config
import dj_database_url

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

# Production allowed hosts
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])

# Production PostgreSQL Database
DATABASES = {
    'default': dj_database_url.parse(config('DATABASE_URL')),
}

# Production HTTPS Security Settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', cast=lambda v: [s.strip() for s in v.split(',')])

# Production email settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='mail.infomaniak.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='admin@renditefuchs.de')

# Production environment
ENVIRONMENT = 'production'

# Monitoring Settings für Production - Test und Live Umgebungen
MONITORED_PLATFORMS = {
    # Test Environment Platforms
    'main_test': {
        'name': 'Main Website (Test)',
        'url': 'https://test.renditefuchs.de',
        'health_endpoint': '/health/',
        'environment': 'test',
        'color': 'warning',  # Orange for test
    },
    'focus_test': {
        'name': 'Focus App (Test)',
        'url': 'https://focus.test.renditefuchs.de',
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
    'admin_dashboard': {
        'name': 'Admin Dashboard',
        'url': 'https://admin.renditefuchs.de',
        'health_endpoint': '/health/',
        'environment': 'production',
        'color': 'primary',  # Blue for admin
    },
}

# Production logging
LOGGING['handlers']['file']['filename'] = '/var/log/renditefuchs/admin-dashboard.log'
LOGGING['root']['level'] = config('LOG_LEVEL', default='INFO')

# Additional production security
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'

print("🚀 ADMIN DASHBOARD - PRODUCTION ENVIRONMENT")
print("🎛️  Admin Panel: Port 8004")
print("📊 Monitoring: 8 Platforms")