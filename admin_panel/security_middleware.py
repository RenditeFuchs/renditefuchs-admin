"""
Security Middleware für RENDITEFUCHS Admin Dashboard
Zusätzliche Sicherheitsmaßnahmen für Production Environment
"""

import logging
import time
from django.http import HttpResponseForbidden
from django.core.cache import cache
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
import re

logger = logging.getLogger('security')


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Fügt zusätzliche Security Headers hinzu
    """
    
    def process_response(self, request, response):
        # Security Headers für alle Responses
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Cross-Origin-Opener-Policy'] = 'same-origin'
        response['Cross-Origin-Embedder-Policy'] = 'require-corp'
        
        # Permissions Policy
        response['Permissions-Policy'] = (
            'geolocation=(), '
            'microphone=(), '
            'camera=(), '
            'payment=(), '
            'usb=(), '
            'magnetometer=(), '
            'accelerometer=(), '
            'gyroscope=()'
        )
        
        # Server Header entfernen
        if 'Server' in response:
            del response['Server']
            
        return response


class RateLimitMiddleware(MiddlewareMixin):
    """
    Rate Limiting für Login-Versuche und API-Calls
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.login_url = reverse('admin:login')
        
    def __call__(self, request):
        # Rate Limiting für Login-Versuche
        if request.path == self.login_url and request.method == 'POST':
            client_ip = self.get_client_ip(request)
            
            # Überprüfe Login-Versuche
            login_attempts = cache.get(f'login_attempts_{client_ip}', 0)
            
            if login_attempts >= getattr(settings, 'RATE_LIMIT_LOGIN_ATTEMPTS', 5):
                logger.warning(f'Rate limit exceeded for IP: {client_ip}')
                return HttpResponseForbidden(
                    'Too many login attempts. Please try again later.'
                )
        
        # Rate Limiting für API-Calls
        if request.path.startswith('/api/'):
            client_ip = self.get_client_ip(request)
            
            # Überprüfe API-Calls
            api_calls = cache.get(f'api_calls_{client_ip}', 0)
            
            if api_calls >= getattr(settings, 'RATE_LIMIT_API_CALLS', 100):
                logger.warning(f'API rate limit exceeded for IP: {client_ip}')
                return HttpResponseForbidden(
                    'API rate limit exceeded. Please try again later.'
                )
        
        response = self.get_response(request)
        
        # Zähle fehlgeschlagene Login-Versuche
        if (request.path == self.login_url and 
            request.method == 'POST' and 
            response.status_code == 200 and 
            'error' in str(response.content)):
            
            client_ip = self.get_client_ip(request)
            login_attempts = cache.get(f'login_attempts_{client_ip}', 0)
            cache.set(f'login_attempts_{client_ip}', login_attempts + 1, 900)  # 15 min
            
        return response
    
    def get_client_ip(self, request):
        """Ermittelt die Client-IP-Adresse"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SecurityAuditMiddleware(MiddlewareMixin):
    """
    Auditierung sicherheitsrelevanter Ereignisse
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Gefährliche Patterns
        self.dangerous_patterns = [
            r'(\.\./){3,}',  # Directory traversal
            r'<script[^>]*>',  # XSS attempts
            r'union\s+select',  # SQL injection
            r'drop\s+table',  # SQL injection
            r'exec\s*\(',  # Command injection
            r'eval\s*\(',  # Code injection
        ]
        
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) 
                                 for pattern in self.dangerous_patterns]
    
    def __call__(self, request):
        start_time = time.time()
        
        # Prüfe auf verdächtige Patterns
        self.check_malicious_patterns(request)
        
        # Logge Admin-Zugriffe
        if request.path.startswith('/admin/'):
            self.log_admin_access(request)
        
        response = self.get_response(request)
        
        # Logge Response-Zeit für Performance-Monitoring
        response_time = time.time() - start_time
        if response_time > 5:  # Langsame Requests loggen
            logger.warning(f'Slow request: {request.path} - {response_time:.2f}s')
        
        return response
    
    def check_malicious_patterns(self, request):
        """Prüft auf verdächtige Patterns in Request-Daten"""
        client_ip = self.get_client_ip(request)
        
        # Prüfe URL
        for pattern in self.compiled_patterns:
            if pattern.search(request.path):
                logger.critical(f'Malicious pattern detected in URL: {request.path} from IP: {client_ip}')
                break
        
        # Prüfe POST-Data
        if request.method == 'POST':
            post_data = str(request.POST)
            for pattern in self.compiled_patterns:
                if pattern.search(post_data):
                    logger.critical(f'Malicious pattern detected in POST data from IP: {client_ip}')
                    break
        
        # Prüfe GET-Parameter
        if request.GET:
            get_data = str(request.GET)
            for pattern in self.compiled_patterns:
                if pattern.search(get_data):
                    logger.critical(f'Malicious pattern detected in GET data from IP: {client_ip}')
                    break
    
    def log_admin_access(self, request):
        """Loggt Admin-Zugriffe"""
        if request.user.is_authenticated:
            logger.info(f'Admin access: {request.user.username} - {request.path} - {self.get_client_ip(request)}')
        else:
            logger.info(f'Anonymous admin access: {request.path} - {self.get_client_ip(request)}')
    
    def get_client_ip(self, request):
        """Ermittelt die Client-IP-Adresse"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SessionSecurityMiddleware(MiddlewareMixin):
    """
    Zusätzliche Session-Sicherheit
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Session-Sicherheit
        if request.user.is_authenticated:
            # Prüfe Session-Alter
            session_created = request.session.get('_session_created')
            if not session_created:
                request.session['_session_created'] = time.time()
            else:
                # Session nach 24 Stunden invalidieren
                if time.time() - session_created > 86400:
                    logout(request)
                    logger.info(f'Session expired for user: {request.user.username}')
                    return redirect('admin:login')
            
            # Prüfe IP-Änderung
            session_ip = request.session.get('_session_ip')
            current_ip = self.get_client_ip(request)
            
            if not session_ip:
                request.session['_session_ip'] = current_ip
            elif session_ip != current_ip:
                logout(request)
                logger.warning(f'IP change detected for user: {request.user.username} - Old: {session_ip}, New: {current_ip}')
                return redirect('admin:login')
        
        response = self.get_response(request)
        return response
    
    def get_client_ip(self, request):
        """Ermittelt die Client-IP-Adresse"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip