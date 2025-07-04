"""
Server File Management API Views
Sichere Server-Dateizugriffe über SSH mit umfassender Sicherheit
"""
import json
import os
import tempfile
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings
from .ssh_manager import SSHManager
from .security import PathValidator, RateLimiter
from django.contrib.auth.models import User
from .models import FileOperation, SecurityLog
import logging

logger = logging.getLogger('monitoring')


class ServerFileAPI(View):
    """Base class for server file operations"""
    
    def __init__(self):
        self.ssh_manager = SSHManager()
        self.path_validator = PathValidator()
        self.rate_limiter = RateLimiter()
        
    def dispatch(self, request, *args, **kwargs):
        """Add authentication and rate limiting"""
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        if not request.user.is_superuser:
            return JsonResponse({'error': 'Superuser access required'}, status=403)
        
        # Rate limiting
        if not self.rate_limiter.allow_request(request.user, request.path):
            return JsonResponse({'error': 'Rate limit exceeded'}, status=429)
        
        return super().dispatch(request, *args, **kwargs)
    
    def log_operation(self, user, operation, path, success=True, error_msg=None):
        """Log file operation"""
        try:
            FileOperation.objects.create(
                user_id=str(user.id),
                username=user.username,
                operation=operation,
                status='success' if success else 'failed',
                file_path=path,
                error_message=error_msg or '',
                ip_address=self.get_client_ip(self.request),
                user_agent=self.request.META.get('HTTP_USER_AGENT', '')
            )
        except Exception as e:
            logger.error(f"Failed to log operation: {e}")
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')


