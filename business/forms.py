"""
Forms for business management operations.
"""

from django import forms
from django.core.exceptions import ValidationError
from decimal import Decimal
import json

from .models import PricingPlan, Customer, Subscription, Invoice, InvoiceLineItem


class PricingPlanForm(forms.ModelForm):
    """Form for creating and editing pricing plans"""
    
    features_text = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Ein Feature pro Zeile eingeben...'
        }),
        required=False,
        help_text='Ein Feature pro Zeile eingeben'
    )
    
    class Meta:
        model = PricingPlan
        fields = [
            'name', 'slug', 'plan_type', 'description', 'price', 'billing_cycle',
            'max_users', 'max_projects', 'storage_gb',
            'allows_api_access', 'allows_priority_support', 'allows_custom_branding',
            'is_featured', 'is_active', 'display_order'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control'}),
            'plan_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'billing_cycle': forms.Select(attrs={'class': 'form-select'}),
            'max_users': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_projects': forms.NumberInput(attrs={'class': 'form-control'}),
            'storage_gb': forms.NumberInput(attrs={'class': 'form-control'}),
            'allows_api_access': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allows_priority_support': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allows_custom_branding': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_featured': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control'}),
        }
        
        labels = {
            'name': 'Plan Name',
            'slug': 'URL-Slug',
            'plan_type': 'Plan Typ',
            'description': 'Beschreibung',
            'price': 'Preis (€)',
            'billing_cycle': 'Abrechnungszyklus',
            'max_users': 'Max. Benutzer',
            'max_projects': 'Max. Projekte',
            'storage_gb': 'Speicher (GB)',
            'allows_api_access': 'API-Zugang',
            'allows_priority_support': 'Priority Support',
            'allows_custom_branding': 'Custom Branding',
            'is_featured': 'Als empfohlen markieren',
            'is_active': 'Aktiv',
            'display_order': 'Anzeigereihenfolge',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Pre-populate features_text if editing existing plan
        if self.instance and self.instance.pk and self.instance.features:
            self.fields['features_text'].initial = '\n'.join(self.instance.features)
    
    def clean_slug(self):
        slug = self.cleaned_data['slug']
        
        # Check for duplicate slugs
        queryset = PricingPlan.objects.filter(slug=slug)
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        
        if queryset.exists():
            raise ValidationError('Ein Plan mit diesem Slug existiert bereits.')
        
        return slug
    
    def clean_price(self):
        price = self.cleaned_data['price']
        
        if price < 0:
            raise ValidationError('Der Preis kann nicht negativ sein.')
        
        return price
    
    def clean_features_text(self):
        features_text = self.cleaned_data['features_text']
        
        if features_text:
            # Split by lines and filter out empty lines
            features = [line.strip() for line in features_text.split('\n') if line.strip()]
            return features
        
        return []
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set features from features_text
        features = self.clean_features_text()
        instance.features = features
        
        if commit:
            instance.save()
        
        return instance


class InvoiceForm(forms.ModelForm):
    """Form for creating and editing invoices"""
    
    class Meta:
        model = Invoice
        fields = [
            'customer', 'subscription', 'subtotal', 'tax_rate', 
            'due_date', 'notes'
        ]
        
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'subscription': forms.Select(attrs={'class': 'form-select'}),
            'subtotal': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        
        labels = {
            'customer': 'Kunde',
            'subscription': 'Abonnement (optional)',
            'subtotal': 'Zwischensumme (€)',
            'tax_rate': 'Steuersatz (%)',
            'due_date': 'Fälligkeitsdatum',
            'notes': 'Notizen',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter subscriptions by customer if customer is selected
        if 'customer' in self.data:
            try:
                customer_id = int(self.data.get('customer'))
                self.fields['subscription'].queryset = Subscription.objects.filter(
                    customer_id=customer_id
                )
            except (ValueError, TypeError):
                self.fields['subscription'].queryset = Subscription.objects.none()
        elif self.instance.pk and self.instance.customer:
            self.fields['subscription'].queryset = Subscription.objects.filter(
                customer=self.instance.customer
            )
        else:
            self.fields['subscription'].queryset = Subscription.objects.none()


class InvoiceLineItemForm(forms.ModelForm):
    """Form for invoice line items"""
    
    class Meta:
        model = InvoiceLineItem
        fields = [
            'description', 'quantity', 'unit_price', 
            'period_start', 'period_end'
        ]
        
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'period_start': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'period_end': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
        
        labels = {
            'description': 'Beschreibung',
            'quantity': 'Menge',
            'unit_price': 'Einzelpreis (€)',
            'period_start': 'Zeitraum von',
            'period_end': 'Zeitraum bis',
        }


# Formset for invoice line items
InvoiceLineItemFormSet = forms.inlineformset_factory(
    Invoice,
    InvoiceLineItem,
    form=InvoiceLineItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)


class SubscriptionForm(forms.ModelForm):
    """Form for creating and editing subscriptions"""
    
    class Meta:
        model = Subscription
        fields = [
            'customer', 'plan', 'status', 'start_date', 'end_date',
            'next_billing_date', 'trial_start', 'trial_end',
            'custom_price', 'discount_percentage'
        ]
        
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'plan': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'next_billing_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'trial_start': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'trial_end': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'custom_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'discount_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }
        
        labels = {
            'customer': 'Kunde',
            'plan': 'Preisplan',
            'status': 'Status',
            'start_date': 'Startdatum',
            'end_date': 'Enddatum',
            'next_billing_date': 'Nächste Abrechnung',
            'trial_start': 'Testphase Start',
            'trial_end': 'Testphase Ende',
            'custom_price': 'Angepasster Preis (€)',
            'discount_percentage': 'Rabatt (%)',
        }
    
    def clean_discount_percentage(self):
        discount = self.cleaned_data['discount_percentage']
        
        if discount < 0 or discount > 100:
            raise ValidationError('Der Rabatt muss zwischen 0 und 100% liegen.')
        
        return discount
    
    def clean_custom_price(self):
        custom_price = self.cleaned_data['custom_price']
        
        if custom_price and custom_price < 0:
            raise ValidationError('Der angepasste Preis kann nicht negativ sein.')
        
        return custom_price


class CustomerForm(forms.ModelForm):
    """Form for creating and editing customers"""
    
    class Meta:
        model = Customer
        fields = [
            'customer_type', 'company_name', 'vat_number',
            'billing_address_line1', 'billing_address_line2',
            'billing_city', 'billing_postal_code', 'billing_country',
            'preferred_payment_method'
        ]
        
        widgets = {
            'customer_type': forms.Select(attrs={'class': 'form-select'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'vat_number': forms.TextInput(attrs={'class': 'form-control'}),
            'billing_address_line1': forms.TextInput(attrs={'class': 'form-control'}),
            'billing_address_line2': forms.TextInput(attrs={'class': 'form-control'}),
            'billing_city': forms.TextInput(attrs={'class': 'form-control'}),
            'billing_postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'billing_country': forms.TextInput(attrs={'class': 'form-control'}),
            'preferred_payment_method': forms.TextInput(attrs={'class': 'form-control'}),
        }
        
        labels = {
            'customer_type': 'Kundentyp',
            'company_name': 'Firmenname',
            'vat_number': 'USt-IdNr.',
            'billing_address_line1': 'Adresse Zeile 1',
            'billing_address_line2': 'Adresse Zeile 2',
            'billing_city': 'Stadt',
            'billing_postal_code': 'Postleitzahl',
            'billing_country': 'Land',
            'preferred_payment_method': 'Bevorzugte Zahlungsmethode',
        }


class BulkActionForm(forms.Form):
    """Form for bulk actions on subscriptions/invoices"""
    
    ACTION_CHOICES = [
        ('', 'Aktion wählen...'),
        ('cancel_subscriptions', 'Abonnements kündigen'),
        ('reactivate_subscriptions', 'Abonnements reaktivieren'),
        ('send_invoices', 'Rechnungen versenden'),
        ('mark_invoices_paid', 'Rechnungen als bezahlt markieren'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Aktion'
    )
    
    selected_items = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    def clean_selected_items(self):
        selected_items = self.cleaned_data['selected_items']
        
        try:
            item_ids = [int(id) for id in selected_items.split(',') if id]
            if not item_ids:
                raise ValidationError('Keine Elemente ausgewählt.')
            return item_ids
        except ValueError:
            raise ValidationError('Ungültige Auswahl.')


class RevenueReportForm(forms.Form):
    """Form for generating revenue reports"""
    
    PERIOD_CHOICES = [
        ('7d', 'Letzte 7 Tage'),
        ('30d', 'Letzte 30 Tage'),
        ('90d', 'Letzte 90 Tage'),
        ('12m', 'Letzte 12 Monate'),
        ('custom', 'Benutzerdefiniert'),
    ]
    
    FORMAT_CHOICES = [
        ('csv', 'CSV'),
        ('xlsx', 'Excel'),
        ('pdf', 'PDF'),
    ]
    
    period = forms.ChoiceField(
        choices=PERIOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Zeitraum'
    )
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=False,
        label='Startdatum'
    )
    
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=False,
        label='Enddatum'
    )
    
    format = forms.ChoiceField(
        choices=FORMAT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Format'
    )
    
    include_details = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        required=False,
        label='Detaillierte Aufschlüsselung einbeziehen'
    )
    
    def clean(self):
        cleaned_data = super().clean()
        period = cleaned_data.get('period')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if period == 'custom':
            if not start_date or not end_date:
                raise ValidationError('Bei benutzerdefiniertem Zeitraum sind Start- und Enddatum erforderlich.')
            
            if start_date >= end_date:
                raise ValidationError('Das Startdatum muss vor dem Enddatum liegen.')
        
        return cleaned_data