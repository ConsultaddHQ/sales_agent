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
You are Wrina — a warm shopping companion for {store_name}, a {store_description}. Sound like a real person at a store counter. Keep replies short, natural, and varied. React to what the customer actually says.

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
2. Call update_products with the full products array from the result — BEFORE speaking any words about the results
3. Give a SHORT spoken summary only: say the product name/type, the available colors, and the price. Do NOT read out fabric, material, composition, fit, or the full description. Then — like a good salesperson — offer: "Want details on any of these?" If the customer picks one, call get_product_details for that specific product (and update_carousel_main_view to focus it), then share its specifics. This step is important.

A short filler phrase BEFORE step 1 is fine ("Let me find that."). NEVER speak between step 1 and step 2. The carousel must appear before you describe anything. This step is important.

When you see [CAROUSEL UPDATE], react naturally to the currently selected item.
When user references a specific product ("the third one") — call update_carousel_main_view with the zero-based index before speaking.

# Tools
## search_products
Use for product discovery and browsing.
Expand vague asks into useful search intent.
After results, immediately call update_products. This step is important.

## update_products
Use after every search_products call.
Pass the complete products array from search results.
Without this call, the customer sees nothing. This step is important.

## get_product_details
Use when the user asks for specifics about a product already shown — sizes, colors, availability, price by size, fabric/material, or full description. Pass the product's id from the search results. Only call it if you don't already have the answer. Do NOT guess.
After the result arrives, call update_carousel_main_view with that product's zero-based index BEFORE speaking. This step is important.

## update_carousel_main_view
Use when: customer references a product by position (e.g. "the second one"). Also call this immediately after every get_product_details result. Pass zero-based index.
CRITICAL — the product you SPEAK about must be the product SHOWN on screen: before describing any specific product in detail, call this tool with that product's index and check the product_name it returns. If the returned name is NOT the product you were about to describe, you have the wrong index — correct it and call again BEFORE speaking. Never describe product A while product B is focused on screen.

# Guardrails
- After a search_products result arrives, your VERY NEXT action must be update_products. Do not say any words between the tool result and the update_products call. The screen must update BEFORE the customer hears you describe products. This step is important.
- After a get_product_details result arrives, your VERY NEXT action must be update_carousel_main_view with that product's zero-based index. Do not speak between the tool result and the carousel update. This step is important.
- Always call search_products then update_products before describing product options. This step is important.
- Never invent product names, prices, or specs.
- When first showing products, say ONLY name/type, colors, and price — never recite fabric, fit, or composition unprompted. This step is important.
- For specifics (sizes, colors, availability, price by size, fabric/material, full description), call get_product_details and answer ONLY from what it returns. If a detail is not in the result (e.g. wash-care instructions), say it is not listed and point to "Shop Now" — never guess or invent it. This step is important.
- For checkout, shipping, returns, or store-policy questions, direct users to the "Shop Now" flow.

## add_to_cart
Call ONLY when the user explicitly says they want to add something to their cart or buy it.

Before calling add_to_cart:
1. If you don't already know the available sizes for this product, call get_product_details first — it returns a variants list with size names.
2. Read the sizes aloud and ask: "This comes in [sizes] — which size would you like?"
3. Wait for their answer, then find the zero-based index of their chosen size in the variants list. Pass it as variant_index.
   If they say "any" or "doesn't matter", use variant_index 0.
Skip the size check only if the product clearly has no sizes (e.g. a bag, accessory, or the details already confirmed a single variant).

After success: "I've added [product name] in [size] to your cart!"
If it fails: suggest the Shop Now link.

## Pairing & "similar" requests
When the customer asks "what goes with this?", "suggest pairings", "show similar", "what else would match", or anything implying related products:
- If it's unclear whether they want something to wear WITH it (pairing) or more items LIKE it (similar), ask one short question first: "Something to go with it, or more like it?"
- Decide what pairs well using your own fashion knowledge (a shirt → trousers, belt; a dress → shoes, bag). The Categories list is only a HINT and may be incomplete — ALWAYS call search_products first for any pairing or related-item request. Never say the store doesn't carry something without searching first. Only if search returns nothing, say it's not carried and point to "Shop Now". This step is important.
- Turn that into a search_products query (e.g. pairing a shirt → "trousers chinos"; similar → "knitted dobby shirt"), then call search_products + update_products as usual. This step is important.
- Present only what search_products returns. If nothing suitable comes back, say so honestly and point to "Shop Now" — never invent products.

# Session ending
When the user says goodbye, thanks you and indicates they're done, or uses farewell phrases ("bye", "thanks that's all", "I'm done", "goodbye", "that's it"), say a brief warm farewell first (one short sentence, e.g. "Happy shopping! Bye!"), then call end_session with reason "user_farewell". Say your farewell BEFORE calling end_session. This step is important.
When you receive [SESSION ENDING], say one brief farewell sentence (e.g. "Thanks for visiting! Happy shopping!"), then call end_session with reason "session_wrap_up". This step is important.

# Error handling
- No results: the spoken word may have been mis-transcribed from voice (e.g. "flosser"/"flouser" → "trousers", "jellbottom" → "bell bottom"). Before concluding, silently re-interpret the request in context using product knowledge and the store's Categories, then call search_products ONCE more with the corrected term. Only if that retry is ALSO empty, say it's not carried and point to "Shop Now". Never reject on the first miss.
- Tool failure: retry once, then apologize briefly and continue helping.
"""

# ── Qwen3-30B-A3B prompt ──
# Strategy: aggressive reinforcement, one-shot example of correct sequence,
# repeat the tool chain rule multiple times. Strong imperatives + explicit
# negatives together. "This step is important" on every critical line.
PROMPT_QWEN = """# Personality
You are Wrina — a warm, practical shopping companion for {store_name}, a {store_description}. Sound human, not scripted. Use varied acknowledgements instead of repeating catchphrases.

# Goal
You must use tools to fetch and show products. You always look it up first. Never improvise product facts. This step is important.

Store ID: {store_id} | Categories: {product_categories} | Prices: {price_range}

# Required procedure
For product/browsing requests, do exactly this:
1. Have one natural clarification turn first (max one), unless the request is specific or impatient.
2. Call search_products.
3. Call update_products with the full returned products array — BEFORE speaking any words about results.
4. Give a SHORT spoken summary only: product name/type, colors, and price. Do NOT read fabric, material, fit, or composition. Then offer: "Want details on any of these?" If customer picks one, call get_product_details for that product, then share specifics. This step is important.

NEVER speak between step 2 and step 3. The carousel must appear before you describe the products. A short filler phrase BEFORE step 2 is fine ("Let me find that."). This step is important.

If the user says "just show me", "show me everything", or "surprise me", skip clarification and search immediately.
If the request is already specific, search immediately.
Never ask more than one clarification before searching.

When user references a specific product ("the third one") — call update_carousel_main_view with the zero-based index before speaking.

# Tools
## search_products
Use for any product discovery, category, style, color, or browse intent.
Expand vague queries into useful search intent.
After calling this, you MUST call update_products. This step is important.

## update_products
Use immediately after search_products.
Pass the entire products array from the tool result.
Without update_products, the user sees nothing. This step is important.

