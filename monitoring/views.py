import json
import time
import requests
import sys
import os
from datetime import datetime, timedelta
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q, Count, Avg
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

from .models import (
    Platform, SystemHealth, ErrorLog, Alert, 
    PerformanceMetric, MonitoringSettings,
    FileOperation, SecurityLog, ServerPath
)
import logging

logger = logging.getLogger('monitoring')


@login_required
def dashboard_home(request):
    """Main dashboard overview"""
    # Get all platforms with latest health status, grouped by environment
    platforms = Platform.objects.filter(is_active=True).prefetch_related('health_checks').order_by('environment', 'name')
    
    # Group platforms by environment
    platform_groups = {
        'test': [],
        'live': []
    }
    
    for platform in platforms:
        latest_health = platform.health_checks.first()
        
        # Get error count in last 24h
        last_24h = timezone.now() - timedelta(hours=24)
        error_count = platform.errors.filter(
            last_seen__gte=last_24h,
            is_resolved=False
        ).count()
        
        # Get active alerts
        active_alerts = platform.alerts.filter(status='active').count()
        
        platform_info = {
            'platform': platform,
            'health': latest_health,
            'error_count_24h': error_count,
            'active_alerts': active_alerts,
            'status_class': get_status_class(latest_health.status if latest_health else 'unknown')
        }
        
        # Add to appropriate environment group
        if platform.environment in platform_groups:
            platform_groups[platform.environment].append(platform_info)
    
    # Create flat list for backwards compatibility
    platform_status = []
    for env_platforms in platform_groups.values():
        platform_status.extend(env_platforms)
    
    # Recent errors across all platforms
    recent_errors = ErrorLog.objects.filter(
        is_resolved=False
    ).select_related('platform').order_by('-last_seen')[:10]
    
    # Active alerts
    active_alerts = Alert.objects.filter(
        status='active'
    ).select_related('platform').order_by('-created_at')[:5]
    
    # System overview stats
    total_platforms = platforms.count()
    online_platforms = sum(1 for p in platform_status if p['health'] and p['health'].status == 'online')
    total_errors_24h = sum(p['error_count_24h'] for p in platform_status)
    total_active_alerts = sum(p['active_alerts'] for p in platform_status)
    
    # Calculate environment-specific stats
    env_stats = {}
    for env, env_platforms in platform_groups.items():
        if env_platforms:  # Only calculate stats for environments that have platforms
            env_online = sum(1 for p in env_platforms if p['health'] and p['health'].status == 'online')
            env_total = len(env_platforms)
            env_errors = sum(p['error_count_24h'] for p in env_platforms)
            env_alerts = sum(p['active_alerts'] for p in env_platforms)
            
            env_stats[env] = {
                'total': env_total,
                'online': env_online,
                'offline': env_total - env_online,
                'errors_24h': env_errors,
                'alerts': env_alerts,
                'uptime_percentage': round((env_online / env_total * 100), 1) if env_total > 0 else 0
            }

    context = {
        'platform_status': platform_status,
        'platform_groups': platform_groups,
        'recent_errors': recent_errors,
        'active_alerts': active_alerts,
        'stats': {
            'total_platforms': total_platforms,
            'online_platforms': online_platforms,
            'offline_platforms': total_platforms - online_platforms,
            'total_errors_24h': total_errors_24h,
            'total_active_alerts': total_active_alerts,
            'uptime_percentage': round((online_platforms / total_platforms * 100), 1) if total_platforms > 0 else 0
        },
        'env_stats': env_stats
    }
    
    return render(request, 'monitoring/dashboard.html', context)


def health_check_api(request):
    """API endpoint for real-time health status"""
    platforms = Platform.objects.filter(is_active=True)
    
    platform_data = []
    for platform in platforms:
        # Perform health check
        health_status = perform_health_check(platform)
        
        platform_data.append({
            'id': platform.id,
            'name': platform.name,
            'status': health_status['status'],
            'response_time': health_status['response_time'],
            'last_checked': health_status['checked_at'].isoformat() if health_status['checked_at'] else None,
            'error_message': health_status.get('error_message', ''),
        })
    
    return JsonResponse({
        'platforms': platform_data,
        'timestamp': timezone.now().isoformat()
    })


