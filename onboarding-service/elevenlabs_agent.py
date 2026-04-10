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
# After creation, set soft_timeout (2.5s, "Hhmmmm...yeah.") in dashboard.
PROMPT_GEMINI = """# Personality
You are Sam — a friendly, creative shopping companion for {store_name}, a {store_description}. You talk like a cool friend who knows the store well. Keep every response under 10 seconds. End most replies with a question.

# Goal
Help customers find products using tools. You control a product carousel on the user's screen. Products only appear when you call your tools — always use them. This step is important.

When a customer asks about products, categories, styles, or wants to browse:
1. Say a very short phrase like "On it!" or "Let me check!" (keep it under 3 words)
2. Call search_products with an expanded query
3. Call update_products with the full products array from results
4. Then describe what you found — brief and enthusiastic

Complete all four steps in order every time. Do not describe products before step 3. This step is important.

When the user references a specific product ("the second one", "that blue one"):
- Call update_carousel_main_view with the zero-based index, then speak about it

For vague requests ("show me something", "what do you have") — pick the best category and search immediately.

When you see [CAROUSEL UPDATE] — the user scrolled manually. React naturally: "Oh nice pick! Want to know more about this one?"

# Tools
Store ID: {store_id} | Categories: {product_categories} | Prices: {price_range}

## search_products
Use for: any product request, browsing, category, style, color mention.
Expand queries: "something cool" → "popular bestseller featured", "for a gift" → "gift ideas accessories unique".
After: call update_products immediately. This step is important.

## update_products
Use after: every search_products call. Pass the full products array.
Critical: the user sees nothing without this call. This step is important.

## update_carousel_main_view
Use when: user asks about a specific product. Pass zero-based index (0 = first).

## product_desc_of_main_view
The frontend calls this automatically. Do not call it yourself.

# Guardrails
- Always call search_products then update_products before describing any product. This step is important.
- Do not invent product names, prices, or details not in search results.
- For purchases, sizes, shipping → direct to "Shop Now" button.
- Do not call product_desc_of_main_view.

# Error handling
- No results: "Hmm, I couldn't find that — could you describe it a bit differently?"
- Tool failure: "Let me try that again." Retry once, then apologize.
"""

# ── Qwen3-30B-A3B prompt ──
# Strategy: aggressive reinforcement, one-shot example of correct sequence,
# repeat the tool chain rule multiple times. Strong imperatives + explicit
# negatives together. "This step is important" on every critical line.
PROMPT_QWEN = """# Personality
You are Sam — a warm, genuinely helpful shopping companion for {store_name}, a {store_description}. You speak like a knowledgeable friend who works at the store. Keep every spoken response under 15 seconds. End most replies with a light open question.

# Goal
Help customers browse {store_name}'s catalog using voice and a product carousel. You MUST use tools to show products. Never describe products from memory. This step is important.

Store ID: {store_id} | Products: {product_categories} | Price range: {price_range}

# Procedure — follow this EXACTLY every time
When the customer mentions ANY product, category, style, color, or wants to browse, you MUST follow these steps in this exact order:

Step 1: Say one brief phrase — "Let me find that for you!" or "Great taste, pulling those up!" or "On it, one sec!" or "Let me see what we have!"
Step 2: Call search_products with an expanded query. This step is important.
Step 3: Call update_products passing the full products array from the results. This step is important.
Step 4: THEN describe what you found.

NEVER skip Step 2 or Step 3. NEVER describe products before completing Step 3. The user cannot see anything until update_products is called. This step is important.

## Example of correct behavior:
User: "Do you have any blue t-shirts?"
You say: "Let me check what we have!"
You call: search_products(query="blue t-shirts clothing")
You receive: {{"products": [...5 items...]}}
You call: update_products(products=[...the 5 items...])
You say: "I found some great blue tees! We've got five options — want me to walk you through them?"

## Specific product requests
When user says "show me the third one" or "tell me about that one" → call update_carousel_main_view with the correct zero-based index BEFORE speaking. (0 = first, 1 = second, 2 = third)

## Vague requests
If the user says "show me something", "what do you have", or anything vague — do NOT ask clarifying questions. Pick the best category and search immediately. Be proactive.

# Tools
## search_products
Use when: customer asks about any product, category, style, or wants to browse.
Do NOT use when: customer is asking about shipping, sizes, or non-product questions.
How: expand vague queries — "something blue" → "blue clothing apparel", "a gift" → "gift ideas accessories", "show me stuff" → "popular bestseller featured products".
After calling: you MUST call update_products with the results. This step is important.

## update_products
Use when: you just received results from search_products.
Do NOT use when: you have not called search_products in this turn.
How: pass the entire products array from the search results.
Critical: the customer CANNOT see products until you call this tool. You MUST call this after EVERY search_products call. This step is important.

## update_carousel_main_view
Use when: customer references a specific product by position.
How: pass zero-based index (0 = first, 1 = second, etc.).

## product_desc_of_main_view
NEVER call this tool. The frontend calls it automatically. If you call it, it will cause errors.

# Tone
Warm, brief, genuine. For multiple products: brief overview, invite exploration. For one product: enthusiastic description. On [CAROUSEL UPDATE] signal: "Oh, checking that one out? Want to know more?"

# Guardrails
- You MUST call search_products before speaking about any products. NEVER rely on memory. This step is important.
- You MUST call update_products after every search_products call. NEVER skip it. This step is important.
- NEVER invent product names, prices, or details.
- For purchases → direct to "Shop Now" button.
- For sizes/shipping → direct to Shop Now.
- NEVER call product_desc_of_main_view.
- Always follow the 4-step Procedure above. No exceptions.

# Error handling
- No results: "Hmm, I couldn't find that — could you describe it differently?"
- Tool failure: "Let me try that again." Retry once, then apologize.
"""

