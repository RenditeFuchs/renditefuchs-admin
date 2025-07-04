"""
Security module for server file operations
Includes path validation, rate limiting, and security logging
"""
import os
import re
import time
import logging
from typing import Dict, List, Set
from django.core.cache import cache
from django.utils import timezone
from django.contrib.auth.models import User
from .models import SecurityLog, FileOperation

logger = logging.getLogger('monitoring')


class SecurityException(Exception):
    """Custom security exception"""
    pass


class PathValidator:
    """
    Validates file paths for security
    """
    
    def __init__(self):
        # Dangerous patterns to block
        self.dangerous_patterns = [
            r'\.\./',           # Path traversal
            r'\/\.\./',         # Path traversal  
            r'\.\.\\',          # Windows path traversal
            r'\/etc\/passwd',   # System files
            r'\/etc\/shadow',   # System files
            r'\/proc\/',        # System files
            r'\/sys\/',         # System files
            r'\/dev\/',         # Device files
            r'\/root\/',        # Root home
            r'\/home\/[^\/]+\/\.[^\/]+', # Hidden files in home
            r'\/tmp\/.*\.sh',   # Temp scripts
            r'\/var\/log\/.*\.log', # Log files (read-only)
        ]
        
        # Allowed base paths
        self.allowed_paths = [
            '/var/www',
            '/var/www/',
            '/opt/projects/',
            '/home/ubuntu/projects/',
        ]
        
        # Dangerous file extensions
        self.dangerous_extensions = {
            '.exe', '.bat', '.cmd', '.com', '.scr', '.vbs', '.js', '.jar',
            '.sh', '.bash', '.zsh', '.fish', '.csh', '.tcsh',
            '.ps1', '.psm1', '.psd1'
        }
        
        # Editable file extensions
        self.editable_extensions = {
            '.txt', '.md', '.html', '.htm', '.css', '.js', '.json', '.xml',
            '.py', '.php', '.rb', '.go', '.java', '.cpp', '.c', '.h',
            '.sql', '.conf', '.ini', '.cfg', '.env', '.yml', '.yaml',
            '.log', '.csv', '.tsv', '.properties', '.dockerfile'
        }
    
    def is_safe_path(self, path: str) -> bool:
        """
        Check if path is safe for access
        
        Args:
            path: File path to validate
            
        Returns:
            True if path is safe
        """
        try:
            # Normalize path
            normalized_path = os.path.normpath(path)
            
            # Check for dangerous patterns
            for pattern in self.dangerous_patterns:
                if re.search(pattern, normalized_path, re.IGNORECASE):
                    logger.warning(f"Dangerous path pattern detected: {path}")
                    return False
            
            # Check if path starts with allowed base path
            for allowed_path in self.allowed_paths:
                if normalized_path.startswith(allowed_path):
                    return True
            
            # Log unauthorized path access attempt
            logger.warning(f"Unauthorized path access attempted: {path}")
            return False
            
        except Exception as e:
            logger.error(f"Error validating path {path}: {e}")
            return False
    
    def is_editable_file(self, file_path: str) -> bool:
        """
        Check if file is editable
        
        Args:
            file_path: File path to check
            
        Returns:
            True if file can be edited
        """
        try:
            # Get file extension
            _, ext = os.path.splitext(file_path.lower())
            
            # Check if extension is editable
            if ext in self.editable_extensions:
                return True
            
            # Check if it's a config file without extension
            filename = os.path.basename(file_path).lower()
            config_files = {
                'makefile', 'dockerfile', 'requirements.txt', 'package.json',
                'composer.json', 'gemfile', 'rakefile', 'gulpfile',
                'gruntfile', 'webpack.config', 'tsconfig.json'
            }
            
            for config_file in config_files:
                if config_file in filename:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if file is editable {file_path}: {e}")
            return False
    
    def is_deletable_path(self, path: str) -> bool:
        """
        Check if path can be deleted
        
        Args:
            path: Path to check
            
        Returns:
            True if path can be deleted
        """
        try:
            # Must be safe path first
            if not self.is_safe_path(path):
                return False
            
            # Protected paths that cannot be deleted
            protected_paths = [
                '/var/www/live/',
                '/var/www/test/',
                '/var/www/shared/',
                '/var/www/html/',
                '/var/www/logs/',
            ]
            
            # Check if path is protected
            for protected_path in protected_paths:
                if path.startswith(protected_path) and len(path.split('/')) <= len(protected_path.split('/')):
                    return False
            
            # Check file extension
            _, ext = os.path.splitext(path.lower())
            if ext in self.dangerous_extensions:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking if path is deletable {path}: {e}")
            return False
    
    def validate_filename(self, filename: str) -> bool:
        """
        Validate filename for security
        
        Args:
            filename: Filename to validate
            
        Returns:
            True if filename is safe
        """
        try:
            # Check for dangerous characters
            dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\x00']
            for char in dangerous_chars:
                if char in filename:
                    return False
            
            # Check for reserved names (Windows)
            reserved_names = [
                'con', 'prn', 'aux', 'nul', 'com1', 'com2', 'com3', 'com4',
                'com5', 'com6', 'com7', 'com8', 'com9', 'lpt1', 'lpt2',
                'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
            ]
            
            if filename.lower() in reserved_names:
                return False
            
            # Check filename length
            if len(filename) > 255:
                return False
            
            # Check for hidden files starting with dot
            if filename.startswith('.') and len(filename) > 1:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating filename {filename}: {e}")
            return False


