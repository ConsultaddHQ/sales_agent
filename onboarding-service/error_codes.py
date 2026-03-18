"""
Error codes and messages for onboarding service
Provides user-friendly error messages for all failure scenarios
"""

from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class ErrorResponse:
    """Structured error response"""
    success: bool = False
    error_code: str = ""
    error_message: str = ""
    retry_after: Optional[int] = None  # seconds
    help_text: Optional[str] = None


class ErrorCodes:
    """Centralized error codes"""
    
    # URL/Input errors
    INVALID_URL = "invalid_url"
    NOT_SHOPIFY = "not_shopify_store"
    MALFORMED_URL = "malformed_url"
    
    # Access errors
    PASSWORD_PROTECTED = "password_protected"
    PRODUCTS_FEED_DISABLED = "products_feed_disabled"
    ACCESS_DENIED = "access_denied"
    
    # Content errors
    NO_PRODUCTS = "no_products_found"
    EMPTY_STORE = "empty_store"
    
    # Network errors
    RATE_LIMITED = "rate_limited"
    NETWORK_TIMEOUT = "network_timeout"
    CONNECTION_ERROR = "connection_error"
    SERVER_ERROR = "server_error"
    
    # Processing errors
    SUPABASE_ERROR = "database_error"
    EMBEDDING_ERROR = "embedding_error"
    IMAGE_DOWNLOAD_ERROR = "image_download_error"
    ELEVENLABS_ERROR = "agent_creation_error"
    
    # Generic
    UNKNOWN_ERROR = "unknown_error"


def get_error_response(
    error_code: str,
    custom_message: Optional[str] = None,
    retry_after: Optional[int] = None
) -> Dict:
    """
    Get user-friendly error response for a given error code
    
    Args:
        error_code: Error code from ErrorCodes class
        custom_message: Optional custom message to override default
        retry_after: Optional retry delay in seconds
    
    Returns:
        Dict with error details for API response
    """
    
    error_messages = {
        # URL/Input errors
        ErrorCodes.INVALID_URL: {
            "message": "Please enter a valid URL (e.g., example.myshopify.com or https://example.com)",
            "help": "Make sure the URL is correct and includes the domain name."
        },
        ErrorCodes.NOT_SHOPIFY: {
            "message": "This doesn't appear to be a Shopify store. Please enter a valid Shopify store URL.",
            "help": "We currently only support Shopify stores. The URL should end with .myshopify.com or be a custom domain connected to Shopify."
        },
        ErrorCodes.MALFORMED_URL: {
            "message": "The URL format is invalid. Please check and try again.",
            "help": "Example formats: example.myshopify.com or https://example.com"
        },
        
        # Access errors
        ErrorCodes.PASSWORD_PROTECTED: {
            "message": "This store is password-protected. Please disable the password to proceed.",
            "help": "Go to Shopify Admin → Online Store → Preferences → Password Protection and disable it temporarily."
        },
        ErrorCodes.PRODUCTS_FEED_DISABLED: {
            "message": "This store has disabled the public product feed.",
            "help": "The /products.json endpoint needs to be accessible. This is enabled by default in Shopify."
        },
        ErrorCodes.ACCESS_DENIED: {
            "message": "Access denied. The store may have restricted public access.",
            "help": "Check if the store is published and publicly accessible."
        },
        
        # Content errors
        ErrorCodes.NO_PRODUCTS: {
            "message": "No products found in this store. Please add products first.",
            "help": "Go to Shopify Admin → Products and add at least one published product."
        },
        ErrorCodes.EMPTY_STORE: {
            "message": "This store appears to be empty. Please add products before onboarding.",
            "help": "Add products in Shopify Admin and make sure they are published to your online store."
        },
        
        # Network errors
        ErrorCodes.RATE_LIMITED: {
            "message": "Shopify is rate-limiting requests. Automatically retrying...",
            "help": "This is temporary. We'll retry automatically with exponential backoff."
        },
        ErrorCodes.NETWORK_TIMEOUT: {
            "message": "Connection timed out. Please check your internet connection and try again.",
            "help": "The store took too long to respond. Please verify the URL and try again."
        },
        ErrorCodes.CONNECTION_ERROR: {
            "message": "Failed to connect to the store. Please check the URL and try again.",
            "help": "Make sure the URL is correct and the store is online."
        },
        ErrorCodes.SERVER_ERROR: {
            "message": "The store is currently unavailable. Please try again later.",
            "help": "This might be a temporary issue with the Shopify store."
        },
        
        # Processing errors
        ErrorCodes.SUPABASE_ERROR: {
            "message": "Database error occurred. Please contact support.",
            "help": "There was an issue storing the products. Please try again or contact support if the issue persists."
        },
        ErrorCodes.EMBEDDING_ERROR: {
            "message": "Failed to create product embeddings. Please try again.",
            "help": "This is usually a temporary issue. Please retry."
        },
        ErrorCodes.IMAGE_DOWNLOAD_ERROR: {
            "message": "Some product images failed to download. Continuing anyway...",
            "help": "The agent will still work, but some products may not have images."
        },
        ErrorCodes.ELEVENLABS_ERROR: {
            "message": "Failed to create AI agent. Please try again.",
            "help": "There was an issue with the ElevenLabs API. Please retry or contact support."
        },
        
        # Generic
        ErrorCodes.UNKNOWN_ERROR: {
            "message": "An unexpected error occurred. Please try again.",
            "help": "If this issue persists, please contact support with the error details."
        }
    }
    
    error_info = error_messages.get(
        error_code,
        error_messages[ErrorCodes.UNKNOWN_ERROR]
    )
    
    return {
        "success": False,
        "error_code": error_code,
        "error_message": custom_message or error_info["message"],
        "help_text": error_info["help"],
        "retry_after": retry_after
    }


def success_response(data: Dict) -> Dict:
    """Create success response"""
    return {
        "success": True,
        **data
    }
