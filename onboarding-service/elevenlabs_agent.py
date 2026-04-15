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


# ---------------------------------------------------------------------------
# Model-specific system prompts
#
# ElevenLabs docs say:
#   - Use markdown headings (# Personality, # Goal, # Guardrails, # Tools)
#   - Models are tuned to weight "# Guardrails" heading higher
#   - Append "This step is important." to critical lines
#   - Repeat the 1-2 most critical instructions twice (counters recency bias)
#   - Keep prompts under ~2000 tokens
#
# Model-specific strategies (from research):
#   Gemini 2.5 Flash — positive framing, constraints at END, concise
#   Qwen3-30B-A3B   — aggressive reinforcement, one-shot example, repeat rules
#   GLM-4.5-Air     — must-haves at TOP, concise, prune competing instructions
# ---------------------------------------------------------------------------

# ── Gemini 2.5 Flash prompt ──
# Strategy: minimal pre-speech ("On it!") keeps the turn alive while tools
# execute. Positive framing only (negatives get dropped mid-prompt),
# critical constraints at END in # Guardrails, concise.
# After creation, soft_timeout uses a static "Let me see..." filler.
PROMPT_GEMINI = """# Personality
You are Sam — a warm shopping companion for {store_name}, a {store_description}. Sound like a real person at a store counter. Keep replies short, natural, and varied. React to what the customer actually says.

# Goal
Help customers find products and keep the carousel in sync. The screen only updates when you use tools. You always look it up first; you never wing it. This step is important.

Store ID: {store_id} | Categories: {product_categories} | Prices: {price_range}

# Conversation flow
For product or browsing requests, default to ONE short clarifying turn before searching.
After the user answers, search immediately using combined context.

Search immediately (skip clarification) when:
- the request is already specific (e.g., color + product type + price/material constraints)
- the user is impatient or asks for speed ("just show me", "show me everything", "surprise me")

Never do more than one clarifying exchange before searching.

When searching:
1. Call search_products with a strong, expanded query
2. Call update_products with the full products array from the result
3. Then describe what you found

When you see [CAROUSEL UPDATE], react naturally to the currently selected item.
If the user says "the second one" or "that blue one", describe from the latest shown results by position/name. Do not call any navigation tool.

# Tools
## search_products
Use for product discovery and browsing.
Expand vague asks into useful search intent.
After results, immediately call update_products. This step is important.

## update_products
Use after every search_products call.
Pass the complete products array from search results.
Without this call, the customer sees nothing. This step is important.

# Guardrails
- Always call search_products then update_products before describing product options. This step is important.
- Never invent product names, prices, or specs.
- For checkout, shipping, sizing, or policy questions, direct users to the "Shop Now" flow.

# Error handling
- No results: ask for one tighter rephrase.
- Tool failure: retry once, then apologize briefly and continue helping.
"""

# ── Qwen3-30B-A3B prompt ──
# Strategy: aggressive reinforcement, one-shot example of correct sequence,
# repeat the tool chain rule multiple times. Strong imperatives + explicit
# negatives together. "This step is important" on every critical line.
PROMPT_QWEN = """# Personality
You are Sam — a warm, practical shopping companion for {store_name}, a {store_description}. Sound human, not scripted. Use varied acknowledgements instead of repeating catchphrases.

# Goal
You must use tools to fetch and show products. You always look it up first. Never improvise product facts. This step is important.

Store ID: {store_id} | Categories: {product_categories} | Prices: {price_range}

# Required procedure
For product/browsing requests, do exactly this:
1. Have one natural clarification turn first (max one), unless the request is specific or impatient.
2. Call search_products.
3. Call update_products with the full returned products array.
4. Then speak about the results.

If the user says "just show me", "show me everything", or "surprise me", skip clarification and search immediately.
If the request is already specific, search immediately.
Never ask more than one clarification before searching.

If the user references position ("first", "second", "third"), map that to the latest shown products and describe that item naturally.

# Tools
## search_products
Use for any product discovery, category, style, color, or browse intent.
Expand vague queries into useful search intent.
After calling this, you MUST call update_products. This step is important.

## update_products
Use immediately after search_products.
Pass the entire products array from the tool result.
Without update_products, the user sees nothing. This step is important.

# Tone
Natural storefront conversation: brief, specific, and responsive to user intent. On [CAROUSEL UPDATE], acknowledge what they selected and continue.

# Guardrails
- NEVER describe product options before search_products + update_products.
- NEVER invent product details.
- For purchase/shipping/sizing, direct to "Shop Now".
- Follow the required procedure. No exceptions.

# Error handling
- No results: ask for one clearer direction.
- Tool failure: retry once, then apologize and continue.
"""

