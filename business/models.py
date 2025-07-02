from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
import uuid


class PricingPlan(models.Model):
    """Subscription pricing plans"""
    PLAN_TYPES = [
        ('free', 'Kostenlos'),
        ('basic', 'Basic'),
        ('premium', 'Premium'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    ]
    
    BILLING_CYCLES = [
        ('monthly', 'Monatlich'),
        ('quarterly', 'Vierteljährlich'),
        ('yearly', 'Jährlich'),
        ('lifetime', 'Einmalig'),
    ]
    
    # Basic Info
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES)
    description = models.TextField()
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLES, default='monthly')
    
    # Features
    features = models.JSONField(default=list, help_text="List of features included in this plan")
    max_users = models.IntegerField(default=1, help_text="Maximum number of users")
    max_projects = models.IntegerField(default=1, help_text="Maximum number of projects")
    storage_gb = models.IntegerField(default=1, help_text="Storage limit in GB")
    
    # Access Control
    allows_api_access = models.BooleanField(default=False)
    allows_priority_support = models.BooleanField(default=False)
    allows_custom_branding = models.BooleanField(default=False)
    
    # Display
    is_featured = models.BooleanField(default=False, help_text="Show as recommended plan")
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['display_order', 'price']
        verbose_name = "Preisplan"
        verbose_name_plural = "Preispläne"
    
    def __str__(self):
        return f"{self.name} - {self.get_price_display()}"
    
    def get_price_display(self):
        """Get formatted price with currency"""
        if self.price == 0:
            return "Kostenlos"
        
        cycle_suffix = {
            'monthly': '/Monat',
            'quarterly': '/Quartal', 
            'yearly': '/Jahr',
            'lifetime': ' (Einmalig)'
        }
        
        return f"€{self.price}{cycle_suffix.get(self.billing_cycle, '')}"
    
    def get_yearly_equivalent(self):
        """Calculate yearly equivalent pricing"""
        if self.billing_cycle == 'monthly':
            return self.price * 12
        elif self.billing_cycle == 'quarterly':
            return self.price * 4
        elif self.billing_cycle == 'yearly':
            return self.price
        return self.price  # lifetime


