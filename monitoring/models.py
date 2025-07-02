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