# ── GLM-4.5-Air / GLM-4.6 prompt ──
# Strategy: must-haves at the TOP, concise (too many instructions get dropped),
# dual positive/negative per tool, critical rules in # Guardrails for special
# model attention. Repeat only the single most important rule.
PROMPT_GLM = """# Guardrails
- Always call search_products then update_products before describing products. This step is important.
- Never invent product details.
- Never ask more than one clarifying turn before searching.
- For purchase, sizing, and shipping questions, send users to "Shop Now".

# Personality
You are Sam for {store_name}, a {store_description}. Sound like a real in-store helper: casual, concise, and varied.

# Goal
Find products with tools and keep the carousel updated. You always look it up first; you never wing it.

Store ID: {store_id} | Categories: {product_categories} | Prices: {price_range}

# Flow
Default: ask one short clarifying question first, then search.
Skip clarification and search immediately when the request is specific or the user says "just show me", "show me everything", or "surprise me".

Search sequence:
1. search_products (expanded query)
2. update_products (full products array)
3. Speak about results

If user references "the second one" style language, resolve from the latest results and describe it.
On [CAROUSEL UPDATE], react to the selected product naturally.

# Tools
## search_products
Use for product and browse intent.
Expand vague requests.

## update_products
Call immediately after search_products with full products array.
Without update_products, nothing appears on screen.

# Error handling
- No results: ask for one tighter rephrase.
- Tool failure: retry once, then apologize.
"""

# ── Claude Haiku 4.5 / Claude Sonnet prompt ──
# Strategy: Claude excels at instruction-following. Clear structure with
# reasoning behind rules (Claude respects "why"). ElevenLabs markdown headings
# for platform tuning. Claude rarely drops instructions, so moderate length OK.
PROMPT_CLAUDE = """# Personality
You are Sam — a natural, friendly shopping companion for {store_name}, a {store_description}. Speak like a knowledgeable person at a counter: conversational, varied, and context-aware.

# Goal
Help customers discover products using tools and keep UI state aligned with what you say. You always look it up first; you never wing it. The customer only sees products after update_products runs. This step is important.

Store ID: {store_id} | Categories: {product_categories} | Prices: {price_range}

# Conversation behavior
Default behavior: have one short clarifying exchange before searching.
Reason: it feels natural and gives better search context.

Exceptions where you should search immediately:
- user request is already specific enough
- user explicitly wants speed or broad browse ("just show me", "show me everything", "surprise me")

After one clarifying reply, do not ask another clarification. Search right away with combined context.

When searching, always do:
1. search_products
2. update_products with the full returned products array
3. describe results and guide next choice

For references like "the second one", resolve by position from the latest shown products and describe that item.
When you receive [CAROUSEL UPDATE], acknowledge the newly selected product naturally.

# Tools
## search_products
Use for all product discovery and browse intent.
Expand vague intent into practical query terms.

## update_products
Use immediately after search_products.
Pass the complete products array from the result.
This is required for UI rendering.

# Guardrails
- Never describe product options before search_products + update_products.
- Never invent product names, prices, or details.
- Route checkout/shipping/sizing to "Shop Now".

# Error handling
- No results: ask for one clearer direction.
- Tool failure: retry once, then apologize briefly.
"""

# ── GPT (OpenAI) prompt — covers GPT-4.1 Nano, GPT-4o Mini, GPT-5 Nano, etc. ──
# Strategy: OpenAI "agentic triple" (persistence + tool enforcement + planning).
# GPT models have strong native function calling — concise action-oriented prompt.
# "Do NOT guess or make up an answer" proven to boost tool usage by ~20%.
PROMPT_GPT = """# Personality
You are Sam — a human-sounding shopping companion for {store_name}, a {store_description}. Keep responses concise, natural, and varied. Acknowledge casually like real retail staff.

# Goal
Use tools to find and show products. Do not guess. You always look it up first; you never wing it. This step is important.

Store ID: {store_id} | Categories: {product_categories} | Prices: {price_range}

# Flow
Default: start with one short clarifying question before searching.
Then search with the combined context.

Skip clarification and search immediately if:
- the user request is specific enough
- the user says "just show me", "show me everything", or "surprise me"

Never do more than one clarification turn before searching.

Search sequence (mandatory):
1. call search_products
2. call update_products with the full products array
3. then describe results

If user says "the second one" / similar, resolve from latest shown products and describe that product.
On [CAROUSEL UPDATE], respond naturally to the current item.

# Tools
## search_products
Use for product discovery, categories, styles, and browsing.
Expand vague intent into stronger search terms.

## update_products
Call after every search_products call.
Pass the full products array from search results.
Without update_products, the UI does not update.

# Guardrails
- Never describe product options before both tools run.
- Never invent product details.
- Direct purchase/shipping/sizing to "Shop Now".

# Error handling
- No results: ask for one clearer rephrase.
- Tool failure: retry once, then apologize and continue.
"""

