# Glossary

## What This Is

A quick-reference glossary for the product, architecture, and repo-specific vocabulary used across Team Pop docs and code.

## Product And System Terms

**Team Pop**
The voice-first shopping assistant product implemented in this repo.

**Onboarding**
The process that turns a store URL into scraped products, Supabase rows, an ElevenLabs agent, and a demo page.

**Store context**
A compact summary of a store's catalog, categories, and price range used when creating an agent prompt/config.

**Demo page**
A generated HTML page that injects the widget into a captured or prepared storefront view for testing or delivery.

**Widget snippet**
The embed HTML returned by onboarding, including script loading and the `<team-pop-agent>` element.

## Services And Repo Terms

**Onboarding service**
The FastAPI service in `onboarding-service/` that owns onboarding, client/admin APIs, demo assets, and the dev/demo search proxy.

**Search service**
The FastAPI service in `search-service/` that embeds a query and calls `hybrid_search_products`.

**Shared library**
The `shared/` folder containing cross-service config, DB access, embedding helpers, and parsing utilities.

**Adapter**
A store-specific implementation that knows how to scrape and normalize one storefront type before the unified pipeline continues.

**Universal adapter**
The catch-all adapter for sites that do not have a dedicated store-specific path.

## Data And Search Terms

**`products` table**
The main product storage table in Supabase. It includes an `embedding` column used for semantic search.

**`products.embedding`**
The vector column that currently uses `vector(384)` and is tied to `all-MiniLM-L6-v2`.

**`hybrid_search_products`**
The core Supabase RPC contract used by the search service to combine semantic and text-based retrieval.

**Embedding**
A numeric vector representation of text used for semantic similarity search.

**pgvector**
The PostgreSQL extension used for vector storage and similarity search.

## Voice / Widget Terms

**`<team-pop-agent>`**
The custom element that acts as the widget's public integration API.

**Shadow DOM**
The browser mechanism used to isolate widget markup and CSS from the host page.

**`ConversationProvider`**
The ElevenLabs React provider required by the current widget SDK integration.

**`useConversationClientTool`**
The hook used in the widget to register client-side handlers for agent tool calls like `update_products`.

**`update_products`**
The client tool that loads returned products into the widget UI.

**`update_carousel_main_view`**
The client tool that changes which product card is active in the carousel.

**`product_desc_of_main_view`**
The client tool used to enrich or narrate the currently active product state. React code should not invoke it manually.

## Operational Terms

**Single-tunnel architecture**
The current demo/dev pattern where the onboarding service fronts widget assets, images, and the search webhook path so one ngrok tunnel can expose the system.

**`store_id`**
A UUID representing one onboarded store. It is baked into the ElevenLabs webhook config as a constant.

**`agent_requests`**
The table used for merchant intake and admin workflow status tracking.

**`X-Admin-Password`**
The current simple admin authentication header used by the website/admin backend flow.

## Documentation Terms

**Agent docs**
The `docs/agents/` files that own hard rules, decisions, active memory, completions, handoffs, and roadmap.

**Knowledge base**
This `docs/knowledge-base/` folder, which summarizes the system for humans and links back to the agent docs for source evidence.