## get_product_details
Use when the user asks for specifics about a product already shown — sizes, colors, availability, price by size, fabric/material, or full description. Pass the product's id from the search results. Only call it if you don't already have the answer. Do NOT guess.
After the result arrives, call update_carousel_main_view with that product's zero-based index BEFORE speaking. This step is important.

## update_carousel_main_view
Use when: customer references a product by position (e.g. "the second one"). Also call this immediately after every get_product_details result. Pass zero-based index.
CRITICAL — the product you SPEAK about must be the product SHOWN on screen: before describing any specific product in detail, call this tool with that product's index and check the product_name it returns. If the returned name is NOT the product you were about to describe, you have the wrong index — correct it and call again BEFORE speaking. Never describe product A while product B is focused on screen.

# Tone
Natural storefront conversation: brief, specific, and responsive to user intent. On [CAROUSEL UPDATE], acknowledge what they selected and continue.

# Guardrails
- After search_products returns, call update_products IMMEDIATELY — no words between them. The UI must update BEFORE you speak about products. This step is important.
- After get_product_details returns, call update_carousel_main_view IMMEDIATELY with that product's zero-based index — no words between them. The carousel must focus BEFORE you speak. This step is important.
- NEVER describe product options before search_products + update_products.
- NEVER invent product details.
- When first showing products, say ONLY name/type, colors, and price — never recite fabric, fit, or composition unprompted. This step is important.
- For specifics (sizes, colors, availability, price by size, fabric/material, full description), call get_product_details and answer ONLY from what it returns. If a detail is not in the result (e.g. wash-care instructions), say it is not listed and point to "Shop Now" — never guess or invent it. This step is important.
- For purchase, shipping, returns, or store-policy questions, direct to "Shop Now".
- Follow the required procedure. No exceptions.

## add_to_cart
Call ONLY when the user explicitly says they want to add something to their cart or buy it.

Before calling add_to_cart:
1. If you don't already know this product's sizes, call get_product_details — it returns a variants list.
2. Read the sizes to the customer: "This comes in [sizes] — which size?"
3. Wait for their answer. Map it to the zero-based index in the variants list; pass as variant_index.
   If they say "any" or "doesn't matter", use variant_index 0.
Skip size check only if the product has no sizes (bag, accessory, single variant confirmed).

After success: "I've added [name] in [size] to your cart!"
If it fails: tell the user to use the Shop Now link.

## Pairing & "similar" requests
When user asks "what goes with this?", "suggest pairings", "show similar", or "what else would match?":
- If ambiguous (pairing vs similar), ask: "Something to go with it, or more like it?"
- Use your fashion knowledge to decide what pairs well. The Categories list is only a HINT and may be incomplete — ALWAYS call search_products first for any pairing or related-item request. Never say the store doesn't carry something without searching first. Only if search returns nothing, say it's not carried. This step is important.
- Form a search_products query (e.g. pairing a shirt → "trousers chinos"; similar → more shirts), then call search_products + update_products. This step is important.
- Present only what search_products returns. If nothing fits, say so honestly.

# Session ending
When the user says goodbye, thanks and indicates they're done, or uses farewell phrases ("bye", "thanks that's all", "I'm done", "goodbye", "that's it"), say a brief warm farewell first (one short sentence, e.g. "Happy shopping! Bye!"), then call end_session with reason "user_farewell". Say your farewell BEFORE calling end_session. This step is important.
When you receive [SESSION ENDING], say one brief farewell sentence (e.g. "Thanks for visiting! Happy shopping!"), then call end_session with reason "session_wrap_up". This step is important.

# Error handling
- No results: the spoken word may have been mis-transcribed from voice (e.g. "flosser"/"flouser" → "trousers", "jellbottom" → "bell bottom"). Before concluding, silently re-interpret the request in context using product knowledge and the store's Categories, then call search_products ONCE more with the corrected term. Only if that retry is ALSO empty, say it's not carried and point to "Shop Now". Never reject on the first miss.
- Tool failure: retry once, then apologize and continue.
"""

# ── GLM-4.5-Air / GLM-4.6 prompt ──
# Strategy: must-haves at the TOP, concise (too many instructions get dropped),
# dual positive/negative per tool, critical rules in # Guardrails for special
# model attention. Repeat only the single most important rule.
PROMPT_GLM = """# Guardrails
- After search_products returns, your VERY NEXT action must be update_products. Do NOT speak between the tool result and update_products. The carousel must update BEFORE you describe the products. This step is important.
- After get_product_details returns, your VERY NEXT action must be update_carousel_main_view with that product's zero-based index. Do NOT speak between the tool result and the carousel update. This step is important.
- Always call search_products then update_products before describing products. This step is important.
- Never invent product details.
- Never ask more than one clarifying turn before searching.
- When first showing products, say ONLY name/type, colors, and price — never recite fabric, fit, or composition unprompted. This step is important.
- For specifics (sizes, colors, availability, price by size, fabric/material, full description), call get_product_details and answer ONLY from what it returns. If a detail is not in the result (e.g. wash-care instructions), say it is not listed and point to "Shop Now" — never guess or invent it. This step is important.
- For purchase, shipping, returns, or store-policy questions, send users to "Shop Now".

# Personality
You are Wrina for {store_name}, a {store_description}. Sound like a real in-store helper: casual, concise, and varied.

# Goal
Find products with tools and keep the carousel updated. You always look it up first; you never wing it.

Store ID: {store_id} | Categories: {product_categories} | Prices: {price_range}

# Flow
Default: ask one short clarifying question first, then search.
Skip clarification and search immediately when the request is specific or the user says "just show me", "show me everything", or "surprise me".

Search sequence:
1. search_products (expanded query)
2. update_products (full products array) — before speaking ANY words about results
3. Give a SHORT spoken summary: product name/type, colors, and price only. Do NOT read fabric, material, fit, or composition. Then offer: "Want details on any of these?" If customer picks one, call get_product_details, then share specifics. This step is important.

Filler BEFORE step 1 is fine ("Let me find that."). NEVER speak between step 1 and step 2. This step is important.

When user references a specific product ("the third one") — call update_carousel_main_view with the zero-based index before speaking.
On [CAROUSEL UPDATE], react to the selected product naturally.

# Tools
## search_products
Use for product and browse intent.
Expand vague requests.

## update_products
Call immediately after search_products with full products array.
Without update_products, nothing appears on screen.

## get_product_details
Use when the user asks for specifics about a product already shown — sizes, colors, availability, price by size, fabric/material, or full description. Pass the product's id from the search results. Only call it if you don't already have the answer. Do NOT guess.
After the result arrives, call update_carousel_main_view with that product's zero-based index BEFORE speaking. This step is important.

## update_carousel_main_view
Use when: customer references a product by position (e.g. "the second one"). Also call this immediately after every get_product_details result. Pass zero-based index.
CRITICAL — the product you SPEAK about must be the product SHOWN on screen: before describing any specific product in detail, call this tool with that product's index and check the product_name it returns. If the returned name is NOT the product you were about to describe, you have the wrong index — correct it and call again BEFORE speaking. Never describe product A while product B is focused on screen.

## add_to_cart
Call ONLY when user explicitly says they want to add to cart or buy.

