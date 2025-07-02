from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    PricingPlan, Customer, Subscription, Invoice, 
    InvoiceLineItem, Payment, RevenueMetric
)


@admin.register(PricingPlan)
class PricingPlanAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'plan_type', 'get_price_display', 'billing_cycle', 
        'is_active', 'is_featured', 'display_order', 'created_at'
    ]
    list_filter = ['plan_type', 'billing_cycle', 'is_active', 'is_featured']
    search_fields = ['name', 'description']
    ordering = ['display_order', 'price']
    
    fieldsets = (
        ('Grundinformationen', {
            'fields': ('name', 'slug', 'plan_type', 'description')
        }),
        ('Preisgestaltung', {
            'fields': ('price', 'billing_cycle')
        }),
        ('Features & Limits', {
            'fields': ('features', 'max_users', 'max_projects', 'storage_gb')
        }),
        ('Zugriffsrechte', {
            'fields': ('allows_api_access', 'allows_priority_support', 'allows_custom_branding')
        }),
        ('Anzeige', {
            'fields': ('is_featured', 'is_active', 'display_order')
        }),
    )
    
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = [
        'get_display_name', 'user_email', 'customer_type', 
        'billing_country', 'created_at'
    ]
    list_filter = ['customer_type', 'billing_country', 'created_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'company_name']
    raw_id_fields = ['user']
    
    fieldsets = (
        ('Verknüpfter Benutzer', {
            'fields': ('user',)
        }),
        ('Kundeninformationen', {
            'fields': ('customer_type', 'company_name', 'vat_number')
        }),
        ('Rechnungsadresse', {
            'fields': (
                'billing_address_line1', 'billing_address_line2',
                'billing_city', 'billing_postal_code', 'billing_country'
            )
        }),
        ('Zahlungsinformationen', {
            'fields': ('stripe_customer_id', 'preferred_payment_method')
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'E-Mail'
    
    def get_display_name(self, obj):
        return obj.get_display_name()
    get_display_name.short_description = 'Name'


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 1
    fields = ['description', 'quantity', 'unit_price', 'total_price', 'period_start', 'period_end']
    readonly_fields = ['total_price']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        'customer_name', 'plan_name', 'status', 'get_effective_price',
        'start_date', 'next_billing_date', 'created_at'
    ]
    list_filter = ['status', 'plan__plan_type', 'plan__billing_cycle', 'created_at']
    search_fields = ['customer__user__email', 'customer__company_name', 'plan__name']
    raw_id_fields = ['customer', 'plan']
    
    fieldsets = (
        ('Abonnement', {
            'fields': ('customer', 'plan', 'status')
        }),
        ('Zeiträume', {
            'fields': ('start_date', 'end_date', 'next_billing_date')
        }),
        ('Testphase', {
            'fields': ('trial_start', 'trial_end')
        }),
        ('Preisanpassungen', {
            'fields': ('custom_price', 'discount_percentage')
        }),
        ('Payment Integration', {
            'fields': ('stripe_subscription_id',)
        }),
    )
    
    def customer_name(self, obj):
        return obj.customer.get_display_name()
    customer_name.short_description = 'Kunde'
    
    def plan_name(self, obj):
        return obj.plan.name
    plan_name.short_description = 'Plan'


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_number', 'customer_name', 'total_amount', 'status',
        'issue_date', 'due_date', 'is_overdue_display'
    ]
    list_filter = ['status', 'issue_date', 'due_date']
    search_fields = ['invoice_number', 'customer__user__email', 'customer__company_name']
    raw_id_fields = ['customer', 'subscription']
    inlines = [InvoiceLineItemInline]
    readonly_fields = ['invoice_number', 'tax_amount', 'total_amount']
    
    fieldsets = (
        ('Rechnungsinformationen', {
            'fields': ('invoice_number', 'customer', 'subscription')
        }),
        ('Beträge', {
            'fields': ('subtotal', 'tax_rate', 'tax_amount', 'total_amount')
        }),
        ('Status & Termine', {
            'fields': ('status', 'issue_date', 'due_date', 'paid_date')
        }),
        ('Payment Integration', {
            'fields': ('stripe_invoice_id', 'payment_method')
        }),
        ('Dateien & Notizen', {
            'fields': ('pdf_file', 'notes')
        }),
    )
    
    def customer_name(self, obj):
        return obj.customer.get_display_name()
    customer_name.short_description = 'Kunde'
    
    def is_overdue_display(self, obj):
        if obj.is_overdue():
            return format_html('<span style="color: red;">Überfällig</span>')
        return '-'
    is_overdue_display.short_description = 'Überfällig'


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'payment_id', 'customer_name', 'invoice_number', 'amount',
        'payment_method', 'status', 'created_at'
    ]
    list_filter = ['payment_method', 'status', 'created_at']
    search_fields = ['payment_id', 'customer__user__email', 'invoice__invoice_number']
    raw_id_fields = ['customer', 'invoice']
    readonly_fields = ['payment_id']
    
    fieldsets = (
        ('Zahlungsinformationen', {
            'fields': ('payment_id', 'invoice', 'customer', 'amount')
        }),
        ('Zahlungsmethode & Status', {
            'fields': ('payment_method', 'status', 'processed_at')
        }),
        ('Externe Referenzen', {
            'fields': ('stripe_payment_intent_id', 'external_transaction_id')
        }),
        ('Notizen', {
            'fields': ('notes',)
        }),
    )
    
    def customer_name(self, obj):
        return obj.customer.get_display_name()
    customer_name.short_description = 'Kunde'
    
    def invoice_number(self, obj):
        return obj.invoice.invoice_number
    invoice_number.short_description = 'Rechnungsnummer'


@admin.register(RevenueMetric)
class RevenueMetricAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'period_type', 'total_revenue', 'subscription_revenue',
        'new_customers', 'active_subscriptions'
    ]
    list_filter = ['period_type', 'date']
    search_fields = ['date']
    ordering = ['-date']
    
    fieldsets = (
        ('Zeitraum', {
            'fields': ('date', 'period_type')
        }),
        ('Umsatzmetriken', {
            'fields': ('total_revenue', 'subscription_revenue', 'one_time_revenue')
        }),
        ('Kundenmetriken', {
            'fields': ('new_customers', 'active_subscriptions', 'canceled_subscriptions')
        }),
        ('Plan-spezifische Daten', {
            'fields': ('plan_metrics',)
        }),
    )


# Admin site customization
admin.site.site_header = 'RenditeFuchs Business Management'
admin.site.site_title = 'Business Admin'
admin.site.index_title = 'Business Management Dashboard'
