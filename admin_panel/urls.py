"""
URL configuration for admin_panel project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from .views import custom_login, dashboard_redirect, custom_logout

# Disable Django admin login redirect
admin.site.login = custom_login

urlpatterns = [
    path('', dashboard_redirect, name='root'),
    path('login/', custom_login, name='login'),
    path('logout/', custom_logout, name='logout'),
    path('django-admin/', admin.site.urls),  # Keep Django admin as fallback
    path('monitoring/', include('monitoring.urls')),
    path('business/', include('business.urls')),
]
