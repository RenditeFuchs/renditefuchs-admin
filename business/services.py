"""
Business services for subscription management, billing, and notifications.
"""

from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from datetime import timedelta, date
from decimal import Decimal
import logging

from .models import (
    Subscription, Invoice, InvoiceLineItem, Payment, 
    RevenueMetric, Customer, PricingPlan
)

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Service for managing subscription lifecycle"""
    
    @staticmethod
    def create_subscription(customer, plan, start_trial=True):
        """Create a new subscription for a customer"""
        subscription = Subscription.objects.create(
            customer=customer,
            plan=plan,
            status='trial' if start_trial else 'active',
            start_date=timezone.now(),
        )
        
        if start_trial and plan.plan_type != 'free':
            # Set trial period (14 days default)
            subscription.trial_start = timezone.now()
            subscription.trial_end = timezone.now() + timedelta(days=14)
        else:
            # Start billing immediately
            subscription.next_billing_date = SubscriptionService.calculate_next_billing_date(
                subscription.start_date, plan.billing_cycle
            )
        
        subscription.save()
        
        # Send welcome notification
        NotificationService.send_subscription_created_notification(subscription)
        
        logger.info(f"Subscription created: {subscription}")
        return subscription
    
    @staticmethod
    def cancel_subscription(subscription, reason="customer_request"):
        """Cancel a subscription"""
        subscription.status = 'canceled'
        subscription.canceled_at = timezone.now()
        subscription.save()
        
        # Send cancellation notification
        NotificationService.send_subscription_canceled_notification(subscription, reason)
        
        logger.info(f"Subscription canceled: {subscription}")
        return subscription
    
    @staticmethod
    def reactivate_subscription(subscription):
        """Reactivate a canceled or suspended subscription"""
        if subscription.status in ['canceled', 'suspended', 'past_due']:
            subscription.status = 'active'
            subscription.next_billing_date = SubscriptionService.calculate_next_billing_date(
                timezone.now(), subscription.plan.billing_cycle
            )
            subscription.save()
            
            # Send reactivation notification
            NotificationService.send_subscription_reactivated_notification(subscription)
            
            logger.info(f"Subscription reactivated: {subscription}")
            return subscription
        
        return None
    
    @staticmethod
    def change_plan(subscription, new_plan):
        """Change subscription plan (upgrade/downgrade)"""
        old_plan = subscription.plan
        subscription.plan = new_plan
        
        # Calculate prorated amount if needed
        proration = SubscriptionService.calculate_plan_change_proration(
            subscription, old_plan, new_plan
        )
        
        subscription.save()
        
        # Create proration invoice if needed
        if proration != 0:
            InvoiceService.create_proration_invoice(subscription, proration, old_plan, new_plan)
        
        # Send plan change notification
        NotificationService.send_plan_changed_notification(subscription, old_plan, new_plan)
        
        logger.info(f"Plan changed: {subscription} from {old_plan} to {new_plan}")
        return subscription
    
    @staticmethod
    def calculate_next_billing_date(current_date, billing_cycle):
        """Calculate next billing date based on cycle"""
        if billing_cycle == 'monthly':
            return current_date + timedelta(days=30)
        elif billing_cycle == 'quarterly':
            return current_date + timedelta(days=90)
        elif billing_cycle == 'yearly':
            return current_date + timedelta(days=365)
        else:  # lifetime
            return None
    
    @staticmethod
    def calculate_plan_change_proration(subscription, old_plan, new_plan):
        """Calculate proration amount for plan changes"""
        if not subscription.next_billing_date:
            return Decimal('0.00')
        
        # Days remaining in current billing period
        days_remaining = (subscription.next_billing_date.date() - timezone.now().date()).days
        
        # Calculate daily rates
        old_daily_rate = old_plan.price / 30  # Simplified to 30 days
        new_daily_rate = new_plan.price / 30
        
        # Calculate proration
        proration = (new_daily_rate - old_daily_rate) * days_remaining
        
        return proration


class InvoiceService:
    """Service for invoice management and generation"""
    
    @staticmethod
    def create_subscription_invoice(subscription):
        """Create an invoice for subscription renewal"""
        # Calculate billing period
        billing_start = subscription.next_billing_date or timezone.now()
        billing_end = SubscriptionService.calculate_next_billing_date(
            billing_start, subscription.plan.billing_cycle
        )
        
        # Create invoice
        invoice = Invoice.objects.create(
            customer=subscription.customer,
            subscription=subscription,
            subtotal=subscription.get_effective_price(),
            status='draft',
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30),
        )
        
        # Create line item
        InvoiceLineItem.objects.create(
            invoice=invoice,
            description=f"{subscription.plan.name} - {subscription.plan.get_billing_cycle_display()}",
            quantity=Decimal('1.00'),
            unit_price=subscription.get_effective_price(),
            period_start=billing_start.date() if billing_start else None,
            period_end=billing_end.date() if billing_end else None,
        )
        
        # Send the invoice
        InvoiceService.send_invoice(invoice)
        
        logger.info(f"Invoice created: {invoice}")
        return invoice
    
    @staticmethod
    def create_proration_invoice(subscription, proration_amount, old_plan, new_plan):
        """Create proration invoice for plan changes"""
        invoice = Invoice.objects.create(
            customer=subscription.customer,
            subscription=subscription,
            subtotal=abs(proration_amount),
            status='draft',
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30),
        )
        
        # Create line item
        description = f"Plan-Änderung: {old_plan.name} → {new_plan.name}"
        if proration_amount < 0:
            description += " (Gutschrift)"
        
        InvoiceLineItem.objects.create(
            invoice=invoice,
            description=description,
            quantity=Decimal('1.00'),
            unit_price=abs(proration_amount),
        )
        
        # Send the invoice
        InvoiceService.send_invoice(invoice)
        
        logger.info(f"Proration invoice created: {invoice}")
        return invoice
    
    @staticmethod
    def send_invoice(invoice):
        """Send invoice to customer"""
        invoice.status = 'sent'
        invoice.save()
        
        # Send email notification
        NotificationService.send_invoice_notification(invoice)
        
        logger.info(f"Invoice sent: {invoice}")
    
    @staticmethod
    def mark_invoice_paid(invoice, payment_method="manual"):
        """Mark invoice as paid"""
        invoice.status = 'paid'
        invoice.paid_date = timezone.now()
        invoice.payment_method = payment_method
        invoice.save()
        
        # Create payment record
        Payment.objects.create(
            invoice=invoice,
            customer=invoice.customer,
            amount=invoice.total_amount,
            payment_method=payment_method,
            status='completed',
            processed_at=timezone.now(),
        )
        
        # Send payment confirmation
        NotificationService.send_payment_confirmation_notification(invoice)
        
        logger.info(f"Invoice marked as paid: {invoice}")


class NotificationService:
    """Service for sending notifications to customers"""
    
    @staticmethod
    def send_subscription_created_notification(subscription):
        """Send welcome email for new subscription"""
        subject = f"Willkommen bei RenditeFuchs - {subscription.plan.name}"
        
        context = {
            'subscription': subscription,
            'customer': subscription.customer,
            'plan': subscription.plan,
        }
        
        message = render_to_string('business/emails/subscription_created.html', context)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[subscription.customer.user.email],
            html_message=message,
        )
    
    @staticmethod
    def send_trial_converted_notification(subscription):
        """Send notification when trial converts to paid"""
        subject = "Ihre Testphase wurde aktiviert - RenditeFuchs"
        
        context = {
            'subscription': subscription,
            'customer': subscription.customer,
            'plan': subscription.plan,
        }
        
        message = render_to_string('business/emails/trial_converted.html', context)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[subscription.customer.user.email],
            html_message=message,
        )
    
    @staticmethod
    def send_subscription_canceled_notification(subscription, reason):
        """Send cancellation confirmation"""
        subject = "Abonnement gekündigt - RenditeFuchs"
        
        context = {
            'subscription': subscription,
            'customer': subscription.customer,
            'reason': reason,
        }
        
        message = render_to_string('business/emails/subscription_canceled.html', context)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[subscription.customer.user.email],
            html_message=message,
        )
    
    @staticmethod
    def send_invoice_notification(invoice):
        """Send invoice to customer"""
        subject = f"Neue Rechnung {invoice.invoice_number} - RenditeFuchs"
        
        context = {
            'invoice': invoice,
            'customer': invoice.customer,
            'line_items': invoice.line_items.all(),
        }
        
        message = render_to_string('business/emails/invoice_notification.html', context)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invoice.customer.user.email],
            html_message=message,
        )
    
    @staticmethod
    def send_payment_overdue_notification(subscription, invoice):
        """Send overdue payment notification"""
        subject = f"Überfällige Zahlung - Rechnung {invoice.invoice_number}"
        
        context = {
            'subscription': subscription,
            'invoice': invoice,
            'customer': subscription.customer,
        }
        
        message = render_to_string('business/emails/payment_overdue.html', context)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[subscription.customer.user.email],
            html_message=message,
        )
    
    @staticmethod
    def send_renewal_reminder_notification(subscription, invoice):
        """Send renewal reminder"""
        subject = f"Verlängerung Ihres Abonnements - {subscription.plan.name}"
        
        context = {
            'subscription': subscription,
            'invoice': invoice,
            'customer': subscription.customer,
        }
        
        message = render_to_string('business/emails/renewal_reminder.html', context)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[subscription.customer.user.email],
            html_message=message,
        )
    
    @staticmethod
    def send_subscription_reactivated_notification(subscription):
        """Send reactivation notification"""
        subject = "Ihr Abonnement wurde reaktiviert - RenditeFuchs"
        
        context = {
            'subscription': subscription,
            'customer': subscription.customer,
        }
        
        message = render_to_string('business/emails/subscription_reactivated.html', context)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[subscription.customer.user.email],
            html_message=message,
        )
    
    @staticmethod
    def send_plan_changed_notification(subscription, old_plan, new_plan):
        """Send plan change notification"""
        subject = f"Plan geändert: {old_plan.name} → {new_plan.name}"
        
        context = {
            'subscription': subscription,
            'customer': subscription.customer,
            'old_plan': old_plan,
            'new_plan': new_plan,
        }
        
        message = render_to_string('business/emails/plan_changed.html', context)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[subscription.customer.user.email],
            html_message=message,
        )
    
    @staticmethod
    def send_payment_confirmation_notification(invoice):
        """Send payment confirmation"""
        subject = f"Zahlung erhalten - Rechnung {invoice.invoice_number}"
        
        context = {
            'invoice': invoice,
            'customer': invoice.customer,
        }
        
        message = render_to_string('business/emails/payment_confirmation.html', context)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invoice.customer.user.email],
            html_message=message,
        )
    
    @staticmethod
    def send_payment_setup_required_notification(subscription):
        """Send payment setup required notification"""
        subject = "Zahlungsmethode einrichten - RenditeFuchs"
        
        context = {
            'subscription': subscription,
            'customer': subscription.customer,
        }
        
        message = render_to_string('business/emails/payment_setup_required.html', context)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[subscription.customer.user.email],
            html_message=message,
        )


class RevenueMetricService:
    """Service for generating revenue analytics"""
    
    @staticmethod
    def generate_daily_metrics(target_date):
        """Generate daily revenue metrics for a specific date"""
        # Calculate revenue for the day
        total_revenue = Invoice.objects.filter(
            status='paid',
            paid_date__date=target_date
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        
        # Subscription vs one-time revenue
        subscription_revenue = Invoice.objects.filter(
            status='paid',
            paid_date__date=target_date,
            subscription__isnull=False
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        
        one_time_revenue = total_revenue - subscription_revenue
        
        # Customer metrics
        new_customers = Customer.objects.filter(
            created_at__date=target_date
        ).count()
        
        # Subscription metrics
        active_subscriptions = Subscription.objects.filter(
            status__in=['trial', 'active']
        ).count()
        
        canceled_subscriptions = Subscription.objects.filter(
            status='canceled',
            canceled_at__date=target_date
        ).count()
        
        # Plan metrics
        plan_metrics = {}
        for plan in PricingPlan.objects.filter(is_active=True):
            plan_revenue = Invoice.objects.filter(
                status='paid',
                paid_date__date=target_date,
                subscription__plan=plan
            ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
            
            plan_count = Subscription.objects.filter(
                status__in=['trial', 'active'],
                plan=plan
            ).count()
            
            plan_metrics[plan.slug] = {
                'revenue': float(plan_revenue),
                'count': plan_count,
                'name': plan.name
            }
        
        # Create revenue metric record
        revenue_metric = RevenueMetric.objects.create(
            date=target_date,
            period_type='daily',
            total_revenue=total_revenue,
            subscription_revenue=subscription_revenue,
            one_time_revenue=one_time_revenue,
            new_customers=new_customers,
            active_subscriptions=active_subscriptions,
            canceled_subscriptions=canceled_subscriptions,
            plan_metrics=plan_metrics,
        )
        
        logger.info(f"Daily revenue metrics generated: {target_date} - €{total_revenue}")
        return revenue_metric
    
    @staticmethod
    def generate_monthly_metrics(year, month):
        """Generate monthly revenue metrics"""
        from calendar import monthrange
        
        start_date = date(year, month, 1)
        end_date = date(year, month, monthrange(year, month)[1])
        
        # Aggregate daily metrics for the month
        daily_metrics = RevenueMetric.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
            period_type='daily'
        )
        
        if not daily_metrics.exists():
            return None
        
        # Calculate monthly totals
        total_revenue = daily_metrics.aggregate(
            total=Sum('total_revenue')
        )['total'] or Decimal('0.00')
        
        subscription_revenue = daily_metrics.aggregate(
            total=Sum('subscription_revenue')
        )['total'] or Decimal('0.00')
        
        one_time_revenue = daily_metrics.aggregate(
            total=Sum('one_time_revenue')
        )['total'] or Decimal('0.00')
        
        new_customers = daily_metrics.aggregate(
            total=Sum('new_customers')
        )['total'] or 0
        
        # Get end-of-month subscription counts
        active_subscriptions = Subscription.objects.filter(
            Q(created_at__date__lte=end_date) &
            (Q(canceled_at__isnull=True) | Q(canceled_at__date__gt=end_date))
        ).count()
        
        canceled_subscriptions = daily_metrics.aggregate(
            total=Sum('canceled_subscriptions')
        )['total'] or 0
        
        # Create monthly metric record
        monthly_metric = RevenueMetric.objects.create(
            date=start_date,
            period_type='monthly',
            total_revenue=total_revenue,
            subscription_revenue=subscription_revenue,
            one_time_revenue=one_time_revenue,
            new_customers=new_customers,
            active_subscriptions=active_subscriptions,
            canceled_subscriptions=canceled_subscriptions,
        )
        
        logger.info(f"Monthly revenue metrics generated: {year}-{month:02d} - €{total_revenue}")
        return monthly_metric