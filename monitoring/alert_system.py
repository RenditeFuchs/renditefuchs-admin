import smtplib
import json
import requests
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from .models import Alert, Platform, ErrorLog, MonitoringSettings


logger = logging.getLogger('monitoring')


class AlertManager:
    """Manages real-time alerts for critical system issues"""
    
    def __init__(self):
        self.settings = MonitoringSettings.get_settings()
    
    def create_alert(self, platform, alert_type, title, message, severity='medium', related_error=None):
        """Create a new alert and trigger notifications"""
        try:
            # Check if similar alert already exists and is active
            existing_alert = Alert.objects.filter(
                platform=platform,
                alert_type=alert_type,
                status='active'
            ).first()
            
            if existing_alert:
                # Update existing alert
                existing_alert.message = message
                existing_alert.save()
                logger.info(f'Updated existing alert: {existing_alert.id}')
                return existing_alert
            
            # Create new alert
            alert = Alert.objects.create(
                platform=platform,
                alert_type=alert_type,
                title=title,
                message=message,
                severity=severity,
                related_error=related_error
            )
            
            logger.info(f'Created new alert: {alert.id} - {title}')
            
            # Trigger notifications based on severity
            if severity in ['high', 'critical']:
                self._send_notifications(alert)
            
            return alert
            
        except Exception as e:
            logger.error(f'Failed to create alert: {e}')
            return None
    
    def resolve_alert(self, alert_id, resolved_by="System"):
        """Mark an alert as resolved"""
        try:
            alert = Alert.objects.get(id=alert_id)
            alert.resolve(resolved_by)
            logger.info(f'Alert resolved: {alert_id} by {resolved_by}')
            return True
        except Alert.DoesNotExist:
            logger.error(f'Alert not found: {alert_id}')
            return False
    
    def _send_notifications(self, alert):
        """Send notifications via configured channels"""
        notification_methods = []
        
        # Send email notifications
        if self.settings.email_notifications:
            if self._send_email_notification(alert):
                notification_methods.append('email')
        
        # Send Slack notifications
        if self.settings.slack_notifications and self.settings.slack_webhook_url:
            if self._send_slack_notification(alert):
                notification_methods.append('slack')
        
        # Update alert with notification status
        alert.notification_sent = True
        alert.notification_methods = notification_methods
        alert.save()
        
        logger.info(f'Notifications sent for alert {alert.id}: {notification_methods}')
    
    def _send_email_notification(self, alert):
        """Send email notification"""
        try:
            if not self.settings.notification_emails:
                logger.warning('No notification emails configured')
                return False
            
            # Prepare email content
            subject = f'🚨 RenditeFuchs Alert: {alert.title}'
            
            # Generate email body from template
            email_context = {
                'alert': alert,
                'platform': alert.platform,
                'settings': self.settings,
                'dashboard_url': 'http://127.0.0.1:8003'  # Should be configurable
            }
            
            html_content = render_to_string('monitoring/emails/alert_notification.html', email_context)
            text_content = render_to_string('monitoring/emails/alert_notification.txt', email_context)
            
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = 'admin@renditefuchs.de'
            msg['To'] = ', '.join(self.settings.notification_emails)
            
            msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # Send email (using console backend for development)
            # In production, configure proper SMTP settings
            logger.info(f'Email notification prepared for alert: {alert.id}')
            
            # For now, just log the email content
            logger.info(f'EMAIL SUBJECT: {subject}')
            logger.info(f'EMAIL RECIPIENTS: {self.settings.notification_emails}')
            logger.info(f'EMAIL CONTENT: {text_content}')
            
            return True
            
        except Exception as e:
            logger.error(f'Failed to send email notification: {e}')
            return False
    
    def _send_slack_notification(self, alert):
        """Send Slack notification via webhook"""
        try:
            if not self.settings.slack_webhook_url:
                return False
            
            # Determine emoji and color based on severity
            severity_config = {
                'low': {'emoji': '🔵', 'color': '#36a3f7'},
                'medium': {'emoji': '🟡', 'color': '#ffc107'},
                'high': {'emoji': '🟠', 'color': '#fd7e14'},
                'critical': {'emoji': '🔴', 'color': '#dc3545'}
            }
            
            config = severity_config.get(alert.severity, severity_config['medium'])
            
            # Environment emoji
            env_emoji = '🟧' if alert.platform.environment == 'test' else '🟩' if alert.platform.environment == 'live' else '🔵'
            
            # Prepare Slack message
            slack_payload = {
                'text': f'{config["emoji"]} RenditeFuchs Alert: {alert.title}',
                'attachments': [
                    {
                        'color': config['color'],
                        'fields': [
                            {
                                'title': 'Platform',
                                'value': f'{env_emoji} {alert.platform.name}',
                                'short': True
                            },
                            {
                                'title': 'Schweregrad',
                                'value': alert.get_severity_display(),
                                'short': True
                            },
                            {
                                'title': 'Alert Typ',
                                'value': alert.get_alert_type_display(),
                                'short': True
                            },
                            {
                                'title': 'Zeit',
                                'value': alert.created_at.strftime('%d.%m.%Y %H:%M'),
                                'short': True
                            },
                            {
                                'title': 'Nachricht',
                                'value': alert.message,
                                'short': False
                            }
                        ],
                        'footer': 'RenditeFuchs Monitoring',
                        'footer_icon': 'https://renditefuchs.de/static/images/logo.png'
                    }
                ]
            }
            
            # Send to Slack
            response = requests.post(
                self.settings.slack_webhook_url,
                json=slack_payload,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f'Slack notification sent for alert: {alert.id}')
                return True
            else:
                logger.error(f'Slack notification failed: {response.status_code}')
                return False
                
        except Exception as e:
            logger.error(f'Failed to send Slack notification: {e}')
            return False
    
    def check_error_thresholds(self, platform):
        """Check if error thresholds are exceeded and create alerts"""
        try:
            from datetime import timedelta
            
            # Check error rate in last hour
            last_hour = timezone.now() - timedelta(hours=1)
            recent_errors = ErrorLog.objects.filter(
                platform=platform,
                last_seen__gte=last_hour,
                is_resolved=False
            )
            
            error_count = recent_errors.count()
            critical_errors = recent_errors.filter(severity='critical').count()
            
            # High error rate threshold
            if error_count >= self.settings.error_rate_threshold:
                self.create_alert(
                    platform=platform,
                    alert_type='high_error_rate',
                    title=f'Hohe Fehlerrate: {platform.name}',
                    message=f'{error_count} Fehler in der letzten Stunde erkannt',
                    severity='high'
                )
            
            # Critical error threshold
            if critical_errors > 0:
                latest_critical = recent_errors.filter(severity='critical').first()
                self.create_alert(
                    platform=platform,
                    alert_type='critical_error',
                    title=f'Kritischer Fehler: {platform.name}',
                    message=f'Kritischer Fehler erkannt: {latest_critical.message}',
                    severity='critical',
                    related_error=latest_critical
                )
            
        except Exception as e:
            logger.error(f'Failed to check error thresholds for {platform.name}: {e}')
    
    def check_downtime_alerts(self, platform, health_status):
        """Check if platform is down and create downtime alerts"""
        try:
            if health_status in ['offline', 'error']:
                self.create_alert(
                    platform=platform,
                    alert_type='downtime',
                    title=f'Platform Ausfall: {platform.name}',
                    message=f'Platform ist {health_status} und nicht erreichbar',
                    severity='critical' if health_status == 'offline' else 'high'
                )
            else:
                # Platform is back online, resolve downtime alerts
                downtime_alerts = Alert.objects.filter(
                    platform=platform,
                    alert_type='downtime',
                    status='active'
                )
                
                for alert in downtime_alerts:
                    alert.resolve("System - Platform wieder online")
                    
        except Exception as e:
            logger.error(f'Failed to check downtime alerts for {platform.name}: {e}')
    
    def check_response_time_alerts(self, platform, response_time):
        """Check if response time exceeds thresholds"""
        try:
            if response_time and response_time > self.settings.response_time_threshold:
                self.create_alert(
                    platform=platform,
                    alert_type='slow_response',
                    title=f'Langsame Antwortzeit: {platform.name}',
                    message=f'Antwortzeit ({response_time:.0f}ms) überschreitet Grenzwert ({self.settings.response_time_threshold:.0f}ms)',
                    severity='medium'
                )
        except Exception as e:
            logger.error(f'Failed to check response time alerts for {platform.name}: {e}')


# Global alert manager instance
alert_manager = AlertManager()


def create_platform_alert(platform_slug, alert_type, title, message, severity='medium'):
    """Convenience function to create alerts for platforms"""
    try:
        platform = Platform.objects.get(slug=platform_slug, is_active=True)
        return alert_manager.create_alert(platform, alert_type, title, message, severity)
    except Platform.DoesNotExist:
        logger.error(f'Platform not found: {platform_slug}')
        return None


def process_error_alert(error_log):
    """Process error log and create appropriate alerts"""
    alert_manager.check_error_thresholds(error_log.platform)
    
    # Create specific alert for critical errors
    if error_log.severity == 'critical':
        alert_manager.create_alert(
            platform=error_log.platform,
            alert_type='critical_error',
            title=f'Kritischer Fehler: {error_log.platform.name}',
            message=error_log.message,
            severity='critical',
            related_error=error_log
        )


def process_health_check_alert(platform, health_result):
    """Process health check result and create appropriate alerts"""
    alert_manager.check_downtime_alerts(platform, health_result['status'])
    
    if 'response_time' in health_result:
        alert_manager.check_response_time_alerts(platform, health_result['response_time'])