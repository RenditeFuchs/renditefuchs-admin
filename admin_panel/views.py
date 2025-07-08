from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache

@csrf_protect
@never_cache
def custom_login(request):
    """Custom Login View that ACTUALLY WORKS"""
    # Check if user is already logged in
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if username and password:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                if user.is_active:
                    login(request, user)
                    # Redirect to next page or dashboard
                    next_url = request.GET.get('next', '/')
                    return redirect(next_url)
                else:
                    messages.error(request, 'Ihr Account ist deaktiviert.')
            else:
                messages.error(request, 'Ungültige Anmeldedaten.')
        else:
            messages.error(request, 'Bitte beide Felder ausfüllen.')
    
    return render(request, 'registration/login.html')

@login_required
def dashboard(request):
    """Main Dashboard View"""
    return render(request, 'dashboard.html', {
        'title': 'Admin Dashboard',
        'user': request.user,
    })

def dashboard_redirect(request):
    """Redirect root to main dashboard"""
    if not request.user.is_authenticated:
        return redirect('login')
    return redirect('dashboard')

def custom_logout(request):
    """Custom Logout View with proper redirect"""
    logout(request)
    messages.success(request, 'Sie wurden erfolgreich abgemeldet.')
    return redirect('login')