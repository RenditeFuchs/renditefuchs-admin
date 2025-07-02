from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring.models import Platform, Alert, MonitoringSettings
from monitoring.views import perform_health_check
import logging

logger = logging.getLogger('monitoring')


class Command(BaseCommand):
    help = 'Run health checks for all platforms'

    def add_arguments(self, parser):
        parser.add_argument(
            '--platform',
            type=str,
            help='Check specific platform only (by slug)',
        )
        parser.add_argument(
            '--create-alerts',
            action='store_true',
            help='Create alerts for failed health checks',
        )

    def handle(self, *args, **options):
        settings = MonitoringSettings.get_settings()
        
        # Get platforms to check
        if options['platform']:
            platforms = Platform.objects.filter(slug=options['platform'], is_active=True)
            if not platforms.exists():
                self.stdout.write(
                    self.style.ERROR(f'Platform "{options["platform"]}" not found')
                )
                return
        else:
            platforms = Platform.objects.filter(is_active=True)
        
        self.stdout.write(f'🔍 Running health checks for {platforms.count()} platforms...')
        
        results = {}
        alerts_created = 0
        
        for platform in platforms:
            self.stdout.write(f'   Checking {platform.name}...', ending='')
            
            try:
                # Perform health check
                health_result = perform_health_check(platform)
                results[platform.name] = health_result
                
                # Determine status symbol
                status_symbol = {
                    'online': '✅',
                    'offline': '❌',
                    'warning': '⚠️',
                    'error': '🚨'
                }.get(health_result['status'], '❓')
                
                response_time = health_result.get('response_time', 0)
                self.stdout.write(
                    f' {status_symbol} {health_result["status"]} ({response_time:.0f}ms)'
                )
                
                # Create alerts if enabled and status is problematic
                if options['create_alerts'] and health_result['status'] in ['offline', 'error']:
                    # Check if similar alert already exists
                    existing_alert = Alert.objects.filter(
                        platform=platform,
                        alert_type='downtime',
                        status='active'
                    ).first()
                    
                    if not existing_alert:
                        Alert.objects.create(
                            platform=platform,
                            alert_type='downtime',
                            title=f'{platform.name} is {health_result["status"]}',
                            message=f'Platform health check failed: {health_result.get("error_message", "Unknown error")}',
                            severity='critical' if health_result['status'] == 'offline' else 'high'
                        )
                        alerts_created += 1
                        self.stdout.write(f'     🔔 Alert created')
                
                # Check response time threshold
                if (response_time > settings.response_time_threshold and 
                    health_result['status'] == 'online'):
                    
                    if options['create_alerts']:
                        existing_alert = Alert.objects.filter(
                            platform=platform,
                            alert_type='slow_response',
                            status='active'
                        ).first()
                        
                        if not existing_alert:
                            Alert.objects.create(
                                platform=platform,
                                alert_type='slow_response',
                                title=f'{platform.name} slow response time',
                                message=f'Response time ({response_time:.0f}ms) exceeds threshold ({settings.response_time_threshold:.0f}ms)',
                                severity='medium'
                            )
                            alerts_created += 1
                            self.stdout.write(f'     🐌 Slow response alert created')
                
            except Exception as e:
                self.stdout.write(f' ❌ Error: {e}')
                results[platform.name] = {'status': 'error', 'error_message': str(e)}
                logger.error(f'Health check failed for {platform.name}: {e}')
        
        # Summary
        self.stdout.write('')
        self.stdout.write('📊 HEALTH CHECK SUMMARY:')
        
        online_count = sum(1 for r in results.values() if r['status'] == 'online')
        offline_count = sum(1 for r in results.values() if r['status'] == 'offline')
        warning_count = sum(1 for r in results.values() if r['status'] == 'warning')
        error_count = sum(1 for r in results.values() if r['status'] == 'error')
        
        self.stdout.write(f'   ✅ Online: {online_count}')
        self.stdout.write(f'   ❌ Offline: {offline_count}')
        self.stdout.write(f'   ⚠️  Warning: {warning_count}')
        self.stdout.write(f'   🚨 Error: {error_count}')
        
        if options['create_alerts'] and alerts_created > 0:
            self.stdout.write(f'   🔔 Alerts created: {alerts_created}')
        
        # Calculate average response time for online platforms
        online_response_times = [
            r['response_time'] for r in results.values() 
            if r['status'] == 'online' and 'response_time' in r
        ]
        
        if online_response_times:
            avg_response_time = sum(online_response_times) / len(online_response_times)
            self.stdout.write(f'   ⏱️  Avg response time: {avg_response_time:.0f}ms')
        
        self.stdout.write('')
        
        # Exit with error code if any platforms are down
        if offline_count > 0 or error_count > 0:
            self.stdout.write(
                self.style.WARNING(f'⚠️  {offline_count + error_count} platforms have issues!')
            )
            exit(1)
        else:
            self.stdout.write(
                self.style.SUCCESS('🎉 All platforms are healthy!')
            )