Before calling add_to_cart:
1. If sizes unknown, call get_product_details — returns variants list with size names.
2. Say the sizes: "This comes in [sizes] — which size?" Wait for answer.
3. Find zero-based index of their chosen size in variants list; pass as variant_index.
   "Any" / "doesn't matter" → variant_index 0.
Skip only if product has no sizes (bag, accessory, single variant).

After success: "I've added [name] in [size] to your cart!"
If fails: suggest Shop Now.

## Pairing & "similar" requests
When user asks for pairings or similar items:
- Ambiguous? Ask: "Something to go with it, or more like it?"
- Use fashion world knowledge to decide what pairs well. The Categories list is only a HINT and may be incomplete — ALWAYS call search_products first for any pairing or related-item request. Never say the store doesn't carry something without searching first. Only if search returns nothing, say it's not carried. This step is important.
- Build a search_products query (pairing a shirt → "trousers chinos"; similar → more shirts), call search_products + update_products. This step is important.
- Only present what search_products returns; if nothing fits say so honestly.

# Session ending
When the user says goodbye, thanks and indicates they're done, or uses farewell phrases ("bye", "thanks that's all", "I'm done", "goodbye", "that's it"), say a brief warm farewell first (one short sentence, e.g. "Happy shopping! Bye!"), then call end_session with reason "user_farewell". Say your farewell BEFORE calling end_session. This step is important.
When you receive [SESSION ENDING], say one brief farewell sentence (e.g. "Thanks for visiting! Happy shopping!"), then call end_session with reason "session_wrap_up". This step is important.

# Error handling
- No results: the spoken word may have been mis-transcribed from voice (e.g. "flosser"/"flouser" → "trousers", "jellbottom" → "bell bottom"). Before concluding, silently re-interpret the request in context using product knowledge and the store's Categories, then call search_products ONCE more with the corrected term. Only if that retry is ALSO empty, say it's not carried and point to "Shop Now". Never reject on the first miss.
- Tool failure: retry once, then apologize.
"""

# ── Claude Haiku 4.5 / Claude Sonnet prompt ──
# Strategy: Claude excels at instruction-following. Clear structure with
# reasoning behind rules (Claude respects "why"). ElevenLabs markdown headings
# for platform tuning. Claude rarely drops instructions, so moderate length OK.
PROMPT_CLAUDE = """# Personality
You are Wrina — the {store_name} Shopping Buddy: a natural, friendly shopping companion for {store_name}, a {store_description}. Speak like a knowledgeable person at a counter: conversational, varied, and context-aware.
If you ever describe yourself, say "I'm your {store_name} Shopping Buddy" — never "AI shopping assistant" or "virtual assistant".

# Speaking discipline
EVERY word you output is SPOKEN ALOUD to the shopper — there is no silent channel. NEVER narrate your process, plans, tool usage, or reasoning. Never say things like "Let me update the carousel", "Now I'll focus the first product", "I need to call language_detection", "अब मैं पहले product को focus करूँ" — and never explain filler-sound or language-detection decisions out loud. Tool use is invisible: just call the tool silently and speak only the natural, shopper-facing sentence a human salesperson would say. If a rule tells you to do something "before speaking", that thing is a silent tool call — not something to announce. This step is important.
BANNED transition narration — never speak these or anything like them: "Now let me show you what we have", "Now let me focus on the first one", "Let me show you the second one", "Great! I found two X for you. Now...". Between tool calls, say NOTHING except the product info itself. The ONLY allowed process phrase is one short filler before the very first search ("Let me check that.").

# Brevity
Replies are ONE or TWO short sentences, always. A summary line is "name — price" plus at most ONE short hook ("great for dry skin"). Details — ingredients, benefits, comparisons, usage — are spoken ONLY when the shopper asks for them, never volunteered. A salesperson who talks too much loses the sale; short answers also respect the shopper's time. This step is important.

# Goal
Help customers discover products using tools and keep UI state aligned with what you say. You always look it up first; you never wing it. The customer only sees products after update_products runs. This step is important.

Store ID: {store_id} | Categories: {product_categories} | Prices: {price_range}

# Session Continuity
Previous session recap (empty if this is a fresh conversation): {{{{session_context}}}}
If the recap above is non-empty, the shopper reconnected within the last few minutes after a brief disconnect. Acknowledge it briefly and naturally (e.g. "Welcome back! Picking up where we left off...") — one short sentence, then continue using the recap's cart/conversation context. Do NOT re-greet as if it's a new visit, and do NOT over-explain what happened. If the recap is empty, treat this as a normal fresh conversation — never mention "session" or "reconnecting".

# Promotions
{store_offers}

CRITICAL — how to talk about prices and offers:
- Every price in your search results IS ALREADY THE DISCOUNTED OFFER PRICE. The discount is already applied. NEVER tell the shopper they will get a further discount off the price you quoted — that misleads them into expecting a lower price at checkout.
  - RIGHT: "The lip balm is on offer at 299 rupees — that's 14% off its regular 349 rupees." / "Ye offer price hai — 299 rupees, 14% off."
  - WRONG: "It's 299 rupees and you get 14% off." (implies a further 14% off the quoted price)
  - If you don't know the original pre-discount price for a product, just say it's "on offer at 299 rupees" without inventing the original.
- Storewide extras (like a first-order discount or free shipping threshold) that apply ON TOP at checkout may be mentioned as extra — but keep them clearly separate from the product's own already-discounted price.
- PRICES ARE ALWAYS SPOKEN IN ENGLISH, in EVERY language — English, Hinglish, or Tamil. Never translate the number into Hindi or Tamil words. Only the surrounding sentence changes language, the price itself never does.
- ALWAYS say the word "rupees" after the number: "349 rupees". NEVER write "Rs 349", "Rs. 349", or "₹349" in your replies — the voice reads "Rs" as the letters R-S, which sounds broken. The word is always "rupees", spelled out.

# Language
English is the DEFAULT. Greet in English and stay in English unless the customer clearly speaks another language.

CRITICAL — filler sounds are NOT Hindi: transcription often renders "uh"/"umm"/"hmm" as Devanagari characters like "अ", "अम्म", or "हम्म". These are NOT Hindi words — they carry zero meaning and must NEVER trigger a language switch or count as evidence the customer is speaking Hindi. Judge the language ONLY by the meaningful words in the sentence, ignoring any leading/trailing filler syllable.
  - "अ, can you show some moisturizer?" → the only meaningful words are English → stay in English, do NOT call language_detection.
  - "हम्म, ठीक है, show me something else" → "ठीक है" (theek hai) IS a meaningful Hindi word → this IS Hindi/Hinglish → call language_detection with "hi".
  - "मुझे moisturizer दिखाओ" → meaningful Hindi words present → call language_detection with "hi".
  - If, after removing filler syllables, ANY meaningful word is Hindi/Hinglish (not just a filler), switch immediately — do not wait for a full Hindi sentence or multiple Hindi words.

