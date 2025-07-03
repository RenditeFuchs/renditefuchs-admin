from django.db import models
from django.utils import timezone
import json


class Platform(models.Model):
    """Represents a monitored platform (Main, Focus, Blog, Academy)"""
    ENVIRONMENT_CHOICES = [
        ('test', 'Test'),
        ('live', 'Live'),
    ]
    
    COLOR_CHOICES = [
        ('success', 'Grün (Live)'),
        ('warning', 'Orange (Test)'),
        ('secondary', 'Grau (Inaktiv)'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    url = models.URLField()
    health_endpoint = models.CharField(max_length=200, default='/health/')
    environment = models.CharField(max_length=10, choices=ENVIRONMENT_CHOICES, default='test')
    color = models.CharField(max_length=15, choices=COLOR_CHOICES, default='info')
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = "Plattform"
        verbose_name_plural = "Plattformen"
    
    def __str__(self):
        return self.name


class SystemHealth(models.Model):
    """Tracks system health status for each platform"""
    STATUS_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('warning', 'Warnung'),
        ('error', 'Fehler'),
    ]
    
    platform = models.ForeignKey(Platform, on_delete=models.CASCADE, related_name='health_checks')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    response_time = models.FloatField(null=True, blank=True)  # in milliseconds
    status_code = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)
    
    # Additional metrics
    cpu_usage = models.FloatField(null=True, blank=True)
    memory_usage = models.FloatField(null=True, blank=True)
    disk_usage = models.FloatField(null=True, blank=True)
    database_status = models.CharField(max_length=20, null=True, blank=True)
    
    class Meta:
        ordering = ['-checked_at']
        verbose_name = "Systemzustand"
        verbose_name_plural = "Systemzustände"
        indexes = [
            models.Index(fields=['platform', '-checked_at']),
            models.Index(fields=['status', '-checked_at']),
        ]
    
    def __str__(self):
        return f"{self.platform.name} - {self.status} ({self.checked_at})"


