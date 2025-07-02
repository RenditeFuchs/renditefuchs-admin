from django.core.management.base import BaseCommand
from monitoring.models import Platform, ErrorLog
from monitoring.alert_system import alert_manager, create_platform_alert
import time


class Command(BaseCommand):
    help = 'Test the real-time alert system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--severity',
            type=str,
            choices=['low', 'medium', 'high', 'critical'],
            default='medium',
            help='Alert severity to test',
        )
        parser.add_argument(
            '--platform',
            type=str,
            help='Platform slug to test (default: first available)',
        )
        parser.add_argument(
            '--type',
            type=str,
            choices=['downtime', 'high_error_rate', 'critical_error', 'slow_response', 'custom'],
            default='custom',
            help='Type of alert to test',
        )

    def handle(self, *args, **options):
        severity = options['severity']
        platform_slug = options['platform']
        alert_type = options['type']
        
        self.stdout.write('🚨 Testing RenditeFuchs Alert System...')
        
        # Get platform to test
        if platform_slug:
            try:
                platform = Platform.objects.get(slug=platform_slug, is_active=True)
            except Platform.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Platform nicht gefunden: {platform_slug}')
                )
                return
        else:
            platform = Platform.objects.filter(is_active=True).first()
            if not platform:
                self.stdout.write(
                    self.style.ERROR('Keine aktiven Plattformen gefunden')
                )
                return
        
        self.stdout.write(f'📝 Platform: {platform.name} ({platform.environment})')
        self.stdout.write(f'⚠️  Severity: {severity}')
        self.stdout.write(f'🔧 Alert Type: {alert_type}')
        
        # Test different alert scenarios
        if alert_type == 'downtime':
            self._test_downtime_alert(platform, severity)
        elif alert_type == 'high_error_rate':
            self._test_error_rate_alert(platform, severity)
        elif alert_type == 'critical_error':
            self._test_critical_error_alert(platform, severity)
        elif alert_type == 'slow_response':
            self._test_slow_response_alert(platform, severity)
        else:
            self._test_custom_alert(platform, severity)
        
        self.stdout.write('')
        self.stdout.write('✅ Alert System Test abgeschlossen')
        self.stdout.write('💡 Überprüfe die Alerts im Dashboard: http://127.0.0.1:8003/monitoring/')
    
    def _test_downtime_alert(self, platform, severity):
        """Test downtime alert"""
        self.stdout.write('🔴 Teste Downtime Alert...')
        
        alert = alert_manager.create_alert(
            platform=platform,
            alert_type='downtime',
            title=f'TEST: Platform Ausfall - {platform.name}',
            message=f'TEST ALERT: Platform {platform.name} ist nicht erreichbar und wurde als offline erkannt.',
            severity=severity
        )
        
        if alert:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Downtime Alert erstellt: ID {alert.id}')
            )
        else:
            self.stdout.write(
                self.style.ERROR('❌ Fehler beim Erstellen des Downtime Alerts')
            )
    
    def _test_error_rate_alert(self, platform, severity):
        """Test high error rate alert"""
        self.stdout.write('📈 Teste High Error Rate Alert...')
        
        # Create some test errors first
        self.stdout.write('   📝 Erstelle Test-Errors...')
        for i in range(5):
            ErrorLog.objects.create(
                platform=platform,
                error_type='500',
                severity='medium',
                message=f'TEST ERROR {i+1}: Internal server error during load test',
                url_path=f'/api/test/{i+1}',
                user_agent='Alert Test Suite'
            )
            time.sleep(0.1)
        
        alert = alert_manager.create_alert(
            platform=platform,
            alert_type='high_error_rate',
            title=f'TEST: Hohe Fehlerrate - {platform.name}',
            message=f'TEST ALERT: 5 Fehler in kurzer Zeit erkannt auf {platform.name}',
            severity=severity
        )
        
        if alert:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Error Rate Alert erstellt: ID {alert.id}')
            )
        else:
            self.stdout.write(
                self.style.ERROR('❌ Fehler beim Erstellen des Error Rate Alerts')
            )
    
    def _test_critical_error_alert(self, platform, severity):
        """Test critical error alert"""
        self.stdout.write('🚨 Teste Critical Error Alert...')
        
        # Create a critical error
        critical_error = ErrorLog.objects.create(
            platform=platform,
            error_type='database',
            severity='critical',
            message='TEST CRITICAL ERROR: Database connection completely lost',
            stack_trace='TEST STACK TRACE:\nDatabase connection timeout\nConnection pool exhausted',
            url_path='/dashboard/critical',
            user_agent='Alert Test Suite'
        )
        
        alert = alert_manager.create_alert(
            platform=platform,
            alert_type='critical_error',
            title=f'TEST: Kritischer Fehler - {platform.name}',
            message=f'TEST ALERT: Kritischer Datenbankfehler erkannt',
            severity='critical',
            related_error=critical_error
        )
        
        if alert:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Critical Error Alert erstellt: ID {alert.id}')
            )
        else:
            self.stdout.write(
                self.style.ERROR('❌ Fehler beim Erstellen des Critical Error Alerts')
            )
    
    def _test_slow_response_alert(self, platform, severity):
        """Test slow response alert"""
        self.stdout.write('🐌 Teste Slow Response Alert...')
        
        alert = alert_manager.create_alert(
            platform=platform,
            alert_type='slow_response',
            title=f'TEST: Langsame Antwortzeit - {platform.name}',
            message=f'TEST ALERT: Antwortzeit (5000ms) überschreitet Grenzwert (2000ms) auf {platform.name}',
            severity=severity
        )
        
        if alert:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Slow Response Alert erstellt: ID {alert.id}')
            )
        else:
            self.stdout.write(
                self.style.ERROR('❌ Fehler beim Erstellen des Slow Response Alerts')
            )
    
    def _test_custom_alert(self, platform, severity):
        """Test custom alert"""
        self.stdout.write('🔧 Teste Custom Alert...')
        
        # Severity-specific messages
        severity_messages = {
            'low': 'Geringfügiges Problem erkannt, überwachung empfohlen',
            'medium': 'Mäßiges Problem erkannt, Aufmerksamkeit erforderlich',
            'high': 'Ernstes Problem erkannt, sofortige Überprüfung erforderlich',
            'critical': 'KRITISCHES PROBLEM erkannt, SOFORTIGE MASSNAHMEN erforderlich!'
        }
        
        alert = alert_manager.create_alert(
            platform=platform,
            alert_type='custom',
            title=f'TEST: Custom Alert ({severity.upper()}) - {platform.name}',
            message=f'TEST ALERT: {severity_messages.get(severity, "Test-Problem erkannt")}',
            severity=severity
        )
        
        if alert:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Custom Alert erstellt: ID {alert.id}')
            )
            
            # Test notification system
            if severity in ['high', 'critical']:
                self.stdout.write('📧 Teste Benachrichtigungssystem...')
                self.stdout.write('   💡 Email-Benachrichtigung würde gesendet (Console-Backend aktiv)')
                
                # Test Slack notification if configured
                settings = alert_manager.settings
                if settings.slack_notifications and settings.slack_webhook_url:
                    self.stdout.write('   💬 Slack-Benachrichtigung wird getestet...')
                else:
                    self.stdout.write('   💬 Slack-Benachrichtigung nicht konfiguriert')
        else:
            self.stdout.write(
                self.style.ERROR('❌ Fehler beim Erstellen des Custom Alerts')
            )