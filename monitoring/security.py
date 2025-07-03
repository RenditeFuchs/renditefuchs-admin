"""
Security module for server directory access
Provides path validation, security checks, and access control
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User
from .models import ServerPath, SecurityLog, FileOperation, MonitoringSettings

logger = logging.getLogger(__name__)


class SecurityException(Exception):
    """Custom exception for security violations"""
    pass


class ServerPathValidator:
    """
    Validates server paths and enforces security policies
    """
    
    # Dangerous path patterns to block
    DANGEROUS_PATTERNS = [
        r'\.\./',  # Path traversal
        r'\.\.\\',  # Windows path traversal
        r'/etc/',  # System config
        r'/var/log/',  # System logs
        r'/root/',  # Root directory
        r'/home/(?!ubuntu)',  # Other user homes
        r'/bin/',  # System binaries
        r'/sbin/',  # System binaries
        r'/usr/bin/',  # User binaries
        r'/usr/sbin/',  # User binaries
        r'/proc/',  # Process filesystem
        r'/sys/',  # System filesystem
        r'/dev/',  # Device files
        r'/tmp/',  # Temporary files
        r'\.ssh/',  # SSH keys
        r'\.git/',  # Git repositories (sensitive)
        r'\.env',  # Environment files
        r'\.key',  # Key files
        r'\.pem',  # Certificate files
        r'\.crt',  # Certificate files
        r'password',  # Password files
        r'secret',  # Secret files
        r'private',  # Private files
    ]
    
    # Allowed base paths for server access
    ALLOWED_BASE_PATHS = [
        '/var/www/',
        '/home/ubuntu/',
    ]
    
    # Dangerous file extensions
    DANGEROUS_EXTENSIONS = [
        '.sh', '.bash', '.zsh', '.fish',  # Shell scripts
        '.py', '.php', '.js', '.rb',  # Scripts (unless explicitly allowed)
        '.exe', '.bin', '.so', '.dll',  # Binaries
        '.key', '.pem', '.crt', '.p12',  # Certificates
        '.sql', '.dump', '.backup',  # Database files
        '.passwd', '.shadow', '.htpasswd',  # Password files
    ]
    
    # Safe file extensions for viewing/editing
    SAFE_EXTENSIONS = [
        '.txt', '.md', '.html', '.css', '.scss',
        '.json', '.xml', '.yaml', '.yml',
        '.conf', '.config', '.ini', '.properties',
        '.log', '.csv', '.tsv',
    ]
    
    def __init__(self, user: User, ip_address: str = None, user_agent: str = None):
        self.user = user
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.settings = MonitoringSettings.get_settings()
        
    def validate_path(self, path: str, operation: str = 'read') -> Tuple[bool, str]:
        """
        Validate a server path for security
        
        Args:
            path: The path to validate
            operation: The operation type (read, write, delete, etc.)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Normalize path
            normalized_path = self._normalize_path(path)
            
            # Check for dangerous patterns
            if self._contains_dangerous_pattern(normalized_path):
                self._log_security_event(
                    'path_traversal',
                    f"Dangerous path pattern detected: {path}",
                    'critical'
                )
                return False, "Pfad enthält verdächtige Muster"
            
            # Check if path is in allowed base paths
            if not self._is_in_allowed_base_path(normalized_path):
                self._log_security_event(
                    'unauthorized_access',
                    f"Access to restricted path: {path}",
                    'warning'
                )
                return False, "Zugriff auf diesen Pfad ist nicht erlaubt"
            
            # Check configured server paths
            server_path = self._get_server_path_config(normalized_path)
            if server_path:
                if not server_path.allows_operation(operation):
                    self._log_security_event(
                        'permission_denied',
                        f"Operation {operation} not allowed on {path}",
                        'warning'
                    )
                    return False, f"Operation '{operation}' ist für diesen Pfad nicht erlaubt"
                
                if server_path.require_admin and not self.user.is_superuser:
                    self._log_security_event(
                        'unauthorized_access',
                        f"Admin required for {path}",
                        'warning'
                    )
                    return False, "Administrator-Berechtigung erforderlich"
            
            # Check file extension if it's a file
            if os.path.isfile(normalized_path) or '.' in os.path.basename(normalized_path):
                filename = os.path.basename(normalized_path)
                if not self._is_file_safe(filename, operation):
                    self._log_security_event(
                        'malicious_file',
                        f"Dangerous file access attempt: {filename}",
                        'error'
                    )
                    return False, "Dateityp ist nicht erlaubt"
            
            # Path is valid
            return True, ""
            
        except Exception as e:
            logger.error(f"Error validating path {path}: {str(e)}")
            self._log_security_event(
                'system_alert',
                f"Path validation error: {str(e)}",
                'error'
            )
            return False, "Fehler bei der Pfad-Validierung"
    
    def calculate_risk_score(self, path: str, operation: str) -> int:
        """
        Calculate risk score for a path operation (0-100)
        
        Args:
            path: The path being accessed
            operation: The operation type
            
        Returns:
            Risk score (0-100)
        """
        score = 0
        
        # Base score by operation type
        operation_scores = {
            'read': 10,
            'list': 5,
            'write': 30,
            'delete': 50,
            'execute': 70,
            'upload': 40,
            'download': 20,
        }
        score += operation_scores.get(operation, 20)
        
        # Path-based risk
        if any(pattern in path.lower() for pattern in ['config', 'settings', 'database']):
            score += 20
        
        if any(pattern in path.lower() for pattern in ['production', 'live', 'prod']):
            score += 15
        
        # File extension risk
        if '.' in os.path.basename(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in self.DANGEROUS_EXTENSIONS:
                score += 25
            elif ext not in self.SAFE_EXTENSIONS:
                score += 10
        
        # User-based risk
        if not self.user.is_superuser:
            score += 10
        
        return min(score, 100)
    
    def _normalize_path(self, path: str) -> str:
        """Normalize and resolve path"""
        # Remove dangerous characters
        path = re.sub(r'[<>"|*?]', '', path)
        
        # Resolve relative paths
        path = os.path.abspath(path)
        
        # Normalize path separators
        path = os.path.normpath(path)
        
        return path
    
    def _contains_dangerous_pattern(self, path: str) -> bool:
        """Check if path contains dangerous patterns"""
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, path, re.IGNORECASE):
                return True
        return False
    
    def _is_in_allowed_base_path(self, path: str) -> bool:
        """Check if path is within allowed base paths"""
        for base_path in self.ALLOWED_BASE_PATHS:
            if path.startswith(base_path):
                return True
        return False
    
    def _get_server_path_config(self, path: str) -> Optional[ServerPath]:
        """Get server path configuration for a given path"""
        try:
            # Find the most specific matching path
            matching_paths = []
            for server_path in ServerPath.objects.filter(is_active=True):
                if path.startswith(server_path.path):
                    matching_paths.append(server_path)
            
            if matching_paths:
                # Return the most specific path (longest match)
                return max(matching_paths, key=lambda p: len(p.path))
            
        except Exception as e:
            logger.error(f"Error getting server path config: {str(e)}")
        
        return None
    
    def _is_file_safe(self, filename: str, operation: str) -> bool:
        """Check if file is safe for the given operation"""
        if not filename or '.' not in filename:
            return True
            
        ext = os.path.splitext(filename)[1].lower()
        
        # Check server path configuration first
        server_path = self._get_server_path_config(filename)
        if server_path:
            return server_path.is_file_allowed(filename)
        
        # Default safety checks
        if ext in self.DANGEROUS_EXTENSIONS:
            # Only allow for admin users with explicit permission
            if operation in ['read', 'list'] and self.user.is_superuser:
                return True
            return False
        
        return True
    
    def _log_security_event(self, event_type: str, message: str, severity: str = 'info'):
        """Log security event"""
        try:
            SecurityLog.objects.create(
                event_type=event_type,
                severity=severity,
                message=message,
                user_id=str(self.user.id),
                username=self.user.username,
                ip_address=self.ip_address,
                user_agent=self.user_agent
            )
        except Exception as e:
            logger.error(f"Error logging security event: {str(e)}")


