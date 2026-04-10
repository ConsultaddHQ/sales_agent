# Repo Map

## What This Is

This is a navigation guide to the live monorepo so a new engineer can quickly find the right service, entrypoint, or implementation file.

## Why It Exists

The repo contains several moving pieces that look like separate products at first glance. This file explains what each major area owns and where to start reading.

## Top-Level Areas

| Path | What it owns | Start here |
|------|---------------|------------|
| `shared/` | Shared config, DB access, embeddings, parsing helpers | `shared/config.py`, `shared/db.py`, `shared/embeddings.py` |
| `onboarding-service/` | Store onboarding, scraping, demo-page generation, agent creation, client/admin APIs | `onboarding-service/main.py`, `onboarding-service/pipeline.py` |
| `search-service/` | Search API that embeds queries and calls Supabase hybrid search | `search-service/main.py` |
| `www.teampop/frontend/` | Embeddable widget shipped as `<team-pop-agent>` | `www.teampop/frontend/src/main.jsx`, `www.teampop/frontend/src/components/AvatarWidget.jsx` |
| `www.teampop/website/` | Marketing site and admin dashboard UI | `www.teampop/website/src/pages/` |
| `universal-scraper/` | Legacy scraping scripts still referenced by adapters | inspect only when adapter behavior points here |
| `docs/agents/` | Source-of-truth agent constraints, decisions, memory, completions, roadmap | `docs/agents/constraints.md`, `docs/agents/decisions.md` |
| `docs/knowledge-base/` | Human-facing KT handbook | `docs/knowledge-base/README.md` |
| `.personal/learning/` | Optional personal study notes, not canonical | use only as a supplement |

## Onboarding Service Map

## What Is It

The onboarding service is the operational center of the current system. It wires together scraping, Supabase writes, ElevenLabs agent creation, demo-page generation, and the public/client/admin APIs.

## How It Works

- `main.py` sets up FastAPI, wildcard CORS for alpha, static mounts, route wiring, and the local `/search` proxy.
- `pipeline.py` runs the 7-step onboarding flow.
- `routes/onboard.py` exposes `/onboard` and the legacy aliases.
- `routes/client.py` and `routes/admin.py` handle request intake and admin workflows.
- `services/` holds business logic that the routes and pipeline call.
- `adapters/` selects the correct store-specific scraping approach.
- `scraping/` contains universal fallback extraction logic.

## Where The Code Is

| Area | Path | Notes |
|------|------|-------|
| App setup | `onboarding-service/main.py` | CORS, static files, route registration, search proxy |
| Unified pipeline | `onboarding-service/pipeline.py` | Scrape -> process -> store -> create agent -> generate page |
| Adapter registry | `onboarding-service/adapters/registry.py` | store-type resolution |
| Store adapters | `onboarding-service/adapters/` | Shopify, Threadless, Supermicro, Universal |
| Product processing | `onboarding-service/services/products.py` | row shaping, images, embeddings, Supabase writes |
| Test pages | `onboarding-service/services/test_page.py` | injects widget into demo HTML |
| Agent creation | `onboarding-service/services/agent_creator.py`, `onboarding-service/elevenlabs_agent.py` | ElevenLabs config |
| Error contract | `onboarding-service/error_codes.py` | user-facing onboarding errors |

## Search Service Map

## What Is It

The search service is intentionally small. Its main job is to turn a query into an embedding, call the `hybrid_search_products` RPC, and return products fast enough for the voice loop.

## Where The Code Is

- `search-service/main.py`
- `shared/embeddings.py`
- `shared/db.py`
- `shared/config.py`

## Widget Map

## What Is It

The frontend widget is a React app wrapped as a custom element so it can be embedded into host pages without CSS collisions.

## Where The Code Is

| Concern | Path |
|---------|------|
| Custom element registration | `www.teampop/frontend/src/main.jsx` |
| ElevenLabs session + client tools | `www.teampop/frontend/src/components/AvatarWidget.jsx` |
| Provider wiring | `www.teampop/frontend/src/App.jsx` |
| Build output contract | `www.teampop/frontend/vite.config.js` |

## Website Map

## What Is It

The website is both marketing surface and internal admin surface for request management.

## Where The Code Is

- `www.teampop/website/src/pages/Landing.jsx`
- `www.teampop/website/src/pages/RequestPage.jsx`
- `www.teampop/website/src/pages/AdminPage.jsx`
- `www.teampop/website/src/lib/api.js`

## Stable Interfaces To Find Quickly

| Contract | Code path |
|----------|-----------|
| `hybrid_search_products` RPC usage | `search-service/main.py` |
| Embedding model lockstep | `shared/config.py` |
| `<team-pop-agent>` public API | `www.teampop/frontend/src/main.jsx` |
| Legacy onboarding endpoint compatibility | `onboarding-service/routes/onboard.py` |
| `X-Admin-Password` admin auth | `onboarding-service/routes/admin.py`, `onboarding-service/routes/client.py`, `www.teampop/website/src/lib/api.js` |
| Built widget served from `/widget/widget.js` | `onboarding-service/main.py`, `www.teampop/frontend/vite.config.js` |

## Tradeoffs

- Some responsibilities that would be separate in production are still grouped for demo speed.
- The repo still contains legacy scraper material, so “where code lives” is not always the same as “what should be touched first.”
- The onboarding service owns too many edges today, but that centralization also makes current demo flows easier to reason about.

## What Can Break

- Editing legacy files instead of the active adapter/service path
- Treating the Vite dev server output as the embeddable production widget
- Missing the shared/ dependency and changing config in only one service

## What Should Improve Next

- Add richer per-service READMEs where still thin or outdated
- Reduce ambiguity between active and legacy scraping paths
- Add integration-test entrypoints that map directly onto this repo structure
