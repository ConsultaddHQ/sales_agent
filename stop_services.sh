#!/bin/bash

# TeamPop Shopify Flow - Stop All Services

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}Stopping All Services${NC}"
echo -e "${BLUE}================================${NC}\n"

# Function to stop a service
stop_service() {
    local name=$1
    local pid_file="${name}.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            echo -e "${YELLOW}Stopping ${name} (PID: ${pid})...${NC}"
            kill $pid
            sleep 1
            if ps -p $pid > /dev/null 2>&1; then
                echo -e "${RED}Force killing ${name}...${NC}"
                kill -9 $pid
            fi
            echo -e "${GREEN}✅ ${name} stopped${NC}"
        else
            echo -e "${YELLOW}⚠️  ${name} not running${NC}"
        fi
        rm "$pid_file"
    else
        echo -e "${YELLOW}⚠️  ${name} PID file not found${NC}"
    fi
}

# Stop all services
stop_service "image-server"
stop_service "search-service"
stop_service "onboarding-service"
stop_service "dashboard"
stop_service "widget"

echo -e "\n${GREEN}✅ All services stopped${NC}"

# Optional: Clean up log files
read -p "Delete log files? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -f *.log
    echo -e "${GREEN}✅ Log files deleted${NC}"
fi
