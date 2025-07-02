"""
Management command to generate revenue metrics for analytics.
Should be run daily via cron job.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
import logging

from business.services import RevenueMetricService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate revenue metrics for analytics dashboard'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Date to generate metrics for (YYYY-MM-DD format, default: today)',
        )
        parser.add_argument(
            '--period',
            choices=['daily', 'monthly'],
            default='daily',
            help='Period type to generate (default: daily)',
        )
        parser.add_argument(
            '--backfill',
            action='store_true',
            help='Backfill missing metrics for the last 30 days',
        )

    def handle(self, *args, **options):
        target_date = options.get('date')
        period = options['period']
        backfill = options['backfill']
        
        if target_date:
            try:
                target_date = date.fromisoformat(target_date)
            except ValueError:
                self.stdout.write(
                    self.style.ERROR('Invalid date format. Use YYYY-MM-DD.')
                )
                return
        else:
            target_date = timezone.now().date()
        
        self.stdout.write(f'🔄 Generiere Revenue-Metriken für {target_date}...')
        
        if backfill:
            self.backfill_metrics(target_date)
        elif period == 'daily':
            self.generate_daily_metrics(target_date)
        elif period == 'monthly':
            self.generate_monthly_metrics(target_date)
    
    def generate_daily_metrics(self, target_date):
        """Generate daily metrics for a specific date"""
        try:
            revenue_metric = RevenueMetricService.generate_daily_metrics(target_date)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Daily metrics generated for {target_date}: '
                    f'€{revenue_metric.total_revenue}, '
                    f'{revenue_metric.new_customers} new customers, '
                    f'{revenue_metric.active_subscriptions} active subscriptions'
                )
            )
            
        except Exception as e:
            logger.error(f"Error generating daily metrics for {target_date}: {e}")
            self.stdout.write(
                self.style.ERROR(f'❌ Error generating daily metrics: {e}')
            )
    
    def generate_monthly_metrics(self, target_date):
        """Generate monthly metrics for the month containing target_date"""
        try:
            revenue_metric = RevenueMetricService.generate_monthly_metrics(
                target_date.year, target_date.month
            )
            
            if revenue_metric:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Monthly metrics generated for {target_date.year}-{target_date.month:02d}: '
                        f'€{revenue_metric.total_revenue}, '
                        f'{revenue_metric.new_customers} new customers'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️ No daily metrics found for {target_date.year}-{target_date.month:02d}'
                    )
                )
                
        except Exception as e:
            logger.error(f"Error generating monthly metrics for {target_date}: {e}")
            self.stdout.write(
                self.style.ERROR(f'❌ Error generating monthly metrics: {e}')
            )
    
    def backfill_metrics(self, end_date):
        """Backfill missing daily metrics for the last 30 days"""
        start_date = end_date - timedelta(days=30)
        current_date = start_date
        
        self.stdout.write(f'🔄 Backfilling metrics from {start_date} to {end_date}...')
        
        generated_count = 0
        skipped_count = 0
        
        while current_date <= end_date:
            try:
                # Check if metrics already exist
                from business.models import RevenueMetric
                if RevenueMetric.objects.filter(
                    date=current_date, 
                    period_type='daily'
                ).exists():
                    skipped_count += 1
                    self.stdout.write(f'  ⏭️ Skipping {current_date} (already exists)')
                else:
                    revenue_metric = RevenueMetricService.generate_daily_metrics(current_date)
                    generated_count += 1
                    self.stdout.write(
                        f'  ✅ Generated {current_date}: €{revenue_metric.total_revenue}'
                    )
                
            except Exception as e:
                logger.error(f"Error backfilling metrics for {current_date}: {e}")
                self.stdout.write(
                    self.style.ERROR(f'  ❌ Error for {current_date}: {e}')
                )
            
            current_date += timedelta(days=1)
        
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Backfill complete: {generated_count} generated, {skipped_count} skipped'
            )
        )