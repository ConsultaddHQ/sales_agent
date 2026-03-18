#!/bin/bash

# TeamPop Shopify Flow - Start All Services
# This script starts all required services for local development

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}TeamPop Shopify Flow - Startup${NC}"
echo -e "${BLUE}================================${NC}\n"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found. Please install Python 3.10+${NC}"
    exit 1
fi

# Check Node
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js not found. Please install Node.js 18+${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Prerequisites check passed${NC}\n"

# Function to start a service in the background
start_service() {
    local name=$1
    local command=$2
    local port=$3
    
    echo -e "${BLUE}Starting ${name} on port ${port}...${NC}"
    eval "$command" > "${name}.log" 2>&1 &
    local pid=$!
    echo $pid > "${name}.pid"
    echo -e "${GREEN}✅ ${name} started (PID: ${pid})${NC}"
}

# Create logs directory
mkdir -p logs

echo -e "${YELLOW}Step 1/5: Starting Image Server (port 8000)${NC}"
start_service "image-server" "python3 image_server.py" "8000"
sleep 2

echo -e "\n${YELLOW}Step 2/5: Starting Search Service (port 8006)${NC}"
cd search-service
if [ ! -d ".venv" ]; then
    echo -e "${BLUE}Creating virtual environment...${NC}"
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
start_service "search-service" "uvicorn main:app --port 8006" "8006"
cd ..
sleep 2

echo -e "\n${YELLOW}Step 3/5: Starting Onboarding Service (port 8005)${NC}"
cd onboarding-service
if [ ! -d ".venv" ]; then
    echo -e "${BLUE}Creating virtual environment...${NC}"
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
start_service "onboarding-service" "python3 main.py" "8005"
cd ..
sleep 3

echo -e "\n${YELLOW}Step 4/5: Starting Dashboard (port 5174)${NC}"
cd www.teampop/dashboard
if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}Installing dependencies...${NC}"
    npm install
fi
start_service "dashboard" "npm run dev" "5174"
cd ../..
sleep 3

echo -e "\n${YELLOW}Step 5/5: Starting Widget Dev Server (port 5173)${NC}"
cd www.teampop/frontend
if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}Installing dependencies...${NC}"
    npm install
fi
start_service "widget" "npm run dev" "5173"
cd ../..
sleep 3

echo -e "\n${BLUE}================================${NC}"
echo -e "${GREEN}✅ All services started!${NC}"
echo -e "${BLUE}================================${NC}\n"

echo -e "${YELLOW}Services running:${NC}"
echo -e "  - Image Server:       ${GREEN}http://localhost:8000${NC}"
echo -e "  - Search Service:     ${GREEN}http://localhost:8006${NC}"
echo -e "  - Onboarding Service: ${GREEN}http://localhost:8005${NC}"
echo -e "  - Dashboard:          ${GREEN}http://localhost:5174${NC}"
echo -e "  - Widget Dev:         ${GREEN}http://localhost:5173${NC}"

echo -e "\n${YELLOW}Logs:${NC}"
echo -e "  - tail -f image-server.log"
echo -e "  - tail -f search-service.log"
echo -e "  - tail -f onboarding-service.log"
echo -e "  - tail -f dashboard.log"
echo -e "  - tail -f widget.log"

echo -e "\n${YELLOW}To stop all services:${NC}"
echo -e "  ./stop_services.sh"

echo -e "\n${YELLOW}Next steps:${NC}"
echo -e "  1. Open dashboard: ${GREEN}http://localhost:5174${NC}"
echo -e "  2. Enter Shopify store URL"
echo -e "  3. Test the widget!"

echo -e "\n${BLUE}Press Ctrl+C to view logs (services will keep running)${NC}"
echo -e "${YELLOW}Tailing onboarding-service.log...${NC}\n"

tail -f onboarding-service.log