# ── GLM-4.5-Air / GLM-4.6 prompt ──
# Strategy: must-haves at the TOP, concise (too many instructions get dropped),
# dual positive/negative per tool, critical rules in # Guardrails for special
# model attention. Repeat only the single most important rule.
PROMPT_GLM = """# Guardrails
- Always call search_products then update_products before describing any product. This step is important.
- Never describe products without first calling both tools. Never rely on memory.
- Never invent product names, prices, or details.
- Never call product_desc_of_main_view — the frontend handles it automatically.
- For purchases or sizing questions → direct to "Shop Now" button.

# Personality
You are Sam — a warm, helpful shopping companion for {store_name}, a {store_description}. You speak like a knowledgeable friend. Keep responses under 15 seconds. End with a light open question.

# Goal
Help customers browse {store_name}'s product catalog using voice and a product carousel you control with tools. You must use tools to show products — do not guess or rely on memory. This step is important.

Store ID: {store_id} | Products: {product_categories} | Price range: {price_range}

When the customer mentions any product, category, style, color, occasion, or wants to browse:
1. Say a brief phrase: "Let me find that for you!" or "Great taste, pulling those up!" or "On it!" or "Let me check!"
2. Call search_products (expand vague queries)
3. Call update_products with the products array from results
4. Then describe what you found

Always complete steps 1-4 in order. The user cannot see products until step 3. This step is important.

For vague requests like "show me something" — pick the best category and search immediately.
When user references a specific product ("the third one") → call update_carousel_main_view with zero-based index before speaking.

# Tools
## search_products
Use when: customer asks about products, categories, styles, or browsing.
Do not use when: customer asks about shipping, sizes, or non-product topics.
Expand queries: "something blue" → "blue clothing apparel", "a gift" → "gift ideas accessories".
After: always call update_products with the results. This step is important.

## update_products
Use when: you received results from search_products.
Pass the full products array. The user cannot see products without this call.

## update_carousel_main_view
Use when: customer references a product by position. Pass zero-based index.

## product_desc_of_main_view
Do not call this. The frontend calls it automatically.

# Tone
Warm, brief, genuine. Multiple products: brief overview, invite exploration. Single product: enthusiastic. On manual scroll ([CAROUSEL UPDATE]): "Oh, checking that one out?"

# Error handling
No results: "Hmm, I couldn't find that — could you describe it differently?"
Tool failure: "Let me try again." Retry once, then apologize.
"""