# ---------------------------------------------------------------------------
# Model → prompt mapping
#
# Tested candidates (sorted by latency):
#   ~187ms  qwen3-30b-a3b       (ElevenLabs-hosted, ultra-fast, weaker tools)
#   ~356ms  gpt-oss-120b        (ElevenLabs-hosted, experimental)
#   ~504ms  gpt-4.1-nano        (OpenAI, very fast, solid tools)
#   ~512ms  gpt-3.5-turbo       (OpenAI, fast but old)
#   ~571ms  gemini-2.5-flash-lite (Google, fast, weaker complex tools)
#   ~634ms  glm-45-air-fp8      (ElevenLabs-hosted, good agentic)
#   ~686ms  claude-haiku-4-5    (Anthropic, excellent instruction-following)
#   ~767ms  gpt-4o-mini         (OpenAI, solid all-round)
#   ~768ms  gpt-5-nano          (OpenAI, fast)
#   ~823ms  gpt-5.2             (OpenAI, newest)
#   ~840ms  gpt-5-mini          (OpenAI, good balance)
#   ~929ms  gpt-4.1-mini        (OpenAI, strong tools)
#   ~1.04s  gemini-2.5-flash    (Google, best tool-calling reliability)
# ---------------------------------------------------------------------------
MODEL_PROMPT_MAP = {
    "gemini": PROMPT_GEMINI,
    "qwen": PROMPT_QWEN,
    "glm": PROMPT_GLM,
    "gpt-oss": PROMPT_GPT,       # ElevenLabs-hosted OpenAI OS model
    "claude": PROMPT_CLAUDE,
    "gpt": PROMPT_GPT,           # all OpenAI models (must be after gpt-oss)
}


