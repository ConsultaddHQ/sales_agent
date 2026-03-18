#!/usr/bin/env python3
"""
TeamPop Shopify Flow - End-to-End Test Script
Tests the complete flow from URL input to widget preview
"""

import requests
import time
import json
from typing import Dict, Optional

# Test configuration
ONBOARDING_URL = "http://localhost:8005"
SEARCH_URL = "http://localhost:8006"
IMAGE_SERVER_URL = "http://localhost:8000"

# Test stores
TEST_STORES = {
    "shopify_valid": "sensesindia.in",
    "shopify_empty": "empty-store.myshopify.com",  # Replace with actual empty store
    "not_shopify": "google.com",
    "invalid_url": "not-a-real-url",
}

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_test(name: str):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}TEST: {name}{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}")

def print_pass(message: str):
    print(f"{Colors.GREEN}✅ PASS: {message}{Colors.END}")

def print_fail(message: str):
    print(f"{Colors.RED}❌ FAIL: {message}{Colors.END}")

def print_info(message: str):
    print(f"{Colors.YELLOW}ℹ️  {message}{Colors.END}")


def test_health_checks() -> bool:
    """Test all service health endpoints"""
    print_test("Service Health Checks")
    
    services = [
        ("Onboarding Service", f"{ONBOARDING_URL}/health"),
        ("Search Service", f"{SEARCH_URL}/health"),
        ("Image Server", f"{IMAGE_SERVER_URL}/health"),
    ]
    
    all_healthy = True
    
    for name, url in services:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print_pass(f"{name} is healthy")
            else:
                print_fail(f"{name} returned status {response.status_code}")
                all_healthy = False
        except Exception as e:
            print_fail(f"{name} is not reachable: {e}")
            all_healthy = False
    
    return all_healthy


def test_onboarding_valid_store() -> Optional[Dict]:
    """Test onboarding with a valid Shopify store"""
    print_test("Onboarding Valid Shopify Store")
    
    store_url = TEST_STORES["shopify_valid"]
    print_info(f"Testing with: {store_url}")
    
    try:
        print_info("Sending onboard request...")
        response = requests.post(
            f"{ONBOARDING_URL}/onboard",
            json={"url": store_url},
            timeout=120  # Onboarding can take time
        )
        
        if response.status_code != 200:
            print_fail(f"Onboarding failed with status {response.status_code}")
            print_info(f"Response: {response.text}")
            return None
        
        data = response.json()
        
        # Verify response structure
        required_fields = ["success", "store_id", "agent_id", "widget_snippet", "products_count"]
        missing_fields = [f for f in required_fields if f not in data]
        
        if missing_fields:
            print_fail(f"Missing fields in response: {missing_fields}")
            return None
        
        if not data.get("success"):
            print_fail(f"Onboarding returned success=false")
            return None
        
        print_pass("Onboarding completed successfully")
        print_info(f"Store ID: {data['store_id']}")
        print_info(f"Agent ID: {data['agent_id']}")
        print_info(f"Products: {data['products_count']}")
        print_info(f"Test URL: {data.get('test_url', 'N/A')}")
        
        return data
        
    except requests.Timeout:
        print_fail("Onboarding timed out (>120s)")
        return None
    except Exception as e:
        print_fail(f"Onboarding error: {e}")
        return None


def test_onboarding_error_cases():
    """Test onboarding error handling"""
    print_test("Onboarding Error Cases")
    
    test_cases = [
        ("Invalid URL", TEST_STORES["invalid_url"], "invalid_url"),
        ("Not Shopify", TEST_STORES["not_shopify"], "not_shopify"),
    ]
    
    for name, url, expected_error in test_cases:
        print_info(f"Testing: {name} ({url})")
        
        try:
            response = requests.post(
                f"{ONBOARDING_URL}/onboard",
                json={"url": url},
                timeout=30
            )
            
            if response.status_code == 200:
                print_fail(f"{name} should have failed but succeeded")
                continue
            
            data = response.json()
            error_code = data.get("detail", {}).get("error_code")
            
            if error_code == expected_error:
                print_pass(f"{name} returned correct error: {error_code}")
            else:
                print_fail(f"{name} returned unexpected error: {error_code} (expected: {expected_error})")
                
        except Exception as e:
            print_fail(f"{name} test error: {e}")


def test_search(store_id: str):
    """Test search functionality"""
    print_test("Search Functionality")
    
    test_queries = [
        "blue shirt",
        "pants",
        "formal wear",
    ]
    
    for query in test_queries:
        print_info(f"Searching for: '{query}'")
        
        try:
            response = requests.post(
                f"{SEARCH_URL}/search",
                json={"store_id": store_id, "query": query},
                timeout=10
            )
            
            if response.status_code != 200:
                print_fail(f"Search failed with status {response.status_code}")
                continue
            
            data = response.json()
            products = data.get("products", [])
            
            if products:
                print_pass(f"Found {len(products)} products for '{query}'")
                print_info(f"First result: {products[0].get('name', 'N/A')}")
            else:
                print_fail(f"No products found for '{query}'")
                
        except Exception as e:
            print_fail(f"Search error for '{query}': {e}")


def test_image_serving(store_id: str):
    """Test image server"""
    print_test("Image Server")
    
    try:
        # List images for store
        response = requests.get(f"{IMAGE_SERVER_URL}/images/{store_id}", timeout=5)
        
        if response.status_code != 200:
            print_fail(f"Image listing failed with status {response.status_code}")
            return
        
        data = response.json()
        image_count = data.get("image_count", 0)
        images = data.get("images", [])
        
        print_pass(f"Found {image_count} images for store")
        
        if images:
            # Test fetching first image
            first_image_url = images[0]["url"]
            print_info(f"Testing image: {first_image_url}")
            
            img_response = requests.get(f"{IMAGE_SERVER_URL}{first_image_url}", timeout=5)
            
            if img_response.status_code == 200:
                print_pass("Image served successfully")
            else:
                print_fail(f"Image fetch failed with status {img_response.status_code}")
        
    except Exception as e:
        print_fail(f"Image server error: {e}")


def run_all_tests():
    """Run complete test suite"""
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}TeamPop Shopify Flow - Test Suite{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    start_time = time.time()
    
    # Test 1: Health Checks
    if not test_health_checks():
        print_fail("\n⚠️  Some services are not healthy. Please start all services.")
        return
    
    # Test 2: Onboarding (Valid Store)
    onboarding_result = test_onboarding_valid_store()
    if not onboarding_result:
        print_fail("\n⚠️  Onboarding failed. Skipping dependent tests.")
    else:
        store_id = onboarding_result["store_id"]
        
        # Test 3: Search
        test_search(store_id)
        
        # Test 4: Images
        test_image_serving(store_id)
    
    # Test 5: Error Handling
    test_onboarding_error_cases()
    
    # Summary
    elapsed = time.time() - start_time
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}Test Suite Complete ({elapsed:.1f}s){Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    if onboarding_result:
        print(f"{Colors.GREEN}✅ All critical tests passed!{Colors.END}")
        print(f"\n{Colors.YELLOW}Next Steps:{Colors.END}")
        print(f"1. Open dashboard: http://localhost:5174")
        print(f"2. Enter store URL: {TEST_STORES['shopify_valid']}")
        print(f"3. Click 'Preview Widget' to test")
        print(f"4. Try voice conversation")
    else:
        print(f"{Colors.RED}❌ Some tests failed. Check logs above.{Colors.END}")


if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Tests interrupted by user{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.RED}Test suite error: {e}{Colors.END}")
