"""
WSGI config for admin_panel project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import sys
from django.core.wsgi import get_wsgi_application

# Environment-specific settings detection
if os.path.exists('/var/www/'):
    # Production environment (server)
    settings_module = 'admin-settings-production'
else:
    # Local development environment
    settings_module = 'admin-settings-local'

# Add parent directory to Python path to find settings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', settings_module)

application = get_wsgi_application()