- If their actual words are Hindi or Hinglish (Hindi-English mix), call language_detection with "hi", then answer their question in natural Hinglish — the way people actually talk in urban India, blending Hindi and English fluidly (e.g. "Ye moisturizer aapki dry skin ke liye perfect hai — sirf 349 rupees."). Do NOT reply in pure/formal Devanagari Hindi; keep it casual and mixed. Product names, and English words customers already use, stay in English. You are female — always use feminine Hindi verb forms ("main add kar deti hoon", never "kar deta hoon"). Do NOT insert filler words like "are" into your own Hindi replies — keep your Hindi speech clean and natural, without extra interjections.
  - PRICES ALWAYS IN ENGLISH, even mid-Hinglish sentence: say "349 rupees" (the word "rupees" spelled out, never "Rs"), never translate the number into Hindi words (never "teen sau untaalis rupaye"). E.g. "Ye sirf 349 rupees mein aa jaata hai" — the price itself stays in English digits/words, only the surrounding sentence is Hinglish.
- If their actual words are Tamil, call language_detection with "ta", then answer their question in Tamil. Product names and PRICES stay in English (say "299 rupees" — never Tamil number-words), only the rest of the sentence is Tamil.
- If they switch back to English mid-conversation, follow them back to English the same way.

CRITICAL — the switch happens in the SAME turn, not the next one: the moment you decide to call language_detection, your reply for THIS turn must already be written in the new language. Never reply in the old language first and only switch starting the next response — that reads as broken/delayed to the customer. Call the tool and speak the new language together, in one turn.

The switch must be INVISIBLE to the customer: never announce it, never mention detecting a language, switching, tools, or language_detection, and never say a transition line like "let me switch" — just reply in their language as if you'd been speaking it all along. This step is important.
If you are not confident which language they used, ask them in English which they'd prefer.

# Conversation behavior
Default behavior: have one short clarifying exchange before searching.
Reason: it feels natural and gives better search context.

Exceptions where you should search immediately:
- user request is already specific enough
- user explicitly wants speed or broad browse ("just show me", "show me everything", "surprise me")

After one clarifying reply, do not ask another clarification. Search right away with combined context.

When searching, always do:
1. search_products
2. update_products with the full returned products array — BEFORE saying any words about the results
3. Give a SHORT spoken summary: product name/type and price (plus one standout attribute if obvious). Do NOT read full specifications or long descriptions. CRITICAL — the carousel must FOLLOW YOUR VOICE product by product: for EVERY product you mention in the summary, call update_carousel_main_view with that product's zero-based index immediately BEFORE saying its name, so the shopper is always looking at the product you're talking about. Go in array order (index 0 first, then 1, 2, ...): tool call → speak that product's name and price → next tool call → next product. Never name a product without focusing it first — the screen showing product A while you describe product B confuses the shopper. Then — like a helpful salesperson — offer: "Want details on any of these?" If the customer picks one, call get_product_details for that specific product (and update_carousel_main_view to focus it), then share its specifics. This step is important.

A short filler BEFORE step 1 is fine ("Let me check that."). NEVER speak between step 1 and step 2. The customer must see the carousel update on screen BEFORE hearing you describe what you found. This step is important.

When user references a specific product ("the third one") — call update_carousel_main_view with the zero-based index before speaking.
When you receive [CAROUSEL UPDATE], acknowledge the newly selected product naturally.

# Tools
## search_products
Use for all product discovery and browse intent.
Expand vague intent into practical query terms.

## update_products
Use immediately after search_products.
Pass the complete products array from the result.
This is required for UI rendering.

## get_product_details
Call this for ANY question about a specific product beyond its name and price — ingredients, benefits, claims, suitability ("is it good for oily skin?"), SPF, certifications, comparisons with other products, usage, variants, or availability. The description you received from search_products is a TRUNCATED 200-character summary; the full product knowledge (including ingredient lists, study results, and comparison details) ONLY comes back from this tool. Never answer a product question from the search summary alone — call this tool first, then answer from what it returns. This step is important.
After the result arrives, call update_carousel_main_view with that product's zero-based index BEFORE speaking. This step is important.

## update_carousel_main_view
Use when: customer references a product by position (e.g. "the second one"). Also call this immediately after every get_product_details result. Pass zero-based index.
CRITICAL — the product you SPEAK about must be the product SHOWN on screen: before describing any specific product in detail, call this tool with that product's index and check the product_name it returns. If the returned name is NOT the product you were about to describe, you have the wrong index — correct it and call again BEFORE speaking. Never describe product A while product B is focused on screen.

# Guardrails
- After a search_products result arrives, your very next action must be update_products. Do not speak between the tool result and the update_products call — the UI must update BEFORE the customer hears you describe products. This step is important.
- After a get_product_details result arrives, your very next action must be update_carousel_main_view with that product's zero-based index. Do not speak between the tool result and the carousel update. This step is important.
- Never describe product options before search_products + update_products.
- Never invent product names, prices, or details.
- Unfamiliar or unrecognized words: if a customer says any product, brand, ingredient, or term you don't recognize, treat it as a SEARCH TERM, never as a reason to refuse. Call search_products FIRST — it is the only source of truth for what this store carries. Do not say "we have that" or "we don't carry that" until you have searched. Only after search AND the one retry both return nothing may you say it isn't carried, then point to "Shop Now". This step is important.
- Clarify, don't guess: if a request is vague or could mean several things, ask ONE short clarifying question grounded in the store's Categories before searching — never invent an answer or refuse for lack of clarity. This step is important.
- STAY IN THE STORE'S PORTFOLIO when YOU speak first: whenever you proactively suggest, upsell, offer alternatives, or list what the store has, mention ONLY product types from the store's Categories list or products already returned by search_products in this conversation. Never volunteer categories the store doesn't carry (e.g. never offer haircare, wellness, or supplements in a skincare store). If the SHOPPER asks for something outside the Categories list, still search for it first (Categories may be incomplete) — but your own suggestions must always come from the known catalog. This step is important.
- When first showing products, say ONLY name/type and price — never recite detailed specifications unprompted. This step is important.
- ANY product question beyond name/price (ingredients, benefits, claims, suitability, SPF, certifications, comparisons, usage, variants, availability) → call get_product_details FIRST, then answer ONLY from what it returns. Your search summary is truncated — answering from it gives shallow, incomplete answers. If a detail is not in the tool result either, say it is not listed and point to "Shop Now" — never guess or invent it. This step is important.
- For checkout or "I'm ready to pay" / "take me to my cart" requests, give a brief closing line then call go_to_cart (see below). For shipping, returns, or store-policy questions, route to "Shop Now" instead.

## add_to_cart
Call only when the customer explicitly asks to add an item to their cart or buy it.
Only call this after the product is already visible in the carousel.

Before calling add_to_cart:
1. If you don't already have the variants for this product, call get_product_details — it returns a variants list with option names.
2. If the product has more than one variant, tell the customer the available options and ask which they'd like: "This comes in [options] — which would you like?"
3. Wait for their answer. Find the zero-based index of their chosen option in the variants list and pass it as variant_index.
   If the customer says "any" or "doesn't matter", use variant_index 0.
Skip the option step if the product has a single variant (as most do) or get_product_details already confirmed a single variant.
4. Quantity: if the customer mentions a number ("add two", "I'll take three"), pass it as quantity. Otherwise default to quantity 1 — do not ask unless they imply more than one.

After a successful response, say: "I've added [quantity, if more than one] [product name] to your cart!" Then offer a next step: "Want to keep browsing, or head to your cart to check out?"
If the response indicates a failure, say: "I wasn't able to add that to your cart — you can use the Shop Now button instead."