class Customer(models.Model):
    """Customer management (extending User model)"""
    CUSTOMER_TYPES = [
        ('individual', 'Privatperson'),
        ('business', 'Unternehmen'),
    ]
    
    # Link to User
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')
    
    # Customer Info
    customer_type = models.CharField(max_length=20, choices=CUSTOMER_TYPES, default='individual')
    company_name = models.CharField(max_length=200, blank=True)
    vat_number = models.CharField(max_length=50, blank=True, help_text="USt-IdNr.")
    
    # Billing Address
    billing_address_line1 = models.CharField(max_length=200)
    billing_address_line2 = models.CharField(max_length=200, blank=True)
    billing_city = models.CharField(max_length=100)
    billing_postal_code = models.CharField(max_length=20)
    billing_country = models.CharField(max_length=100, default='Deutschland')
    
    # Payment Info
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    preferred_payment_method = models.CharField(max_length=50, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Kunde"
        verbose_name_plural = "Kunden"
    
    def __str__(self):
        if self.company_name:
            return f"{self.company_name} ({self.user.email})"
        return f"{self.user.get_full_name()} ({self.user.email})"
    
    def get_display_name(self):
        """Get customer display name"""
        if self.customer_type == 'business' and self.company_name:
            return self.company_name
        return self.user.get_full_name() or self.user.username


class Subscription(models.Model):
    """Customer subscriptions"""
    STATUS_CHOICES = [
        ('trial', 'Testphase'),
        ('active', 'Aktiv'),
        ('past_due', 'Überfällig'),
        ('canceled', 'Gekündigt'),
        ('suspended', 'Gesperrt'),
    ]
    
    # Core Info
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(PricingPlan, on_delete=models.PROTECT, related_name='subscriptions')
    
    # Subscription Details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trial')
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    next_billing_date = models.DateTimeField(null=True, blank=True)
    
    # Trial Info
    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    
    # Pricing Override (for custom pricing)
    custom_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Payment Integration
    stripe_subscription_id = models.CharField(max_length=100, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Abonnement"
        verbose_name_plural = "Abonnements"
    
    def __str__(self):
        return f"{self.customer.get_display_name()} - {self.plan.name} ({self.status})"
    
    def get_effective_price(self):
        """Get the actual price being charged"""
        base_price = self.custom_price if self.custom_price else self.plan.price
        
        if self.discount_percentage > 0:
            discount_amount = base_price * (self.discount_percentage / 100)
            return base_price - discount_amount
        
        return base_price
    
    def is_active(self):
        """Check if subscription is currently active"""
        return self.status in ['trial', 'active']
    
    def days_until_renewal(self):
        """Calculate days until next billing"""
        if not self.next_billing_date:
            return None
        
        delta = self.next_billing_date - timezone.now()
        return delta.days if delta.days >= 0 else 0


class Invoice(models.Model):
    """Invoice management"""
    STATUS_CHOICES = [
        ('draft', 'Entwurf'),
        ('sent', 'Versendet'),
        ('paid', 'Bezahlt'),
        ('overdue', 'Überfällig'),
        ('canceled', 'Storniert'),
    ]
    
    # Invoice Info
    invoice_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Amounts
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=19.00)  # German VAT
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Status & Dates
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    paid_date = models.DateTimeField(null=True, blank=True)
    
    # Payment Integration
    stripe_invoice_id = models.CharField(max_length=100, blank=True)
    payment_method = models.CharField(max_length=50, blank=True)
    
    # Files
    pdf_file = models.FileField(upload_to='invoices/', blank=True)
    
    # Metadata
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-issue_date']
        verbose_name = "Rechnung"
        verbose_name_plural = "Rechnungen"
    
    def __str__(self):
        return f"Rechnung {self.invoice_number} - {self.customer.get_display_name()}"
    
    def save(self, *args, **kwargs):
        # Auto-generate invoice number
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        
        # Calculate tax amount
        self.tax_amount = self.subtotal * (self.tax_rate / 100)
        self.total_amount = self.subtotal + self.tax_amount
        
        super().save(*args, **kwargs)
    
    def generate_invoice_number(self):
        """Generate unique invoice number"""
        year = timezone.now().year
        count = Invoice.objects.filter(issue_date__year=year).count() + 1
        return f"RF-{year}-{count:04d}"
    
    def is_overdue(self):
        """Check if invoice is overdue"""
        return self.status == 'sent' and self.due_date < timezone.now().date()


class InvoiceLineItem(models.Model):
    """Individual line items on invoices"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='line_items')
    
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1.00)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Optional link to subscription period
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Rechnungsposition"
        verbose_name_plural = "Rechnungspositionen"
    
    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.description} - €{self.total_price}"


class Payment(models.Model):
    """Payment tracking"""
    PAYMENT_METHODS = [
        ('stripe', 'Stripe'),
        ('bank_transfer', 'Überweisung'),
        ('paypal', 'PayPal'),
        ('manual', 'Manuell'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Ausstehend'),
        ('processing', 'In Bearbeitung'),
        ('completed', 'Abgeschlossen'),
        ('failed', 'Fehlgeschlagen'),
        ('refunded', 'Erstattet'),
    ]
    
    # Payment Info
    payment_id = models.UUIDField(default=uuid.uuid4, unique=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='payments')
    
    # Amount & Method
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # External References
    stripe_payment_intent_id = models.CharField(max_length=100, blank=True)
    external_transaction_id = models.CharField(max_length=100, blank=True)
    
    # Metadata
    notes = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Zahlung"
        verbose_name_plural = "Zahlungen"
    
    def __str__(self):
        return f"Zahlung {self.payment_id} - €{self.amount} ({self.status})"


class RevenueMetric(models.Model):
    """Revenue tracking and analytics"""
    # Time Period
    date = models.DateField()
    period_type = models.CharField(max_length=20, choices=[
        ('daily', 'Täglich'),
        ('weekly', 'Wöchentlich'),
        ('monthly', 'Monatlich'),
        ('yearly', 'Jährlich'),
    ], default='daily')
    
    # Revenue Metrics
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    subscription_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    one_time_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Customer Metrics
    new_customers = models.IntegerField(default=0)
    active_subscriptions = models.IntegerField(default=0)
    canceled_subscriptions = models.IntegerField(default=0)
    
    # Plan Distribution
    plan_metrics = models.JSONField(default=dict, help_text="Revenue and count per plan")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['date', 'period_type']
        ordering = ['-date']
        verbose_name = "Umsatzmetrik"
        verbose_name_plural = "Umsatzmetriken"
    
    def __str__(self):
        return f"{self.date} ({self.period_type}) - €{self.total_revenue}"