def perform_health_check(platform):
    """Perform actual health check for a platform"""
    from .alert_system import process_health_check_alert
    
    start_time = time.time()
    
    try:
        # Build health check URL
        health_url = f"{platform.url.rstrip('/')}{platform.health_endpoint}"
        
        # Perform request with timeout
        response = requests.get(health_url, timeout=10)
        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        # Determine status based on response
        if response.status_code == 200:
            status = 'online'
            error_message = ''
        elif response.status_code in [500, 502, 503, 504]:
            status = 'error'
            error_message = f'HTTP {response.status_code}'
        else:
            status = 'warning'
            error_message = f'HTTP {response.status_code}'
        
        # Save health check result
        health_check = SystemHealth.objects.create(
            platform=platform,
            status=status,
            response_time=response_time,
            status_code=response.status_code,
            error_message=error_message
        )
        
        # Process alerts for this health check
        health_result = {
            'status': status,
            'response_time': response_time,
            'status_code': response.status_code,
            'error_message': error_message,
            'checked_at': health_check.checked_at
        }
        
        # Trigger alert processing
        process_health_check_alert(platform, health_result)
        
        return health_result
        
    except requests.exceptions.Timeout:
        response_time = (time.time() - start_time) * 1000
        
        SystemHealth.objects.create(
            platform=platform,
            status='offline',
            response_time=response_time,
            error_message='Connection timeout'
        )
        
        # Process alerts for timeout
        health_result = {
            'status': 'offline',
            'response_time': response_time,
            'error_message': 'Connection timeout',
            'checked_at': timezone.now()
        }
        
        # Trigger alert processing
        process_health_check_alert(platform, health_result)
        
        return health_result
        
    except requests.exceptions.ConnectionError:
        response_time = (time.time() - start_time) * 1000
        
        SystemHealth.objects.create(
            platform=platform,
            status='offline',
            response_time=response_time,
            error_message='Connection failed'
        )
        
        # Process alerts for connection error
        health_result = {
            'status': 'offline',
            'response_time': response_time,
            'error_message': 'Connection failed',
            'checked_at': timezone.now()
        }
        
        # Trigger alert processing
        process_health_check_alert(platform, health_result)
        
        return health_result
        
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        
        SystemHealth.objects.create(
            platform=platform,
            status='error',
            response_time=response_time,
            error_message=str(e)
        )
        
        return {
            'status': 'error',
            'response_time': response_time,
            'error_message': str(e),
            'checked_at': timezone.now()
        }


@login_required
def errors_list(request):
    """List all errors with filtering"""
    errors = ErrorLog.objects.select_related('platform').order_by('-last_seen')
    
    # Filter by platform
    platform_id = request.GET.get('platform')
    if platform_id:
        errors = errors.filter(platform_id=platform_id)
    
    # Filter by severity
    severity = request.GET.get('severity')
    if severity:
        errors = errors.filter(severity=severity)
    
    # Filter by status
    status = request.GET.get('status', 'active')
    if status == 'active':
        errors = errors.filter(is_resolved=False)
    elif status == 'resolved':
        errors = errors.filter(is_resolved=True)
    
    # Pagination
    paginator = Paginator(errors, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'platforms': Platform.objects.filter(is_active=True),
        'current_filters': {
            'platform': platform_id,
            'severity': severity,
            'status': status,
        }
    }
    
    return render(request, 'monitoring/errors_list.html', context)


@login_required
def alerts_list(request):
    """List all alerts"""
    alerts = Alert.objects.select_related('platform').order_by('-created_at')
    
    # Filter by status
    status = request.GET.get('status', 'active')
    if status != 'all':
        alerts = alerts.filter(status=status)
    
    # Pagination
    paginator = Paginator(alerts, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'current_status': status,
    }
    
    return render(request, 'monitoring/alerts_list.html', context)


