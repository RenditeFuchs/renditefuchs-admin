from django.core.management.base import BaseCommand
from monitoring.utils import create_manual_error
from monitoring.models import Platform, ErrorLog
import time


class Command(BaseCommand):
    help = 'Test error tracking system with sample errors'

    def handle(self, *args, **options):
        self.stdout.write('🧪 Testing Error Tracking System...')
        
        # Get platforms
        platforms = Platform.objects.filter(is_active=True)
        
        if not platforms.exists():
            self.stdout.write(
                self.style.ERROR('No platforms found. Run setup_monitoring first.')
            )
            return
        
        # Test different types of errors
        test_errors = [
            {
                'platform': 'main',
                'error_type': '500',
                'severity': 'high',
                'message': 'Internal server error in user registration',
                'url_path': '/auth/?action=register',
                'user_id': 'test_user_123',
                'stack_trace': 'Traceback (most recent call last):\n  File "views.py", line 42, in handle_registration\nValueError: Invalid email format'
            },
            {
                'platform': 'focus',
                'error_type': 'database',
                'severity': 'critical',
                'message': 'Database connection timeout',
                'url_path': '/dashboard/',
                'request_data': {'method': 'GET', 'user_agent': 'Mozilla/5.0 Test Browser'}
            },
            {
                'platform': 'main',
                'error_type': '404',
                'severity': 'low',
                'message': 'Page not found: /nonexistent-page',
                'url_path': '/nonexistent-page',
                'ip_address': '192.168.1.100'
            },
            {
                'platform': 'blog',
                'error_type': 'api',
                'severity': 'medium',
                'message': 'External API rate limit exceeded',
                'url_path': '/api/posts/',
                'environment_data': {'api_endpoint': 'external-service.com', 'rate_limit': '100/hour'}
            },
            {
                'platform': 'academy',
                'error_type': 'timeout',
                'severity': 'high',
                'message': 'Request timeout while loading course content',
                'url_path': '/courses/bitcoin-basics/',
                'user_id': 'student_456'
            }
        ]
        
        errors_created = 0
        
        for i, error_data in enumerate(test_errors, 1):
            platform_slug = error_data.pop('platform')
            
            self.stdout.write(f'   {i}. Creating {error_data["error_type"]} error for {platform_slug}...', ending='')
            
            success = create_manual_error(platform_slug, **error_data)
            
            if success:
                self.stdout.write(' ✅')
                errors_created += 1
            else:
                self.stdout.write(' ❌')
            
            # Small delay to simulate real-time errors
            time.sleep(0.5)
        
        # Create some duplicate errors to test error counting
        self.stdout.write('   📈 Creating duplicate errors to test counting...')
        for _ in range(3):
            create_manual_error(
                'main',
                error_type='500',
                message='Internal server error in user registration',
                severity='high'
            )
            time.sleep(0.2)
        
        # Summary
        total_errors = ErrorLog.objects.count()
        active_errors = ErrorLog.objects.filter(is_resolved=False).count()
        
        self.stdout.write('')
        self.stdout.write('📊 ERROR TRACKING TEST RESULTS:')
        self.stdout.write(f'   ✅ Test errors created: {errors_created}')
        self.stdout.write(f'   📝 Total errors in database: {total_errors}')
        self.stdout.write(f'   🚨 Active errors: {active_errors}')
        
        # Show recent errors by platform
        self.stdout.write('')
        self.stdout.write('📈 Errors by platform:')
        for platform in platforms:
            platform_errors = ErrorLog.objects.filter(platform=platform).count()
            active_platform_errors = ErrorLog.objects.filter(
                platform=platform, 
                is_resolved=False
            ).count()
            self.stdout.write(f'   {platform.name}: {platform_errors} total, {active_platform_errors} active')
        
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS('🎉 Error tracking test completed! Check the admin dashboard at http://127.0.0.1:8003/monitoring/errors/')
        )