"""
Debug API für Server File Management
Testet verschiedene Komponenten der Server-Dateifunktionalität
"""
import os
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from .ssh_manager import SSHManager, SSHConnectionError
from .security import PathValidator, RateLimiter
from .models import MonitoringSettings

logger = logging.getLogger('monitoring')


@method_decorator(login_required, name='dispatch')
class DebugConfigAPI(View):
    """Debug configuration check"""
    
    def get(self, request):
        """Check configuration"""
        try:
            # Check if user has superuser access
            if not request.user.is_superuser:
                return JsonResponse({
                    'success': False,
                    'error': 'Superuser access required'
                }, status=403)
            
            # Get monitoring settings
            settings = MonitoringSettings.get_settings()
            
            # Check SSH configuration
            ssh_config = {
                'host': settings.ssh_host,
                'port': settings.ssh_port,
                'user': settings.ssh_user,
                'key_path': settings.ssh_key_path,
                'key_exists': os.path.exists(os.path.expanduser(settings.ssh_key_path)) if settings.ssh_key_path else False,
                'directory_enabled': settings.server_directory_enabled
            }
            
            return JsonResponse({
                'success': True,
                'ssh_config': ssh_config,
                'user': {
                    'username': request.user.username,
                    'is_superuser': request.user.is_superuser,
                    'is_staff': request.user.is_staff
                },
                'message': 'Configuration check successful'
            })
            
        except Exception as e:
            logger.error(f"Debug config check failed: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


@method_decorator(login_required, name='dispatch')  
class DebugSSHAPI(View):
    """Debug SSH connection"""
    
    def get(self, request):
        """Test SSH connection"""
        try:
            if not request.user.is_superuser:
                return JsonResponse({
                    'success': False,
                    'error': 'Superuser access required'
                }, status=403)
            
            # Test SSH connection
            ssh_manager = SSHManager()
            
            try:
                with ssh_manager.get_connection() as ssh:
                    # Test command execution
                    stdin, stdout, stderr = ssh.exec_command('echo "SSH connection test"')
                    output = stdout.read().decode('utf-8').strip()
                    
                    if output == "SSH connection test":
                        return JsonResponse({
                            'success': True,
                            'message': 'SSH connection successful',
                            'test_output': output
                        })
                    else:
                        return JsonResponse({
                            'success': False,
                            'error': f'Unexpected output: {output}'
                        })
                        
            except SSHConnectionError as e:
                return JsonResponse({
                    'success': False,
                    'error': f'SSH connection failed: {str(e)}'
                })
                
        except Exception as e:
            logger.error(f"Debug SSH test failed: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


@method_decorator(login_required, name='dispatch')
class DebugDirectoryAPI(View):
    """Debug directory listing"""
    
    def get(self, request):
        """Test directory listing"""
        try:
            if not request.user.is_superuser:
                return JsonResponse({
                    'success': False,
                    'error': 'Superuser access required'
                }, status=403)
            
            # Get path parameter
            path = request.GET.get('path', '/var/www')
            
            # Validate path
            path_validator = PathValidator()
            if not path_validator.is_safe_path(path):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid or unsafe path'
                })
            
            # Test directory listing via SSH
            ssh_manager = SSHManager()
            
            try:
                with ssh_manager.get_connection() as ssh:
                    sftp = ssh.open_sftp()
                    
                    # List directory
                    items = sftp.listdir_attr(path)
                    
                    # Count items by type
                    files = 0
                    directories = 0
                    
                    for item in items:
                        if item.st_mode & 0o040000:  # Directory
                            directories += 1
                        else:
                            files += 1
                    
                    return JsonResponse({
                        'success': True,
                        'path': path,
                        'count': len(items),
                        'files': files,
                        'directories': directories,
                        'message': f'Directory listing successful: {len(items)} items found'
                    })
                    
            except FileNotFoundError:
                return JsonResponse({
                    'success': False,
                    'error': f'Directory not found: {path}'
                })
            except PermissionError:
                return JsonResponse({
                    'success': False,
                    'error': f'Permission denied: {path}'
                })
            except SSHConnectionError as e:
                return JsonResponse({
                    'success': False,
                    'error': f'SSH connection failed: {str(e)}'
                })
                
        except Exception as e:
            logger.error(f"Debug directory test failed: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


@method_decorator(login_required, name='dispatch')
class DebugSecurityAPI(View):
    """Debug security systems"""
    
    def get(self, request):
        """Test security systems"""
        try:
            if not request.user.is_superuser:
                return JsonResponse({
                    'success': False,
                    'error': 'Superuser access required'
                }, status=403)
            
            # Test path validator
            path_validator = PathValidator()
            rate_limiter = RateLimiter()
            
            # Test various paths
            test_paths = [
                '/var/www/',
                '/var/www/test/',
                '/etc/passwd',  # Should be blocked
                '../../../etc/passwd',  # Should be blocked
                '/var/www/test/file.txt'
            ]
            
            path_results = {}
            for test_path in test_paths:
                path_results[test_path] = {
                    'safe': path_validator.is_safe_path(test_path),
                    'editable': path_validator.is_editable_file(test_path),
                    'deletable': path_validator.is_deletable_path(test_path)
                }
            
            # Test rate limiter
            rate_limit_test = rate_limiter.allow_request(request.user, '/test/endpoint')
            
            return JsonResponse({
                'success': True,
                'path_validation': path_results,
                'rate_limit_allows': rate_limit_test,
                'message': 'Security tests completed'
            })
            
        except Exception as e:
            logger.error(f"Debug security test failed: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


@method_decorator(login_required, name='dispatch')
class DebugFullTestAPI(View):
    """Run full debug test suite"""
    
    def get(self, request):
        """Run all debug tests"""
        try:
            if not request.user.is_superuser:
                return JsonResponse({
                    'success': False,
                    'error': 'Superuser access required'
                }, status=403)
            
            results = {}
            
            # Test 1: Configuration
            try:
                config_api = DebugConfigAPI()
                config_response = config_api.get(request)
                config_data = config_response.content.decode('utf-8')
                results['config'] = {
                    'success': config_response.status_code == 200,
                    'data': config_data
                }
            except Exception as e:
                results['config'] = {
                    'success': False,
                    'error': str(e)
                }
            
            # Test 2: SSH Connection
            try:
                ssh_api = DebugSSHAPI()
                ssh_response = ssh_api.get(request)
                ssh_data = ssh_response.content.decode('utf-8')
                results['ssh'] = {
                    'success': ssh_response.status_code == 200,
                    'data': ssh_data
                }
            except Exception as e:
                results['ssh'] = {
                    'success': False,
                    'error': str(e)
                }
            
            # Test 3: Directory Listing
            try:
                dir_api = DebugDirectoryAPI()
                dir_response = dir_api.get(request)
                dir_data = dir_response.content.decode('utf-8')
                results['directory'] = {
                    'success': dir_response.status_code == 200,
                    'data': dir_data
                }
            except Exception as e:
                results['directory'] = {
                    'success': False,
                    'error': str(e)
                }
            
            # Test 4: Security
            try:
                security_api = DebugSecurityAPI()
                security_response = security_api.get(request)
                security_data = security_response.content.decode('utf-8')
                results['security'] = {
                    'success': security_response.status_code == 200,
                    'data': security_data
                }
            except Exception as e:
                results['security'] = {
                    'success': False,
                    'error': str(e)
                }
            
            # Calculate overall success
            all_success = all(result['success'] for result in results.values())
            
            return JsonResponse({
                'success': all_success,
                'tests': results,
                'message': f'Debug test suite completed. {len([r for r in results.values() if r["success"]])}/{len(results)} tests passed.'
            })
            
        except Exception as e:
            logger.error(f"Debug full test failed: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


# View functions for URL routing
debug_config_api = DebugConfigAPI.as_view()
debug_ssh_api = DebugSSHAPI.as_view()
debug_directory_api = DebugDirectoryAPI.as_view()
debug_security_api = DebugSecurityAPI.as_view()
debug_full_test_api = DebugFullTestAPI.as_view()