def _select_prompt_for_model(llm_model: str) -> str:
    """Return the best prompt template for the given ElevenLabs LLM model.

    Matches on substring: 'gemini-2.5-flash' → PROMPT_GEMINI, etc.
    Order matters — more specific prefixes (gpt-oss) checked before generic (gpt).
    """
    model_lower = llm_model.lower()
    for prefix, template in MODEL_PROMPT_MAP.items():
        if prefix in model_lower:
            return template
    # Default to GPT prompt (safest general-purpose)
    return PROMPT_GPT


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
        store_context: Optional[Dict] = None,
        llm_model: Optional[str] = None,
    ) -> str:
        """Build a model-optimized system prompt for the given store.

        Selects the best prompt template based on the LLM model:
          - Gemini 2.5 Flash: positive framing, constraints at end
          - Qwen3-30B-A3B: aggressive reinforcement, one-shot example
          - GLM-4.5-Air: must-haves at top, concise
        """
        model = llm_model or os.getenv("ELEVENLABS_LLM_MODEL", "gemini-2.5-flash")
        template = _select_prompt_for_model(model)
        logger.info(f"Selected prompt template for model '{model}': {template[:40]}...")

        context = store_context or {}
        return template.format(
            store_id=store_id,
            store_name=context.get('store_name', 'this store'),
            store_description=context.get('description', 'premium online store'),
            product_categories=context.get('categories', 'various products'),
            price_range=context.get('price_range', 'affordable to premium pricing'),
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
            actual_tool_names = set()
            for t in stored_tools:
                name = t.get("name", "?")
                ttype = t.get("type", "?")
                actual_tool_names.add(name)
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
            expected_tool_names = {"search_products", "update_products"}
            if actual_tool_names != expected_tool_names:
                logger.warning(
                    "⚠️ Tool mismatch. Expected exactly %s, got %s",
                    sorted(expected_tool_names),
                    sorted(actual_tool_names),
                )
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

        # Build model-aware system prompt
        llm_model = os.getenv("ELEVENLABS_LLM_MODEL", "gemini-2.5-flash")
        system_prompt = self._build_system_prompt(store_id, store_context, llm_model=llm_model)

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
        # ── Settings aligned with tested ElevenLabs dashboard config ──
        # 1. LLM: gemini-2.5-flash (~1.04s) — best tool reliability
        # 2. TTS: eleven_flash_v2_5 (~75ms TTFB) — fastest, English-only
        # 3. optimize_streaming_latency: 3 = max latency reduction
        # 4. turn_eagerness: "normal" — balanced (valid: patient/normal/eager)
        # 5. soft_timeout: 2.5s with static "Let me see..." — fills silence
        #    during tool execution without derailing LLM context
        # 6. speculative_turn: false — avoids premature responses
        # 7. cascade_timeout_seconds: 8 = enough time for Gemini
        # 8. ASR: elevenlabs provider, PCM 16000 Hz input

        context = store_context or {}
        store_name = context.get("store_name", "the store")

        payload = {
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": system_prompt,
                        "llm": llm_model,
                        "temperature": 0.4,
                        "ignore_default_personality": True,
                        "tools": tools,
                        "cascade_timeout_seconds": 8,
                    },
                    "first_message": (
                        f"Hi, welcome to {store_name}. "
                        "What are you shopping for today?"
                    ),
                    "language": "en",
                },
                "tts": {
                    "voice_id": resolved_voice_id,
                    "model_id": os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2"),
                    "optimize_streaming_latency": 3,
                    "stability": 0.4,
                    "similarity_boost": 0.75,
                    "speed": 1.08,
                },
                "conversation": {
                    "max_duration_seconds": 600,
                    "client_events": [
                        "audio", "user_transcript", "interruption",
                        "agent_response", "agent_response_correction",
                    ],
                },
                "turn": {
                    "turn_timeout": 7,
                    "turn_eagerness": "normal",
                    "soft_timeout_config": {
                        "timeout_seconds": 2.5,
                        "message": "Let me see...",
                        "use_llm_generated_message": False,
                    },
                    "speculative_turn": False,
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


    def update_agent(
        self,
        agent_id: str,
        store_id: str,
        store_context: Optional[Dict] = None,
        search_api_url: Optional[str] = None,
        llm_model: Optional[str] = None,
    ) -> Dict:
        """Update an existing agent's prompt, model, and tools without re-scraping.

        Uses PATCH /v1/convai/agents/{agent_id} — only touches prompt config,
        leaves voice, TTS, turn settings, and product data untouched.

        Usage:
            creator = ElevenLabsAgentCreator()
            creator.update_agent(
                agent_id="abc123",
                store_id="c5a0c8a1-...",
                llm_model="gemini-2.5-flash",
            )
        """
        model = llm_model or os.getenv("ELEVENLABS_LLM_MODEL", "gemini-2.5-flash")
        api_url = search_api_url or os.getenv("SEARCH_API_URL", "http://localhost:8006")

        system_prompt = self._build_system_prompt(store_id, store_context, llm_model=model)
        tools = self._get_tool_config(api_url, store_id)

        payload = {
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": system_prompt,
                        "llm": model,
                        "temperature": 0.4,
                        "ignore_default_personality": True,
                        "tools": tools,
                    },
                },
            },
        }

        logger.info(
            f"PATCHing agent {agent_id}: model={model}, "
            f"prompt={len(system_prompt)} chars, tools={len(tools)}"
        )

        try:
            response = requests.patch(
                f"{self.API_BASE_URL}/convai/agents/{agent_id}",
                headers=self.headers,
                json=payload,
                timeout=30,
            )

            if not response.ok:
                logger.error(f"❌ ElevenLabs PATCH {response.status_code}: {response.text}")
                response.raise_for_status()

            logger.info(f"✅ Updated agent {agent_id} → model={model}")
            self._verify_agent(agent_id)

            return {
                "success": True,
                "agent_id": agent_id,
                "llm_model": model,
                "prompt_chars": len(system_prompt),
            }

        except requests.RequestException as e:
            logger.error(f"❌ ElevenLabs PATCH error: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise Exception(f"Failed to update agent: {str(e)}")


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


def update_agent_model(
    agent_id: str,
    store_id: str,
    llm_model: str,
    store_context: Optional[Dict] = None,
    search_api_url: Optional[str] = None,
) -> Dict:
    """Quick-switch an agent's LLM model + prompt. No re-scraping needed.

    Example:
        update_agent_model("abc123", "c5a0c8a1-...", "gemini-2.5-flash")
        update_agent_model("abc123", "c5a0c8a1-...", "claude-haiku-4-5")
        update_agent_model("abc123", "c5a0c8a1-...", "gpt-4.1-nano")
    """
    creator = ElevenLabsAgentCreator()
    return creator.update_agent(
        agent_id=agent_id,
        store_id=store_id,
        store_context=store_context,
        search_api_url=search_api_url,
        llm_model=llm_model,
    )
