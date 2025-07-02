from django.urls import path
from . import views, api_views

app_name = 'business'

urlpatterns = [
    # Main Dashboard
    path('', views.business_dashboard, name='dashboard'),
    
    # Pricing Plans Management
    path('pricing-plans/', views.pricing_plans_list, name='pricing_plans'),
    path('pricing-plans/create/', views.pricing_plan_create, name='pricing_plan_create'),
    path('pricing-plans/<int:plan_id>/edit/', views.pricing_plan_edit, name='pricing_plan_edit'),
    path('pricing-plans/<int:plan_id>/delete/', views.pricing_plan_delete, name='pricing_plan_delete'),
    
    # Customer Management
    path('customers/', views.customers_list, name='customers'),
    
    # Subscription Management
    path('subscriptions/', views.subscriptions_list, name='subscriptions'),
    
    # Invoice Management
    path('invoices/', views.invoices_list, name='invoices'),
    path('invoices/create/', views.invoice_create, name='invoice_create'),
    path('invoices/<int:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:invoice_id>/edit/', views.invoice_edit, name='invoice_edit'),
    path('invoices/<int:invoice_id>/send/', views.invoice_send, name='invoice_send'),
    path('invoices/<int:invoice_id>/mark-paid/', views.invoice_mark_paid, name='invoice_mark_paid'),
    
    # Revenue Analytics
    path('analytics/', views.revenue_analytics, name='analytics'),
    
    # API Endpoints
    path('api/subscriptions/', api_views.SubscriptionManagementAPI.as_view(), name='api_subscriptions'),
    path('api/subscriptions/<int:subscription_id>/', api_views.SubscriptionManagementAPI.as_view(), name='api_subscription_detail'),
    path('api/invoices/', api_views.InvoiceManagementAPI.as_view(), name='api_invoices'),
    path('api/invoices/<int:invoice_id>/', api_views.InvoiceManagementAPI.as_view(), name='api_invoice_detail'),
    path('api/analytics/', api_views.subscription_analytics_api, name='api_analytics'),
]