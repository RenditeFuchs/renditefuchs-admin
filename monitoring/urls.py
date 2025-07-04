from django.urls import path
from . import views
from .server_api import (
    directory_list_api, file_content_api, file_edit_api, 
    file_delete_api, file_upload_api
)
from . import debug_views

app_name = 'monitoring'

urlpatterns = [
    # Dashboard
    path('', views.dashboard_home, name='dashboard'),
    
    # Health Checks
    path('api/health/', views.health_check_api, name='health_api'),
    
    # Errors
    path('errors/', views.errors_list, name='errors_list'),
    path('webhook/error/', views.error_webhook, name='error_webhook'),
    
    # Alerts
    path('alerts/', views.alerts_list, name='alerts_list'),
    
    # Platform Details
    path('platform/<int:platform_id>/', views.platform_detail, name='platform_detail'),
    
    # Settings
    path('settings/', views.settings_view, name='settings'),
    
    # System Status
    path('system-status/', views.system_status_view, name='system_status'),
    
    # User Management  
    path('users/', views.user_management_view, name='user_management'),
    
    # Database Status
    path('database/', views.database_status_view, name='database_status'),
    
    # Server Status
    path('server/', views.server_status_view, name='server_status'),
    
    # Server Files
    path('server-files/', views.server_files_view, name='server_files'),
    
    # API Endpoints
    path('api/error/<int:error_id>/', views.error_detail_api, name='error_detail_api'),
    path('api/error/<int:error_id>/resolve/', views.error_resolve_api, name='error_resolve_api'),
    
    # Server File Management API
    path('api/server/directory/', directory_list_api, name='directory_list_api'),
    path('api/server/file/content/', file_content_api, name='file_content_api'),
    path('api/server/file/edit/', file_edit_api, name='file_edit_api'),
    path('api/server/file/delete/', file_delete_api, name='file_delete_api'),
    path('api/server/file/upload/', file_upload_api, name='file_upload_api'),
    
    # Debug endpoints
    path('debug/config/', debug_views.debug_config, name='debug_config'),
    path('debug/ssh/', debug_views.test_ssh_connection, name='debug_ssh'),
    path('debug/directory/', debug_views.test_directory_listing, name='debug_directory'),
]