#!/bin/bash
# RenditeFuchs Admin Dashboard - Local Development Server
# Usage: ./start_admin.sh

echo "🎛️  RenditeFuchs Admin Dashboard - Local Development"
echo "================================================"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment 'venv' not found!"
    echo "Please create it first with: python -m venv venv"
    exit 1
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Check if requirements are installed
echo "📦 Checking dependencies..."
if ! python -c "import django" 2>/dev/null; then
    echo "⚡ Installing dependencies..."
    pip install -r requirements.txt
fi

# Database migrations (if needed)
echo "🗄️  Checking database..."
python manage.py migrate --check >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "⚡ Running database migrations..."
    python manage.py migrate
fi

echo ""
echo "✅ Starting Admin Dashboard server..."
echo "🎛️  Admin Dashboard: http://127.0.0.1:8003"
echo "📊 Monitoring: System Health für alle RenditeFuchs Apps"
echo "🔧 Django Admin: http://127.0.0.1:8003/django-admin"
echo ""
echo "Press Ctrl+C to stop the server"
echo "================================================"

# Start the development server on port 8003
python manage.py runserver 127.0.0.1:8003