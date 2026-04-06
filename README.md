# sales-voice-agent

This repository implements the Team‑Pop voice‑first AI agent platform and supporting microservices. The project is a proof‑of‑concept / early‑alpha product enabling merchants to add an interactive conversational assistant to their storefronts. Components work together to crawl a target store, index product data, and surface voice‑enabled search and chat through a floating "Avatar Widget".

> **Status:** early‑alpha / lab prototype. Components work end‑to‑end for internal
demonstrations; expect breaking changes and frequent refactors.

## Repository layout

```
sales-voice-agent/
├── onboarding-service/      # Python FastAPI crawler & embedder
├── search-service/          # Python FastAPI semantic search API
└── www.teampop/             # front‑end applications
    ├── frontend/            # Embeddable Avatar Widget
    └── website/             # Marketing website
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

## Contributing

Add new features as separate microservices or components. Follow the existing
folder organization and update this README when adding a new top‑level folder.

## License

MIT.
