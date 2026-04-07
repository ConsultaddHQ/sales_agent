"""
ElevenLabs Conversational Agent Creation
Automatically creates and configures agents with store-specific context

Updated 2026-04-08 for current ElevenLabs API format:
  - Structure: conversation_config.agent.prompt.tools (agent nested INSIDE conversation_config)
  - Webhook tool constant params use constant_value directly (no value_type + description combo)
  - Array params require "items" field
  - Latency-optimized: glm-45-air-fp8 LLM, eleven_flash_v2_5 TTS, eager turn, speculative turn
"""

import json
import os
import logging
import uuid
import requests
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


# Base system prompt template - will be customized per store
BASE_SYSTEM_PROMPT = """# IDENTITY
You are Sam — a warm, helpful shopping companion for {store_name}, a {store_description}. You speak like a knowledgeable friend. Keep every response under 15 seconds. End most replies with a light open question.

# ENVIRONMENT
Voice assistant on {store_name} website. You control a product carousel via tools.
Store ID: {store_id} | Products: {product_categories} | Price range: {price_range}

# TOOL CHAIN — NEVER BREAK THIS SEQUENCE
When the user mentions ANY product, category, style, color, occasion, or wants to browse:

1. Say ONE brief phrase: "Let me find that for you!" or "Great taste, pulling those up!" or "On it, one moment!" or "Let me check what we have!"
2. Call search_products (expand vague queries — "something blue" → "blue clothing apparel")
3. Call update_products with the results array
4. THEN describe what you found

NEVER skip steps 2 or 3. NEVER talk about products without completing all 4 steps.
If the user says something vague like "show me something" — do NOT ask clarifying questions. Pick the best category and search NOW.

When user says "show me the third one" → call update_carousel_main_view with the correct index BEFORE speaking.
NEVER call product_desc_of_main_view — the frontend calls it automatically.

# STYLE
- 2+ products: Brief overview, invite exploration.
- 1 product: Describe with enthusiasm, mention others exist.
- [CAROUSEL UPDATE]: User scrolled. Say something light like "Oh, checking that one out?"
- Be warm, brief, genuine. Never robotic.

# GUARDRAILS
- NEVER invent product names, prices, or details.
- For purchases → direct to "Shop Now" button.
- For sizes/shipping details → direct to Shop Now.
"""


class ElevenLabsAgentCreator:
    """Creates and configures ElevenLabs conversational agents"""

    API_BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(self, api_key: Optional[str] = None):
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
        context = store_context or {}
        return BASE_SYSTEM_PROMPT.format(
            store_id=store_id,
            store_name=context.get('store_name', 'this store'),
            store_description=context.get('description', 'premium online store'),
            product_categories=context.get('categories', 'various products'),
            price_range=context.get('price_range', 'affordable to premium pricing')
        )

    def _get_tool_config(self, search_api_url: str, store_id: str) -> List[Dict]:
        """Configure tools using current ElevenLabs API format.

        Key format notes (as of 2026-04):
        - Webhook body params: use constant_value directly (no value_type wrapper)
        - LLM-generated params: just type + description (no value_type needed)
        - Client tools: parameters as JSON Schema object
        """
        return [
            # --- Webhook tool: search_products ---
            {
                "type": "webhook",
                "name": "search_products",
                "description": "Search the product catalog. After receiving results, you MUST immediately call update_products with the products array — the user cannot see products until you do. Expand vague queries: 'something blue' → 'blue clothing apparel', 'show me stuff' → 'popular bestseller featured products', 'a gift' → 'gift ideas accessories'.",
                "response_timeout_secs": 5,
                "execution_mode": "immediate",
                "tool_error_handling_mode": "auto",
                "api_schema": {
                    "url": f"{search_api_url}/search",
                    "method": "POST",
                    "request_headers": {},
                    "request_body_schema": {
                        "type": "object",
                        "properties": {
                            "store_id": {
                                "type": "string",
                                "constant_value": store_id,
                            },
                            "query": {
                                "type": "string",
                                "description": "The user's search query — product name, description, category, or natural language request.",
                            }
                        },
                        "required": ["store_id", "query"]
                    },
                    "content_type": "application/json"
                }
            },
            # --- Client tool: update_products ---
            {
                "type": "client",
                "name": "update_products",
                "description": "Update the product carousel displayed to the user. You MUST call this immediately after every search_products call, passing the products array from the search results. The user cannot see any products until you call this tool.",
                "expects_response": False,
                "execution_mode": "immediate",
                "tool_error_handling_mode": "auto",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "products": {
                            "type": "array",
                            "description": "Array of products from search_products result",
                            "items": {"type": "object"}
                        }
                    },
                    "required": ["products"]
                }
            },
            # --- Client tool: update_carousel_main_view ---
            {
                "type": "client",
                "name": "update_carousel_main_view",
                "description": "Focus on a specific product in the carousel by index",
                "expects_response": False,
                "execution_mode": "immediate",
                "tool_error_handling_mode": "auto",
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
            # --- Client tool: product_desc_of_main_view ---
            {
                "type": "client",
                "name": "product_desc_of_main_view",
                "description": "Get description of currently focused product. NEVER call this — frontend calls it automatically.",
                "expects_response": True,
                "execution_mode": "immediate",
                "tool_error_handling_mode": "auto",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]

    def _verify_agent(self, agent_id: str) -> None:
        """Fetch agent back from ElevenLabs and log full config for verification."""
        try:
            resp = requests.get(
                f"{self.API_BASE_URL}/convai/agents/{agent_id}",
                headers=self.headers,
                timeout=15,
            )
            if not resp.ok:
                logger.warning(f"⚠️ Could not fetch agent for verification (HTTP {resp.status_code})")
                return

            data = resp.json()

            # Dump top-level keys and nested structure so we can see the real format
            def _keys_deep(obj, prefix="", depth=0):
                """Return a list of key paths up to depth 3."""
                lines = []
                if isinstance(obj, dict) and depth < 3:
                    for k, v in obj.items():
                        label = f"{prefix}.{k}" if prefix else k
                        vtype = type(v).__name__
                        if isinstance(v, str):
                            preview = v[:60].replace("\n", "\\n") + ("..." if len(v) > 60 else "")
                            lines.append(f"  {label} ({vtype}): \"{preview}\"")
                        elif isinstance(v, list):
                            lines.append(f"  {label} ({vtype}): [{len(v)} items]")
                        elif isinstance(v, dict):
                            lines.append(f"  {label} ({vtype}): {{{len(v)} keys}}")
                            lines.extend(_keys_deep(v, label, depth + 1))
                        else:
                            lines.append(f"  {label} ({vtype}): {v}")
                return lines

            raw_structure = "\n".join(_keys_deep(data))
            logger.info(f"\n{'='*70}\n🔬 RAW AGENT RESPONSE STRUCTURE:\n{'='*70}\n{raw_structure}\n{'='*70}")

            # ── Extract prompt config ──
            # Agent config lives at conversation_config.agent.prompt
            prompt_cfg = (
                data.get("conversation_config", {})
                .get("agent", {})
                .get("prompt", {})
            )

            stored_prompt = prompt_cfg.get("prompt", "")
            stored_llm = prompt_cfg.get("llm", "<not set>")
            stored_temp = prompt_cfg.get("temperature", "<not set>")
            ignore_default = prompt_cfg.get("ignore_default_personality", "<not set>")

            # ── Tools ──
            stored_tools = prompt_cfg.get("tools", [])
            tools_summary = []
            for t in stored_tools:
                name = t.get("name", "?")
                ttype = t.get("type", "?")
                detail = ""
                if ttype == "webhook":
                    url = t.get("api_schema", {}).get("url", "?")
                    method = t.get("api_schema", {}).get("method", "?")
                    body_props = list(
                        t.get("api_schema", {})
                        .get("request_body_schema", {})
                        .get("properties", {})
                        .keys()
                    )
                    # Check if store_id has a constant value
                    store_id_prop = (
                        t.get("api_schema", {})
                        .get("request_body_schema", {})
                        .get("properties", {})
                        .get("store_id", {})
                    )
                    constant_val = store_id_prop.get("constant_value", "<not set>")
                    detail = f"{method} {url} | body_params={body_props} | store_id_constant={constant_val}"
                elif ttype == "client":
                    params = list(
                        t.get("parameters", {}).get("properties", {}).keys()
                    )
                    expects = t.get("expects_response", "?")
                    detail = f"params={params} expects_response={expects}"
                tools_summary.append(f"  [{ttype}] {name}: {detail}")

            # ── TTS / conversation / turn ──
            conv_cfg = data.get("conversation_config", data.get("conversational_config", {}))
            tts = conv_cfg.get("tts", {})
            turn = conv_cfg.get("turn", {})
            conversation = conv_cfg.get("conversation", {})

            # ── First message ──
            first_msg = (
                data.get("conversation_config", {})
                .get("agent", {})
                .get("first_message", "")
            )

            # ── Log everything ──
            sep = "=" * 70
            logger.info(
                f"\n{sep}\n"
                f"🔍 AGENT VERIFICATION — {agent_id}\n"
                f"{sep}\n"
                f"  Name:                    {data.get('name', '?')}\n"
                f"  Tags:                    {data.get('tags', [])}\n"
                f"\n"
                f"  LLM model:               {stored_llm}\n"
                f"  Temperature:             {stored_temp}\n"
                f"  ignore_default_personality: {ignore_default}\n"
                f"  First message:           {first_msg[:80]}{'...' if len(first_msg) > 80 else ''}\n"
                f"\n"
                f"  System prompt length:    {len(stored_prompt)} chars\n"
                f"  Prompt starts with:      {stored_prompt[:120]}{'...' if len(stored_prompt) > 120 else ''}\n"
                f"  Prompt contains 'Sam':   {'Sam' in stored_prompt}\n"
                f"  Prompt contains tools:   {'search_products' in stored_prompt}\n"
                f"\n"
                f"  Tools ({len(stored_tools)}):\n"
                + "\n".join(tools_summary)
                + f"\n\n"
                f"  TTS voice_id:            {tts.get('voice_id', '?')}\n"
                f"  TTS model:               {tts.get('model_id', '?')}\n"
                f"  Turn timeout:            {turn.get('turn_timeout', '?')}s\n"
                f"  Max duration:            {conversation.get('max_duration_seconds', '?')}s\n"
                f"  Client events:           {conversation.get('client_events', [])}\n"
                f"{sep}"
            )

            # ── Warnings ──
            if not stored_prompt:
                logger.error("❌ CRITICAL: Agent has NO system prompt!")
            elif "Sam" not in stored_prompt:
                logger.warning("⚠️ System prompt does not contain 'Sam' — personality may be missing")
            if ignore_default is not True and ignore_default != "true":
                logger.warning("⚠️ ignore_default_personality is NOT true — ElevenLabs default personality is active")
            if not stored_tools:
                logger.error("❌ CRITICAL: Agent has NO tools configured!")
            if stored_llm in ("<not set>", "gemini-2.5-flash"):
                logger.warning(f"⚠️ LLM is '{stored_llm}' — may not follow complex prompts well")

        except Exception as e:
            logger.warning(f"Agent verification skipped due to error: {e}")

    def create_agent(
        self,
        store_id: str,
        store_context: Optional[Dict] = None,
        search_api_url: Optional[str] = None,
        voice_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict:
        """Create a new conversational agent for a store."""
        # Validate store_id is a proper UUID before baking it into the webhook
        try:
            uuid.UUID(store_id)
        except ValueError:
            raise ValueError(
                f"store_id must be a valid UUID (36 chars), got: '{store_id}' ({len(store_id)} chars). "
                f"A truncated UUID will cause 400 errors on every search request."
            )

        # Get search API URL
        api_url = search_api_url or os.getenv('SEARCH_API_URL', 'http://localhost:8006')

        # Build system prompt
        system_prompt = self._build_system_prompt(store_id, store_context)

        # Get tools configuration
        tools = self._get_tool_config(api_url, store_id)

        # Resolve voice
        resolved_voice_id = (
            voice_id
            or os.getenv('ELEVENLABS_VOICE_ID')
            or "EXAVITQu4vr4xnSDxMaL"  # Sarah — ElevenLabs public default voice
        )

        # Build payload — current ElevenLabs API format (2026-04)
        # Agent config is nested INSIDE conversation_config.agent
        #
        # ── Latency optimization notes ──
        # 1. LLM: ElevenLabs-hosted models (glm-45-air-fp8, qwen3-30b-a3b) have
        #    lowest latency because they skip external API round-trips.
        #    glm-45-air-fp8 (~634ms) is recommended for agentic tool-calling.
        #    qwen3-30b-a3b (~187ms) is ultra-fast but weaker on complex prompts.
        #    gpt-4o-mini (~1-2s) is external API so adds network hop.
        # 2. TTS: eleven_flash_v2_5 (~75ms TTFB) is fastest. v2 is English-only.
        # 3. optimize_streaming_latency: 3 = max latency reduction (slight quality cost)
        # 4. turn_eagerness: "eager" = respond as soon as user pauses
        # 5. speculative_turn: true = start generating before user fully stops
        # 6. cascade_timeout_seconds: 5 = fail over to backup LLM faster
        # 7. Webhook timeout: 5s — pitch LLM removed, search is now <1s

        payload = {
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": system_prompt,
                        "llm": os.getenv("ELEVENLABS_LLM_MODEL", "glm-45-air-fp8"),
                        "temperature": 0.4,
                        "ignore_default_personality": True,
                        "tools": tools,
                        "cascade_timeout_seconds": 5,
                    },
                    "first_message": (
                        "Hey there! Welcome to the store. "
                        "I'm here to help you find exactly what you're looking for. "
                        "What can I show you today?"
                    ),
                    "language": "en",
                },
                "tts": {
                    "voice_id": resolved_voice_id,
                    "model_id": os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5"),
                    "optimize_streaming_latency": 3,
                    "stability": 0.4,
                    "similarity_boost": 0.75,
                    "speed": 1.05,
                },
                "conversation": {
                    "max_duration_seconds": 600,
                    "client_events": ["audio", "user_transcript"],
                },
                "turn": {
                    "turn_timeout": 5,
                    "turn_eagerness": "eager",
                    "speculative_turn": True,
                },
            },
            "name": agent_name or f"Agent for Store {store_id[:8]}",
            "tags": tags or ["teampop", store_id],
        }

        # Log the payload structure (not the full prompt) for debugging
        agent_cfg = payload["conversation_config"]["agent"]
        debug_payload = {
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": f"<{len(system_prompt)} chars>",
                        "llm": agent_cfg["prompt"]["llm"],
                        "temperature": agent_cfg["prompt"]["temperature"],
                        "ignore_default_personality": agent_cfg["prompt"]["ignore_default_personality"],
                        "tools": f"<{len(tools)} tools>",
                    },
                    "first_message": agent_cfg["first_message"][:50] + "...",
                    "language": agent_cfg["language"],
                },
                "tts": payload["conversation_config"]["tts"],
                "turn": payload["conversation_config"]["turn"],
            },
            "name": payload["name"],
            "tags": payload["tags"],
        }
        logger.info(f"ElevenLabs create-agent payload structure: {json.dumps(debug_payload, indent=2)}")

        # Create agent via API
        try:
            response = requests.post(
                f"{self.API_BASE_URL}/convai/agents/create",
                headers=self.headers,
                json=payload,
                timeout=30
            )

            if not response.ok:
                logger.error(f"❌ ElevenLabs API {response.status_code}: {response.text}")
                response.raise_for_status()

            result = response.json()

            agent_id = result.get('agent_id')
            if not agent_id:
                raise ValueError(f"No agent_id in response: {result}")

            logger.info(f"✅ Created ElevenLabs agent: {agent_id}")

            # ── Full verification: pull agent back and dump everything ──
            self._verify_agent(agent_id)

            return {
                "success": True,
                "agent_id": agent_id,
                "agent_url": f"https://elevenlabs.io/app/conversational-ai/{agent_id}"
            }

        except requests.RequestException as e:
            logger.error(f"❌ ElevenLabs API error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise Exception(f"Failed to create agent: {str(e)}")


def create_agent_for_store(
    store_id: str,
    store_context: Optional[Dict] = None,
    search_api_url: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> Dict:
    """Convenience function to create an agent."""
    creator = ElevenLabsAgentCreator()
    return creator.create_agent(
        store_id=store_id,
        store_context=store_context,
        search_api_url=search_api_url,
        tags=tags
    )