@login_required
def platform_detail(request, platform_id):
    """Detailed view for a specific platform"""
    platform = Platform.objects.get(id=platform_id)
    
    # Recent health checks (last 24 hours)
    last_24h = timezone.now() - timedelta(hours=24)
    health_checks = platform.health_checks.filter(
        checked_at__gte=last_24h
    ).order_by('-checked_at')[:100]
    
    # Recent errors
    recent_errors = platform.errors.filter(
        last_seen__gte=last_24h
    ).order_by('-last_seen')[:20]
    
    # Performance metrics (if available)
    performance_metrics = platform.metrics.order_by('-created_at')[:10]
    
    # Calculate uptime for last 24h
    total_checks = health_checks.count()
    online_checks = health_checks.filter(status='online').count()
    uptime_percentage = round((online_checks / total_checks * 100), 2) if total_checks > 0 else 0
    
    # Average response time
    avg_response_time = health_checks.aggregate(
        avg_time=Avg('response_time')
    )['avg_time'] or 0
    
    context = {
        'platform': platform,
        'health_checks': health_checks,
        'recent_errors': recent_errors,
        'performance_metrics': performance_metrics,
        'stats': {
            'uptime_percentage': uptime_percentage,
            'avg_response_time': round(avg_response_time, 2),
            'total_checks_24h': total_checks,
            'error_count_24h': recent_errors.count(),
        }
    }
    
    return render(request, 'monitoring/platform_detail.html', context)