class ErrorLog(models.Model):
    """Tracks errors across all platforms"""
    SEVERITY_CHOICES = [
        ('low', 'Niedrig'),
        ('medium', 'Mittel'),
        ('high', 'Hoch'),
        ('critical', 'Kritisch'),
    ]
    
    ERROR_TYPE_CHOICES = [
        ('500', 'Serverfehler (500)'),
        ('404', 'Nicht gefunden (404)'),
        ('403', 'Verboten (403)'),
        ('database', 'Datenbankfehler'),
        ('api', 'API-Fehler'),
        ('timeout', 'Timeout-Fehler'),
        ('other', 'Andere'),
    ]
    
    platform = models.ForeignKey(Platform, on_delete=models.CASCADE, related_name='errors')
    error_type = models.CharField(max_length=20, choices=ERROR_TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    message = models.TextField()
    stack_trace = models.TextField(blank=True)
    url_path = models.CharField(max_length=500, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_id = models.CharField(max_length=100, blank=True)  # Store user ID as string
    
    # Error context
    request_data = models.JSONField(default=dict, blank=True)
    environment_data = models.JSONField(default=dict, blank=True)
    
    # Tracking
    count = models.IntegerField(default=1)  # How many times this error occurred
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=100, blank=True)
    
    class Meta:
        ordering = ['-last_seen']
        verbose_name = "Fehlerprotokoll"
        verbose_name_plural = "Fehlerprotokolle"
        indexes = [
            models.Index(fields=['platform', '-last_seen']),
            models.Index(fields=['severity', '-last_seen']),
            models.Index(fields=['error_type', '-last_seen']),
            models.Index(fields=['is_resolved', '-last_seen']),
        ]
    
    def __str__(self):
        return f"{self.platform.name} - {self.error_type} - {self.severity}"
    
    def resolve(self, resolved_by="System"):
        """Mark error as resolved"""
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolved_by = resolved_by
        self.save()


class PerformanceMetric(models.Model):
    """Tracks performance metrics for platforms"""
    platform = models.ForeignKey(Platform, on_delete=models.CASCADE, related_name='metrics')
    
    # Response time metrics
    avg_response_time = models.FloatField()  # milliseconds
    min_response_time = models.FloatField()
    max_response_time = models.FloatField()
    
    # Request metrics
    total_requests = models.IntegerField(default=0)
    successful_requests = models.IntegerField(default=0)
    failed_requests = models.IntegerField(default=0)
    
    # System metrics
    cpu_usage = models.FloatField(null=True, blank=True)
    memory_usage = models.FloatField(null=True, blank=True)
    disk_usage = models.FloatField(null=True, blank=True)
    
    # Database metrics
    db_connections = models.IntegerField(null=True, blank=True)
    slow_queries = models.IntegerField(default=0)
    
    # Time period
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Leistungsmetrik"
        verbose_name_plural = "Leistungsmetriken"
        indexes = [
            models.Index(fields=['platform', '-created_at']),
            models.Index(fields=['period_start', 'period_end']),
        ]
    
    def __str__(self):
        return f"{self.platform.name} - {self.period_start.strftime('%Y-%m-%d %H:%M')}"


class Alert(models.Model):
    """System alerts for critical issues"""
    ALERT_TYPE_CHOICES = [
        ('downtime', 'Plattform-Ausfall'),
        ('high_error_rate', 'Hohe Fehlerrate'),
        ('slow_response', 'Langsame Antwortzeit'),
        ('resource_usage', 'Hohe Ressourcennutzung'),
        ('database_issue', 'Datenbankproblem'),
        ('custom', 'Benutzerdefinierte Warnung'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Aktiv'),
        ('acknowledged', 'Bestätigt'),
        ('resolved', 'Gelöst'),
    ]
    
    platform = models.ForeignKey(Platform, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    severity = models.CharField(max_length=10, choices=ErrorLog.SEVERITY_CHOICES)
    
    # Related error if applicable
    related_error = models.ForeignKey(ErrorLog, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.CharField(max_length=100, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=100, blank=True)
    
    # Notification tracking
    notification_sent = models.BooleanField(default=False)
    notification_methods = models.JSONField(default=list, blank=True)  # ['email', 'slack', etc.]
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Warnung"
        verbose_name_plural = "Warnungen"
        indexes = [
            models.Index(fields=['platform', 'status', '-created_at']),
            models.Index(fields=['severity', 'status', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.platform.name} - {self.title} ({self.status})"
    
    def acknowledge(self, acknowledged_by="Admin"):
        """Mark alert as acknowledged"""
        self.status = 'acknowledged'
        self.acknowledged_at = timezone.now()
        self.acknowledged_by = acknowledged_by
        self.save()
    
    def resolve(self, resolved_by="Admin"):
        """Mark alert as resolved"""
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.resolved_by = resolved_by
        self.save()


class FileOperation(models.Model):
    """Tracks all file operations for security audit trail"""
    OPERATION_CHOICES = [
        ('read', 'Datei gelesen'),
        ('write', 'Datei geschrieben'),
        ('delete', 'Datei gelöscht'),
        ('create', 'Datei erstellt'),
        ('rename', 'Datei umbenannt'),
        ('copy', 'Datei kopiert'),
        ('move', 'Datei verschoben'),
        ('list', 'Verzeichnis aufgelistet'),
        ('upload', 'Datei hochgeladen'),
        ('download', 'Datei heruntergeladen'),
    ]
    
    STATUS_CHOICES = [
        ('success', 'Erfolgreich'),
        ('failed', 'Fehlgeschlagen'),
        ('blocked', 'Blockiert'),
        ('unauthorized', 'Nicht autorisiert'),
    ]
    
    # Operation details
    operation = models.CharField(max_length=20, choices=OPERATION_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    file_path = models.CharField(max_length=1000)
    original_path = models.CharField(max_length=1000, blank=True)  # For rename/move operations
    file_size = models.BigIntegerField(null=True, blank=True)
    file_type = models.CharField(max_length=100, blank=True)
    
    # User and session information
    user_id = models.CharField(max_length=100)
    username = models.CharField(max_length=150)
    session_id = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=500, blank=True)
    
    # Security context
    security_level = models.CharField(max_length=20, default='normal')
    risk_score = models.IntegerField(default=0)  # 0-100 risk assessment
    blocked_reason = models.TextField(blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    execution_time = models.FloatField(null=True, blank=True)  # milliseconds
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Dateioperation"
        verbose_name_plural = "Dateioperationen"
        indexes = [
            models.Index(fields=['user_id', '-created_at']),
            models.Index(fields=['operation', 'status', '-created_at']),
            models.Index(fields=['file_path', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['security_level', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.username} - {self.operation} - {self.file_path} ({self.status})"
    
    def is_high_risk(self):
        """Check if operation is considered high risk"""
        return self.risk_score >= 70
    
    def get_relative_path(self):
        """Get relative path for display"""
        if self.file_path.startswith('/var/www/'):
            return self.file_path.replace('/var/www/', '')
        return self.file_path


class SecurityLog(models.Model):
    """Logs security events and incidents"""
    EVENT_TYPE_CHOICES = [
        ('login_success', 'Erfolgreiche Anmeldung'),
        ('login_failed', 'Fehlgeschlagene Anmeldung'),
        ('unauthorized_access', 'Unbefugter Zugriff'),
        ('suspicious_activity', 'Verdächtige Aktivität'),
        ('permission_denied', 'Zugriff verweigert'),
        ('path_traversal', 'Pfad-Traversal-Versuch'),
        ('malicious_file', 'Schädliche Datei erkannt'),
        ('rate_limit_exceeded', 'Rate-Limit überschritten'),
        ('ssh_connection', 'SSH-Verbindung'),
        ('file_access_denied', 'Dateizugriff verweigert'),
        ('admin_action', 'Administrator-Aktion'),
        ('system_alert', 'System-Warnung'),
    ]
    
    SEVERITY_CHOICES = [
        ('info', 'Information'),
        ('warning', 'Warnung'),
        ('error', 'Fehler'),
        ('critical', 'Kritisch'),
    ]
    
    # Event details
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    
    # User and session
    user_id = models.CharField(max_length=100, blank=True)
    username = models.CharField(max_length=150, blank=True)
    session_id = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    
    # Context
    file_path = models.CharField(max_length=1000, blank=True)
    url_path = models.CharField(max_length=500, blank=True)
    request_method = models.CharField(max_length=10, blank=True)
    
    # Related objects
    related_file_operation = models.ForeignKey(
        FileOperation, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='security_logs'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Sicherheitsprotokoll"
        verbose_name_plural = "Sicherheitsprotokolle"
        indexes = [
            models.Index(fields=['event_type', '-created_at']),
            models.Index(fields=['severity', '-created_at']),
            models.Index(fields=['user_id', '-created_at']),
            models.Index(fields=['ip_address', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.event_type} - {self.severity} - {self.created_at}"
    
    def is_security_incident(self):
        """Check if this is a security incident requiring attention"""
        return self.severity in ['error', 'critical'] or self.event_type in [
            'unauthorized_access', 'suspicious_activity', 'path_traversal', 'malicious_file'
        ]


class ServerPath(models.Model):
    """Configuration for allowed server paths and access levels"""
    PATH_TYPE_CHOICES = [
        ('allowed', 'Erlaubter Pfad'),
        ('restricted', 'Eingeschränkter Pfad'),
        ('forbidden', 'Verbotener Pfad'),
        ('whitelist', 'Whitelist-Pfad'),
    ]
    
    ACCESS_LEVEL_CHOICES = [
        ('read', 'Nur Lesen'),
        ('write', 'Lesen und Schreiben'),
        ('execute', 'Ausführen'),
        ('admin', 'Administrator'),
        ('none', 'Kein Zugriff'),
    ]
    
    # Path configuration
    path = models.CharField(max_length=1000, unique=True)
    path_type = models.CharField(max_length=20, choices=PATH_TYPE_CHOICES)
    access_level = models.CharField(max_length=20, choices=ACCESS_LEVEL_CHOICES)
    
    # Permissions
    allow_read = models.BooleanField(default=True)
    allow_write = models.BooleanField(default=False)
    allow_delete = models.BooleanField(default=False)
    allow_execute = models.BooleanField(default=False)
    allow_list = models.BooleanField(default=True)
    
    # File type restrictions
    allowed_extensions = models.JSONField(default=list, blank=True)
    forbidden_extensions = models.JSONField(default=list, blank=True)
    max_file_size = models.BigIntegerField(null=True, blank=True)  # bytes
    
    # Security settings
    require_admin = models.BooleanField(default=False)
    require_confirmation = models.BooleanField(default=False)
    risk_level = models.CharField(max_length=10, default='low')
    
    # Metadata
    description = models.TextField(blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['path']
        verbose_name = "Server-Pfad"
        verbose_name_plural = "Server-Pfade"
        indexes = [
            models.Index(fields=['path_type', 'is_active']),
            models.Index(fields=['access_level', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.path} ({self.path_type})"
    
    def allows_operation(self, operation):
        """Check if path allows specific operation"""
        if not self.is_active:
            return False
            
        operation_map = {
            'read': self.allow_read,
            'write': self.allow_write,
            'delete': self.allow_delete,
            'execute': self.allow_execute,
            'list': self.allow_list,
        }
        
        return operation_map.get(operation, False)
    
    def is_file_allowed(self, filename):
        """Check if file type is allowed"""
        if not filename:
            return True
            
        file_ext = filename.split('.')[-1].lower() if '.' in filename else ''
        
        # Check forbidden extensions first
        if self.forbidden_extensions and file_ext in self.forbidden_extensions:
            return False
            
        # Check allowed extensions
        if self.allowed_extensions and file_ext not in self.allowed_extensions:
            return False
            
        return True
    
    def get_relative_path(self):
        """Get relative path for display"""
        if self.path.startswith('/var/www/'):
            return self.path.replace('/var/www/', '')
        return self.path


class MonitoringSettings(models.Model):
    """Global monitoring configuration"""
    # Health check intervals (in minutes)
    health_check_interval = models.IntegerField(default=5)
    
    # Alert thresholds
    response_time_threshold = models.FloatField(default=5000.0)  # milliseconds
    error_rate_threshold = models.FloatField(default=5.0)  # percentage
    cpu_usage_threshold = models.FloatField(default=80.0)  # percentage
    memory_usage_threshold = models.FloatField(default=80.0)  # percentage
    disk_usage_threshold = models.FloatField(default=90.0)  # percentage
    
    # Notification settings
    email_notifications = models.BooleanField(default=True)
    slack_notifications = models.BooleanField(default=False)
    slack_webhook_url = models.URLField(blank=True)
    notification_emails = models.JSONField(default=list, blank=True)
    
    # Data retention (in days)
    health_data_retention = models.IntegerField(default=30)
    error_data_retention = models.IntegerField(default=90)
    performance_data_retention = models.IntegerField(default=30)
    
    # Server directory security settings
    server_directory_enabled = models.BooleanField(default=False)
    ssh_key_path = models.CharField(max_length=500, default='~/.ssh/id_rsa')
    ssh_host = models.CharField(max_length=255, default='193.108.55.82')
    ssh_user = models.CharField(max_length=100, default='ubuntu')
    ssh_port = models.IntegerField(default=22)
    
    # Security settings
    max_file_operations_per_hour = models.IntegerField(default=100)
    enable_audit_logging = models.BooleanField(default=True)
    require_admin_for_sensitive_paths = models.BooleanField(default=True)
    auto_block_suspicious_activity = models.BooleanField(default=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Überwachungseinstellungen"
        verbose_name_plural = "Überwachungseinstellungen"
    
    def __str__(self):
        return "Monitoring Configuration"
    
    @classmethod
    def get_settings(cls):
        """Get or create monitoring settings singleton"""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings