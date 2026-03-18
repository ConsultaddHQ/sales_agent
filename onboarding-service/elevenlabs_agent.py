"""
ElevenLabs Conversational Agent Creation
Automatically creates and configures agents with store-specific context
"""

import os
import logging
import requests
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


# Base system prompt template - will be customized per store
BASE_SYSTEM_PROMPT = """# Personality
You are Sam — a warm, stylish, and genuinely helpful shopping companion for {store_name}, a {store_description}. You speak like a knowledgeable friend who works at the store and knows every product deeply. You are excited about fashion but never pushy.
Speak naturally as if in a real conversation. Keep every response under 20 seconds when spoken aloud. End most replies with a light, open question to keep the conversation flowing. Never lecture — guide.

# Environment
You are a voice shopping assistant embedded on the {store_name} website. The user sees a product carousel on screen that you can control. You can search products, update the carousel, and highlight specific items. The user can also manually scroll the carousel — when they do, you will receive a [CAROUSEL UPDATE] signal.

# Store Context
Store ID: {store_id}
Products: {product_categories}
Price range: {price_range}

# Goal
Be the customer's personal shopping partner. Your job is to:
1. Understand what they want — even if they haven't fully said it yet
2. Show them the right products on screen
3. Help them find something they love through natural conversation

# Core Decision Flow
Follow this sequence silently before every response:
**Step 1 — Understand intent**
- New search needed? (new category, new color, new occasion)
- Asking about a product already on screen?
- Just browsing / chatting?
- Sent a [CAROUSEL UPDATE] (manual scroll)?

**Step 2 — Proactive product discovery**
If the user says something vague like "show me something", "what do you have", "I want to buy something", or mentions any occasion or style preference — DO NOT ask what category. Instead, pick the most relevant category from the store context and search immediately.

**Step 3 — Smart search query construction**
Never pass raw user words to search_products. Always expand the query using intent + store context.

**Step 4 — Tool execution order (never skip)**
1. Call search_products
2. Immediately call update_products with the result — do NOT speak yet
3. Then speak

**Step 5 — Product response style**
- If 2+ products returned: Give a short combined overview first.
- If user asks about ONE specific product: Speak about that product first, then briefly mention others exist.
- If user says "show me the blue one" or "tell me about the third": Call update_carousel_main_view first, then speak about it.

**Step 6 — [CAROUSEL UPDATE] behavior (manual scroll)**
When you receive [CAROUSEL UPDATE], the user is browsing on their own. Do NOT immediately narrate the product. Instead, respond with light curiosity: "Oh, I see you're taking a look at that one — anything you'd like to know about it?"

**Step 7 — Speak only after tools are done**
Never speak before update_products or update_carousel_main_view when required.

# Tools
## search_products
**When to use:** User wants a new category, color, occasion, or says anything browsing-related.
**Do not use:** If the product is already in the current list.
Parameters:
- store_id (required): Always "{store_id}"
- query (required): Your expanded natural language search query — NOT the user's raw words

## update_products
**When to use:** Immediately after every search_products call. Always. No exceptions.
**Do not speak before calling this.**
Parameters:
- products (required): The exact array returned by search_products

## update_carousel_main_view
**When to use:** User refers to a specific product already on screen (by color, name, or position).
Preferred parameter: {{ "index": 0 }} — count from 0 (first product = 0, second = 1, etc.)

## product_desc_of_main_view
**NEVER call this yourself.** The frontend calls it automatically when the user manually scrolls.

# Guardrails
- Never call product_desc_of_main_view. The frontend handles this.
- Never invent product names, IDs, prices, or indexes.
- Never speak before update_products when a search just ran.
- Keep every spoken response under 20 seconds.
- If user wants to purchase, direct them to the "Shop Now" button.
- If user asks for details you don't have (size chart, shipping, returns) — point them to Shop Now.
- Never make up product details.
"""


class ElevenLabsAgentCreator:
    """Creates and configures ElevenLabs conversational agents"""
    
    API_BASE_URL = "https://api.elevenlabs.io/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize agent creator
        
        Args:
            api_key: ElevenLabs API key (defaults to env var ELEVENLABS_API_KEY)
        """
        self.api_key = api_key or os.getenv('ELEVENLABS_API_KEY')
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY not found in environment")
        
        self.headers = {
            'xi-api-key': self.api_key,
            'Content-Type': 'application/json'
        }
    
    def _build_system_prompt(
        self,
        store_id: str,
        store_context: Optional[Dict] = None
    ) -> str:
        """
        Build customized system prompt for store
        
        Args:
            store_id: Unique store identifier
            store_context: Optional context (name, categories, price range, etc.)
        
        Returns:
            Formatted system prompt
        """
        context = store_context or {}
        
        return BASE_SYSTEM_PROMPT.format(
            store_id=store_id,
            store_name=context.get('store_name', 'this store'),
            store_description=context.get('description', 'premium online store'),
            product_categories=context.get('categories', 'various products'),
            price_range=context.get('price_range', 'affordable to premium pricing')
        )
    
    def _get_tool_config(self, search_api_url: str, store_id: str) -> List[Dict]:
        """
        Configure server-side tools for the agent
        
        Args:
            search_api_url: URL of the search service API
            store_id: Store ID to pass to tools
        
        Returns:
            List of tool configurations
        """
        return [
            {
                "type": "webhook",
                "name": "search_products",
                "description": "Search for products in the store based on user query. Always use this when user asks for products.",
                "url": f"{search_api_url}/search",
                "method": "POST",
                "body": {
                    "store_id": store_id,
                    "query": "{{query}}"
                },
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query (expanded with context, NOT raw user words)"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "type": "client_tool",
                "name": "update_products",
                "description": "Update the product carousel with new products. Call immediately after search_products.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "products": {
                            "type": "array",
                            "description": "Array of products from search_products result"
                        }
                    },
                    "required": ["products"]
                }
            },
            {
                "type": "client_tool",
                "name": "update_carousel_main_view",
                "description": "Focus on a specific product in the carousel by index",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "index": {
                            "type": "integer",
                            "description": "Zero-based index of product (0 = first, 1 = second, etc.)"
                        }
                    },
                    "required": ["index"]
                }
            },
            {
                "type": "client_tool",
                "name": "product_desc_of_main_view",
                "description": "Get description of currently focused product. NEVER call this - frontend calls it automatically.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    
    def create_agent(
        self,
        store_id: str,
        store_context: Optional[Dict] = None,
        search_api_url: Optional[str] = None,
        voice_id: Optional[str] = None,
        agent_name: Optional[str] = None
    ) -> Dict:
        """
        Create a new conversational agent for a store
        
        Args:
            store_id: Unique store identifier
            store_context: Store-specific context (name, categories, etc.)
            search_api_url: URL of search service (defaults to env var SEARCH_API_URL)
            voice_id: ElevenLabs voice ID (defaults to system default)
            agent_name: Display name for the agent
        
        Returns:
            {
                "success": True,
                "agent_id": "agent_xyz",
                "agent_url": "https://...",
            }
        
        Raises:
            Exception if agent creation fails
        """
        # Get search API URL
        api_url = search_api_url or os.getenv('SEARCH_API_URL', 'http://localhost:8006')
        
        # Build system prompt
        system_prompt = self._build_system_prompt(store_id, store_context)
        
        # Get tools configuration
        tools = self._get_tool_config(api_url, store_id)
        
        # Build agent configuration
        agent_config = {
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": system_prompt
                    },
                    "first_message": "Hey there! Welcome to the store. I'm here to help you find exactly what you're looking for. What can I show you today?",
                    "language": "en"
                },
                "tts": {
                    "voice_id": voice_id or os.getenv('ELEVENLABS_VOICE_ID')
                    # Uses ElevenLabs default voice if not specified
                },
                "tools": tools
            },
            "name": agent_name or f"Agent for Store {store_id[:8]}",
            "tags": ["teampop", "shopify", store_id]
        }
        
        # Create agent via API
        try:
            response = requests.post(
                f"{self.API_BASE_URL}/convai/agents/create",
                headers=self.headers,
                json=agent_config,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            agent_id = result.get('agent_id')
            if not agent_id:
                raise ValueError("No agent_id in response")
            
            logger.info(f"✅ Created ElevenLabs agent: {agent_id}")
            
            return {
                "success": True,
                "agent_id": agent_id,
                "agent_url": f"https://elevenlabs.io/app/conversational-ai/{agent_id}"
            }
        
        except requests.RequestException as e:
            logger.error(f"❌ ElevenLabs API error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Failed to create agent: {str(e)}")


def create_agent_for_store(
    store_id: str,
    store_context: Optional[Dict] = None,
    search_api_url: Optional[str] = None
) -> Dict:
    """
    Convenience function to create an agent
    
    Args:
        store_id: Store UUID
        store_context: Optional store metadata
        search_api_url: Search service URL
    
    Returns:
        Agent creation result
    """
    creator = ElevenLabsAgentCreator()
    return creator.create_agent(
        store_id=store_id,
        store_context=store_context,
        search_api_url=search_api_url
    )
