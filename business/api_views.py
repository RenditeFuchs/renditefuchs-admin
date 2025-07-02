"""
API endpoints for subscription management and business operations.
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import json
import logging

from .models import Subscription, Invoice, Customer, PricingPlan
from .services import SubscriptionService, InvoiceService, NotificationService

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required, name='dispatch')
class SubscriptionManagementAPI(View):
    """API for subscription management operations"""
    
    def get(self, request, subscription_id=None):
        """Get subscription details or list subscriptions"""
        if subscription_id:
            subscription = get_object_or_404(Subscription, id=subscription_id)
            return JsonResponse({
                'subscription': self._serialize_subscription(subscription)
            })
        else:
            # List subscriptions with filters
            subscriptions = Subscription.objects.select_related('customer__user', 'plan')
            
            # Apply filters
            status = request.GET.get('status')
            if status:
                subscriptions = subscriptions.filter(status=status)
            
            plan_id = request.GET.get('plan_id')
            if plan_id:
                subscriptions = subscriptions.filter(plan_id=plan_id)
            
            customer_id = request.GET.get('customer_id')
            if customer_id:
                subscriptions = subscriptions.filter(customer_id=customer_id)
            
            # Pagination
            page = int(request.GET.get('page', 1))
            per_page = int(request.GET.get('per_page', 25))
            start = (page - 1) * per_page
            end = start + per_page
            
            total_count = subscriptions.count()
            subscriptions = subscriptions[start:end]
            
            return JsonResponse({
                'subscriptions': [
                    self._serialize_subscription(sub) for sub in subscriptions
                ],
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_count,
                    'has_next': end < total_count,
                    'has_previous': page > 1
                }
            })
    
    def post(self, request):
        """Create a new subscription"""
        try:
            data = json.loads(request.body)
            
            customer_id = data.get('customer_id')
            plan_id = data.get('plan_id')
            start_trial = data.get('start_trial', True)
            
            if not customer_id or not plan_id:
                return JsonResponse({
                    'error': 'customer_id and plan_id are required'
                }, status=400)
            
            customer = get_object_or_404(Customer, id=customer_id)
            plan = get_object_or_404(PricingPlan, id=plan_id)
            
            # Check if customer already has active subscription for this plan
            existing = Subscription.objects.filter(
                customer=customer,
                plan=plan,
                status__in=['trial', 'active']
            ).first()
            
            if existing:
                return JsonResponse({
                    'error': 'Customer already has an active subscription for this plan'
                }, status=400)
            
            subscription = SubscriptionService.create_subscription(
                customer=customer,
                plan=plan,
                start_trial=start_trial
            )
            
            return JsonResponse({
                'subscription': self._serialize_subscription(subscription),
                'message': 'Subscription created successfully'
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error creating subscription: {e}")
            return JsonResponse({'error': 'Internal server error'}, status=500)
    
    def patch(self, request, subscription_id):
        """Update subscription (status, plan change, etc.)"""
        try:
            subscription = get_object_or_404(Subscription, id=subscription_id)
            data = json.loads(request.body)
            
            action = data.get('action')
            
            if action == 'cancel':
                reason = data.get('reason', 'customer_request')
                SubscriptionService.cancel_subscription(subscription, reason)
                message = 'Subscription canceled successfully'
                
            elif action == 'reactivate':
                SubscriptionService.reactivate_subscription(subscription)
                message = 'Subscription reactivated successfully'
                
            elif action == 'change_plan':
                new_plan_id = data.get('new_plan_id')
                if not new_plan_id:
                    return JsonResponse({'error': 'new_plan_id is required'}, status=400)
                
                new_plan = get_object_or_404(PricingPlan, id=new_plan_id)
                SubscriptionService.change_plan(subscription, new_plan)
                message = f'Plan changed to {new_plan.name} successfully'
                
            elif action == 'update_custom_price':
                custom_price = data.get('custom_price')
                if custom_price is not None:
                    subscription.custom_price = custom_price
                    subscription.save()
                    message = 'Custom price updated successfully'
                else:
                    return JsonResponse({'error': 'custom_price is required'}, status=400)
                
            elif action == 'update_discount':
                discount_percentage = data.get('discount_percentage')
                if discount_percentage is not None:
                    subscription.discount_percentage = discount_percentage
                    subscription.save()
                    message = 'Discount updated successfully'
                else:
                    return JsonResponse({'error': 'discount_percentage is required'}, status=400)
                
            else:
                return JsonResponse({'error': 'Invalid action'}, status=400)
            
            return JsonResponse({
                'subscription': self._serialize_subscription(subscription),
                'message': message
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error updating subscription: {e}")
            return JsonResponse({'error': 'Internal server error'}, status=500)
    
    def _serialize_subscription(self, subscription):
        """Serialize subscription object to JSON"""
        return {
            'id': subscription.id,
            'customer': {
                'id': subscription.customer.id,
                'name': subscription.customer.get_display_name(),
                'email': subscription.customer.user.email,
                'type': subscription.customer.customer_type,
            },
            'plan': {
                'id': subscription.plan.id,
                'name': subscription.plan.name,
                'price': float(subscription.plan.price),
                'billing_cycle': subscription.plan.billing_cycle,
                'type': subscription.plan.plan_type,
            },
            'status': subscription.status,
            'start_date': subscription.start_date.isoformat() if subscription.start_date else None,
            'end_date': subscription.end_date.isoformat() if subscription.end_date else None,
            'next_billing_date': subscription.next_billing_date.isoformat() if subscription.next_billing_date else None,
            'trial_start': subscription.trial_start.isoformat() if subscription.trial_start else None,
            'trial_end': subscription.trial_end.isoformat() if subscription.trial_end else None,
            'effective_price': float(subscription.get_effective_price()),
            'custom_price': float(subscription.custom_price) if subscription.custom_price else None,
            'discount_percentage': float(subscription.discount_percentage),
            'is_active': subscription.is_active(),
            'days_until_renewal': subscription.days_until_renewal(),
            'created_at': subscription.created_at.isoformat(),
            'updated_at': subscription.updated_at.isoformat(),
            'canceled_at': subscription.canceled_at.isoformat() if subscription.canceled_at else None,
        }


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(login_required, name='dispatch')
class InvoiceManagementAPI(View):
    """API for invoice management operations"""
    
    def get(self, request, invoice_id=None):
        """Get invoice details or list invoices"""
        if invoice_id:
            invoice = get_object_or_404(Invoice, id=invoice_id)
            return JsonResponse({
                'invoice': self._serialize_invoice(invoice)
            })
        else:
            # List invoices with filters
            invoices = Invoice.objects.select_related('customer__user', 'subscription')
            
            # Apply filters
            status = request.GET.get('status')
            if status:
                invoices = invoices.filter(status=status)
            
            customer_id = request.GET.get('customer_id')
            if customer_id:
                invoices = invoices.filter(customer_id=customer_id)
            
            # Pagination
            page = int(request.GET.get('page', 1))
            per_page = int(request.GET.get('per_page', 25))
            start = (page - 1) * per_page
            end = start + per_page
            
            total_count = invoices.count()
            invoices = invoices[start:end]
            
            return JsonResponse({
                'invoices': [
                    self._serialize_invoice(inv) for inv in invoices
                ],
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_count,
                    'has_next': end < total_count,
                    'has_previous': page > 1
                }
            })
    
    def patch(self, request, invoice_id):
        """Update invoice status"""
        try:
            invoice = get_object_or_404(Invoice, id=invoice_id)
            data = json.loads(request.body)
            
            action = data.get('action')
            
            if action == 'send':
                InvoiceService.send_invoice(invoice)
                message = 'Invoice sent successfully'
                
            elif action == 'mark_paid':
                payment_method = data.get('payment_method', 'manual')
                InvoiceService.mark_invoice_paid(invoice, payment_method)
                message = 'Invoice marked as paid successfully'
                
            elif action == 'cancel':
                invoice.status = 'canceled'
                invoice.save()
                message = 'Invoice canceled successfully'
                
            else:
                return JsonResponse({'error': 'Invalid action'}, status=400)
            
            return JsonResponse({
                'invoice': self._serialize_invoice(invoice),
                'message': message
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error updating invoice: {e}")
            return JsonResponse({'error': 'Internal server error'}, status=500)
    
    def _serialize_invoice(self, invoice):
        """Serialize invoice object to JSON"""
        return {
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'customer': {
                'id': invoice.customer.id,
                'name': invoice.customer.get_display_name(),
                'email': invoice.customer.user.email,
            },
            'subscription': {
                'id': invoice.subscription.id,
                'plan_name': invoice.subscription.plan.name,
            } if invoice.subscription else None,
            'subtotal': float(invoice.subtotal),
            'tax_rate': float(invoice.tax_rate),
            'tax_amount': float(invoice.tax_amount),
            'total_amount': float(invoice.total_amount),
            'status': invoice.status,
            'issue_date': invoice.issue_date.isoformat(),
            'due_date': invoice.due_date.isoformat(),
            'paid_date': invoice.paid_date.isoformat() if invoice.paid_date else None,
            'is_overdue': invoice.is_overdue(),
            'line_items': [
                {
                    'description': item.description,
                    'quantity': float(item.quantity),
                    'unit_price': float(item.unit_price),
                    'total_price': float(item.total_price),
                    'period_start': item.period_start.isoformat() if item.period_start else None,
                    'period_end': item.period_end.isoformat() if item.period_end else None,
                }
                for item in invoice.line_items.all()
            ],
            'created_at': invoice.created_at.isoformat(),
            'updated_at': invoice.updated_at.isoformat(),
        }


@csrf_exempt
@require_http_methods(["GET"])
def subscription_analytics_api(request):
    """API endpoint for subscription analytics"""
    try:
        # Date range
        from datetime import datetime, timedelta
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)
        
        period = request.GET.get('period', '30d')
        if period == '7d':
            start_date = end_date - timedelta(days=7)
        elif period == '90d':
            start_date = end_date - timedelta(days=90)
        elif period == '365d':
            start_date = end_date - timedelta(days=365)
        
        # Calculate metrics
        total_subscriptions = Subscription.objects.count()
        active_subscriptions = Subscription.objects.filter(
            status__in=['trial', 'active']
        ).count()
        
        new_subscriptions = Subscription.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).count()
        
        canceled_subscriptions = Subscription.objects.filter(
            status='canceled',
            canceled_at__date__gte=start_date,
            canceled_at__date__lte=end_date
        ).count()
        
        # Revenue metrics - MRR calculation
        monthly_subscriptions = Subscription.objects.filter(
            status__in=['trial', 'active'],
            plan__billing_cycle='monthly'
        ).aggregate(total=Sum('plan__price'))['total'] or 0
        
        quarterly_subscriptions = Subscription.objects.filter(
            status__in=['trial', 'active'],
            plan__billing_cycle='quarterly'
        ).aggregate(total=Sum('plan__price'))['total'] or 0
        
        yearly_subscriptions = Subscription.objects.filter(
            status__in=['trial', 'active'],
            plan__billing_cycle='yearly'
        ).aggregate(total=Sum('plan__price'))['total'] or 0
        
        mrr = monthly_subscriptions + (quarterly_subscriptions / 3) + (yearly_subscriptions / 12)
        
        # Revenue for period
        from django.db.models import Count, Sum, Q
        revenue_for_period = Invoice.objects.filter(
            status='paid',
            paid_date__date__gte=start_date,
            paid_date__date__lte=end_date
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Churn rate (simplified calculation)
        churn_rate = 0
        if total_subscriptions > 0:
            churn_rate = (canceled_subscriptions / total_subscriptions) * 100
        
        # Top plans
        top_plans = PricingPlan.objects.annotate(
            subscription_count=Count('subscriptions', filter=Q(subscriptions__status__in=['trial', 'active'])),
            revenue=Sum('subscriptions__plan__price', filter=Q(subscriptions__status__in=['trial', 'active']))
        ).filter(subscription_count__gt=0).order_by('-revenue')[:5]
        
        return JsonResponse({
            'period': period,
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
            },
            'metrics': {
                'total_subscriptions': total_subscriptions,
                'active_subscriptions': active_subscriptions,
                'new_subscriptions': new_subscriptions,
                'canceled_subscriptions': canceled_subscriptions,
                'mrr': float(mrr),
                'revenue_for_period': float(revenue_for_period),
                'churn_rate': float(churn_rate),
            },
            'top_plans': [
                {
                    'id': plan.id,
                    'name': plan.name,
                    'subscription_count': plan.subscription_count,
                    'revenue': float(plan.revenue or 0),
                }
                for plan in top_plans
            ],
        })
        
    except Exception as e:
        logger.error(f"Error in subscription analytics API: {e}")
        return JsonResponse({'error': 'Internal server error'}, status=500)