"""
Security decorators for server directory access
Provides authentication, authorization, and rate limiting
"""

import functools
import logging
from typing import Any, Callable, Dict, Optional
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponseForbidden
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
from django.utils import timezone
from .models import SecurityLog, FileOperation, MonitoringSettings
from .security import RateLimiter, SecurityException

logger = logging.getLogger(__name__)


def server_directory_required(view_func: Callable) -> Callable:
    """
    Decorator to ensure server directory feature is enabled
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        settings = MonitoringSettings.get_settings()
        if not settings.server_directory_enabled:
            return JsonResponse({
                'error': 'Server directory feature is disabled',
                'code': 'FEATURE_DISABLED'
            }, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_required(view_func: Callable) -> Callable:
    """
    Decorator to require admin/superuser access
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({
                'error': 'Authentication required',
                'code': 'NOT_AUTHENTICATED'
            }, status=401)
        
        if not request.user.is_superuser:
            # Log unauthorized access attempt
            SecurityLog.objects.create(
                event_type='unauthorized_access',
                severity='warning',
                message=f"Non-admin user {request.user.username} attempted admin action",
                user_id=str(request.user.id),
                username=request.user.username,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                url_path=request.path,
                request_method=request.method
            )
            
            return JsonResponse({
                'error': 'Admin access required',
                'code': 'INSUFFICIENT_PERMISSIONS'
            }, status=403)
        
        return view_func(request, *args, **kwargs)
    return wrapper


def rate_limited(operation: str = None, max_requests: int = None, window_minutes: int = 60):
    """
    Rate limiting decorator
    
    Args:
        operation: Operation type for specific rate limits
        max_requests: Maximum requests per window (overrides default)
        window_minutes: Time window in minutes
    """
    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            
            rate_limiter = RateLimiter(request.user)
            is_limited, message = rate_limiter.is_rate_limited(operation)
            
            if is_limited:
                rate_limiter.record_rate_limit_violation(message)
                return JsonResponse({
                    'error': 'Rate limit exceeded',
                    'message': message,
                    'code': 'RATE_LIMIT_EXCEEDED'
                }, status=429)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def audit_logged(operation: str, get_path: Callable = None):
    """
    Decorator to automatically log operations in audit trail
    
    Args:
        operation: Operation type (read, write, delete, etc.)
        get_path: Function to extract file path from request
    """
    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            start_time = timezone.now()
            
            # Extract path if function provided
            path = ''
            if get_path:
                try:
                    path = get_path(request, *args, **kwargs)
                except Exception as e:
                    logger.warning(f"Could not extract path for audit log: {str(e)}")
            
            try:
                # Execute view
                response = view_func(request, *args, **kwargs)
                
                # Determine status
                status = 'success'
                if hasattr(response, 'status_code'):
                    if response.status_code >= 400:
                        status = 'failed'
                    elif response.status_code >= 200:
                        status = 'success'
                
                # Log operation
                if request.user.is_authenticated:
                    from .security import FileOperationTracker
                    tracker = FileOperationTracker(
                        request.user,
                        get_client_ip(request),
                        request.META.get('HTTP_USER_AGENT', ''),
                        request.session.session_key
                    )
                    
                    execution_time = (timezone.now() - start_time).total_seconds() * 1000
                    
                    tracker.track_operation(
                        operation=operation,
                        file_path=path,
                        status=status,
                        execution_time=execution_time,
                        metadata={
                            'view_name': view_func.__name__,
                            'request_method': request.method,
                            'response_status': getattr(response, 'status_code', None)
                        }
                    )
                
                return response
                
            except Exception as e:
                # Log failed operation
                if request.user.is_authenticated:
                    from .security import FileOperationTracker
                    tracker = FileOperationTracker(
                        request.user,
                        get_client_ip(request),
                        request.META.get('HTTP_USER_AGENT', ''),
                        request.session.session_key
                    )
                    
                    execution_time = (timezone.now() - start_time).total_seconds() * 1000
                    
                    tracker.track_operation(
                        operation=operation,
                        file_path=path,
                        status='failed',
                        error_message=str(e),
                        execution_time=execution_time,
                        metadata={
                            'view_name': view_func.__name__,
                            'request_method': request.method,
                            'exception_type': type(e).__name__
                        }
                    )
                
                raise
        return wrapper
    return decorator


