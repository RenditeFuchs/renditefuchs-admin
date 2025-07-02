from django.core.management.base import BaseCommand
from django.conf import settings
from monitoring.models import Platform, MonitoringSettings


class Command(BaseCommand):
    help = 'Setup monitoring platforms and default settings'

    def handle(self, *args, **options):
        self.stdout.write('🚀 Setting up RenditeFuchs Platform Monitoring...')
        
        # Create platforms from settings
        platforms_created = 0
        platforms_updated = 0
        
        for slug, config in settings.MONITORED_PLATFORMS.items():
            platform, created = Platform.objects.get_or_create(
                slug=slug,
                defaults={
                    'name': config['name'],
                    'url': config['url'],
                    'health_endpoint': config['health_endpoint'],
                    'environment': config.get('environment', 'test'),
                    'color': config.get('color', 'info'),
                    'is_active': True,
                    'description': f'Monitoring for {config["name"]} platform'
                }
            )
            
            if created:
                platforms_created += 1
                env_icon = '🟧' if config.get('environment') == 'test' else '🟩' if config.get('environment') == 'live' else '🔵'
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Created platform: {env_icon} {platform.name}')
                )
            else:
                # Update existing platform with new fields
                platform.name = config['name']
                platform.url = config['url']
                platform.health_endpoint = config['health_endpoint']
                platform.environment = config.get('environment', platform.environment)
                platform.color = config.get('color', platform.color)
                platform.save()
                platforms_updated += 1
                env_icon = '🟧' if platform.environment == 'test' else '🟩' if platform.environment == 'live' else '🔵'
                self.stdout.write(
                    self.style.WARNING(f'🔄 Updated platform: {env_icon} {platform.name}')
                )
        
        # Create default monitoring settings
        settings_obj = MonitoringSettings.get_settings()
        self.stdout.write(
            self.style.SUCCESS('⚙️  Monitoring settings configured')
        )
        
        # Summary
        self.stdout.write('')
        self.stdout.write('📊 MONITORING SETUP COMPLETE')
        self.stdout.write(f'   • Platforms created: {platforms_created}')
        self.stdout.write(f'   • Platforms updated: {platforms_updated}')
        self.stdout.write(f'   • Total platforms: {Platform.objects.count()}')
        self.stdout.write('')
        self.stdout.write('💡 Next steps:')
        self.stdout.write('   1. Start the health check service')
        self.stdout.write('   2. Configure alert thresholds')
        self.stdout.write('   3. Set up notification channels')
        self.stdout.write('')
        self.stdout.write('🎛️  Access the monitoring dashboard at: http://127.0.0.1:8003/')