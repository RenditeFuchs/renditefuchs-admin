# Generated by Django 5.2.3 on 2025-07-02 07:54

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PricingPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('slug', models.SlugField(max_length=100, unique=True)),
                ('plan_type', models.CharField(choices=[('free', 'Kostenlos'), ('basic', 'Basic'), ('premium', 'Premium'), ('pro', 'Pro'), ('enterprise', 'Enterprise')], max_length=20)),
                ('description', models.TextField()),
                ('price', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('billing_cycle', models.CharField(choices=[('monthly', 'Monatlich'), ('quarterly', 'Vierteljährlich'), ('yearly', 'Jährlich'), ('lifetime', 'Einmalig')], default='monthly', max_length=20)),
                ('features', models.JSONField(default=list, help_text='List of features included in this plan')),
                ('max_users', models.IntegerField(default=1, help_text='Maximum number of users')),
                ('max_projects', models.IntegerField(default=1, help_text='Maximum number of projects')),
                ('storage_gb', models.IntegerField(default=1, help_text='Storage limit in GB')),
                ('allows_api_access', models.BooleanField(default=False)),
                ('allows_priority_support', models.BooleanField(default=False)),
                ('allows_custom_branding', models.BooleanField(default=False)),
                ('is_featured', models.BooleanField(default=False, help_text='Show as recommended plan')),
                ('is_active', models.BooleanField(default=True)),
                ('display_order', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Preisplan',
                'verbose_name_plural': 'Preispläne',
                'ordering': ['display_order', 'price'],
            },
        ),
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_type', models.CharField(choices=[('individual', 'Privatperson'), ('business', 'Unternehmen')], default='individual', max_length=20)),
                ('company_name', models.CharField(blank=True, max_length=200)),
                ('vat_number', models.CharField(blank=True, help_text='USt-IdNr.', max_length=50)),
                ('billing_address_line1', models.CharField(max_length=200)),
                ('billing_address_line2', models.CharField(blank=True, max_length=200)),
                ('billing_city', models.CharField(max_length=100)),
                ('billing_postal_code', models.CharField(max_length=20)),
                ('billing_country', models.CharField(default='Deutschland', max_length=100)),
                ('stripe_customer_id', models.CharField(blank=True, max_length=100)),
                ('preferred_payment_method', models.CharField(blank=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='customer_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Kunde',
                'verbose_name_plural': 'Kunden',
            },
        ),
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('invoice_number', models.CharField(max_length=50, unique=True)),
                ('subtotal', models.DecimalField(decimal_places=2, max_digits=10)),
                ('tax_rate', models.DecimalField(decimal_places=2, default=19.0, max_digits=5)),
                ('tax_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('status', models.CharField(choices=[('draft', 'Entwurf'), ('sent', 'Versendet'), ('paid', 'Bezahlt'), ('overdue', 'Überfällig'), ('canceled', 'Storniert')], default='draft', max_length=20)),
                ('issue_date', models.DateField(default=django.utils.timezone.now)),
                ('due_date', models.DateField()),
                ('paid_date', models.DateTimeField(blank=True, null=True)),
                ('stripe_invoice_id', models.CharField(blank=True, max_length=100)),
                ('payment_method', models.CharField(blank=True, max_length=50)),
                ('pdf_file', models.FileField(blank=True, upload_to='invoices/')),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='business.customer')),
            ],
            options={
                'verbose_name': 'Rechnung',
                'verbose_name_plural': 'Rechnungen',
                'ordering': ['-issue_date'],
            },
        ),
        migrations.CreateModel(
            name='InvoiceLineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=200)),
                ('quantity', models.DecimalField(decimal_places=2, default=1.0, max_digits=10)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('total_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('period_start', models.DateField(blank=True, null=True)),
                ('period_end', models.DateField(blank=True, null=True)),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='line_items', to='business.invoice')),
            ],
            options={
                'verbose_name': 'Rechnungsposition',
                'verbose_name_plural': 'Rechnungspositionen',
            },
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payment_id', models.UUIDField(default=uuid.uuid4, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('payment_method', models.CharField(choices=[('stripe', 'Stripe'), ('bank_transfer', 'Überweisung'), ('paypal', 'PayPal'), ('manual', 'Manuell')], max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Ausstehend'), ('processing', 'In Bearbeitung'), ('completed', 'Abgeschlossen'), ('failed', 'Fehlgeschlagen'), ('refunded', 'Erstattet')], default='pending', max_length=20)),
                ('stripe_payment_intent_id', models.CharField(blank=True, max_length=100)),
                ('external_transaction_id', models.CharField(blank=True, max_length=100)),
                ('notes', models.TextField(blank=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='business.customer')),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='business.invoice')),
            ],
            options={
                'verbose_name': 'Zahlung',
                'verbose_name_plural': 'Zahlungen',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='RevenueMetric',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('period_type', models.CharField(choices=[('daily', 'Täglich'), ('weekly', 'Wöchentlich'), ('monthly', 'Monatlich'), ('yearly', 'Jährlich')], default='daily', max_length=20)),
                ('total_revenue', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('subscription_revenue', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('one_time_revenue', models.DecimalField(decimal_places=2, default=0.0, max_digits=12)),
                ('new_customers', models.IntegerField(default=0)),
                ('active_subscriptions', models.IntegerField(default=0)),
                ('canceled_subscriptions', models.IntegerField(default=0)),
                ('plan_metrics', models.JSONField(default=dict, help_text='Revenue and count per plan')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Umsatzmetrik',
                'verbose_name_plural': 'Umsatzmetriken',
                'ordering': ['-date'],
                'unique_together': {('date', 'period_type')},
            },
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('trial', 'Testphase'), ('active', 'Aktiv'), ('past_due', 'Überfällig'), ('canceled', 'Gekündigt'), ('suspended', 'Gesperrt')], default='trial', max_length=20)),
                ('start_date', models.DateTimeField(default=django.utils.timezone.now)),
                ('end_date', models.DateTimeField(blank=True, null=True)),
                ('next_billing_date', models.DateTimeField(blank=True, null=True)),
                ('trial_start', models.DateTimeField(blank=True, null=True)),
                ('trial_end', models.DateTimeField(blank=True, null=True)),
                ('custom_price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('discount_percentage', models.DecimalField(decimal_places=2, default=0.0, max_digits=5)),
                ('stripe_subscription_id', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('canceled_at', models.DateTimeField(blank=True, null=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscriptions', to='business.customer')),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='subscriptions', to='business.pricingplan')),
            ],
            options={
                'verbose_name': 'Abonnement',
                'verbose_name_plural': 'Abonnements',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='invoice',
            name='subscription',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='business.subscription'),
        ),
    ]
