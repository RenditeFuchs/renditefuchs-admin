from django.apps import AppConfig


class AdminPanelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'admin_panel'
    verbose_name = 'RenditeFuchs Admin Panel'
    
    def ready(self):
        # Import admin configuration
        from . import admin_config