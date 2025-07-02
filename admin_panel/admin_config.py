"""
Custom Django Admin Configuration für RenditeFuchs Admin Dashboard
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

# Custom Admin Site Configuration
admin.site.site_header = 'RenditeFuchs Admin Dashboard'
admin.site.site_title = 'RenditeFuchs Admin'
admin.site.index_title = 'Platform Administration'

# Customize User Admin
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('-date_joined',)
    
    fieldsets = UserAdmin.fieldsets + (
        ('Admin Dashboard Permissions', {
            'fields': ('is_staff', 'is_superuser'),
            'description': 'Berechtigungen für das RenditeFuchs Admin Dashboard'
        }),
    )

# Re-register User with custom admin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)