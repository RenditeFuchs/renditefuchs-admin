"""
File Manager for secure server file operations
Provides high-level file operations with security validation
"""

import os
import logging
import time
import mimetypes
from typing import Dict, List, Optional, Tuple, Union
from django.contrib.auth.models import User
from django.utils import timezone
from django.http import HttpRequest
from .ssh_manager import SecureSSHManager, SSHConnectionError, ssh_pool
from .security import ServerPathValidator, FileOperationTracker, RateLimiter, SecurityException
from .models import MonitoringSettings

logger = logging.getLogger(__name__)


class FileManagerError(Exception):
    """File manager related errors"""
    pass


class SecureFileManager:
    """
    Secure file manager with validation and audit logging
    """
    
    def __init__(self, user: User, request: HttpRequest = None):
        self.user = user
        self.request = request
        self.ip_address = self._get_ip_address()
        self.user_agent = self._get_user_agent()
        self.session_id = self._get_session_id()
        
        # Initialize security components
        self.validator = ServerPathValidator(user, self.ip_address, self.user_agent)
        self.tracker = FileOperationTracker(user, self.ip_address, self.user_agent, self.session_id)
        self.rate_limiter = RateLimiter(user)
        
        # Settings
        self.settings = MonitoringSettings.get_settings()
        
        # SSH manager will be initialized when needed
        self.ssh_manager = None
    
    def __enter__(self):
        """Context manager entry"""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.ssh_manager:
            self.ssh_manager.disconnect()
    
    def list_directory(self, path: str) -> Dict:
        """
        List directory contents with security validation
        
        Args:
            path: Directory path to list
            
        Returns:
            Dictionary with directory contents and metadata
        """
        start_time = time.time()
        
        try:
            # Check rate limiting
            is_limited, limit_message = self.rate_limiter.is_rate_limited('list')
            if is_limited:
                self.rate_limiter.record_rate_limit_violation(limit_message)
                raise FileManagerError(f"Rate limit exceeded: {limit_message}")
            
            # Validate path
            is_valid, error_message = self.validator.validate_path(path, 'list')
            if not is_valid:
                self.tracker.track_operation(
                    'list', path, 'blocked', 
                    error_message=error_message,
                    execution_time=(time.time() - start_time) * 1000
                )
                raise FileManagerError(error_message)
            
            # Get SSH connection
            ssh_manager = self._get_ssh_manager()
            
            # List directory
            items = ssh_manager.list_directory(path)
            
            # Filter items based on permissions
            filtered_items = []
            for item in items:
                item_path = item['path']
                item_is_valid, _ = self.validator.validate_path(item_path, 'read')
                if item_is_valid:
                    # Add additional metadata
                    item.update({
                        'can_read': True,
                        'can_write': self.validator.validate_path(item_path, 'write')[0],
                        'can_delete': self.validator.validate_path(item_path, 'delete')[0],
                        'risk_score': self.validator.calculate_risk_score(item_path, 'read'),
                        'file_type': self._get_file_type(item['name']),
                        'is_safe': self._is_file_safe(item['name']),
                    })
                    filtered_items.append(item)
            
            # Track operation
            execution_time = (time.time() - start_time) * 1000
            self.tracker.track_operation(
                'list', path, 'success',
                execution_time=execution_time,
                metadata={
                    'item_count': len(filtered_items),
                    'total_items': len(items),
                    'filtered_items': len(items) - len(filtered_items)
                }
            )
            
            return {
                'path': path,
                'parent_path': os.path.dirname(path) if path != '/' else None,
                'items': filtered_items,
                'total_items': len(filtered_items),
                'can_write': self.validator.validate_path(path, 'write')[0],
                'can_create': self.validator.validate_path(path, 'write')[0],
                'execution_time': execution_time,
            }
            
        except SSHConnectionError as e:
            self.tracker.track_operation(
                'list', path, 'failed',
                error_message=str(e),
                execution_time=(time.time() - start_time) * 1000
            )
            raise FileManagerError(f"SSH error: {str(e)}")
            
        except Exception as e:
            self.tracker.track_operation(
                'list', path, 'failed',
                error_message=str(e),
                execution_time=(time.time() - start_time) * 1000
            )
            logger.error(f"Error listing directory {path}: {str(e)}")
            raise FileManagerError(f"Error listing directory: {str(e)}")
    
    def read_file(self, file_path: str, max_size: int = None) -> Dict:
        """
        Read file content with security validation
        
        Args:
            file_path: Path to file
            max_size: Maximum file size to read
            
        Returns:
            Dictionary with file content and metadata
        """
        start_time = time.time()
        
        try:
            # Check rate limiting
            is_limited, limit_message = self.rate_limiter.is_rate_limited('read')
            if is_limited:
                self.rate_limiter.record_rate_limit_violation(limit_message)
                raise FileManagerError(f"Rate limit exceeded: {limit_message}")
            
            # Validate path
            is_valid, error_message = self.validator.validate_path(file_path, 'read')
            if not is_valid:
                self.tracker.track_operation(
                    'read', file_path, 'blocked',
                    error_message=error_message,
                    execution_time=(time.time() - start_time) * 1000
                )
                raise FileManagerError(error_message)
            
            # Get SSH connection
            ssh_manager = self._get_ssh_manager()
            
            # Get file info first
            file_info = ssh_manager.get_file_info(file_path)
            
            # Check if it's a file
            if file_info['is_dir']:
                raise FileManagerError("Cannot read directory as file")
            
            # Check file size
            max_size = max_size or (10 * 1024 * 1024)  # 10MB default
            if file_info['size'] > max_size:
                raise FileManagerError(f"File too large: {file_info['size']} bytes")
            
            # Read file content
            content = ssh_manager.read_file(file_path, max_size)
            
            # Track operation
            execution_time = (time.time() - start_time) * 1000
            self.tracker.track_operation(
                'read', file_path, 'success',
                file_size=file_info['size'],
                execution_time=execution_time,
                metadata={
                    'file_type': self._get_file_type(file_info['name']),
                    'encoding': self._detect_encoding(content),
                    'line_count': len(content.splitlines()) if content else 0,
                }
            )
            
            return {
                'path': file_path,
                'name': file_info['name'],
                'content': content,
                'size': file_info['size'],
                'modified': file_info['modified'],
                'permissions': file_info['permissions'],
                'file_type': self._get_file_type(file_info['name']),
                'is_safe': self._is_file_safe(file_info['name']),
                'can_write': self.validator.validate_path(file_path, 'write')[0],
                'can_delete': self.validator.validate_path(file_path, 'delete')[0],
                'execution_time': execution_time,
            }
            
        except SSHConnectionError as e:
            self.tracker.track_operation(
                'read', file_path, 'failed',
                error_message=str(e),
                execution_time=(time.time() - start_time) * 1000
            )
            raise FileManagerError(f"SSH error: {str(e)}")
            
        except Exception as e:
            self.tracker.track_operation(
                'read', file_path, 'failed',
                error_message=str(e),
                execution_time=(time.time() - start_time) * 1000
            )
            logger.error(f"Error reading file {file_path}: {str(e)}")
            raise FileManagerError(f"Error reading file: {str(e)}")
    
    def write_file(self, file_path: str, content: str, backup: bool = True) -> Dict:
        """
        Write file content with security validation
        
        Args:
            file_path: Path to file
            content: Content to write
            backup: Whether to create backup
            
        Returns:
            Dictionary with operation result
        """
        start_time = time.time()
        
        try:
            # Check rate limiting
            is_limited, limit_message = self.rate_limiter.is_rate_limited('write')
            if is_limited:
                self.rate_limiter.record_rate_limit_violation(limit_message)
                raise FileManagerError(f"Rate limit exceeded: {limit_message}")
            
            # Validate path
            is_valid, error_message = self.validator.validate_path(file_path, 'write')
            if not is_valid:
                self.tracker.track_operation(
                    'write', file_path, 'blocked',
                    error_message=error_message,
                    execution_time=(time.time() - start_time) * 1000
                )
                raise FileManagerError(error_message)
            
            # Validate content
            if not self._is_content_safe(content):
                error_message = "Content contains potentially dangerous code"
                self.tracker.track_operation(
                    'write', file_path, 'blocked',
                    error_message=error_message,
                    execution_time=(time.time() - start_time) * 1000
                )
                raise FileManagerError(error_message)
            
            # Get SSH connection
            ssh_manager = self._get_ssh_manager()
            
            # Write file
            success = ssh_manager.write_file(file_path, content, backup)
            
            if success:
                # Track operation
                execution_time = (time.time() - start_time) * 1000
                self.tracker.track_operation(
                    'write', file_path, 'success',
                    file_size=len(content.encode('utf-8')),
                    execution_time=execution_time,
                    metadata={
                        'backup_created': backup,
                        'content_length': len(content),
                        'line_count': len(content.splitlines()),
                    }
                )
                
                return {
                    'path': file_path,
                    'success': True,
                    'size': len(content.encode('utf-8')),
                    'backup_created': backup,
                    'execution_time': execution_time,
                }
            else:
                raise FileManagerError("Failed to write file")
                
        except SSHConnectionError as e:
            self.tracker.track_operation(
                'write', file_path, 'failed',
                error_message=str(e),
                execution_time=(time.time() - start_time) * 1000
            )
            raise FileManagerError(f"SSH error: {str(e)}")
            
        except Exception as e:
            self.tracker.track_operation(
                'write', file_path, 'failed',
                error_message=str(e),
                execution_time=(time.time() - start_time) * 1000
            )
            logger.error(f"Error writing file {file_path}: {str(e)}")
            raise FileManagerError(f"Error writing file: {str(e)}")
    
    def delete_file(self, file_path: str, confirm: bool = False) -> Dict:
        """
        Delete file with security validation
        
        Args:
            file_path: Path to file
            confirm: Confirmation for deletion
            
        Returns:
            Dictionary with operation result
        """
        start_time = time.time()
        
        try:
            # Check rate limiting
            is_limited, limit_message = self.rate_limiter.is_rate_limited('delete')
            if is_limited:
                self.rate_limiter.record_rate_limit_violation(limit_message)
                raise FileManagerError(f"Rate limit exceeded: {limit_message}")
            
            # Validate path
            is_valid, error_message = self.validator.validate_path(file_path, 'delete')
            if not is_valid:
                self.tracker.track_operation(
                    'delete', file_path, 'blocked',
                    error_message=error_message,
                    execution_time=(time.time() - start_time) * 1000
                )
                raise FileManagerError(error_message)
            
            # Check if confirmation is required
            risk_score = self.validator.calculate_risk_score(file_path, 'delete')
            if risk_score >= 50 and not confirm:
                raise FileManagerError("Confirmation required for high-risk deletion")
            
            # Get SSH connection
            ssh_manager = self._get_ssh_manager()
            
            # Get file info before deletion
            file_info = ssh_manager.get_file_info(file_path)
            
            # Delete file
            success = ssh_manager.delete_file(file_path)
            
            if success:
                # Track operation
                execution_time = (time.time() - start_time) * 1000
                self.tracker.track_operation(
                    'delete', file_path, 'success',
                    file_size=file_info['size'],
                    execution_time=execution_time,
                    metadata={
                        'file_type': self._get_file_type(file_info['name']),
                        'risk_score': risk_score,
                        'confirmed': confirm,
                    }
                )
                
                return {
                    'path': file_path,
                    'success': True,
                    'size': file_info['size'],
                    'execution_time': execution_time,
                }
            else:
                raise FileManagerError("Failed to delete file")
                
        except SSHConnectionError as e:
            self.tracker.track_operation(
                'delete', file_path, 'failed',
                error_message=str(e),
                execution_time=(time.time() - start_time) * 1000
            )
            raise FileManagerError(f"SSH error: {str(e)}")
            
        except Exception as e:
            self.tracker.track_operation(
                'delete', file_path, 'failed',
                error_message=str(e),
                execution_time=(time.time() - start_time) * 1000
            )
            logger.error(f"Error deleting file {file_path}: {str(e)}")
            raise FileManagerError(f"Error deleting file: {str(e)}")
    
    def create_directory(self, dir_path: str) -> Dict:
        """
        Create directory with security validation
        
        Args:
            dir_path: Directory path to create
            
        Returns:
            Dictionary with operation result
        """
        start_time = time.time()
        
        try:
            # Check rate limiting
            is_limited, limit_message = self.rate_limiter.is_rate_limited('create')
            if is_limited:
                self.rate_limiter.record_rate_limit_violation(limit_message)
                raise FileManagerError(f"Rate limit exceeded: {limit_message}")
            
            # Validate path
            is_valid, error_message = self.validator.validate_path(dir_path, 'write')
            if not is_valid:
                self.tracker.track_operation(
                    'create', dir_path, 'blocked',
                    error_message=error_message,
                    execution_time=(time.time() - start_time) * 1000
                )
                raise FileManagerError(error_message)
            
            # Get SSH connection
            ssh_manager = self._get_ssh_manager()
            
            # Create directory
            success = ssh_manager.create_directory(dir_path)
            
            if success:
                # Track operation
                execution_time = (time.time() - start_time) * 1000
                self.tracker.track_operation(
                    'create', dir_path, 'success',
                    execution_time=execution_time,
                    metadata={'type': 'directory'}
                )
                
                return {
                    'path': dir_path,
                    'success': True,
                    'execution_time': execution_time,
                }
            else:
                raise FileManagerError("Failed to create directory")
                
        except SSHConnectionError as e:
            self.tracker.track_operation(
                'create', dir_path, 'failed',
                error_message=str(e),
                execution_time=(time.time() - start_time) * 1000
            )
            raise FileManagerError(f"SSH error: {str(e)}")
            
        except Exception as e:
            self.tracker.track_operation(
                'create', dir_path, 'failed',
                error_message=str(e),
                execution_time=(time.time() - start_time) * 1000
            )
            logger.error(f"Error creating directory {dir_path}: {str(e)}")
            raise FileManagerError(f"Error creating directory: {str(e)}")
    
    def get_file_info(self, file_path: str) -> Dict:
        """
        Get file information with security validation
        
        Args:
            file_path: Path to file
            
        Returns:
            Dictionary with file information
        """
        start_time = time.time()
        
        try:
            # Validate path
            is_valid, error_message = self.validator.validate_path(file_path, 'read')
            if not is_valid:
                raise FileManagerError(error_message)
            
            # Get SSH connection
            ssh_manager = self._get_ssh_manager()
            
            # Get file info
            file_info = ssh_manager.get_file_info(file_path)
            
            # Add security information
            file_info.update({
                'can_read': True,
                'can_write': self.validator.validate_path(file_path, 'write')[0],
                'can_delete': self.validator.validate_path(file_path, 'delete')[0],
                'risk_score': self.validator.calculate_risk_score(file_path, 'read'),
                'file_type': self._get_file_type(file_info['name']),
                'is_safe': self._is_file_safe(file_info['name']),
                'execution_time': (time.time() - start_time) * 1000,
            })
            
            return file_info
            
        except SSHConnectionError as e:
            raise FileManagerError(f"SSH error: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {str(e)}")
            raise FileManagerError(f"Error getting file info: {str(e)}")
    
    def _get_ssh_manager(self) -> SecureSSHManager:
        """Get SSH manager instance"""
        if not self.ssh_manager:
            self.ssh_manager = ssh_pool.get_connection(self.user, self.ip_address)
            if not self.ssh_manager.connection:
                self.ssh_manager.connect()
        return self.ssh_manager
    
    def _get_ip_address(self) -> str:
        """Get user's IP address from request"""
        if not self.request:
            return '127.0.0.1'
        
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return self.request.META.get('REMOTE_ADDR', '127.0.0.1')
    
    def _get_user_agent(self) -> str:
        """Get user agent from request"""
        if not self.request:
            return 'Unknown'
        return self.request.META.get('HTTP_USER_AGENT', 'Unknown')
    
    def _get_session_id(self) -> str:
        """Get session ID from request"""
        if not self.request:
            return ''
        return self.request.session.session_key or ''
    
    def _get_file_type(self, filename: str) -> str:
        """Get file type from filename"""
        if not filename or '.' not in filename:
            return 'unknown'
        
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type:
            return mime_type.split('/')[0]
        
        ext = os.path.splitext(filename)[1].lower()
        type_map = {
            '.txt': 'text',
            '.md': 'text',
            '.html': 'text',
            '.css': 'text',
            '.js': 'text',
            '.py': 'text',
            '.php': 'text',
            '.json': 'data',
            '.xml': 'data',
            '.yaml': 'data',
            '.yml': 'data',
            '.conf': 'config',
            '.config': 'config',
            '.log': 'log',
            '.jpg': 'image',
            '.jpeg': 'image',
            '.png': 'image',
            '.gif': 'image',
            '.pdf': 'document',
            '.doc': 'document',
            '.docx': 'document',
        }
        
        return type_map.get(ext, 'unknown')
    
    def _is_file_safe(self, filename: str) -> bool:
        """Check if file is safe to access"""
        if not filename:
            return True
        
        # Check against validator
        return self.validator._is_file_safe(filename, 'read')
    
    def _is_content_safe(self, content: str) -> bool:
        """Check if content is safe to write"""
        if not content:
            return True
        
        # Check for dangerous patterns in content
        dangerous_patterns = [
            r'rm\s+-rf\s+/',  # Dangerous rm commands
            r'sudo\s+rm',     # Sudo rm
            r'chmod\s+777',   # Dangerous permissions
            r'>/dev/null',    # Redirecting to /dev/null
            r'eval\s*\(',     # Eval functions
            r'exec\s*\(',     # Exec functions
            r'system\s*\(',   # System calls
            r'shell_exec',    # Shell execution
            r'passthru',      # Pass through to shell
            r'<script',       # Script tags
            r'javascript:',   # JavaScript URLs
            r'vbscript:',     # VBScript URLs
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return False
        
        return True
    
    def _detect_encoding(self, content: str) -> str:
        """Detect content encoding"""
        try:
            # Try to encode as UTF-8
            content.encode('utf-8')
            return 'utf-8'
        except UnicodeEncodeError:
            return 'unknown'