class RateLimiter:
    """
    Rate limiter for API requests
    """
    
    def __init__(self):
        self.limits = {
            'file_operations': {
                'requests': 50,
                'window': 300,  # 5 minutes
            },
            'directory_listing': {
                'requests': 100,
                'window': 300,
            },
            'file_editing': {
                'requests': 20,
                'window': 300,
            }
        }
    
    def allow_request(self, user: User, endpoint: str) -> bool:
        """
        Check if request is allowed under rate limit
        
        Args:
            user: User making request
            endpoint: API endpoint
            
        Returns:
            True if request is allowed
        """
        try:
            # Determine rate limit type
            limit_type = self._get_limit_type(endpoint)
            if not limit_type:
                return True
            
            # Get limit configuration
            limit_config = self.limits.get(limit_type, self.limits['file_operations'])
            
            # Create cache key
            cache_key = f"rate_limit_{user.id}_{limit_type}"
            
            # Get current request count
            current_requests = cache.get(cache_key, 0)
            
            # Check if limit exceeded
            if current_requests >= limit_config['requests']:
                logger.warning(f"Rate limit exceeded for user {user.username} on {endpoint}")
                return False
            
            # Increment counter
            cache.set(cache_key, current_requests + 1, limit_config['window'])
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True  # Allow request if rate limiter fails
    
    def _get_limit_type(self, endpoint: str) -> str:
        """Get rate limit type for endpoint"""
        if 'directory' in endpoint:
            return 'directory_listing'
        elif 'edit' in endpoint:
            return 'file_editing'
        else:
            return 'file_operations'


class SecurityAuditor:
    """
    Security auditing and logging
    """
    
    def __init__(self):
        self.suspicious_patterns = [
            r'rm\s+-rf',
            r'sudo\s+',
            r'passwd\s+',
            r'chmod\s+777',
            r'curl\s+.*\|\s*sh',
            r'wget\s+.*\|\s*sh',
            r'nc\s+.*\s+-e',
            r'telnet\s+',
            r'ftp\s+',
        ]
    
    def audit_file_access(self, user: User, operation: str, file_path: str, 
                         success: bool, ip_address: str = None, 
                         user_agent: str = None, content: str = None):
        """
        Audit file access operation
        
        Args:
            user: User performing operation
            operation: Type of operation
            file_path: Path being accessed
            success: Whether operation was successful
            ip_address: User's IP address
            user_agent: User's user agent
            content: File content (for edit operations)
        """
        try:
            # Check for suspicious content
            security_score = self._calculate_security_score(file_path, content)
            
            # Log operation
            FileOperation.objects.create(
                user_id=str(user.id),
                username=user.username,
                operation=operation,
                status='success' if success else 'failed',
                file_path=file_path,
                ip_address=ip_address or '',
                user_agent=user_agent or '',
                risk_score=security_score
            )
            
            # Log security event if suspicious
            if security_score > 50:
                SecurityLog.objects.create(
                    event_type='suspicious_activity',
                    severity='warning',
                    message=f"Suspicious file operation: {operation} on {file_path}",
                    user_id=str(user.id),
                    username=user.username,
                    ip_address=ip_address or '',
                    metadata={
                        'operation': operation,
                        'file_path': file_path,
                        'security_score': security_score
                    }
                )
            
        except Exception as e:
            logger.error(f"Error auditing file access: {e}")
    
    def _calculate_security_score(self, file_path: str, content: str = None) -> int:
        """
        Calculate security risk score (0-100)
        
        Args:
            file_path: File path
            content: File content
            
        Returns:
            Security score (higher = more suspicious)
        """
        score = 0
        
        try:
            # Check file path
            if '/etc/' in file_path:
                score += 30
            if '/root/' in file_path:
                score += 40
            if '/home/' in file_path and '/.ssh/' in file_path:
                score += 50
            
            # Check file extension
            _, ext = os.path.splitext(file_path.lower())
            if ext in ['.sh', '.bash', '.bat', '.cmd', '.exe']:
                score += 20
            
            # Check content if provided
            if content:
                for pattern in self.suspicious_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        score += 25
                
                # Check for encoded content
                if 'base64' in content.lower() or 'eval(' in content:
                    score += 15
            
            return min(score, 100)  # Cap at 100
            
        except Exception as e:
            logger.error(f"Error calculating security score: {e}")
            return 0
    
    def check_user_activity(self, user: User, hours: int = 24) -> Dict:
        """
        Check user activity for suspicious patterns
        
        Args:
            user: User to check
            hours: Hours to look back
            
        Returns:
            Activity summary
        """
        try:
            since = timezone.now() - timezone.timedelta(hours=hours)
            
            # Get recent operations
            operations = FileOperation.objects.filter(
                user=user,
                created_at__gte=since
            )
            
            # Get recent security events
            security_events = SecurityLog.objects.filter(
                user_id=str(user.id),
                created_at__gte=since
            )
            
            # Calculate statistics
            total_operations = operations.count()
            failed_operations = operations.filter(status='failed').count()
            high_risk_operations = operations.filter(risk_score__gte=50).count()
            
            return {
                'total_operations': total_operations,
                'failed_operations': failed_operations,
                'high_risk_operations': high_risk_operations,
                'security_events': security_events.count(),
                'risk_level': self._calculate_risk_level(
                    total_operations, failed_operations, high_risk_operations
                )
            }
            
        except Exception as e:
            logger.error(f"Error checking user activity: {e}")
            return {}
    
    def _calculate_risk_level(self, total: int, failed: int, high_risk: int) -> str:
        """Calculate overall risk level"""
        if total == 0:
            return 'low'
        
        failure_rate = failed / total
        risk_rate = high_risk / total
        
        if failure_rate > 0.3 or risk_rate > 0.2:
            return 'high'
        elif failure_rate > 0.1 or risk_rate > 0.1:
            return 'medium'
        else:
            return 'low'


# Global instances
path_validator = PathValidator()
rate_limiter = RateLimiter()
security_auditor = SecurityAuditor()