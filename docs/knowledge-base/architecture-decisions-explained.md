# Architecture Decisions Explained

## What This Is

This file translates key entries from `docs/agents/decisions.md` into plain-English summaries for humans who need the rationale without reading the full append-only log first.

## Why It Exists

The decision log is durable and detailed, but it is optimized for preserving history. This file is optimized for quick understanding.

## Reading Note

If you need exact historical wording, tradeoffs, or supersession context, use `../agents/decisions.md`. This file is a summary layer, not the authoritative archive.

## 1. Monorepo Refactor With Shared Library, Adapter Registry, And Unified Pipeline

## What

The repo was refactored so onboarding, search, and shared utilities live together with a cleaner separation:

- `shared/` for cross-service config, DB access, embeddings, and parsing
- adapter registry for store-type selection
- unified onboarding pipeline instead of duplicated store-specific branches

## Why

This reduced duplicated logic, especially around embedding config, Supabase access, and onboarding steps.

## How It Shows Up In Code

- `shared/`
- `onboarding-service/pipeline.py`
- `onboarding-service/adapters/`
- `search-service/main.py`

## Tradeoffs

- Simpler local development and shared invariants
- Less formal service isolation than a more production-hardened setup

## Source

- `../agents/decisions.md` entry dated 2026-04-07

## 2. Single-Tunnel Demo Architecture

## What

External demo traffic is funneled through the onboarding service so one ngrok tunnel can serve demo pages, widget assets, images, and search webhook traffic.

## Why

ngrok free-tier limitations made multi-tunnel demos too fragile.

## How It Shows Up In Code

- `onboarding-service/main.py` mounts `/widget` and `/images`
- `onboarding-service/main.py` proxies `POST /search` to the search service

## Tradeoffs

- Better demo ergonomics
- More coupling through the onboarding service for dev/demo traffic

## Source

- `../agents/decisions.md` entry dated 2026-04-08

## 3. Widget Served As Built IIFE, Not Vite Dev Output

## What

The embeddable widget contract is the built `widget.js` file served from onboarding, not the Vite dev server output.

## Why

Vite Fast Refresh globals break when the file is consumed from external pages.

## How It Shows Up In Code

- `www.teampop/frontend/vite.config.js`
- `onboarding-service/main.py`

## Tradeoffs

- Reliable external embedding
- Requires `npm run build` after widget changes before demo testing

## Source

- `../agents/decisions.md` entry dated 2026-04-03

## 4. Shadow DOM As Widget Isolation Strategy

## What

The widget renders inside a custom element with a shadow root.

## Why

The team needed CSS and DOM isolation from merchant storefronts.

## How It Shows Up In Code

- `www.teampop/frontend/src/main.jsx`

## Tradeoffs

- Strong isolation for embeds
- Extra constraints such as no CSS `@import` inside widget styles

## Source

- `../agents/constraints.md`
- related widget migration context in `../agents/decisions.md` and `../agents/completions.md`

## 5. ElevenLabs React SDK v1 Migration

## What

The widget uses `@elevenlabs/react` v1-style provider and client-tool registration.

## Why

The older path stopped working with ElevenLabs' deprecated connection model.

## How It Shows Up In Code

- `www.teampop/frontend/src/App.jsx`
- `www.teampop/frontend/src/components/AvatarWidget.jsx`

## Tradeoffs

- Current compatibility with ElevenLabs
- Stronger dependency on exact SDK patterns and tool registration behavior

## Source

- `../agents/decisions.md` entry dated 2026-04-03

## 6. Constant `store_id` In ElevenLabs Webhook Tool Config

## What

The agent webhook tool stores `store_id` as a constant value, not an LLM-generated field.

## Why

LLM-generated UUIDs were getting truncated and causing failed search requests.

## How It Shows Up In Code

- `onboarding-service/elevenlabs_agent.py`
- `search-service/main.py`

## Tradeoffs

- Correct by construction for a given created agent
- If the store changes, the agent must be recreated or updated explicitly

## Source

- `../agents/decisions.md` entry dated 2026-04-05

## 7. Model-Specific Prompting And Latency Tuning

## What

The team uses model-aware prompting plus conversation settings tuned for faster tool execution and interruption handling.

## Why

Different LLM families behaved differently in the agent loop, especially around filler speech, tool order, and responsiveness.

## How It Shows Up In Code

- `onboarding-service/elevenlabs_agent.py`

## Tradeoffs

- Better real-world conversation behavior
- More prompt/config complexity to maintain

## Source

- `../agents/decisions.md` entries dated 2026-04-08 and 2026-04-09

## 8. Search Service No Longer Builds Sales Pitch With A Separate LLM Call

## What

The search response still returns a `pitch` field, but it is now static instead of using a synchronous LLM call.

## Why

That call dominated latency and was not needed because the voice agent already generates spoken explanations.

## How It Shows Up In Code

- `search-service/main.py`

## Tradeoffs

- Much faster search
- Less dynamic copy in the API payload, but no actual product loss in the voice flow

## Source

- `../agents/decisions.md` entry dated 2026-04-08

## Informed Inferences

Some rationale is explicit in the decision log. Some broader interpretation in this file is an informed inference from code, docs, and the surrounding implementation context. When that happens, the goal is explanation, not replacing the source decision record.
