"""
Debug views for troubleshooting server file operations
"""
import os
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from .models import MonitoringSettings
from .security import PathValidator
from .ssh_manager import SSHManager
import logging

logger = logging.getLogger('monitoring')


@login_required
def debug_config(request):
    """Debug configuration view"""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Superuser access required'}, status=403)
    
    try:
        settings = MonitoringSettings.get_settings()
        path_validator = PathValidator()
        
        # Check SSH key file
        key_path = os.path.expanduser(settings.ssh_key_path)
        key_exists = os.path.exists(key_path)
        
        # Test path validation
        test_paths = ['/var/www', '/var/www/', '/var/www/test', '/etc/passwd']
        path_validations = {}
        for test_path in test_paths:
            path_validations[test_path] = path_validator.is_safe_path(test_path)
        
        return JsonResponse({
            'success': True,
            'ssh_config': {
                'host': settings.ssh_host,
                'port': settings.ssh_port,
                'user': settings.ssh_user,
                'key_path': settings.ssh_key_path,
                'key_exists': key_exists,
                'expanded_key_path': key_path
            },
            'path_validation': {
                'allowed_paths': path_validator.allowed_paths,
                'test_results': path_validations
            },
            'django_user': {
                'username': request.user.username,
                'is_superuser': request.user.is_superuser,
                'is_staff': request.user.is_staff
            }
        })
        
    except Exception as e:
        logger.error(f"Debug config error: {e}")
        return JsonResponse({
            'error': str(e),
            'traceback': str(e.__traceback__)
        }, status=500)


@login_required
def test_ssh_connection(request):
    """Test SSH connection"""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Superuser access required'}, status=403)
    
    try:
        ssh_manager = SSHManager()
        
        with ssh_manager.get_connection() as ssh:
            # Test basic command
            stdin, stdout, stderr = ssh.exec_command('pwd')
            current_dir = stdout.read().decode().strip()
            
            # Test SFTP
            sftp = ssh.open_sftp()
            sftp.listdir('/var/www')
            sftp.close()
            
            return JsonResponse({
                'success': True,
                'connection': 'established',
                'current_directory': current_dir,
                'sftp': 'working'
            })
            
    except Exception as e:
        logger.error(f"SSH connection test failed: {e}")
        return JsonResponse({
            'error': str(e),
            'connection': 'failed'
        }, status=500)


@login_required  
def test_directory_listing(request):
    """Test directory listing"""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Superuser access required'}, status=403)
    
    path = request.GET.get('path', '/var/www')
    
    try:
        ssh_manager = SSHManager()
        path_validator = PathValidator()
        
        # Validate path
        is_safe = path_validator.is_safe_path(path)
        
        if not is_safe:
            return JsonResponse({
                'error': 'Invalid path',
                'path': path,
                'allowed_paths': path_validator.allowed_paths
            }, status=400)
        
        # Try listing
        with ssh_manager.get_connection() as ssh:
            sftp = ssh.open_sftp()
            items = sftp.listdir_attr(path)
            
            file_list = []
            for item in items:
                file_list.append({
                    'name': item.filename,
                    'size': item.st_size,
                    'is_dir': item.st_mode & 0o040000 != 0
                })
            
            return JsonResponse({
                'success': True,
                'path': path,
                'items': file_list,
                'count': len(file_list)
            })
            
    except Exception as e:
        logger.error(f"Directory listing test failed: {e}")
        return JsonResponse({
            'error': str(e),
            'path': path
        }, status=500)