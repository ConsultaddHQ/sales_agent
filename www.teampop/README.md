# Team Pop Voice Agent

Monorepo for the Team Pop voice‑first AI assistant. It ties together several
independent services and front‑end applications to deliver a conversational
agent that can be embedded on an e‑commerce website.

> **Current status:** internal prototype / alpha. The code is actively being
developed and may change. Use at your own risk.

## Components

- `onboarding-service/` – FastAPI crawler & embedder.
- `search-service/` – FastAPI semantic search API.
- `www.teampop/dashboard/` – React dashboard used by merchants.
- `www.teampop/frontend/` – Embeddable Avatar Widget (React + ElevenLabs).

Each component has its own README with detailed setup instructions.

## How it works

1. Merchant opens the dashboard and submits their store URL.
2. Dashboard calls `onboarding-service` which ingests the storefront,
   extracts products, embeds descriptions, and stores them in Supabase.
3. The `frontend` widget (embedded on the merchant site) queries
   `search-service` for relevant products during an ElevenLabs voice session.
4. `search-service` returns product cards and an LLM‑generated pitch.

The backend services are simple FastAPI processes; there is currently no
central monolithic server.

## Getting started

Refer to individual README files for each subdirectory. In general:

1. Install Python 3.10+ and Node 18+.
2. Create and activate a virtual environment in each Python service.
3. Copy `.env.example` to `.env` and populate with keys (Supabase, OpenRouter,
   ElevenLabs, etc.).
4. Run the services on distinct ports (8005 for onboarding,
   8006 for search) and front‑ends via `npm run dev`.

## Best practices & tips

- Treat this repo as a developer playground.
- Use `pip freeze` to capture dependencies when continuing work.
- Use environment variables and avoid hard‑coding secrets.
- If adding a new service, update this README with its purpose.
- Consider containerization (Docker) for deployment.

## License

MIT.

## Additional files

- `index.html` – Demo landing page.
- `test_widget.html` – Test page for the widget.
- `demo_click_pattern.md` – Documentation for demo interactions.
