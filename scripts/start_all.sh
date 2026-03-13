#!/bin/bash

echo "🚀 Starting all services..."

# Kill existing services
pkill -f "uvicorn" || true
pkill -f "npm run dev" || true

# Start backend services
echo "Starting onboarding-service (port 8005)..."
cd onboarding-service
source .venv/bin/activate
uvicorn main:app --port 8005 &
deactivate
cd ..

echo "Starting search-service (port 8006)..."
cd search-service
source .venv/bin/activate
uvicorn main:app --port 8006 &
deactivate
cd ..

echo "Starting image-service (port 8000)..."
cd image-service
source .venv/bin/activate
python main.py &
deactivate
cd ..

# Start frontend services
echo "Starting dashboard (port 5174)..."
cd www.teampop/dashboard
npm run dev &
cd ../..

echo "Starting widget (port 5173)..."
cd www.teampop/frontend
npm run dev &
cd ../..

echo ""
echo "✅ All services started!"
echo ""
echo "Services running at:"
echo "  - Onboarding API: http://localhost:8005"
echo "  - Search API: http://localhost:8006"
echo "  - Image Server: http://localhost:8000"
echo "  - Dashboard: http://localhost:5174"
echo "  - Widget: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all services"
wait