@csrf_exempt
def error_webhook(request):
    """Webhook endpoint for receiving errors from platforms"""
    from .alert_system import process_error_alert
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        
        # Get platform
        platform_slug = data.get('platform')
        platform = Platform.objects.get(slug=platform_slug)
        
        # Create or update error log
        error_data = {
            'platform': platform,
            'error_type': data.get('error_type', 'other'),
            'severity': data.get('severity', 'medium'),
            'message': data.get('message', ''),
            'stack_trace': data.get('stack_trace', ''),
            'url_path': data.get('url_path', ''),
            'user_agent': data.get('user_agent', ''),
            'ip_address': data.get('ip_address'),
            'user_id': data.get('user_id', ''),
            'request_data': data.get('request_data', {}),
            'environment_data': data.get('environment_data', {}),
        }
        
        # Check if similar error exists
        existing_error = ErrorLog.objects.filter(
            platform=platform,
            error_type=error_data['error_type'],
            message=error_data['message'],
            is_resolved=False
        ).first()
        
        if existing_error:
            # Update existing error
            existing_error.count += 1
            existing_error.last_seen = timezone.now()
            existing_error.save()
            error_log = existing_error
            error_id = existing_error.id
        else:
            # Create new error
            error_log = ErrorLog.objects.create(**error_data)
            error_id = error_log.id
        
        # Process alerts for this error
        process_error_alert(error_log)
        
        logger.info(f"Error logged for {platform.name}: {error_data['message']}")
        
        return JsonResponse({
            'status': 'success',
            'error_id': error_id
        })
        
    except Platform.DoesNotExist:
        return JsonResponse({'error': 'Platform not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error webhook failed: {e}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


def get_status_class(status):
    """Get CSS class for status"""
    status_classes = {
        'online': 'success',
        'offline': 'danger',
        'warning': 'warning',
        'error': 'danger',
        'unknown': 'secondary'
    }
    return status_classes.get(status, 'secondary')


@login_required  
def alerts_list(request):
    """List all alerts with filtering"""
    # Get filter parameters
    environment = request.GET.get('environment', '')
    platform_id = request.GET.get('platform', '')
    severity = request.GET.get('severity', '')
    status = request.GET.get('status', 'active')
    
    # Start with all alerts
    alerts = Alert.objects.select_related('platform').order_by('-created_at')
    
    # Apply filters
    if environment:
        alerts = alerts.filter(platform__environment=environment)
    
    if platform_id:
        alerts = alerts.filter(platform_id=platform_id)
    
    if severity:
        alerts = alerts.filter(severity=severity)
    
    if status != 'all':
        alerts = alerts.filter(status=status)
    
    # Calculate alert statistics
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    alert_stats = {
        'total_active': Alert.objects.filter(status='active').count(),
        'critical_count': Alert.objects.filter(status='active', severity='critical').count(),
        'resolved_today': Alert.objects.filter(
            status='resolved',
            resolved_at__gte=today
        ).count(),
        'avg_resolution_time': calculate_avg_resolution_time()
    }
    
    # Pagination
    paginator = Paginator(alerts, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get all platforms for filter dropdown
    platforms = Platform.objects.filter(is_active=True).order_by('environment', 'name')
    
    context = {
        'page_obj': page_obj,
        'platforms': platforms,
        'alert_stats': alert_stats,
        'current_filters': {
            'environment': environment,
            'platform': platform_id,
            'severity': severity,
            'status': status,
        }
    }
    
    return render(request, 'monitoring/alerts_list.html', context)


def calculate_avg_resolution_time():
    """Calculate average resolution time in hours"""
    from django.db.models import F, Avg
    
    resolved_alerts = Alert.objects.filter(
        status='resolved',
        resolved_at__isnull=False
    ).annotate(
        resolution_time=F('resolved_at') - F('created_at')
    )
    
    if not resolved_alerts.exists():
        return 0
    
    # Convert to hours
    avg_seconds = resolved_alerts.aggregate(
        avg_time=Avg('resolution_time')
    )['avg_time']
    
    if avg_seconds:
        return round(avg_seconds.total_seconds() / 3600, 1)
    return 0


@login_required
def settings_view(request):
    """Monitoring settings management"""
    if request.method == 'POST':
        settings_obj = MonitoringSettings.get_settings()
        
        # Update settings from form
        settings_obj.health_check_interval = int(request.POST.get('health_check_interval', 5))
        settings_obj.response_time_threshold = float(request.POST.get('response_time_threshold', 5000))
        settings_obj.error_rate_threshold = float(request.POST.get('error_rate_threshold', 5))
        settings_obj.email_notifications = request.POST.get('email_notifications') == 'on'
        settings_obj.slack_notifications = request.POST.get('slack_notifications') == 'on'
        settings_obj.slack_webhook_url = request.POST.get('slack_webhook_url', '')
        
        settings_obj.save()
        
        return JsonResponse({'status': 'success'})
    
    settings_obj = MonitoringSettings.get_settings()
    
    context = {
        'settings': settings_obj,
        'platforms': Platform.objects.filter(is_active=True)
    }
    
    return render(request, 'monitoring/settings.html', context)


@login_required
def system_status_view(request):
    """System status overview"""
    import psutil
    import os
    from django.db import connection
    
    # System Information
    system_info = {
        'cpu_usage': psutil.cpu_percent(interval=1),
        'memory_usage': psutil.virtual_memory().percent,
        'disk_usage': psutil.disk_usage('/').percent,
        'uptime': time.time() - psutil.boot_time(),
        'platform': os.uname().sysname if hasattr(os, 'uname') else 'Unknown',
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }
    
    # Database Information
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            db_version = cursor.fetchone()[0] if cursor.fetchone() else 'Unknown'
    except:
        db_version = 'Unknown'
    
    # Application Statistics
    from django.contrib.auth.models import User
    app_stats = {
        'total_users': User.objects.count(),
        'active_platforms': Platform.objects.filter(is_active=True).count(),
        'total_errors_24h': ErrorLog.objects.filter(
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).count(),
        'active_alerts': Alert.objects.filter(status='active').count(),
    }
    
    context = {
        'system_info': system_info,
        'db_version': db_version,
        'app_stats': app_stats,
    }
    
    return render(request, 'monitoring/system_status.html', context)


@login_required
def user_management_view(request):
    """User management overview"""
    from django.contrib.auth.models import User, Group
    from django.core.paginator import Paginator
    
    # Get users with pagination
    users = User.objects.all().order_by('-date_joined')
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # User statistics
    user_stats = {
        'total_users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'staff_users': User.objects.filter(is_staff=True).count(),
        'superusers': User.objects.filter(is_superuser=True).count(),
        'recent_logins': User.objects.filter(
            last_login__gte=timezone.now() - timedelta(days=30)
        ).count(),
    }
    
    context = {
        'page_obj': page_obj,
        'user_stats': user_stats,
        'groups': Group.objects.all(),
    }
    
    return render(request, 'monitoring/user_management.html', context)


@login_required
def database_status_view(request):
    """Database status and statistics"""
    from django.db import connection, connections
    
    # Database connection info
    db_info = {
        'engine': connection.settings_dict['ENGINE'],
        'name': connection.settings_dict['NAME'],
        'host': connection.settings_dict.get('HOST', 'localhost'),
        'port': connection.settings_dict.get('PORT', 'default'),
    }
    
    # Table sizes and row counts
    table_stats = []
    try:
        with connection.cursor() as cursor:
            # Get table information
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            tables = cursor.fetchall()
            
            for table in tables:
                table_name = table[0]
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = cursor.fetchone()[0]
                table_stats.append({
                    'name': table_name,
                    'rows': row_count
                })
    except Exception as e:
        table_stats = [{'error': str(e)}]
    
    # Recent migrations
    try:
        from django.db.migrations.recorder import MigrationRecorder
        recent_migrations = MigrationRecorder.Migration.objects.order_by('-id')[:10]
    except:
        recent_migrations = []
    
    context = {
        'db_info': db_info,
        'table_stats': table_stats,
        'recent_migrations': recent_migrations,
    }
    
    return render(request, 'monitoring/database_status.html', context)


@login_required
def server_status_view(request):
    """Server status and performance metrics"""
    import psutil
    import socket
    
    # Network interfaces
    network_info = []
    try:
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    network_info.append({
                        'interface': interface,
                        'ip': addr.address,
                        'netmask': addr.netmask,
                    })
    except:
        network_info = []
    
    # Process information
    try:
        process_info = {
            'total_processes': len(psutil.pids()),
            'running_processes': len([p for p in psutil.process_iter() if p.status() == 'running']),
            'cpu_count': psutil.cpu_count(),
            'load_average': os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0],
        }
    except:
        process_info = {
            'total_processes': 0,
            'running_processes': 0,
            'cpu_count': 1,
            'load_average': [0, 0, 0],
        }
    
    # Disk information
    disk_info = []
    try:
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_info.append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'fstype': partition.fstype,
                    'total': usage.total,
                    'used': usage.used,
                    'free': usage.free,
                    'percent': (usage.used / usage.total) * 100 if usage.total > 0 else 0
                })
            except PermissionError:
                continue
    except:
        disk_info = []
    
    context = {
        'network_info': network_info,
        'process_info': process_info,
        'disk_info': disk_info,
    }
    
    return render(request, 'monitoring/server_status.html', context)


