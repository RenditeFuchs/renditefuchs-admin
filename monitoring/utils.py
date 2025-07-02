import requests
import json
import logging
from django.conf import settings

logger = logging.getLogger('monitoring')


def send_error_to_admin(platform_slug, error_data):
    """
    Send error data to the admin dashboard
    
    Args:
        platform_slug (str): Platform identifier (main, focus, blog, academy)
        error_data (dict): Error information
    """
    try:
        # Admin dashboard webhook URL
        webhook_url = getattr(settings, 'ADMIN_DASHBOARD_WEBHOOK_URL', 
                             'http://127.0.0.1:8003/monitoring/webhook/error/')
        
        # Prepare payload
        payload = {
            'platform': platform_slug,
            'error_type': error_data.get('error_type', 'other'),
            'severity': error_data.get('severity', 'medium'),
            'message': error_data.get('message', ''),
            'stack_trace': error_data.get('stack_trace', ''),
            'url_path': error_data.get('url_path', ''),
            'user_agent': error_data.get('user_agent', ''),
            'ip_address': error_data.get('ip_address'),
            'user_id': error_data.get('user_id', ''),
            'request_data': error_data.get('request_data', {}),
            'environment_data': error_data.get('environment_data', {}),
        }
        
        # Send to admin dashboard
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=5,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            logger.info(f'Error sent to admin dashboard: {platform_slug}')
            return True
        else:
            logger.warning(f'Failed to send error to admin dashboard: {response.status_code}')
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f'Error sending to admin dashboard: {e}')
        return False
    except Exception as e:
        logger.error(f'Unexpected error sending to admin dashboard: {e}')
        return False


class AdminErrorHandler(logging.Handler):
    """
    Custom logging handler that sends errors to admin dashboard
    """
    
    def __init__(self, platform_slug='main'):
        super().__init__()
        self.platform_slug = platform_slug
    
    def emit(self, record):
        """Send log record to admin dashboard"""
        try:
            # Only send ERROR and CRITICAL level logs
            if record.levelno < logging.ERROR:
                return
            
            # Extract error information
            error_data = {
                'error_type': 'other',
                'severity': 'critical' if record.levelno >= logging.CRITICAL else 'high',
                'message': self.format(record),
                'stack_trace': self.format(record) if record.exc_info else '',
            }
            
            # Add extra context if available
            if hasattr(record, 'request'):
                request = record.request
                error_data.update({
                    'url_path': request.get_full_path(),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                    'ip_address': get_client_ip(request),
                    'user_id': str(request.user.id) if request.user.is_authenticated else '',
                    'request_data': {
                        'method': request.method,
                        'GET': dict(request.GET),
                        'POST': dict(request.POST) if request.method == 'POST' else {},
                    }
                })
                
                # Determine error type based on response
                if hasattr(record, 'status_code'):
                    if record.status_code >= 500:
                        error_data['error_type'] = '500'
                    elif record.status_code == 404:
                        error_data['error_type'] = '404'
                    elif record.status_code == 403:
                        error_data['error_type'] = '403'
            
            # Send to admin dashboard
            send_error_to_admin(self.platform_slug, error_data)
            
        except Exception:
            # Don't let logging errors break the application
            pass


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def create_manual_error(platform_slug, error_type, message, severity='medium', **kwargs):
    """
    Manually create an error log entry
    
    Args:
        platform_slug (str): Platform identifier
        error_type (str): Type of error (500, 404, database, etc.)
        message (str): Error message
        severity (str): Error severity (low, medium, high, critical)
        **kwargs: Additional error data
    """
    error_data = {
        'error_type': error_type,
        'severity': severity,
        'message': message,
        **kwargs
    }
    
    return send_error_to_admin(platform_slug, error_data)


# Django middleware for automatic error tracking
class AdminErrorTrackingMiddleware:
    """
    Middleware to automatically track errors in Django applications
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.platform_slug = getattr(settings, 'PLATFORM_SLUG', 'main')
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Track 4xx and 5xx errors
        if response.status_code >= 400:
            self.track_error(request, response)
        
        return response
    
    def track_error(self, request, response):
        """Track error response"""
        try:
            # Determine error type and severity
            if response.status_code >= 500:
                error_type = '500'
                severity = 'high'
            elif response.status_code == 404:
                error_type = '404'
                severity = 'low'
            elif response.status_code == 403:
                error_type = '403'
                severity = 'medium'
            else:
                error_type = 'other'
                severity = 'medium'
            
            error_data = {
                'error_type': error_type,
                'severity': severity,
                'message': f'HTTP {response.status_code} error on {request.get_full_path()}',
                'url_path': request.get_full_path(),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'ip_address': get_client_ip(request),
                'user_id': str(request.user.id) if request.user.is_authenticated else '',
                'request_data': {
                    'method': request.method,
                    'GET': dict(request.GET),
                    'POST': dict(request.POST) if request.method == 'POST' else {},
                },
                'environment_data': {
                    'status_code': response.status_code,
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                    'referer': request.META.get('HTTP_REFERER', ''),
                }
            }
            
            # Send to admin dashboard (async to avoid blocking)
            send_error_to_admin(self.platform_slug, error_data)
            
        except Exception as e:
            # Log the error but don't break the response
            logger.error(f'Error tracking middleware failed: {e}')
    
    def process_exception(self, request, exception):
        """Track unhandled exceptions"""
        try:
            import traceback
            
            error_data = {
                'error_type': '500',
                'severity': 'critical',
                'message': str(exception),
                'stack_trace': traceback.format_exc(),
                'url_path': request.get_full_path(),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'ip_address': get_client_ip(request),
                'user_id': str(request.user.id) if request.user.is_authenticated else '',
                'request_data': {
                    'method': request.method,
                    'GET': dict(request.GET),
                    'POST': dict(request.POST) if request.method == 'POST' else {},
                },
                'environment_data': {
                    'exception_type': type(exception).__name__,
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                    'referer': request.META.get('HTTP_REFERER', ''),
                }
            }
            
            send_error_to_admin(self.platform_slug, error_data)
            
        except Exception as e:
            logger.error(f'Exception tracking failed: {e}')
        
        # Return None to let Django handle the exception normally
        return None