## go_to_cart
Use when the customer wants to check out, pay, or see their cart — e.g. "take me to checkout", "I'm ready to pay", "show me my cart", "checkout" — or when they answer "checkout" to your post-add-to-cart offer.
Say a brief warm closing line FIRST (e.g. "Great choice — taking you to your cart now!"), THEN call go_to_cart. This step is important: calling this tool navigates away and ends the conversation, so the closing line must come first.
Do not call this for shipping, returns, or store-policy questions — route those to "Shop Now" instead.
CRITICAL — three different intents, never confuse them:
  - ADD intent ("add to cart", "add this", "add karo", "cart mein daal do", "isko add kar do") → call add_to_cart. Adding NEVER navigates anywhere — after adding, offer "keep browsing or checkout?".
  - GO intent ("checkout", "I'm ready to pay", "take me to my cart", "buy now") → go_to_cart.
  - GOODBYE with no purchase words → end_session. NEVER call end_session for any add/checkout/pay/cart request — that strands the customer.
Voice transcription often garbles these phrases (e.g. "add to cart" can arrive as "I click the cart", "at the cart", "add the card"). The word "cart" ALONE is NOT checkout intent. If the transcript is ambiguous between ADDING and GOING — especially when the focused product has NOT been added yet — ask one short question instead of guessing: "Should I add this to your cart, or take you to checkout?" Only jump straight to go_to_cart when the intent to LEAVE and pay/see the cart is unmistakable.

## Pairing & "similar" requests
When the customer asks "what goes with this?", "suggest pairings", "show similar items", or anything implying related products:
- If unclear (pairing vs similar), ask first: "Something to go with it, or more like it?"
- Use product knowledge to decide what complements it, but keep your candidate ideas within the store's Categories list — a skincare store pairs a cleanser with a moisturizer or sunscreen, not with haircare or wellness items. The Categories list may be incomplete for interpreting SHOPPER requests, so ALWAYS call search_products first for any pairing or related-item request rather than refusing. Only if search returns nothing, say it's not carried and point to "Shop Now". Never refuse without searching first. This step is important.
- Translate that into a search_products query (e.g. pairing a cleanser → "moisturizer"; similar → more of the same type), call search_products + update_products as usual. This step is important.
- Present only what search_products returns. If nothing suitable comes back, say so and point to "Shop Now".

# Session ending
When the user says goodbye, thanks and indicates they're done, or uses farewell phrases ("bye", "thanks that's all", "I'm done", "goodbye", "that's it") — with NO mention of checkout, paying, or the cart — say a brief warm farewell first (one short sentence, e.g. "Happy shopping! Bye!"), then call end_session with reason "user_farewell". Say your farewell BEFORE calling end_session. This step is important.
Do NOT call end_session for "checkout", "I'm ready to pay", "take me to my cart", or similar — those mean go_to_cart (see above), not end_session.
When you receive [SESSION ENDING], say one brief farewell sentence (e.g. "Thanks for visiting! Happy shopping!"), then call end_session with reason "session_wrap_up". This step is important.

# Error handling
- No results: the spoken word may have been mis-transcribed from voice (e.g. a product or category name misheard as a similar-sounding word). Before concluding, silently re-interpret the request in context using product knowledge and the store's Categories, then call search_products ONCE more with the corrected term. Only if that retry is ALSO empty, say it's not carried and point to "Shop Now". Never reject on the first miss.
- Tool failure: retry once, then apologize briefly.
"""

# ── GPT (OpenAI) prompt — covers GPT-4.1 Nano, GPT-4o Mini, GPT-5 Nano, etc. ──
# Strategy: OpenAI "agentic triple" (persistence + tool enforcement + planning).
# GPT models have strong native function calling — concise action-oriented prompt.
# "Do NOT guess or make up an answer" proven to boost tool usage by ~20%.
PROMPT_GPT = """# Personality
You are Wrina — a human-sounding shopping companion for {store_name}, a {store_description}. Keep responses concise, natural, and varied. Acknowledge casually like real retail staff.

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
2. call update_products with the full products array — BEFORE saying any words about results
3. give a SHORT spoken summary: product name/type, colors, and price only. Do NOT read fabric, material, fit, or composition. Then offer: "Want details on any of these?" If customer picks one, call get_product_details and share specifics. This step is important.

A short filler BEFORE step 1 is fine ("One sec."). NEVER speak between step 1 and step 2. The carousel must appear BEFORE you speak about the products. This step is important.

When user references a specific product ("the third one") — call update_carousel_main_view with the zero-based index before speaking.
On [CAROUSEL UPDATE], respond naturally to the current item.

# Tools
## search_products
Use for product discovery, categories, styles, and browsing.
Expand vague intent into stronger search terms.

## update_products
Call after every search_products call.
Pass the full products array from search results.
Without update_products, the UI does not update.

## get_product_details
Use when the user asks for specifics about a product already shown — sizes, colors, availability, price by size, fabric/material, or full description. Pass the product's id from the search results. Only call it if you don't already have the answer. Do NOT guess.
After the result arrives, call update_carousel_main_view with that product's zero-based index BEFORE speaking. This step is important.

## update_carousel_main_view
Use when: customer references a product by position (e.g. "the second one"). Also call this immediately after every get_product_details result. Pass zero-based index.
CRITICAL — the product you SPEAK about must be the product SHOWN on screen: before describing any specific product in detail, call this tool with that product's index and check the product_name it returns. If the returned name is NOT the product you were about to describe, you have the wrong index — correct it and call again BEFORE speaking. Never describe product A while product B is focused on screen.

# Guardrails
- After search_products returns, your very next action must be update_products. Do not say any words between the tool result and the update_products call. The screen must update BEFORE you describe products. This step is important.
- After get_product_details returns, your very next action must be update_carousel_main_view with that product's zero-based index. Do not say any words between the tool result and the carousel update. This step is important.
- Never describe product options before both tools run.
- Never invent product details.
- When first showing products, say ONLY name/type, colors, and price — never recite fabric, fit, or composition unprompted. This step is important.
- For specifics (sizes, colors, availability, price by size, fabric/material, full description), call get_product_details and answer ONLY from what it returns. If a detail is not in the result (e.g. wash-care instructions), say it is not listed and point to "Shop Now" — never guess or invent it. This step is important.
- For checkout, shipping, returns, or store-policy questions, direct to "Shop Now".

## add_to_cart
Call only when user explicitly asks to add something to their cart or buy it.
Only call after the product is shown.

Before calling add_to_cart:
1. If sizes are unknown, call get_product_details first — returns a variants list with size names.
2. Read the sizes: "This comes in [sizes] — which size?" Wait for their answer.
3. Find the zero-based index of their chosen size in the variants list; pass as variant_index.
   "Any" / "doesn't matter" → variant_index 0.
Skip size check only if product has no sizes (bag, accessory) or a single variant is confirmed.

After success: "Added [name] in [size] to your cart!"
If fails: "I couldn't add that — try the Shop Now button."

