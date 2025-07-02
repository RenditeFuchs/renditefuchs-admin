"""
Management command to process subscription renewals, cancellations, and status updates.
Should be run daily via cron job.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta, date
from decimal import Decimal
import logging

from business.models import Subscription, Invoice, InvoiceLineItem, RevenueMetric
from business.services import SubscriptionService, InvoiceService, NotificationService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process subscription renewals, trial expirations, and overdue payments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making changes (preview mode)',
        )
        parser.add_argument(
            '--days-ahead',
            type=int,
            default=7,
            help='Days ahead to check for upcoming renewals (default: 7)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        days_ahead = options['days_ahead']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('🔍 PREVIEW MODE - Keine Änderungen werden durchgeführt')
            )
        
        self.stdout.write('🔄 Starte Subscription Processing...')
        
        # 1. Process trial expirations
        expired_trials = self.process_trial_expirations(dry_run)
        
        # 2. Process upcoming renewals
        upcoming_renewals = self.process_upcoming_renewals(dry_run, days_ahead)
        
        # 3. Process overdue subscriptions
        overdue_subscriptions = self.process_overdue_subscriptions(dry_run)
        
        # 4. Update subscription statuses
        status_updates = self.update_subscription_statuses(dry_run)
        
        # 5. Generate revenue metrics
        revenue_generated = self.generate_daily_revenue_metrics(dry_run)
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✅ Subscription Processing abgeschlossen:'))
        self.stdout.write(f'   • Testphasen abgelaufen: {expired_trials}')
        self.stdout.write(f'   • Bevorstehende Verlängerungen: {upcoming_renewals}')
        self.stdout.write(f'   • Überfällige Abonnements: {overdue_subscriptions}')
        self.stdout.write(f'   • Status-Updates: {status_updates}')
        self.stdout.write(f'   • Revenue-Metriken: {"Generiert" if revenue_generated else "Übersprungen"}')

    def process_trial_expirations(self, dry_run=False):
        """Process subscriptions with expired trials"""
        today = timezone.now().date()
        
        expired_trials = Subscription.objects.filter(
            status='trial',
            trial_end__date__lte=today
        )
        
        count = 0
        for subscription in expired_trials:
            self.stdout.write(f'⏰ Testphase abgelaufen: {subscription}')
            
            if not dry_run:
                # Check if customer has payment method
                if subscription.customer.stripe_customer_id:
                    # Convert to active subscription
                    subscription.status = 'active'
                    subscription.start_date = timezone.now()
                    subscription.next_billing_date = self._calculate_next_billing_date(
                        subscription.start_date, subscription.plan.billing_cycle
                    )
                    subscription.save()
                    
                    # Create first invoice
                    InvoiceService.create_subscription_invoice(subscription)
                    
                    # Send notification
                    NotificationService.send_trial_converted_notification(subscription)
                    
                    self.stdout.write(f'  ✅ Konvertiert zu aktivem Abonnement')
                else:
                    # Suspend subscription - no payment method
                    subscription.status = 'suspended'
                    subscription.save()
                    
                    # Send payment setup notification
                    NotificationService.send_payment_setup_required_notification(subscription)
                    
                    self.stdout.write(f'  ⚠️ Gesperrt - keine Zahlungsmethode')
            
            count += 1
        
        return count

    def process_upcoming_renewals(self, dry_run=False, days_ahead=7):
        """Process upcoming subscription renewals"""
        today = timezone.now().date()
        renewal_date = today + timedelta(days=days_ahead)
        
        upcoming_renewals = Subscription.objects.filter(
            status='active',
            next_billing_date__date__lte=renewal_date,
            next_billing_date__date__gte=today
        )
        
        count = 0
        for subscription in upcoming_renewals:
            days_until_renewal = (subscription.next_billing_date.date() - today).days
            
            self.stdout.write(f'🔄 Verlängerung in {days_until_renewal} Tagen: {subscription}')
            
            if not dry_run:
                # Create renewal invoice
                invoice = InvoiceService.create_subscription_invoice(subscription)
                
                # Send renewal notification
                if days_until_renewal <= 3:
                    NotificationService.send_renewal_reminder_notification(subscription, invoice)
                
                # Update next billing date
                subscription.next_billing_date = self._calculate_next_billing_date(
                    subscription.next_billing_date, subscription.plan.billing_cycle
                )
                subscription.save()
                
                self.stdout.write(f'  ✅ Rechnung erstellt: {invoice.invoice_number}')
            
            count += 1
        
        return count

    def process_overdue_subscriptions(self, dry_run=False):
        """Process subscriptions with overdue payments"""
        today = timezone.now().date()
        grace_period = today - timedelta(days=7)  # 7 days grace period
        
        overdue_subscriptions = Subscription.objects.filter(
            status='active',
            customer__invoices__status='sent',
            customer__invoices__due_date__lt=grace_period
        ).distinct()
        
        count = 0
        for subscription in overdue_subscriptions:
            overdue_invoices = subscription.customer.invoices.filter(
                status='sent',
                due_date__lt=grace_period
            )
            
            self.stdout.write(f'⚠️ Überfällige Zahlung: {subscription}')
            
            if not dry_run:
                # Suspend subscription
                subscription.status = 'past_due'
                subscription.save()
                
                # Send overdue notification
                for invoice in overdue_invoices:
                    NotificationService.send_payment_overdue_notification(subscription, invoice)
                
                self.stdout.write(f'  ⚠️ Status geändert zu "Überfällig"')
            
            count += 1
        
        return count

    def update_subscription_statuses(self, dry_run=False):
        """Update subscription statuses based on current state"""
        count = 0
        
        # Reactivate past_due subscriptions with recent payments
        recent_payments = Subscription.objects.filter(
            status='past_due',
            customer__payments__status='completed',
            customer__payments__processed_at__gte=timezone.now() - timedelta(days=7)
        ).distinct()
        
        for subscription in recent_payments:
            self.stdout.write(f'✅ Reaktivierung: {subscription}')
            
            if not dry_run:
                subscription.status = 'active'
                subscription.save()
                
                # Send reactivation notification
                NotificationService.send_subscription_reactivated_notification(subscription)
            
            count += 1
        
        return count

    def generate_daily_revenue_metrics(self, dry_run=False):
        """Generate daily revenue metrics"""
        today = timezone.now().date()
        
        # Check if metrics already exist for today
        if RevenueMetric.objects.filter(date=today, period_type='daily').exists():
            self.stdout.write('📊 Revenue-Metriken für heute bereits vorhanden')
            return False
        
        if dry_run:
            self.stdout.write('📊 Würde Revenue-Metriken generieren')
            return True
        
        # Calculate metrics
        from business.services import RevenueMetricService
        
        revenue_metric = RevenueMetricService.generate_daily_metrics(today)
        
        self.stdout.write(f'📊 Revenue-Metriken generiert: €{revenue_metric.total_revenue}')
        return True

    def _calculate_next_billing_date(self, current_date, billing_cycle):
        """Calculate next billing date based on cycle"""
        if billing_cycle == 'monthly':
            return current_date + timedelta(days=30)
        elif billing_cycle == 'quarterly':
            return current_date + timedelta(days=90)
        elif billing_cycle == 'yearly':
            return current_date + timedelta(days=365)
        else:  # lifetime
            return None