class FileOperationTracker:
    """
    Tracks file operations for audit trail
    """
    
    def __init__(self, user: User, ip_address: str = None, user_agent: str = None, session_id: str = None):
        self.user = user
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.session_id = session_id
        self.validator = ServerPathValidator(user, ip_address, user_agent)
    
    def track_operation(self, operation: str, file_path: str, status: str = 'success', 
                       original_path: str = None, file_size: int = None, 
                       error_message: str = None, execution_time: float = None,
                       metadata: Dict = None) -> FileOperation:
        """
        Track a file operation in the audit trail
        
        Args:
            operation: Type of operation (read, write, delete, etc.)
            file_path: Path of the file
            status: Operation status (success, failed, blocked, unauthorized)
            original_path: Original path for rename/move operations
            file_size: Size of the file in bytes
            error_message: Error message if operation failed
            execution_time: Time taken for operation in milliseconds
            metadata: Additional metadata
            
        Returns:
            Created FileOperation instance
        """
        try:
            # Calculate risk score
            risk_score = self.validator.calculate_risk_score(file_path, operation)
            
            # Determine security level
            security_level = 'low'
            if risk_score >= 70:
                security_level = 'high'
            elif risk_score >= 40:
                security_level = 'medium'
            
            # Get file type
            file_type = self._get_file_type(file_path)
            
            # Create file operation record
            file_operation = FileOperation.objects.create(
                operation=operation,
                status=status,
                file_path=file_path,
                original_path=original_path or '',
                file_size=file_size,
                file_type=file_type,
                user_id=str(self.user.id),
                username=self.user.username,
                session_id=self.session_id or '',
                ip_address=self.ip_address,
                user_agent=self.user_agent or '',
                security_level=security_level,
                risk_score=risk_score,
                metadata=metadata or {},
                error_message=error_message or '',
                execution_time=execution_time
            )
            
            # Log security event if high risk
            if risk_score >= 70:
                SecurityLog.objects.create(
                    event_type='suspicious_activity',
                    severity='warning',
                    message=f"High-risk file operation: {operation} on {file_path}",
                    user_id=str(self.user.id),
                    username=self.user.username,
                    ip_address=self.ip_address,
                    user_agent=self.user_agent,
                    file_path=file_path,
                    related_file_operation=file_operation
                )
            
            return file_operation
            
        except Exception as e:
            logger.error(f"Error tracking file operation: {str(e)}")
            raise
    
    def _get_file_type(self, file_path: str) -> str:
        """Get file type based on extension"""
        if not file_path or '.' not in os.path.basename(file_path):
            return 'unknown'
        
        ext = os.path.splitext(file_path)[1].lower()
        
        type_map = {
            '.txt': 'text',
            '.md': 'markdown',
            '.html': 'html',
            '.css': 'css',
            '.scss': 'scss',
            '.js': 'javascript',
            '.py': 'python',
            '.php': 'php',
            '.json': 'json',
            '.xml': 'xml',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.conf': 'config',
            '.config': 'config',
            '.ini': 'config',
            '.log': 'log',
            '.csv': 'csv',
            '.sql': 'sql',
            '.sh': 'shell',
            '.bash': 'shell',
        }
        
        return type_map.get(ext, 'unknown')


