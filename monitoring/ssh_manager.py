"""
SSH Manager for secure server connections
Handles SSH connections, command execution, and file operations
"""

import os
import logging
import paramiko
import socket
import threading
from typing import Dict, List, Optional, Tuple, Union
from contextlib import contextmanager
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from .models import SecurityLog, MonitoringSettings
from .security import SecurityException

logger = logging.getLogger(__name__)


class SSHConnectionError(Exception):
    """SSH connection related errors"""
    pass


class SecureSSHManager:
    """
    Manages secure SSH connections to the server
    """
    
    def __init__(self, user: User, ip_address: str = None):
        self.user = user
        self.ip_address = ip_address
        self.settings = MonitoringSettings.get_settings()
        self.connection = None
        self.sftp = None
        self._lock = threading.Lock()
        
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
        
    def connect(self) -> bool:
        """
        Establish SSH connection to server
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self._lock:
                if self.connection and self.connection.get_transport() and self.connection.get_transport().is_active():
                    return True
                
                self.connection = paramiko.SSHClient()
                self.connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # SSH connection parameters
                ssh_config = {
                    'hostname': self.settings.ssh_host,
                    'port': self.settings.ssh_port,
                    'username': self.settings.ssh_user,
                    'timeout': 30,
                    'banner_timeout': 30,
                    'auth_timeout': 30,
                    'compress': True,
                }
                
                # Add key-based authentication
                if self.settings.ssh_key_path:
                    key_path = os.path.expanduser(self.settings.ssh_key_path)
                    if os.path.exists(key_path):
                        ssh_config['key_filename'] = key_path
                    else:
                        logger.error(f"SSH key file not found: {key_path}")
                        raise SSHConnectionError("SSH key file not found")
                
                # Establish connection
                self.connection.connect(**ssh_config)
                
                # Test connection
                self.connection.exec_command('echo "Connection test"')
                
                # Log successful connection
                self._log_security_event(
                    'ssh_connection',
                    f"SSH connection established to {self.settings.ssh_host}",
                    'info'
                )
                
                return True
                
        except paramiko.AuthenticationException as e:
            logger.error(f"SSH authentication failed: {str(e)}")
            self._log_security_event(
                'login_failed',
                f"SSH authentication failed: {str(e)}",
                'error'
            )
            raise SSHConnectionError(f"Authentication failed: {str(e)}")
            
        except paramiko.SSHException as e:
            logger.error(f"SSH connection error: {str(e)}")
            self._log_security_event(
                'ssh_connection',
                f"SSH connection error: {str(e)}",
                'error'
            )
            raise SSHConnectionError(f"SSH connection error: {str(e)}")
            
        except socket.error as e:
            logger.error(f"Network error: {str(e)}")
            raise SSHConnectionError(f"Network error: {str(e)}")
            
        except Exception as e:
            logger.error(f"Unexpected SSH error: {str(e)}")
            raise SSHConnectionError(f"Unexpected error: {str(e)}")
    
    def disconnect(self):
        """Close SSH connection"""
        try:
            with self._lock:
                if self.sftp:
                    self.sftp.close()
                    self.sftp = None
                    
                if self.connection:
                    self.connection.close()
                    self.connection = None
                    
                self._log_security_event(
                    'ssh_connection',
                    "SSH connection closed",
                    'info'
                )
                
        except Exception as e:
            logger.error(f"Error closing SSH connection: {str(e)}")
    
    def execute_command(self, command: str, timeout: int = 30) -> Tuple[str, str, int]:
        """
        Execute command on remote server
        
        Args:
            command: Command to execute
            timeout: Command timeout in seconds
            
        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        try:
            if not self.connection:
                raise SSHConnectionError("Not connected to server")
            
            # Security check - only allow safe commands
            if not self._is_command_safe(command):
                raise SecurityException(f"Command not allowed: {command}")
            
            # Execute command
            stdin, stdout, stderr = self.connection.exec_command(command, timeout=timeout)
            
            # Read output
            stdout_data = stdout.read().decode('utf-8')
            stderr_data = stderr.read().decode('utf-8')
            exit_code = stdout.channel.recv_exit_status()
            
            # Log command execution
            self._log_security_event(
                'admin_action',
                f"Command executed: {command}",
                'info' if exit_code == 0 else 'warning'
            )
            
            return stdout_data, stderr_data, exit_code
            
        except paramiko.SSHException as e:
            logger.error(f"SSH command execution error: {str(e)}")
            raise SSHConnectionError(f"Command execution error: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            raise
    
    def get_sftp(self) -> paramiko.SFTPClient:
        """
        Get SFTP client for file operations
        
        Returns:
            SFTP client instance
        """
        try:
            if not self.connection:
                raise SSHConnectionError("Not connected to server")
            
            if not self.sftp:
                self.sftp = self.connection.open_sftp()
            
            return self.sftp
            
        except Exception as e:
            logger.error(f"Error getting SFTP client: {str(e)}")
            raise SSHConnectionError(f"SFTP error: {str(e)}")
    
    def list_directory(self, path: str) -> List[Dict]:
        """
        List directory contents
        
        Args:
            path: Directory path to list
            
        Returns:
            List of file/directory information
        """
        try:
            sftp = self.get_sftp()
            
            # List directory
            items = []
            for item in sftp.listdir_attr(path):
                item_info = {
                    'name': item.filename,
                    'path': os.path.join(path, item.filename),
                    'size': item.st_size,
                    'is_dir': self._is_directory(item),
                    'is_file': not self._is_directory(item),
                    'permissions': oct(item.st_mode)[-3:],
                    'modified': timezone.datetime.fromtimestamp(item.st_mtime),
                    'owner': item.st_uid,
                    'group': item.st_gid,
                }
                items.append(item_info)
            
            # Sort: directories first, then files
            items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            
            return items
            
        except FileNotFoundError:
            raise SSHConnectionError(f"Directory not found: {path}")
        except PermissionError:
            raise SSHConnectionError(f"Permission denied: {path}")
        except Exception as e:
            logger.error(f"Error listing directory {path}: {str(e)}")
            raise SSHConnectionError(f"Error listing directory: {str(e)}")
    
    def read_file(self, file_path: str, max_size: int = 10 * 1024 * 1024) -> str:
        """
        Read file content from server
        
        Args:
            file_path: Path to file
            max_size: Maximum file size to read (default 10MB)
            
        Returns:
            File content as string
        """
        try:
            sftp = self.get_sftp()
            
            # Check file size
            file_stat = sftp.stat(file_path)
            if file_stat.st_size > max_size:
                raise SSHConnectionError(f"File too large: {file_stat.st_size} bytes")
            
            # Read file
            with sftp.open(file_path, 'r') as f:
                content = f.read()
            
            return content
            
        except FileNotFoundError:
            raise SSHConnectionError(f"File not found: {file_path}")
        except PermissionError:
            raise SSHConnectionError(f"Permission denied: {file_path}")
        except UnicodeDecodeError:
            raise SSHConnectionError("File is not text or uses unsupported encoding")
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            raise SSHConnectionError(f"Error reading file: {str(e)}")
    
    def write_file(self, file_path: str, content: str, backup: bool = True) -> bool:
        """
        Write content to file on server
        
        Args:
            file_path: Path to file
            content: Content to write
            backup: Whether to create backup
            
        Returns:
            True if successful
        """
        try:
            sftp = self.get_sftp()
            
            # Create backup if requested and file exists
            if backup and self._file_exists(file_path):
                backup_path = f"{file_path}.backup_{int(timezone.now().timestamp())}"
                try:
                    sftp.rename(file_path, backup_path)
                    logger.info(f"Created backup: {backup_path}")
                except Exception as e:
                    logger.warning(f"Could not create backup: {str(e)}")
            
            # Write file
            with sftp.open(file_path, 'w') as f:
                f.write(content)
            
            return True
            
        except PermissionError:
            raise SSHConnectionError(f"Permission denied: {file_path}")
        except Exception as e:
            logger.error(f"Error writing file {file_path}: {str(e)}")
            raise SSHConnectionError(f"Error writing file: {str(e)}")
    
    def delete_file(self, file_path: str) -> bool:
        """
        Delete file from server
        
        Args:
            file_path: Path to file
            
        Returns:
            True if successful
        """
        try:
            sftp = self.get_sftp()
            sftp.remove(file_path)
            return True
            
        except FileNotFoundError:
            raise SSHConnectionError(f"File not found: {file_path}")
        except PermissionError:
            raise SSHConnectionError(f"Permission denied: {file_path}")
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {str(e)}")
            raise SSHConnectionError(f"Error deleting file: {str(e)}")
    
    def create_directory(self, dir_path: str) -> bool:
        """
        Create directory on server
        
        Args:
            dir_path: Directory path to create
            
        Returns:
            True if successful
        """
        try:
            sftp = self.get_sftp()
            sftp.mkdir(dir_path)
            return True
            
        except FileExistsError:
            raise SSHConnectionError(f"Directory already exists: {dir_path}")
        except PermissionError:
            raise SSHConnectionError(f"Permission denied: {dir_path}")
        except Exception as e:
            logger.error(f"Error creating directory {dir_path}: {str(e)}")
            raise SSHConnectionError(f"Error creating directory: {str(e)}")
    
    def get_file_info(self, file_path: str) -> Dict:
        """
        Get file/directory information
        
        Args:
            file_path: Path to file/directory
            
        Returns:
            File information dictionary
        """
        try:
            sftp = self.get_sftp()
            stat = sftp.stat(file_path)
            
            return {
                'name': os.path.basename(file_path),
                'path': file_path,
                'size': stat.st_size,
                'is_dir': self._is_directory(stat),
                'is_file': not self._is_directory(stat),
                'permissions': oct(stat.st_mode)[-3:],
                'modified': timezone.datetime.fromtimestamp(stat.st_mtime),
                'owner': stat.st_uid,
                'group': stat.st_gid,
            }
            
        except FileNotFoundError:
            raise SSHConnectionError(f"File not found: {file_path}")
        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {str(e)}")
            raise SSHConnectionError(f"Error getting file info: {str(e)}")
    
    def _is_directory(self, stat_result) -> bool:
        """Check if stat result is a directory"""
        import stat
        return stat.S_ISDIR(stat_result.st_mode)
    
    def _file_exists(self, file_path: str) -> bool:
        """Check if file exists"""
        try:
            sftp = self.get_sftp()
            sftp.stat(file_path)
            return True
        except FileNotFoundError:
            return False
    
    def _is_command_safe(self, command: str) -> bool:
        """Check if command is safe to execute"""
        # Only allow specific safe commands
        safe_commands = [
            'ls', 'cat', 'head', 'tail', 'grep', 'find', 'wc', 'du', 'df',
            'ps', 'top', 'free', 'uname', 'whoami', 'pwd', 'which', 'echo',
            'stat', 'file', 'basename', 'dirname'
        ]
        
        # Extract base command
        base_command = command.split()[0] if command.split() else ''
        
        # Check if command is in safe list
        return base_command in safe_commands
    
    def _log_security_event(self, event_type: str, message: str, severity: str = 'info'):
        """Log security event"""
        try:
            SecurityLog.objects.create(
                event_type=event_type,
                severity=severity,
                message=message,
                user_id=str(self.user.id),
                username=self.user.username,
                ip_address=self.ip_address
            )
        except Exception as e:
            logger.error(f"Error logging security event: {str(e)}")


class SSHConnectionPool:
    """
    Pool of SSH connections for better performance
    """
    
    def __init__(self, max_connections: int = 5):
        self.max_connections = max_connections
        self.connections = {}
        self.lock = threading.Lock()
    
    def get_connection(self, user: User, ip_address: str = None) -> SecureSSHManager:
        """
        Get SSH connection from pool or create new one
        
        Args:
            user: User requesting connection
            ip_address: User's IP address
            
        Returns:
            SSH manager instance
        """
        with self.lock:
            key = f"{user.id}_{ip_address}"
            
            if key in self.connections:
                ssh_manager = self.connections[key]
                # Check if connection is still active
                if ssh_manager.connection and ssh_manager.connection.get_transport() and ssh_manager.connection.get_transport().is_active():
                    return ssh_manager
                else:
                    # Remove dead connection
                    del self.connections[key]
            
            # Create new connection
            ssh_manager = SecureSSHManager(user, ip_address)
            
            # Only add to pool if we haven't reached max connections
            if len(self.connections) < self.max_connections:
                self.connections[key] = ssh_manager
            
            return ssh_manager
    
    def close_all(self):
        """Close all connections in pool"""
        with self.lock:
            for ssh_manager in self.connections.values():
                try:
                    ssh_manager.disconnect()
                except:
                    pass
            self.connections.clear()


# Global connection pool instance
ssh_pool = SSHConnectionPool()