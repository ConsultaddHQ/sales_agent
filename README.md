# sales-voice-agent

This repository implements the Team‑Pop voice‑first AI agent platform and supporting microservices. The project is a proof‑of‑concept / early‑alpha product enabling merchants to add an interactive conversational assistant to their storefronts. Components work together to crawl a target store, index product data, and surface voice‑enabled search and chat through a floating "Avatar Widget".

> **Status:** early‑alpha / lab prototype. Components work end‑to‑end for internal
demonstrations; expect breaking changes and frequent refactors.

## Knowledge Transfer Docs

For the human-facing architecture and KT handbook, start at `docs/knowledge-base/README.md`.

Use that folder to understand the current system, repo layout, core flows, risks, and roadmap without relying on chat history.

## Repository layout

```
sales-voice-agent/
├── shared/                  # Shared Python library (config, db, embeddings, parsing)
├── onboarding-service/      # Python FastAPI onboarding pipeline
│   ├── adapters/            # Plug-and-play store adapters (shopify, threadless, supermicro, universal)
│   ├── scraping/            # Universal extractors (JSON-LD, microdata, OG, sitemap, platform CSS, LLM)
│   ├── routes/              # API endpoints (onboard, admin, client)
│   └── services/            # Business logic (products, test pages, agent creation)
├── search-service/          # Python FastAPI semantic search API
└── www.teampop/             # front-end applications
    ├── frontend/            # Embeddable Avatar Widget
    └── website/             # Marketing website + admin dashboard
```

### How the system works

1. A merchant submits their store URL to the **onboarding-service** API.
2. Onboarding-service crawls the site,
   extracts product data, and embeds text with `all-MiniLM-L6-v2` before
   saving into Supabase.
3. Later, the **frontend widget** uses **search-service** to perform hybrid
   semantic/full‑text queries against the Supabase data, and renders results to
the user during an ElevenLabs-powered voice interaction.

## Getting started

Each component lives in its own virtual environment (Python) or Node project.
You can run them in parallel during development.

### Prerequisites

- Python 3.10+
- Node 18+
- Supabase project with a `products` table and the `hybrid_search_products` RPC
  defined (see `search-service/main.py` comments).
- ElevenLabs API key (for the voice widget).
- API keys: SUPABASE_URL, SUPABASE_KEY, OPENROUTER_API_KEY / other LLM keys.

### Running locally

```bash
# backend services
cd onboarding-service && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8005 &        # onboard service

cd ../search-service && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8006 &        # search service

# widget
cd ../www.teampop/frontend && npm install && npm run dev &
```

Adjust ports as needed; environment variables are managed via `.env` files in each
service.

## Best practices

- Keep service‑role keys (Supabase) private.
- Use separate virtual environments per Python service.
- Use `pip install --upgrade pip` periodically and lock dependencies with
  `pip freeze > requirements.txt` when shipping.

## Current State (June 2026)

The core voice-shopping flow is working end-to-end. Recent stabilisation work includes:

| Area | Fix / Change |
|------|-------------|
| **Voice widget UX** | Inactive state is a small draggable Siri-inspired orb; chat/products panel is a stable phone-sized panel anchored right on desktop, full-height on mobile |
| **Inactivity detection** | 30s smart timer: pauses while agent is speaking, ignores phantom VAD transcripts (`okay`, `hmm`), then ends the session after true user silence |
| **Search service** | PyTorch CPU thread limits (`OMP_NUM_THREADS=1`, `torch.set_num_threads(1)`) + `asyncio.Semaphore(2)` gate prevent embedding thread-pool hangs under concurrent load |
| **Carousel timing** | `update_products` and `update_carousel_main_view` client tools now use `expects_response: True` — carousel renders before agent speaks, eliminating the 1-3s visual lag |
| **Carousel focus** | `get_product_details → update_carousel_main_view` chain enforced at three levels (tool description + `## Tools` + `# Guardrails`) across all 5 model prompts — carousel always focuses on the product being described |
| **Carousel interaction** | Clicking a thumbnail is visual-only (no agent narration). `syncMainProduct()` is kept in `AvatarWidget.jsx` and can be re-enabled in one line |
| **Agent model** | Default LLM: `claude-haiku-4-5` (winner of 6-model A/B test; 100% tool reliability, median 3.4s User→Products) |

> See `docs/agents/completions.md` for detailed implementation notes and `docs/agents/decisions.md` for architectural rationale.

---

## Contributing

Add new features as separate microservices or components. Follow the existing
folder organization and update this README when adding a new top‑level folder.
If you change architecture or major flows, also update the relevant summary in
`docs/knowledge-base/` and the underlying source doc in `docs/agents/`.

## License

MIT.