class RateLimiter:
    """
    Rate limiting for file operations
    """
    
    def __init__(self, user: User):
        self.user = user
        self.settings = MonitoringSettings.get_settings()
    
    def is_rate_limited(self, operation: str = None) -> Tuple[bool, str]:
        """
        Check if user is rate limited
        
        Args:
            operation: Optional operation type for specific limits
            
        Returns:
            Tuple of (is_limited, message)
        """
        try:
            # Check hourly limit
            one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
            recent_operations = FileOperation.objects.filter(
                user_id=str(self.user.id),
                created_at__gte=one_hour_ago
            ).count()
            
            if recent_operations >= self.settings.max_file_operations_per_hour:
                return True, f"Rate limit exceeded: {recent_operations} operations in the last hour"
            
            # Check for suspicious patterns (many failed operations)
            failed_operations = FileOperation.objects.filter(
                user_id=str(self.user.id),
                created_at__gte=one_hour_ago,
                status__in=['failed', 'blocked', 'unauthorized']
            ).count()
            
            if failed_operations >= 10:  # More than 10 failed operations in an hour
                return True, "Too many failed operations detected"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {str(e)}")
            return False, ""
    
    def record_rate_limit_violation(self, reason: str):
        """Record a rate limit violation"""
        try:
            SecurityLog.objects.create(
                event_type='rate_limit_exceeded',
                severity='warning',
                message=f"Rate limit exceeded: {reason}",
                user_id=str(self.user.id),
                username=self.user.username
            )
        except Exception as e:
            logger.error(f"Error recording rate limit violation: {str(e)}")