@method_decorator(login_required, name='dispatch')
class DirectoryListAPI(ServerFileAPI):
    """API for listing directory contents"""
    
    def get(self, request):
        """List directory contents"""
        path = request.GET.get('path', '/var/www')
        
        # Validate path
        if not self.path_validator.is_safe_path(path):
            self.log_operation(request.user, 'list_directory', path, success=False, error_msg='Invalid path')
            return JsonResponse({'error': 'Invalid path'}, status=400)
        
        try:
            # Connect to server and list directory
            with self.ssh_manager.get_connection() as ssh:
                sftp = ssh.open_sftp()
                
                # Get directory listing
                try:
                    items = sftp.listdir_attr(path)
                    
                    files = []
                    directories = []
                    
                    for item in items:
                        item_path = os.path.join(path, item.filename)
                        
                        # Get file stats
                        file_info = {
                            'name': item.filename,
                            'path': item_path,
                            'size': item.st_size,
                            'modified': datetime.fromtimestamp(item.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                            'permissions': oct(item.st_mode)[-3:],
                            'owner': item.st_uid,
                            'group': item.st_gid,
                        }
                        
                        # Check if it's a directory
                        if item.st_mode & 0o040000:  # S_IFDIR
                            file_info['type'] = 'directory'
                            directories.append(file_info)
                        else:
                            file_info['type'] = 'file'
                            files.append(file_info)
                    
                    # Sort by name
                    directories.sort(key=lambda x: x['name'].lower())
                    files.sort(key=lambda x: x['name'].lower())
                    
                    # Log successful operation
                    self.log_operation(request.user, 'list_directory', path, success=True)
                    
                    return JsonResponse({
                        'success': True,
                        'path': path,
                        'parent_path': os.path.dirname(path) if path != '/' else None,
                        'items': directories + files,
                        'total_items': len(directories) + len(files)
                    })
                    
                except FileNotFoundError:
                    self.log_operation(request.user, 'list_directory', path, success=False, error_msg='Directory not found')
                    return JsonResponse({'error': 'Directory not found'}, status=404)
                except PermissionError:
                    self.log_operation(request.user, 'list_directory', path, success=False, error_msg='Permission denied')
                    return JsonResponse({'error': 'Permission denied'}, status=403)
                    
        except Exception as e:
            logger.error(f"Directory listing failed: {e}")
            self.log_operation(request.user, 'list_directory', path, success=False, error_msg=str(e))
            return JsonResponse({'error': 'Server connection failed'}, status=500)


@method_decorator(login_required, name='dispatch')
class FileContentAPI(ServerFileAPI):
    """API for reading file contents"""
    
    def get(self, request):
        """Get file content"""
        file_path = request.GET.get('path')
        
        if not file_path:
            return JsonResponse({'error': 'File path required'}, status=400)
        
        # Validate path
        if not self.path_validator.is_safe_path(file_path):
            self.log_operation(request.user, 'read_file', file_path, success=False, error_msg='Invalid path')
            return JsonResponse({'error': 'Invalid path'}, status=400)
        
        try:
            with self.ssh_manager.get_connection() as ssh:
                sftp = ssh.open_sftp()
                
                try:
                    # Get file stats first
                    file_stats = sftp.stat(file_path)
                    
                    # Check file size (limit to 10MB)
                    if file_stats.st_size > 10 * 1024 * 1024:
                        return JsonResponse({'error': 'File too large (max 10MB)'}, status=413)
                    
                    # Read file content
                    with sftp.open(file_path, 'r') as file:
                        content = file.read()
                        
                        # Try to decode as UTF-8
                        try:
                            if isinstance(content, bytes):
                                content = content.decode('utf-8')
                            is_text = True
                        except UnicodeDecodeError:
                            # Binary file
                            content = f"Binary file ({file_stats.st_size} bytes)"
                            is_text = False
                    
                    # Log successful operation
                    self.log_operation(request.user, 'read_file', file_path, success=True)
                    
                    return JsonResponse({
                        'success': True,
                        'path': file_path,
                        'content': content,
                        'is_text': is_text,
                        'size': file_stats.st_size,
                        'modified': datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                except FileNotFoundError:
                    self.log_operation(request.user, 'read_file', file_path, success=False, error_msg='File not found')
                    return JsonResponse({'error': 'File not found'}, status=404)
                except PermissionError:
                    self.log_operation(request.user, 'read_file', file_path, success=False, error_msg='Permission denied')
                    return JsonResponse({'error': 'Permission denied'}, status=403)
                    
        except Exception as e:
            logger.error(f"File read failed: {e}")
            self.log_operation(request.user, 'read_file', file_path, success=False, error_msg=str(e))
            return JsonResponse({'error': 'Server connection failed'}, status=500)


@method_decorator([login_required, csrf_exempt], name='dispatch')
class FileEditAPI(ServerFileAPI):
    """API for editing file contents"""
    
    def post(self, request):
        """Save file content"""
        try:
            data = json.loads(request.body)
            file_path = data.get('path')
            content = data.get('content', '')
            
            if not file_path:
                return JsonResponse({'error': 'File path required'}, status=400)
            
            # Validate path
            if not self.path_validator.is_safe_path(file_path):
                self.log_operation(request.user, 'edit_file', file_path, success=False, error_msg='Invalid path')
                return JsonResponse({'error': 'Invalid path'}, status=400)
            
            # Check if file is editable
            if not self.path_validator.is_editable_file(file_path):
                self.log_operation(request.user, 'edit_file', file_path, success=False, error_msg='File not editable')
                return JsonResponse({'error': 'File type not editable'}, status=400)
            
            with self.ssh_manager.get_connection() as ssh:
                sftp = ssh.open_sftp()
                
                try:
                    # Create backup if file exists
                    backup_path = None
                    try:
                        sftp.stat(file_path)
                        backup_path = f"{file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        sftp.rename(file_path, backup_path)
                    except FileNotFoundError:
                        pass  # File doesn't exist, no backup needed
                    
                    # Write new content
                    with sftp.open(file_path, 'w') as file:
                        file.write(content)
                    
                    # Log successful operation
                    self.log_operation(request.user, 'edit_file', file_path, success=True)
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'File saved successfully',
                        'backup_created': backup_path is not None,
                        'backup_path': backup_path
                    })
                    
                except PermissionError:
                    self.log_operation(request.user, 'edit_file', file_path, success=False, error_msg='Permission denied')
                    return JsonResponse({'error': 'Permission denied'}, status=403)
                    
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"File edit failed: {e}")
            self.log_operation(request.user, 'edit_file', file_path, success=False, error_msg=str(e))
            return JsonResponse({'error': 'Server connection failed'}, status=500)


