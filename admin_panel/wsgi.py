"""
WSGI config for admin_panel project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Automatische Settings-Auswahl basierend auf Environment
if os.path.exists('/var/www/admin'):
    # Production server environment
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'admin_panel.settings_production')
else:
    # Local development environment
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'admin_panel.settings_local')

application = get_wsgi_application()
