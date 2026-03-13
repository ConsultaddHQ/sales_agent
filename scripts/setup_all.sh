#!/bin/bash
set -e
echo "🔧 Setting up all services..."

# Check if .env files exist
if [ ! -f onboarding-service/.env ]; then
    echo "❌ Missing onboarding-service/.env"
    exit 1
fi

# Python services
for service in onboarding-service search-service universal-scraper image-service; do
    echo "📦 Setting up $service..."
    cd $service
    if [ ! -d .venv ]; then
        python -m venv .venv
    fi
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    deactivate
    cd ..
done

# Node services
for service in www.teampop/dashboard www.teampop/frontend; do
    echo "📦 Setting up $service..."
    cd $service
    npm install
    cd ../..
done

echo "✅ Setup complete!"
