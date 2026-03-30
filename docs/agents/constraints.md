# Agent Constraints — Hard Rules

> These rules must **never** be violated by any agent, in any context, unless a human engineer explicitly overrides in writing with a reason.
> Do not infer permission. If in doubt, ask.

---

## SYSTEM INTEGRITY

### 1. Never change the embedding model without a full migration plan
The entire vector search pipeline depends on `all-MiniLM-L6-v2` (384 dimensions) being used in **both** `onboarding-service` and `search-service`. Changing the model in one service without the other will silently return wrong search results — there are no errors, just bad outputs.

**If you must change:** Create a Linear ticket, migrate the `products.embedding` column to the new dimension, re-embed all existing products, and deploy both services atomically.

### 2. Never remove or modify `hybrid_search_products` RPC without a migration
This Supabase RPC function is the core of the search pipeline. The search service calls it on every query. Changing its signature requires updating `search-service/main.py` and re-deploying in sync.

### 3. Never commit `.env` files or secrets
API keys (`SUPABASE_KEY`, `ELEVENLABS_API_KEY`, `OPENROUTER_API_KEY`) must never be committed to git. Use `.env.example` files with placeholder values only.

---

## WIDGET (Shadow DOM)

### 4. Never use `@import` inside widget CSS
Shadow DOM does not support `@import` rules. They silently fail. Load external fonts via a `<link>` element appended to the shadow root in `src/main.jsx`.

### 5. Never break the `<team-pop-agent>` custom element interface
The custom element name and its attributes are the public API for merchant integrations. Renaming or removing attributes is a breaking change that requires a version bump and migration guide.

### 6. Never call `product_desc_of_main_view` from React code manually
This ElevenLabs tool is invoked automatically via `useEffect` when the carousel scrolls. Manual calls will create duplicate narration and confuse the agent state machine. See `AvatarWidget.jsx` for the warning comment.

---

## DATABASE

### 7. Never use `truncate` or `delete from products` without a store_id filter
The `products` table is shared across all stores via `store_id`. A bare `DELETE FROM products` or `TRUNCATE products` would wipe all stores' data. Always scope destructive queries to a specific `store_id`.

### 8. Never store Supabase service-role key client-side
The `SUPABASE_KEY` (service-role) bypasses row-level security. It must only be used in backend services (`onboarding-service`, `search-service`). Frontend code must use the anon key with RLS policies.

---

## SCRAPER

### 9. Never store scraped content permanently outside Supabase
Scraped product data must be stored in the Supabase `products` table. Do not write scraped data to local files that persist beyond a single session (except `demo_pages/` and `images/` which are gitignored and ephemeral).

---

## CODE QUALITY

### 10. Never widen CORS beyond what is needed
All services currently set `allow_origins=["*"]`. This is acceptable for local development only. Before any production deployment, CORS must be restricted to the specific widget domains. Do not add new services with wildcard CORS intended for production.

### 11. Never skip error codes for user-facing onboarding errors
All errors that surface to the dashboard UI must go through `error_codes.py` using `get_error_response()`. Raw Python exception messages must never be returned in API responses.

### 12. Never add a new top-level service without a README
Every service directory must have a `README.md` describing purpose, setup, endpoints, and env vars. Check `onboarding-service/README.md` as a template.

---

## PROCESS

### 13. Never merge to `main` without a Linear ticket reference
All commits and PRs must reference a `HPF-XXX` Linear ticket. Use `Closes HPF-XXX` in PR descriptions. This is required for traceability across agents and engineers.

### 14. Never make breaking changes to the onboarding API without updating the dashboard
`POST /onboard` is called directly by the dashboard. Changing its request/response schema without updating `www.teampop/dashboard/src/pages/Onboarding.jsx` will silently break the UI.