def error_detail_api(request, error_id):
    """API endpoint for error details"""
    try:
        error = ErrorLog.objects.get(id=error_id)
        
        data = {
            'id': error.id,
            'platform': error.platform.name,
            'error_type': error.get_error_type_display(),
            'severity': error.severity,
            'message': error.message,
            'stack_trace': error.stack_trace,
            'url_path': error.url_path,
            'user_agent': error.user_agent,
            'ip_address': error.ip_address,
            'user_id': error.user_id,
            'count': error.count,
            'first_seen': error.first_seen.strftime('%Y-%m-%d %H:%M:%S'),
            'last_seen': error.last_seen.strftime('%Y-%m-%d %H:%M:%S'),
            'is_resolved': error.is_resolved,
            'request_data': error.request_data,
            'environment_data': error.environment_data,
        }
        
        return JsonResponse(data)
        
    except ErrorLog.DoesNotExist:
        return JsonResponse({'error': 'Error not found'}, status=404)


def error_resolve_api(request, error_id):
    """API endpoint to resolve an error"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    try:
        error = ErrorLog.objects.get(id=error_id)
        
        if not error.is_resolved:
            error.resolve(resolved_by="Admin Dashboard")
            
            # Create alert if this was a critical error
            if error.severity == 'critical':
                Alert.objects.create(
                    platform=error.platform,
                    alert_type='high_error_rate',
                    title=f'Critical error resolved: {error.error_type}',
                    message=f'Critical error has been manually resolved: {error.message[:100]}',
                    severity='medium',
                    status='resolved',
                    related_error=error
                )
        
        return JsonResponse({
            'status': 'success',
            'message': 'Error marked as resolved'
        })
        
    except ErrorLog.DoesNotExist:
        return JsonResponse({'error': 'Error not found'}, status=404)
    except Exception as e:
        logger.error(f"Error resolve failed: {e}")
        return JsonResponse({'error': 'Internal server error'}, status=500)