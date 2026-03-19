"""
Shopify store validation with comprehensive pre-flight checks
Validates store before scraping to provide clear error messages
"""

import re
import requests
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse
import logging

from error_codes import ErrorCodes, get_error_response

logger = logging.getLogger(__name__)


class ShopifyValidator:
    """Validates Shopify stores before scraping"""
    
    SHOPIFY_DOMAINS = ['.myshopify.com', 'shopify.com']
    REQUEST_TIMEOUT = 15  # seconds
    
    @staticmethod
    def clean_url(raw_url: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Clean and validate URL format
        
        Returns:
            (success, cleaned_url, error_response)
        """
        if not raw_url or not raw_url.strip():
            return False, None, get_error_response(
                ErrorCodes.INVALID_URL,
                "URL cannot be empty"
            )
        
        # Remove whitespace
        url = raw_url.strip()
        
        # Add https:// if missing protocol
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        
        # Parse URL
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]
            
            if not domain or '.' not in domain:
                return False, None, get_error_response(ErrorCodes.MALFORMED_URL)
            
            # Reconstruct clean URL
            clean_url = f"https://{domain}"
            return True, clean_url, None
            
        except Exception as e:
            logger.error(f"URL parsing failed: {e}")
            return False, None, get_error_response(ErrorCodes.MALFORMED_URL)
    
    @staticmethod
    def is_shopify_store(url: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if URL is a Shopify store by testing /products.json endpoint
        
        Returns:
            (is_shopify, error_response)
        """
        products_url = f"{url.rstrip('/')}/products.json"
        
        try:
            response = requests.get(
                products_url,
                timeout=ShopifyValidator.REQUEST_TIMEOUT,
                headers={'User-Agent': 'TeamPop-Onboarding/1.0'},
                allow_redirects=True
            )
            
            # Check status codes
            if response.status_code == 404:
                return False, get_error_response(ErrorCodes.NOT_SHOPIFY)
            
            if response.status_code == 401 or response.status_code == 403:
                # Check if it's password protection or access restriction
                if 'password' in response.text.lower():
                    return False, get_error_response(ErrorCodes.PASSWORD_PROTECTED)
                return False, get_error_response(ErrorCodes.ACCESS_DENIED)
            
            if response.status_code == 429:
                return False, get_error_response(
                    ErrorCodes.RATE_LIMITED,
                    retry_after=120  # 2 minutes
                )
            
            if response.status_code >= 500:
                return False, get_error_response(ErrorCodes.SERVER_ERROR)
            
            if response.status_code != 200:
                return False, get_error_response(
                    ErrorCodes.NOT_SHOPIFY,
                    f"Unexpected status code: {response.status_code}"
                )
            
            # Try to parse JSON
            try:
                data = response.json()
                
                # Validate response structure
                if not isinstance(data, dict):
                    return False, get_error_response(ErrorCodes.NOT_SHOPIFY)
                
                if 'products' not in data:
                    return False, get_error_response(ErrorCodes.PRODUCTS_FEED_DISABLED)
                
                return True, None
                
            except ValueError:
                return False, get_error_response(
                    ErrorCodes.NOT_SHOPIFY,
                    "Invalid JSON response from /products.json"
                )
        
        except requests.Timeout:
            return False, get_error_response(ErrorCodes.NETWORK_TIMEOUT)
        
        except requests.ConnectionError:
            return False, get_error_response(ErrorCodes.CONNECTION_ERROR)
        
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False, get_error_response(
                ErrorCodes.UNKNOWN_ERROR,
                str(e)
            )
    
    @staticmethod
    def check_products_exist(url: str) -> Tuple[bool, Optional[int], Optional[Dict]]:
        """
        Check if store has any products
        
        Returns:
            (has_products, product_count, error_response)
        """
        products_url = f"{url.rstrip('/')}/products.json?limit=1"
        
        try:
            response = requests.get(
                products_url,
                timeout=ShopifyValidator.REQUEST_TIMEOUT,
                headers={'User-Agent': 'TeamPop-Onboarding/1.0'}
            )
            
            if response.status_code != 200:
                return False, 0, get_error_response(ErrorCodes.NO_PRODUCTS)
            
            data = response.json()
            products = data.get('products', [])
            
            if len(products) == 0:
                return False, 0, get_error_response(ErrorCodes.EMPTY_STORE)
            
            # Get total count from Link header if available
            link_header = response.headers.get('Link', '')
            # For now, just return that products exist
            
            return True, len(products), None
        
        except Exception as e:
            logger.error(f"Product check error: {e}")
            return False, 0, get_error_response(ErrorCodes.NO_PRODUCTS)
    
    @classmethod
    def validate_store(cls, raw_url: str) -> Dict:
        """
        Complete validation flow
        
        Returns:
            {
                "valid": bool,
                "url": str (if valid),
                "error_code": str (if invalid),
                "error_message": str (if invalid),
                "help_text": str (if invalid)
            }
        """
        # Step 1: Clean URL
        success, clean_url, error = cls.clean_url(raw_url)
        if not success:
            return error
        
        # Step 2: Check if Shopify store
        is_shopify, error = cls.is_shopify_store(clean_url)
        if not is_shopify:
            return error
        
        # Step 3: Check if has products
        has_products, count, error = cls.check_products_exist(clean_url)
        if not has_products:
            return error
        
        # All checks passed
        logger.info(f"Validation successful for {clean_url}")
        return {
            "valid": True,
            "url": clean_url,
            "product_count": count
        }


def validate_shopify_store(url: str) -> Dict:
    """
    Convenience function for validating Shopify stores
    
    Args:
        url: Raw URL from user input
    
    Returns:
        Validation result dict
    """
    return ShopifyValidator.validate_store(url)