def security_validated(check_path: bool = True, required_operation: str = 'read'):
    """
    Decorator to validate security for file operations
    
    Args:
        check_path: Whether to validate the path parameter
        required_operation: Required operation type for validation
    """
    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({
                    'error': 'Authentication required',
                    'code': 'NOT_AUTHENTICATED'
                }, status=401)
            
            # Path validation if required
            if check_path:
                path = request.GET.get('path') or request.POST.get('path')
                if not path:
                    return JsonResponse({
                        'error': 'Path parameter required',
                        'code': 'MISSING_PATH'
                    }, status=400)
                
                # Validate path
                from .security import ServerPathValidator
                validator = ServerPathValidator(
                    request.user,
                    get_client_ip(request),
                    request.META.get('HTTP_USER_AGENT', '')
                )
                
                is_valid, error_message = validator.validate_path(path, required_operation)
                if not is_valid:
                    return JsonResponse({
                        'error': error_message,
                        'code': 'PATH_VALIDATION_FAILED'
                    }, status=403)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def json_response_on_error(view_func: Callable) -> Callable:
    """
    Decorator to return JSON responses for errors
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except SecurityException as e:
            return JsonResponse({
                'error': str(e),
                'code': 'SECURITY_VIOLATION'
            }, status=403)
        except PermissionDenied as e:
            return JsonResponse({
                'error': str(e),
                'code': 'PERMISSION_DENIED'
            }, status=403)
        except Exception as e:
            logger.error(f"Unexpected error in {view_func.__name__}: {str(e)}")
            return JsonResponse({
                'error': 'Internal server error',
                'code': 'INTERNAL_ERROR'
            }, status=500)
    return wrapper


def require_confirmation(get_risk_score: Callable = None, threshold: int = 50):
    """
    Decorator to require confirmation for high-risk operations
    
    Args:
        get_risk_score: Function to calculate risk score
        threshold: Risk threshold requiring confirmation
    """
    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Check if confirmation is provided
            confirmed = request.POST.get('confirm', '').lower() == 'true'
            
            # Calculate risk score if function provided
            risk_score = 0
            if get_risk_score:
                try:
                    risk_score = get_risk_score(request, *args, **kwargs)
                except Exception as e:
                    logger.warning(f"Could not calculate risk score: {str(e)}")
            
            # Require confirmation for high-risk operations
            if risk_score >= threshold and not confirmed:
                return JsonResponse({
                    'error': 'Confirmation required for high-risk operation',
                    'code': 'CONFIRMATION_REQUIRED',
                    'risk_score': risk_score,
                    'requires_confirmation': True
                }, status=400)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def log_security_event(event_type: str, severity: str = 'info', get_message: Callable = None):
    """
    Decorator to log security events
    
    Args:
        event_type: Type of security event
        severity: Event severity
        get_message: Function to generate event message
    """
    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            try:
                response = view_func(request, *args, **kwargs)
                
                # Generate message
                message = f"View {view_func.__name__} executed"
                if get_message:
                    try:
                        message = get_message(request, response, *args, **kwargs)
                    except Exception as e:
                        logger.warning(f"Could not generate security event message: {str(e)}")
                
                # Log event
                if request.user.is_authenticated:
                    SecurityLog.objects.create(
                        event_type=event_type,
                        severity=severity,
                        message=message,
                        user_id=str(request.user.id),
                        username=request.user.username,
                        ip_address=get_client_ip(request),
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        url_path=request.path,
                        request_method=request.method
                    )
                
                return response
                
            except Exception as e:
                # Log error event
                if request.user.is_authenticated:
                    SecurityLog.objects.create(
                        event_type='system_alert',
                        severity='error',
                        message=f"Error in {view_func.__name__}: {str(e)}",
                        user_id=str(request.user.id),
                        username=request.user.username,
                        ip_address=get_client_ip(request),
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        url_path=request.path,
                        request_method=request.method
                    )
                raise
        return wrapper
    return decorator


# Composite decorators for common use cases
def server_directory_view(operation: str = 'read', require_admin: bool = False):
    """
    Composite decorator for server directory views
    
    Args:
        operation: Operation type for validation
        require_admin: Whether admin access is required
    """
    def decorator(view_func: Callable) -> Callable:
        decorated_view = view_func
        
        # Apply decorators in order
        decorated_view = json_response_on_error(decorated_view)
        decorated_view = security_validated(check_path=True, required_operation=operation)(decorated_view)
        decorated_view = rate_limited(operation=operation)(decorated_view)
        decorated_view = audit_logged(operation)(decorated_view)
        
        if require_admin:
            decorated_view = admin_required(decorated_view)
        
        decorated_view = login_required(decorated_view)
        decorated_view = server_directory_required(decorated_view)
        
        return decorated_view
    return decorator


def server_directory_api(operation: str = 'read', require_admin: bool = False):
    """
    Composite decorator for server directory API endpoints
    
    Args:
        operation: Operation type for validation
        require_admin: Whether admin access is required
    """
    def decorator(view_func: Callable) -> Callable:
        decorated_view = view_func
        
        # Apply decorators in order
        decorated_view = json_response_on_error(decorated_view)
        decorated_view = security_validated(check_path=True, required_operation=operation)(decorated_view)
        decorated_view = rate_limited(operation=operation)(decorated_view)
        decorated_view = audit_logged(operation)(decorated_view)
        
        if require_admin:
            decorated_view = admin_required(decorated_view)
        
        decorated_view = login_required(decorated_view)
        decorated_view = server_directory_required(decorated_view)
        decorated_view = csrf_exempt(decorated_view)  # API endpoints don't need CSRF
        
        return decorated_view
    return decorator


# Utility functions
def get_client_ip(request) -> str:
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def get_path_from_request(request, *args, **kwargs) -> str:
    """Extract file path from request"""
    return request.GET.get('path', '') or request.POST.get('path', '')


def calculate_delete_risk(request, *args, **kwargs) -> int:
    """Calculate risk score for delete operations"""
    from .security import ServerPathValidator
    
    path = get_path_from_request(request, *args, **kwargs)
    if not path:
        return 0
    
    validator = ServerPathValidator(
        request.user,
        get_client_ip(request),
        request.META.get('HTTP_USER_AGENT', '')
    )
    
    return validator.calculate_risk_score(path, 'delete')


def calculate_write_risk(request, *args, **kwargs) -> int:
    """Calculate risk score for write operations"""
    from .security import ServerPathValidator
    
    path = get_path_from_request(request, *args, **kwargs)
    if not path:
        return 0
    
    validator = ServerPathValidator(
        request.user,
        get_client_ip(request),
        request.META.get('HTTP_USER_AGENT', '')
    )
    
    return validator.calculate_risk_score(path, 'write')


# Method decorators for class-based views
server_directory_method = method_decorator(server_directory_view())
admin_required_method = method_decorator(admin_required)
rate_limited_method = method_decorator(rate_limited())
audit_logged_method = method_decorator(audit_logged('admin_action'))
security_validated_method = method_decorator(security_validated())
json_response_on_error_method = method_decorator(json_response_on_error)