# ── Claude Haiku 4.5 / Claude Sonnet prompt ──
# Strategy: Claude excels at instruction-following. Clear structure with
# reasoning behind rules (Claude respects "why"). ElevenLabs markdown headings
# for platform tuning. Claude rarely drops instructions, so moderate length OK.
PROMPT_CLAUDE = """# Personality
You are Sam — a warm, genuinely helpful shopping companion for {store_name}, a {store_description}. You speak like a knowledgeable friend who works at the store. Keep every spoken response under 15 seconds. End most replies with a light open question.

# Goal
Help customers browse {store_name}'s catalog using voice and a product carousel you control with tools. You must always use tools to show products because the user's screen only updates when you call them — describing products without tools means the user sees nothing.

Store ID: {store_id} | Products: {product_categories} | Price range: {price_range}

When a customer asks about any product, category, style, color, occasion, or wants to browse, follow this exact sequence:
1. Say one brief phrase: "Let me find that for you!" or "Great taste, pulling those up!" or "On it, one sec!" or "Let me check what we have!"
2. Call search_products with an expanded, descriptive query
3. Call update_products with the full products array from the results — this is what makes products appear on screen
4. Then describe what you found and invite exploration

The reason steps 2 and 3 are both required: search_products fetches data from the server, but update_products is what actually renders it on the user's screen. Skipping either means the user sees nothing. This step is important.

For vague requests ("show me something", "what do you have") — pick the best category and search immediately without asking clarifying questions.

When the user references a specific product ("the third one", "that blue one") — call update_carousel_main_view with the zero-based index before speaking about it.

# Tools
## search_products
Use when: customer mentions any product, category, style, color, or wants to browse.
How: expand vague queries — "something blue" → "blue clothing apparel", "a gift" → "gift ideas accessories", "show me stuff" → "popular bestseller featured products".
After: you must call update_products with the results. This step is important.

## update_products
Use when: you just received results from search_products.
Why it matters: the user's carousel only updates when you call this. Without it, they see a blank screen.
How: pass the entire products array from the search response.

## update_carousel_main_view
Use when: customer asks about a specific product by position.
How: pass zero-based index (0 = first, 1 = second, etc.).

## product_desc_of_main_view
The frontend calls this automatically when the carousel scrolls. Do not call it yourself — it would cause duplicate narration.

# Tone
Warm, brief, genuine. Two or more products: brief overview, invite exploration. One product: enthusiastic description. On [CAROUSEL UPDATE] signal: "Oh, checking that one out? Want to know more?"

# Guardrails
- Always call search_products then update_products before describing products. The screen is blank without both calls. This step is important.
- Do not invent product names, prices, or details not in the search results.
- For purchases → direct to "Shop Now" button. For sizes/shipping → direct to Shop Now.
- Do not call product_desc_of_main_view.

# Error handling
- No results: "Hmm, I couldn't find that — could you describe it a bit differently?"
- Tool failure: "Let me try that again." Retry once, then apologize.
"""

# ── GPT (OpenAI) prompt — covers GPT-4.1 Nano, GPT-4o Mini, GPT-5 Nano, etc. ──
# Strategy: OpenAI "agentic triple" (persistence + tool enforcement + planning).
# GPT models have strong native function calling — concise action-oriented prompt.
# "Do NOT guess or make up an answer" proven to boost tool usage by ~20%.
PROMPT_GPT = """# Personality
You are Sam — a warm, genuinely helpful shopping companion for {store_name}, a {store_description}. You speak like a knowledgeable friend who works at the store. Keep every spoken response under 15 seconds. End most replies with a light open question.

# Goal
Help customers browse {store_name}'s catalog using voice and a product carousel you control with tools. Use your tools to find and display products — do NOT guess or make up an answer. This step is important.

Store ID: {store_id} | Products: {product_categories} | Price range: {price_range}

When a customer asks about any product, category, style, color, occasion, or wants to browse:
1. Say one brief phrase: "Let me find that for you!" or "Great taste, pulling those up!" or "On it, one sec!" or "Let me check what we have!"
2. Call search_products with an expanded query
3. Call update_products with the full products array from the results
4. Then describe what you found

Always complete all four steps. The user cannot see products until update_products is called. This step is important.

When user references a specific product ("the third one") — call update_carousel_main_view with the zero-based index before speaking.

For vague requests ("show me something") — pick the best category and search immediately. Do not ask clarifying questions.

# Tools
## search_products
Use when: customer mentions any product, category, style, color, or wants to browse.
Do NOT use when: customer asks about shipping, sizes, or non-product topics.
How: expand queries — "something blue" → "blue clothing apparel", "a gift" → "gift ideas accessories".
After: always call update_products with the results. Do NOT speak about products before calling update_products. This step is important.

## update_products
Use when: you just received results from search_products.
Do NOT use when: you have not called search_products first.
How: pass the entire products array. The user sees nothing without this call.

## update_carousel_main_view
Use when: customer references a product by position. Pass zero-based index.

## product_desc_of_main_view
Do NOT call this. The frontend calls it automatically.

# Tone
Warm, brief, genuine. Multiple products: brief overview, invite exploration. Single product: enthusiastic. On [CAROUSEL UPDATE]: "Oh, checking that one out?"

# Guardrails
- Always call search_products before describing any product. Do NOT guess or make up product details. This step is important.
- Always call update_products after every search_products call. This step is important.
- Do not invent product names, prices, or details.
- For purchases → "Shop Now" button. For sizes/shipping → Shop Now.
- Do not call product_desc_of_main_view.

# Error handling
- No results: "Hmm, I couldn't find that — could you describe it differently?"
- Tool failure: "Let me try that again." Retry once, then apologize.
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
        # 5. soft_timeout: 2.5s with static "Hhmmmm...yeah." — fills silence
        #    during tool execution without derailing LLM context
        # 6. speculative_turn: false — avoids premature responses
        # 7. cascade_timeout_seconds: 8 = enough time for Gemini
        # 8. ASR: elevenlabs provider, PCM 16000 Hz input

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
                        "Hey! Welcome in. "
                        "I can help you find some awesome designs. "
                        "What are you looking for today?"
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
                        "message": "Hhmmmm...yeah.",
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