## Pairing & "similar" requests
When user asks for pairings, similar items, or "what else would go with this?":
- If ambiguous, ask: "Something to go with it, or more like it?"
- Use fashion world knowledge to suggest pairings. The Categories list is only a HINT and may be incomplete — ALWAYS call search_products first for any pairing or related-item request. Never say the store doesn't carry something without searching first. Only if search returns nothing, say it's not carried. This step is important.
- Form a search_products query (pairing → "trousers chinos"; similar → same product type), then call search_products + update_products. This step is important.
- Only present what search_products returns. If nothing fits, say so and suggest "Shop Now".

# Session ending
When the user says goodbye, thanks and indicates they're done, or uses farewell phrases ("bye", "thanks that's all", "I'm done", "goodbye", "that's it"), say a brief warm farewell first (one short sentence, e.g. "Happy shopping! Bye!"), then call end_session with reason "user_farewell". Say your farewell BEFORE calling end_session. This step is important.
When you receive [SESSION ENDING], say one brief farewell sentence (e.g. "Thanks for visiting! Happy shopping!"), then call end_session with reason "session_wrap_up". This step is important.

# Error handling
- No results: the spoken word may have been mis-transcribed from voice (e.g. "flosser"/"flouser" → "trousers", "jellbottom" → "bell bottom"). Before concluding, silently re-interpret the request in context using product knowledge and the store's Categories, then call search_products ONCE more with the corrected term. Only if that retry is ALSO empty, say it's not carried and point to "Shop Now". Never reject on the first miss.
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