@method_decorator([login_required, csrf_exempt], name='dispatch')
class FileDeleteAPI(ServerFileAPI):
    """API for deleting files"""
    
    def delete(self, request):
        """Delete file or directory"""
        try:
            data = json.loads(request.body)
            file_path = data.get('path')
            
            if not file_path:
                return JsonResponse({'error': 'File path required'}, status=400)
            
            # Validate path
            if not self.path_validator.is_safe_path(file_path):
                self.log_operation(request.user, 'delete_file', file_path, success=False, error_msg='Invalid path')
                return JsonResponse({'error': 'Invalid path'}, status=400)
            
            # Check if file is deletable
            if not self.path_validator.is_deletable_path(file_path):
                self.log_operation(request.user, 'delete_file', file_path, success=False, error_msg='Path not deletable')
                return JsonResponse({'error': 'Path not deletable'}, status=400)
            
            with self.ssh_manager.get_connection() as ssh:
                sftp = ssh.open_sftp()
                
                try:
                    # Check if it's a directory
                    file_stats = sftp.stat(file_path)
                    is_directory = file_stats.st_mode & 0o040000  # S_IFDIR
                    
                    if is_directory:
                        # Remove directory (must be empty)
                        sftp.rmdir(file_path)
                        operation = 'delete_directory'
                    else:
                        # Remove file
                        sftp.remove(file_path)
                        operation = 'delete_file'
                    
                    # Log successful operation
                    self.log_operation(request.user, operation, file_path, success=True)
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'{"Directory" if is_directory else "File"} deleted successfully'
                    })
                    
                except FileNotFoundError:
                    self.log_operation(request.user, 'delete_file', file_path, success=False, error_msg='File not found')
                    return JsonResponse({'error': 'File not found'}, status=404)
                except PermissionError:
                    self.log_operation(request.user, 'delete_file', file_path, success=False, error_msg='Permission denied')
                    return JsonResponse({'error': 'Permission denied'}, status=403)
                except OSError as e:
                    if "Directory not empty" in str(e):
                        self.log_operation(request.user, 'delete_file', file_path, success=False, error_msg='Directory not empty')
                        return JsonResponse({'error': 'Directory not empty'}, status=400)
                    raise
                    
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"File delete failed: {e}")
            self.log_operation(request.user, 'delete_file', file_path, success=False, error_msg=str(e))
            return JsonResponse({'error': 'Server connection failed'}, status=500)


@method_decorator([login_required, csrf_exempt], name='dispatch')
class FileUploadAPI(ServerFileAPI):
    """API for uploading files"""
    
    def post(self, request):
        """Upload file to server"""
        try:
            target_path = request.POST.get('path')
            uploaded_file = request.FILES.get('file')
            
            if not target_path or not uploaded_file:
                return JsonResponse({'error': 'Path and file required'}, status=400)
            
            # Validate path
            if not self.path_validator.is_safe_path(target_path):
                self.log_operation(request.user, 'upload_file', target_path, success=False, error_msg='Invalid path')
                return JsonResponse({'error': 'Invalid path'}, status=400)
            
            # Check file size (limit to 100MB)
            if uploaded_file.size > 100 * 1024 * 1024:
                return JsonResponse({'error': 'File too large (max 100MB)'}, status=413)
            
            # Construct full file path
            file_path = os.path.join(target_path, uploaded_file.name)
            
            with self.ssh_manager.get_connection() as ssh:
                sftp = ssh.open_sftp()
                
                try:
                    # Create temporary file
                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                        for chunk in uploaded_file.chunks():
                            temp_file.write(chunk)
                        temp_file_path = temp_file.name
                    
                    # Upload to server
                    sftp.put(temp_file_path, file_path)
                    
                    # Clean up temporary file
                    os.unlink(temp_file_path)
                    
                    # Log successful operation
                    self.log_operation(request.user, 'upload_file', file_path, success=True)
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'File uploaded successfully',
                        'path': file_path,
                        'size': uploaded_file.size
                    })
                    
                except PermissionError:
                    self.log_operation(request.user, 'upload_file', file_path, success=False, error_msg='Permission denied')
                    return JsonResponse({'error': 'Permission denied'}, status=403)
                    
        except Exception as e:
            logger.error(f"File upload failed: {e}")
            self.log_operation(request.user, 'upload_file', target_path, success=False, error_msg=str(e))
            return JsonResponse({'error': 'Server connection failed'}, status=500)


# API endpoint views
directory_list_api = DirectoryListAPI.as_view()
file_content_api = FileContentAPI.as_view()
file_edit_api = FileEditAPI.as_view()
file_delete_api = FileDeleteAPI.as_view()
file_upload_api = FileUploadAPI.as_view()