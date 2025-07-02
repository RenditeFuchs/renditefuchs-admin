from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring.models import Platform, SystemHealth, ErrorLog, Alert
from datetime import timedelta


class Command(BaseCommand):
    help = 'Show detailed status by environment (Test vs Live)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--environment',
            type=str,
            choices=['test', 'live', 'all'],
            default='all',
            help='Filter by environment (test, live, or all)',
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed platform information',
        )

    def handle(self, *args, **options):
        environment = options['environment']
        detailed = options['detailed']
        
        self.stdout.write('🌍 RenditeFuchs Environment Status Report')
        self.stdout.write('=' * 50)
        
        # Filter platforms by environment
        if environment == 'all':
            platforms = Platform.objects.filter(is_active=True).order_by('environment', 'name')
        else:
            platforms = Platform.objects.filter(
                is_active=True,
                environment=environment
            ).order_by('name')
        
        if not platforms.exists():
            self.stdout.write(
                self.style.WARNING(f'Keine aktiven Plattformen für Environment: {environment}')
            )
            return
        
        # Group by environment for display
        current_env = None
        env_stats = {'test': [], 'live': [], 'local': []}
        
        for platform in platforms:
            # Get latest health check
            latest_health = platform.health_checks.first()
            
            # Get error count in last 24h
            last_24h = timezone.now() - timedelta(hours=24)
            error_count = platform.errors.filter(
                last_seen__gte=last_24h,
                is_resolved=False
            ).count()
            
            # Get active alerts
            active_alerts = platform.alerts.filter(status='active').count()
            
            platform_info = {
                'platform': platform,
                'health': latest_health,
                'error_count_24h': error_count,
                'active_alerts': active_alerts,
            }
            
            if platform.environment in env_stats:
                env_stats[platform.environment].append(platform_info)
        
        # Display environment statistics
        for env, platforms_info in env_stats.items():
            if not platforms_info:
                continue
                
            if environment != 'all' and env != environment:
                continue
            
            env_icon = '🟧' if env == 'test' else '🟩' if env == 'live' else '🔵'
            env_name = env.upper()
            
            self.stdout.write('')
            self.stdout.write(f'{env_icon} {env_name} ENVIRONMENT')
            self.stdout.write('-' * 30)
            
            # Calculate summary stats
            total_platforms = len(platforms_info)
            online_platforms = sum(1 for p in platforms_info 
                                 if p['health'] and p['health'].status == 'online')
            total_errors = sum(p['error_count_24h'] for p in platforms_info)
            total_alerts = sum(p['active_alerts'] for p in platforms_info)
            uptime_pct = (online_platforms / total_platforms * 100) if total_platforms > 0 else 0
            
            self.stdout.write(f'📊 Übersicht:')
            self.stdout.write(f'   Plattformen: {online_platforms}/{total_platforms} online ({uptime_pct:.1f}%)')
            self.stdout.write(f'   Fehler (24h): {total_errors}')
            self.stdout.write(f'   Aktive Warnungen: {total_alerts}')
            
            if detailed:
                self.stdout.write('')
                self.stdout.write('📋 Plattform Details:')
                
                for platform_info in platforms_info:
                    platform = platform_info['platform']
                    health = platform_info['health']
                    
                    # Status icon
                    if health:
                        if health.status == 'online':
                            status_icon = '✅'
                            status_color = self.style.SUCCESS
                        elif health.status == 'offline':
                            status_icon = '❌'
                            status_color = self.style.ERROR
                        else:
                            status_icon = '⚠️'
                            status_color = self.style.WARNING
                    else:
                        status_icon = '❓'
                        status_color = self.style.WARNING
                    
                    platform_line = f'   {status_icon} {platform.name}'
                    
                    if health:
                        platform_line += f' - {health.get_status_display()}'
                        if health.response_time:
                            platform_line += f' ({health.response_time:.0f}ms)'
                        platform_line += f' - {health.checked_at.strftime("%H:%M")}'
                    else:
                        platform_line += ' - Keine Daten'
                    
                    if platform_info['error_count_24h'] > 0:
                        platform_line += f' - {platform_info["error_count_24h"]} Fehler'
                    
                    if platform_info['active_alerts'] > 0:
                        platform_line += f' - {platform_info["active_alerts"]} Warnungen'
                    
                    self.stdout.write(status_color(platform_line))
        
        # Show recent critical issues
        if environment == 'all':
            recent_critical_errors = ErrorLog.objects.filter(
                severity='critical',
                is_resolved=False,
                last_seen__gte=timezone.now() - timedelta(hours=24)
            ).select_related('platform').order_by('-last_seen')[:5]
            
            if recent_critical_errors:
                self.stdout.write('')
                self.stdout.write('🚨 Kritische Fehler (24h):')
                self.stdout.write('-' * 30)
                
                for error in recent_critical_errors:
                    env_icon = '🟧' if error.platform.environment == 'test' else '🟩' if error.platform.environment == 'live' else '🔵'
                    self.stdout.write(
                        self.style.ERROR(
                            f'   {env_icon} {error.platform.name}: {error.message[:60]}...'
                        )
                    )
        
        self.stdout.write('')
        self.stdout.write('✅ Environment Status Report vollständig')