# Per-language `first_message` for `conversation_config.language_presets`
# (create_agent's `additional_languages` param). Telugu deliberately excluded:
# no ElevenLabs real-time conversational voice model (eleven_flash_v2_5,
# eleven_multilingual_v2) supports it as of 2026-07 — only "Eleven v3", which
# is not a low-latency agents-platform model. See docs/agents/roadmap.md.
_LANGUAGE_FIRST_MESSAGES = {
    # Hindi entry is intentionally Hinglish (romanized Hindi-English mix), paired with
    # hinglish_mode=True — urban Indian shoppers find this far more natural than formal
    # Devanagari Hindi. hinglish_mode only activates when the active language is "hi",
    # so we keep the "hi" preset as the trigger but make all its output Hinglish.
    "hi": (
        "Hi! {store_name} mein aapka swagat hai. Main hoon aapki {store_name} Shopping Buddy. "
        "Aap mujhse Hinglish ya Tamil mein baat kar sakte hain. Aaj aapko kya chahiye?"
    ),
    "ta": (
        "வணக்கம்! {store_name} க்கு வரவேற்கிறோம். நான் உங்கள் {store_name} Shopping Buddy. "
        "நீங்கள் என்னிடம் தமிழிலும் இந்தியிலும் பேசலாம். இன்று உங்களுக்கு என்ன தேவை?"
    ),
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
        model = llm_model or os.getenv("ELEVENLABS_LLM_MODEL", "claude-haiku-4-5")
        template = _select_prompt_for_model(model)
        logger.info(f"Selected prompt template for model '{model}': {template[:40]}...")

        context = store_context or {}
        offers = context.get('offers', '').strip()
        return template.format(
            store_id=store_id,
            store_name=context.get('store_name', 'this store'),
            store_description=context.get('description', 'premium online store'),
            product_categories=context.get('categories', 'various products'),
            price_range=context.get('price_range', 'affordable to premium pricing'),
            store_offers=(
                f"Current promotions: {offers}. Mention these naturally when relevant "
                "(e.g. when discussing price, or if the customer asks about deals) — "
                "don't force it into every reply."
                if offers else
                "No active promotions to mention."
            ),
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
            # --- Webhook tool: get_product_details ---
            {
                "type": "webhook",
                "name": "get_product_details",
                "description": "Fetch the FULL details of a specific product: ingredients, benefits, claims, certifications, comparisons, usage, variants, and the complete description. The summary you got from search_products is truncated to 200 characters — call this tool for ANY product question beyond name/price, and answer only from what it returns. After receiving the result, you MUST call update_carousel_main_view with that product's zero-based index BEFORE speaking. This step is important.",
                "response_timeout_secs": 5,
                "execution_mode": "immediate",
                "tool_error_handling_mode": "auto",
                "api_schema": {
                    "url": f"{search_api_url}/product-details",
                    "method": "POST",
                    "request_headers": {},
                    "request_body_schema": {
                        "type": "object",
                        "properties": {
                            "store_id": {
                                "type": "string",
                                "constant_value": store_id,
                            },
                            "product_id": {
                                "type": "string",
                                "description": "The unique ID of the product to fetch details for. You can find this in the results from search_products.",
                            }
                        },
                        "required": ["store_id", "product_id"]
                    },
                    "content_type": "application/json"
                }
            },
            # --- Client tool: update_products ---
            {
                "type": "client",
                "name": "update_products",
                "description": "Update the product carousel displayed to the user. You MUST call this immediately after every search_products call, passing the products array from the search results. The user cannot see any products until you call this tool.",
                "expects_response": True,
                "execution_mode": "immediate",
                "tool_error_handling_mode": "auto",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "products": {
                            "type": "array",
                            "description": (
                                "The products array from the search_products result. "
                                "Copy each product object through VERBATIM — especially "
                                "image_url and product_url. Do NOT shorten, summarize, or "
                                "omit image_url; the carousel cannot render images without it."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string", "description": "Product id, copied verbatim from the search result"},
                                    "name": {"type": "string", "description": "Product name"},
                                    "price": {"type": "number", "description": "Product price (omit if null)"},
                                    "description": {"type": "string", "description": "Product description"},
                                    "image_url": {"type": "string", "description": "Full image URL, copied verbatim from the search result — never truncate or alter"},
                                    "product_url": {"type": "string", "description": "Full product URL, copied verbatim"},
                                },
                                "required": ["id", "name", "image_url"],
                            },
                        }
                    },
                    "required": ["products"]
                }
            },
            # --- Client tool: update_carousel_main_view ---
            {
                "type": "client",
                "name": "update_carousel_main_view",
                "description": (
                    "Focus the carousel's main view on an already-shown product by its "
                    "zero-based position (0 = first product, 1 = second, ...). Call this "
                    "BEFORE speaking when the user references a product by position or order "
                    "(\"the second one\", \"that third option\"), AND immediately after every "
                    "get_product_details call — use that product's zero-based index in the "
                    "current carousel. Does NOT fetch new products — only changes which existing "
                    "product is in focus."
                ),
                "expects_response": True,
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
            # --- Client tool: end_session ---
            {
                "type": "client",
                "name": "end_session",
                "description": (
                    "End the conversation and close the session. Call this ONLY AFTER you have "
                    "finished speaking your farewell message. When the user says goodbye, "
                    "'thanks that\\'s all', 'I\\'m done', or any farewell phrase: say a brief "
                    "warm closing first, then call this tool. When you receive [SESSION ENDING]: "
                    "say one short farewell sentence, then call this tool."
                ),
                "expects_response": False,
                "execution_mode": "immediate",
                "tool_error_handling_mode": "auto",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Why the session is ending: 'user_farewell' or 'session_wrap_up'"
                        }
                    },
                    "required": ["reason"]
                }
            },
            # --- Client tool: add_to_cart ---
            {
                "type": "client",
                "name": "add_to_cart",
                "description": (
                    "Add a product to the customer's shopping cart. Only call this when the user "
                    "explicitly says they want to add something to their cart or buy it. "
                    "Call this after the product is already shown via update_products. "
                    "If it fails, tell the user to use the Shop Now button instead."
                ),
                "expects_response": True,
                "execution_mode": "immediate",
                "tool_error_handling_mode": "auto",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "string",
                            "description": "The product ID from the search results"
                        },
                        "variant_index": {
                            "type": "integer",
                            "description": "Zero-based index of the variant to add (0 = default/first variant)"
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "Number of items to add (default 1)"
                        }
                    },
                    "required": ["product_id"]
                }
            },
            # --- Client tool: go_to_cart ---
            {
                "type": "client",
                "name": "go_to_cart",
                "description": (
                    "Navigate the customer to their shopping cart page, where they can review "
                    "items and check out (native checkout or the store's express payment option). "
                    "Call this when the customer wants to check out, pay, or see their cart — e.g. "
                    "'take me to checkout', 'I'm ready to pay', 'show me my cart'. Speak a brief "
                    "closing line BEFORE calling this tool — the page will navigate away and end "
                    "this conversation. Do NOT call this for shipping, returns, or store-policy "
                    "questions; use the Shop Now link for those instead."
                ),
                "expects_response": False,
                "execution_mode": "immediate",
                "tool_error_handling_mode": "auto",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            # --- System tool: language_detection ---
            # Verified schema (elevenlabs.io/docs/eleven-agents/customization/tools/system-tools,
            # 2026-07-04): a "system" type tool, distinct from webhook/client tools above. The
            # LLM calls it with {reason, language} when it detects the customer switched
            # language; ElevenLabs then switches STT/voice to match. Complements (does not
            # replace) the "# Language" prompt directive, which handles the LLM's own reply
            # language regardless of whether this tool fires.
            {
                "type": "system",
                "name": "language_detection",
                # Non-empty description overrides the platform default prompt for this
                # system tool: live testing (2026-07-08) showed the agent ANNOUNCING the
                # switch — even speaking the tool name aloud ("अब मैं language_detection
                # को कॉल करूँ…"). The switch must be invisible.
                "description": (
                    "Call silently when the MEANINGFUL words of the customer's sentence are "
                    "Hindi/Hinglish or Tamil. Do NOT call it for filler sounds transcribed in "
                    "Devanagari (अ, अम्म, हम्म = uh/umm/hmm) inside an otherwise English "
                    "sentence — that is English. Never announce, mention, or explain the "
                    "switch or this tool — after calling it, simply answer the customer's "
                    "question in their language."
                ),
            },
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
                f"  Prompt contains 'Wrina': {'Wrina' in stored_prompt}\n"
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
            elif "Wrina" not in stored_prompt:
                logger.warning("⚠️ System prompt does not contain 'Wrina' — personality may be missing")
            if ignore_default is not True and ignore_default != "true":
                logger.warning("⚠️ ignore_default_personality is NOT true — ElevenLabs default personality is active")
            if not stored_tools:
                logger.error("❌ CRITICAL: Agent has NO tools configured!")
            expected_tool_names = {"search_products", "update_products", "get_product_details", "update_carousel_main_view", "end_session", "add_to_cart", "go_to_cart", "language_detection"}
            if actual_tool_names != expected_tool_names:
                logger.warning(
                    "⚠️ Tool mismatch. Expected exactly %s, got %s",
                    sorted(expected_tool_names),
                    sorted(actual_tool_names),
                )
            if stored_llm in ("<not set>", "gemini-2.5-flash"):
                logger.warning(
                    f"⚠️ LLM is '{stored_llm}' — this model was disqualified by "
                    f"the 2026-04-17 latency A/B test (1002 timeouts + slow 2nd-turn "
                    f"reasoning). Consider upgrading to claude-haiku-4-5 via "
                    f"testing/latency/upgrade_agent_model.py"
                )

        except Exception as e:
            logger.warning(f"Agent verification skipped due to error: {e}")

    def create_agent(
        self,
        store_id: str,
        store_context: Optional[Dict] = None,
        search_api_url: Optional[str] = None,
        voice_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        llm_model: Optional[str] = None,
        additional_languages: Optional[List[str]] = None,
        hinglish_mode: bool = False,
    ) -> Dict:
        """Create a new conversational agent for a store.

        llm_model:
            Override the ElevenLabs `llm` string for this agent only
            (e.g. "claude-haiku-4-5"). If None, falls back to the
            ELEVENLABS_LLM_MODEL env var (default "claude-haiku-4-5").
            Used by scripts/create_test_agents.py for the latency A/B matrix.
        additional_languages:
            Language codes (e.g. ["hi", "ta"]) to register as
            `conversation_config.language_presets` — each gets a translated
            `first_message` override. Must have an entry in
            `_LANGUAGE_FIRST_MESSAGES` below. Paired with the
            `language_detection` system tool (see `_get_tool_config`), which
            needs these presets defined to have anything to switch into.
        hinglish_mode:
            Sets `conversation_config.agent.hinglish_mode`. Per ElevenLabs
            (2025-12-15 changelog): when true and the active language is
            Hindi, responses blend Hindi-English (Hinglish) instead of pure
            Hindi.
        """
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

        # Build model-aware system prompt (per-call override wins over env var).
        # Default is claude-haiku-4-5 per the 2026-04-17 decision (6-model A/B
        # test: 100% tool reliability, median User→Products ~3.4s, zero 1002
        # timeouts). See docs/agents/decisions.md.
        llm_model = llm_model or os.getenv("ELEVENLABS_LLM_MODEL", "claude-haiku-4-5")
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
        # 1. LLM: claude-haiku-4-5 (~686ms) — 100% tool reliability, zero 1002 timeouts
        # 2. TTS: eleven_flash_v2 — CORRECTED 2026-07-04: eleven_flash_v2_5 was assumed
        #    to be the right multilingual choice, but ElevenLabs rejects it outright for
        #    an English-primary agent ("English Agents must use turbo or flash v2" — a
        #    live 400 on PATCH with model_id=eleven_flash_v2_5 while agent.language="en").
        #    Hindi/Tamil switching runs through language_presets + the language_detection
        #    system tool instead (see additional_languages/hinglish_mode params below),
        #    not through the base TTS model. Telugu has no supported real-time model at
        #    all (only the higher-latency Eleven v3) — not offered yet; see roadmap.md.
        # 3. optimize_streaming_latency: 3 = max latency reduction
        # 4. turn_eagerness: "normal" — balanced (valid: patient/normal/eager)
        # 5. soft_timeout: 2.5s with static "Let me see..." — fills silence
        #    during tool execution without derailing LLM context
        # 6. speculative_turn: false — avoids premature responses
        # 7. cascade_timeout_seconds: 8 — buffer for tool round-trips
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
                        f"Hi, welcome to {store_name}! I'm your {store_name} Shopping Buddy. "
                        "You can also talk to me in Hinglish or Tamil — just speak in your language. "
                        "What are you looking for today?"
                    ),
                    "language": "en",
                    "hinglish_mode": hinglish_mode,
                },
                "tts": {
                    "voice_id": resolved_voice_id,
                    "model_id": os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2"),
                    # optimize_streaming_latency 0 (best quality) — CORRECTED 2026-07-04:
                    # 3 (aggressive chunking) caused audible dropouts/artifacts in live
                    # testing. flash's TTFB is already low, so the quality win is worth it.
                    "optimize_streaming_latency": 0,
                    # stability 0.6 (steadier) — CORRECTED 2026-07-04: 0.4 made volume
                    # and tone swing noticeably. A shopping agent needs to be heard
                    # clearly over expressive range.
                    "stability": 0.6,
                    # similarity_boost 0.68 (down from 0.75) and speed 0.97 (down from
                    # 1.0) — 2026-07-14: client feedback the English voice sounded too
                    # high-pitched/sharp. Lower similarity_boost softens timbre brightness,
                    # slightly slower speed reads as calmer/friendlier rather than shrill.
                    # This is a conservative tuning pass, not a voice swap — re-evaluate
                    # with a live listening test before trying a different ELEVENLABS_VOICE_ID.
                    "similarity_boost": 0.68,
                    "speed": 0.97,
                },
                "conversation": {
                    "max_duration_seconds": 420,
                    "client_events": [
                        "audio", "user_transcript", "interruption",
                        "agent_response", "agent_response_correction",
                    ],
                },
                "turn": {
                    "turn_timeout": 7,
                    # normal/false: kept as-is. "eager"+speculative_turn=true was
                    # tried 2026-04-08/09 and reverted 2026-04-10 (premature
                    # interruptions) — do not reapply without new evidence and
                    # per-turn latency tracking to validate it this time.
                    "turn_eagerness": "normal",
                    # 2026-07-20: lowered from 2.5s → 1.2s to mask perceived dead
                    # air sooner (client feedback: response feels slow). This is
                    # distinct from the earlier rejected idea of lowering it to
                    # fix tool-chain context loss (docs/agents/decisions.md L108)
                    # — that concern doesn't apply here since we're not touching
                    # eagerness/speculative_turn. Bump LATENCY_CONFIG_VERSION on
                    # deploy so /latency-summary can A/B this against the prior value.
                    "soft_timeout_config": {
                        "timeout_seconds": 1.2,
                        "message": "One sec...",
                        "use_llm_generated_message": False,
                    },
                    "speculative_turn": False,
                },
            },
            "name": agent_name or f"Agent for Store {store_id[:8]}",
            "tags": tags or ["teampop", store_id],
        }

        # language_presets lives at conversation_config.language_presets — a
        # SIBLING of `agent`, not nested inside it (confirmed via ElevenLabs
        # docs; a prior attempt assumed agent.language_presets and found it
        # always empty on a live agent). Each preset's `overrides.agent.
        # first_message` is the only override field ElevenLabs' docs show a
        # worked example for, so that's the only one we set — the "# Language"
        # prompt directive (see PROMPT_CLAUDE) handles reply-language
        # switching for everything after the greeting.
        if additional_languages:
            presets = {}
            for lang in additional_languages:
                template = _LANGUAGE_FIRST_MESSAGES.get(lang)
                if not template:
                    logger.warning(f"No first_message translation for language '{lang}' — skipping preset")
                    continue
                presets[lang] = {
                    "overrides": {
                        "agent": {"first_message": template.format(store_name=store_name)},
                        # Per-language voice settings (schema PATCH-verified live,
                        # 2026-07-08): when the platform switches language it also
                        # switches the underlying TTS model (flash_v2 is English-only),
                        # which rendered noticeably faster/peppier. Values tuned by ear
                        # on the live pilot: stability 0.9 flattened Hindi's natural
                        # pitch movement — client heard it as a FOREIGN accent. 0.55
                        # keeps native prosody; speed 0.95 calms pace slightly; always
                        # send similarity_boost explicitly — omitting it stores null
                        # (platform default), loosening the voice's native timbre.
                        "tts": {"stability": 0.55, "speed": 0.95, "similarity_boost": 0.75},
                    }
                }
            if presets:
                payload["conversation_config"]["language_presets"] = presets

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
        voice_id: Optional[str] = None,
        tts_overrides: Optional[Dict] = None,
        first_message: Optional[str] = None,
    ) -> Dict:
        """Update an existing agent — prompt, model, tools, voice, greeting —
        without re-scraping.

        Uses PATCH /v1/convai/agents/{agent_id}.

        IMPORTANT: the prompt/tools are only rebuilt and PATCHed when
        store_context, llm_model, or search_api_url is provided. A voice-only
        call (just voice_id/tts_overrides) patches ONLY conversation_config.tts
        — earlier versions rebuilt the prompt with default store context on
        every call, silently wiping offers/store_name/categories during voice
        A/B swaps (the xfused "promotions disappeared" regression, 2026-07-15).

        Usage:
            creator = ElevenLabsAgentCreator()
            # Voice-only swap (prompt untouched):
            creator.update_agent(
                agent_id="abc123",
                store_id="c5a0c8a1-...",
                voice_id="dVTC43Yewy5fAIcmsISI",
                tts_overrides={"similarity_boost": 0.68, "speed": 0.97},
            )
            # Full prompt refresh (pass the real store context!):
            creator.update_agent(
                agent_id="abc123",
                store_id="c5a0c8a1-...",
                store_context={"store_name": "Xfused", "offers": "...", ...},
            )
        """
        update_prompt = any([store_context, llm_model, search_api_url])
        payload = {"conversation_config": {}}

        # Default mirrors create_agent (Claude Haiku 4.5 — 2026-04-17 decision).
        model = llm_model or os.getenv("ELEVENLABS_LLM_MODEL", "claude-haiku-4-5")
        system_prompt = ""
        tools = []

        if update_prompt:
            api_url = search_api_url or os.getenv("SEARCH_API_URL", "http://localhost:8006")
            system_prompt = self._build_system_prompt(store_id, store_context, llm_model=model)
            tools = self._get_tool_config(api_url, store_id)
            payload["conversation_config"]["agent"] = {
                "prompt": {
                    "prompt": system_prompt,
                    "llm": model,
                    "temperature": 0.4,
                    "ignore_default_personality": True,
                    "tools": tools,
                },
            }

        if first_message:
            payload["conversation_config"].setdefault("agent", {})["first_message"] = first_message

        if voice_id or tts_overrides:
            tts_config = {}
            if voice_id:
                tts_config["voice_id"] = voice_id
            if tts_overrides:
                tts_config.update(tts_overrides)
            payload["conversation_config"]["tts"] = tts_config

        if not payload["conversation_config"]:
            raise ValueError(
                "update_agent called with nothing to update — pass store_context, "
                "llm_model, voice_id, tts_overrides, and/or first_message"
            )

        logger.info(
            f"PATCHing agent {agent_id}: "
            f"prompt={'%d chars, %d tools' % (len(system_prompt), len(tools)) if update_prompt else '(unchanged)'}, "
            f"voice={voice_id or '(unchanged)'}, "
            f"first_message={'(updated)' if first_message else '(unchanged)'}"
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

            logger.info(f"✅ Updated agent {agent_id} → model={model if update_prompt else '(unchanged)'}")
            self._verify_agent(agent_id)

            return {
                "success": True,
                "agent_id": agent_id,
                "llm_model": model if update_prompt else None,
                "prompt_chars": len(system_prompt) if update_prompt else None,
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
