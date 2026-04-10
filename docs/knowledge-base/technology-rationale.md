# Technology Rationale

## What This Is

This file explains why the main technologies in the current Team Pop stack appear to have been chosen, what they buy the team, and what tradeoffs they introduce.

## Why It Exists

New engineers usually ask “why this stack?” before they ask “where is the code?”. This file gives an evidence-backed answer.

## Reading Note

Where the reasoning is directly documented in code history or decisions, it is described as documented rationale. Where it is not explicitly stated, it is marked as an informed inference from repo structure and completed work.

## FastAPI

## What

Both backend services use FastAPI.

## Why

Documented and strongly implied reasons:

- quick JSON API development
- Pydantic request/response modeling
- easy route decomposition during the onboarding refactor
- good fit for alpha-stage internal/admin/public APIs

## Where

- `onboarding-service/main.py`
- `search-service/main.py`

## Tradeoffs

- Fast to ship
- not yet paired with stronger production middleware choices like strict CORS or rate limiting

## Supabase + PostgreSQL + pgvector

## What

Supabase hosts the main product and request data, and pgvector backs semantic similarity search.

## Why

Documented and inferred reasons:

- the product needed hosted Postgres plus vector search without a large infra lift
- the `hybrid_search_products` RPC centralizes search ranking logic
- the team can store relational and vector data in one place

## Where

- `shared/db.py`
- `search-service/main.py`
- `onboarding-service/services/products.py`

## Tradeoffs

- very practical for an alpha
- RPC and schema contracts become critical, so changes need more discipline

## `all-MiniLM-L6-v2`

## What

This is the shared embedding model used during onboarding and search.

## Why

Documented rationale:

- 384 dimensions align with `products.embedding`
- it is fast and good enough for short catalog text
- using the same model in both services avoids silent search quality failures

## Where

- `shared/config.py`
- `shared/embeddings.py`

## Tradeoffs

- simple and cheap operationally
- any future model change requires a coordinated migration and full re-embed

## ElevenLabs

## What

ElevenLabs powers the conversational voice agent layer.

## Why

Documented rationale:

- combines voice, conversation, and tool invocation in one agent flow
- recent work focused on lower latency, tool reliability, and SDK/API compatibility

## Where

- `onboarding-service/elevenlabs_agent.py`
- `www.teampop/frontend/src/App.jsx`
- `www.teampop/frontend/src/components/AvatarWidget.jsx`

## Tradeoffs

- fast path to a polished voice demo
- vendor-specific SDK and config details matter a lot
- the conversation cycle can become brittle if prompts or tool contracts drift

## React Widget + Shadow DOM

## What

The storefront assistant is a React widget exposed as a custom element with Shadow DOM encapsulation.

## Why

Documented rationale:

- React provides a productive UI model for the widget
- Shadow DOM isolates widget styles from arbitrary merchant pages
- the IIFE build allows simple `<script>` plus `<team-pop-agent>` embedding

## Where

- `www.teampop/frontend/src/main.jsx`
- `www.teampop/frontend/vite.config.js`

## Tradeoffs

- easy merchant integration surface
- requires extra care with CSS loading and build output

## Monorepo + Shared Library

## What

The codebase keeps services, frontend apps, and shared utilities together.

## Why

Documented rationale:

- onboarding and search share invariants
- the repo was refactored specifically to reduce duplicated code
- product, search, and widget changes often ship together in alpha

## Where

- `shared/`
- `onboarding-service/`
- `search-service/`
- `www.teampop/`

## Tradeoffs

- easier coordination and refactoring
- can blur boundaries if ownership and docs are weak

## Adapter Model

## What

Store-specific scraping logic is represented as adapters behind a shared onboarding pipeline.

## Why

Documented rationale:

- new store types should not require copy-pasting the full onboarding flow
- non-Shopify catalogs can be normalized before entering shared downstream logic

## Where

- `onboarding-service/adapters/base.py`
- `onboarding-service/adapters/registry.py`
- `onboarding-service/adapters/`

## Tradeoffs

- scalable enough for several store types
- site-specific scraping quality still varies by platform and target site

## Alternatives And Why Not

These are informed inferences based on the current repo and decision history:

- not a separate vector database: pgvector inside Supabase kept infra simpler
- not a single monolithic Python file anymore: the repo already hit maintainability pain before refactoring
- not a plain iframe widget: the chosen integration contract is a custom element with Shadow DOM
- not bespoke scraping pipelines per store forever: the adapter pattern and universal fallback were added to avoid repeated copy-paste growth
- not a separate LLM-generated search pitch service: latency evidence showed that path was not worth the cost

## What Can Break

- vendor API changes
- embedding/search contract drift
- adapter assumptions on fragile target sites
- widget build or asset-serving mismatches

## What Should Improve Next

- explicit production architecture docs once deployment stabilizes
- stronger test coverage around vendor and platform integrations
- clearer decision records whenever a major technology is added or replaced
