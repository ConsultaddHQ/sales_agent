# Deployment & Production Architecture Plan — Team Pop Voice Sales Agent

**Date:** 2026-07-02
**Author:** Claude (Opus 4.8), with Gautam Chaurasiya
**Audience:** Senior engineer — architecture & deployment review before first client onboard
**Trigger:** First real Shopify client onboards **Friday 2026-07-03**. Pilot is a **single client, India-based traffic**. Company intends to **standardize on AWS** for multi-client production.

> **How to read this doc:** Section 0 is the decision summary. Sections 1–2 establish current state and the gap. Section 3 is the **Friday pilot plan** (what we actually do this week). Section 4 is the **AWS production target** (what we build toward after the pilot). Section 5 is the **deployment options comparison** — this is the core decision to review. Sections 6–10 cover client onboarding, Cloudflare, DNS, the production work checklist, and costs. Section 11 lists open decisions for you.

---

## 0. Executive Summary & Key Decisions

We have a working alpha (voice-shopping flow works end-to-end) that today runs behind a **single ngrok tunnel** — fine for demos, **not safe for a real client**. Two things force our hand:

1. **The ElevenLabs agent bakes its search webhook URL in at creation time** (`{SEARCH_API_URL}/search`, `onboarding-service/elevenlabs_agent.py:573`). If that URL changes after we onboard the client (as ngrok URLs do on restart), the client's live voice agent silently stops returning products. **We must onboard the client against a stable HTTPS URL.** This is the #1 hard requirement for Friday.
2. **Images are served from local disk** and **CORS is wildcard** — acceptable for a demo, not for a merchant embedding us on their production storefront.

**Recommendation — two tracks:**

- **Track 1 (this week, Friday):** Stand up the three Python services + widget on **one small always-warm cloud host in AWS Mumbai (ap-south-1)** behind **Caddy** (automatic HTTPS) on a **real subdomain**. Keep images on that host's disk for now. This is the *minimum* that is safe for one real client and buys a stable URL. Fastest concrete option: **AWS Lightsail Container or a Lightsail VM running Docker Compose.**
- **Track 2 (after pilot):** Migrate to a proper AWS layout — **ECS Fargate** for the services, **S3 + CloudFront (or Cloudflare R2)** for images/widget, **ElastiCache/Upstash Redis** for caching, and async onboarding. This is essentially the existing `enterprise-blueprint-2026-06-19.md`, re-pointed from Fly.io to AWS.

### Decision table (recommendation = first option; rationale in body)

| Decision | Recommended (pilot) | Production (AWS) | Why / tradeoff |
|---|---|---|---|
| Where services run | Lightsail (Container *or* VM+Docker) in `ap-south-1` | ECS Fargate, `ap-south-1`, ≥1 always-warm task | App Runner is **closed to new AWS customers** (§5). Lightsail is the fastest safe path; Fargate is the standards-track scale path. |
| Public entrypoint / TLS | Caddy (auto Let's Encrypt) on a subdomain | ALB + ACM cert (or Caddy on EC2) | Need stable HTTPS before onboarding (§0.1). Caddy = zero-config TLS in minutes. |
| Stable URL | **`api.teampop.<tld>`** subdomain, DNS A-record → host | Same subdomain → ALB | ngrok rotation breaks baked agent webhooks. Domain is a **Friday blocker** (§8). |
| Images | Local disk on the host (defer) | **Cloudflare R2** (\$0 egress) or S3+CloudFront | R2 wins on cost for image-heavy CDN; S3+CloudFront wins on single-vendor AWS integration (§7). No code change needed either way (URL composed at read time). |
| Widget JS delivery | Served by onboarding-service `/widget` (defer) | R2/S3 + CDN, versioned `widget.{sha}.js` | Fine for one client; CDN + versioning matters at scale. |
| Search-result cache | In-process TTLCache (Refactor A) | Upstash → ElastiCache Serverless (Valkey) | Refactor A already planned; single node needs no Redis. Redis only when >1 search instance. |
| Onboarding execution | Synchronous (current) is OK for 1 client | Async 202 + queue (Celery/SQS) | One onboard/week doesn't need a queue; it's a scale concern. |
| Supabase region | **Verify it's Mumbai/Singapore, not US** | ap-south-1 or ap-southeast-1 | Every search RPC stacks on the voice round-trip; a US-East Supabase adds ~180–260ms per query (§4.4). Potential **Friday issue** — verify now. |
| Client install | Raw `<script>` in `theme.liquid` (we do it via collaborator access) | Theme App Extension (app embed block) | Raw edit is fastest for Friday but **wiped on theme switch**; app extension is the durable productized install (§6). |
| Agent LLM / voice | Claude Haiku 4.5 + Flash TTS + WebSocket (already set) | same | Already the defaults per prior A/B test; ElevenLabs confirms Claude support and WebSocket as the low-latency path. |

### 0.1 The one thing that must be true before Friday

> **A stable, public, HTTPS URL for the search service must exist and be used as `SEARCH_API_URL` when we create the client's agent.** Everything else can be improved after launch; this one cannot be changed without re-onboarding the client. Do not onboard the client against an ngrok URL.

---

## 1. Current Architecture (as-is)

### 1.1 Components

| Component | Runtime | Port | Role | Heavy deps |
|---|---|---|---|---|
| `onboarding-service` | FastAPI/uvicorn | 8005 | Scrape store → embed products → create ElevenLabs agent → generate snippet & test page. Also **proxies** `/search` & `/product-details` to search-service, and **serves the widget** at `/widget`. Hosts the admin/client API. | `sentence-transformers`(→PyTorch), `playwright` (Chromium) |
| `search-service` | FastAPI/uvicorn | 8006 | Hybrid search: embed query → `hybrid_search_products` RPC (RRF vector+FTS) → cross-encoder rerank → return products. Called by ElevenLabs webhook every utterance. | `sentence-transformers`(→PyTorch), cross-encoder reranker |
| `image_server.py` | FastAPI/uvicorn | 8000 | Serve product JPEGs from local disk (`images/{store_id}/…`). | none |
| `www.teampop/frontend` | React/Vite → **IIFE** | build | The `<team-pop-agent>` Shadow-DOM widget. Built to `dist/widget.js`, served by onboarding-service. | — |
| `www.teampop/website` | React/Vite SPA | build | Marketing site + admin dashboard. | — |
| **Supabase** (managed) | external | — | Postgres + pgvector; `products` (vector(384)), `agent_requests`; `hybrid_search_products` RPC. | — |
| **ElevenLabs** (managed) | external | — | One Conversational AI agent per store; server-tool webhooks call our search service; agent LLM = Claude Haiku 4.5; voice via WebSocket + Flash TTS. | — |

### 1.2 How it runs today

- **Single ngrok tunnel** in front of `onboarding-service`; onboarding proxies search to `:8006` on localhost. All public traffic (widget JS, images, search, product-details) flows through the one tunnel (decision `2026-04-08: Single-Tunnel Architecture`, explicitly "temporary for demo/dev").
- No Dockerfiles for the Python services (only `universal-scraper/config/Dockerfile.images` exists). No `fly.toml`/`render.yaml`/CI. Containerization for the two main services is **greenfield**.

### 1.3 Invariants & wiring that constrain deployment (verified in code)

- **Agent webhook URL is baked at creation** — `_get_tool_config()` writes `f"{search_api_url}/search"` and `/product-details` into the agent's tools (`elevenlabs_agent.py:555–602`); `search_api_url` comes from `SEARCH_API_URL` at creation (`:927`). **Changing it later = re-onboard.** → §0.1.
- **Widget snippet bakes `PUBLIC_SEARCH_API_URL` and `WIDGET_SCRIPT_URL`** into `window.__TEAM_POP_API_URL__` and the `<script src>` (`pipeline.py:110–118`). These must be public HTTPS URLs at onboarding time.
- **Image URLs are composed at *read* time** by search-service from `local_image_path` + `IMAGE_SERVER_URL()` (decision `2026-06-12`). → Changing the image host is just an env var, **no re-onboard** needed. This is the one URL we *can* move freely later.
- **Embedding model `all-MiniLM-L6-v2` (384-dim) must match** across onboarding & search (constraint #1). Both load it in-process (~90MB + PyTorch).
- **`hybrid_search_products` RPC is a hard contract** (constraint #2). Current source of truth = `migrations/2026-06-25_search_text_and_fts.sql` (+ `2026-06-26_fuzzy_trigram_search.sql`). These must be applied to the pilot's Supabase, and stores **re-onboarded** to populate enriched `search_text`.
- Widget must stay an **IIFE** (Shadow DOM/CSP); `<team-pop-agent>` tag is the public API.

---

## 2. The Gap: Alpha → Safe for One Real Client

| Gap | Impact on a real client | Blocks Friday? | Fix track |
|---|---|---|---|
| ngrok URL rotates | Live agent's search webhook dies on restart | **YES** | T1: stable subdomain + always-warm host |
| No real HTTPS domain | Mixed-content/embed issues; unstable URLs | **YES** | T1: DNS + Caddy TLS |
| Wildcard CORS (`*`) both services | Any origin can call our APIs | **Should fix** | T1: `ALLOWED_ORIGINS` (Refactor A) |
| No `WEBHOOK_SECRET` on search | Anyone can hit the search webhook | Recommended | T1/T2: Refactor A |
| Images on local disk | Fine on 1 host; breaks multi-instance | No (1 host) | T2: R2/S3 |
| Supabase possibly in US region | +180–260ms per search RPC, stacked on voice | **Verify now** | T1: confirm region (§4.4) |
| Synchronous onboarding (30–120s) | Only *we* run it, once → acceptable | No | T2: async queue |
| No metrics/alerting | Blind if it breaks mid-pilot | Recommended | T1-lite: `/metrics` + uptime check |
| No search caching | 1 client's traffic won't saturate Supabase | No | T2: Refactor A / Redis |
| Snippet wiped on theme change | Widget silently disappears | Mitigate (§6) | T2: theme app extension |

**Reading:** Only four items are genuine Friday blockers: **stable URL, HTTPS/domain, Supabase region check, and (strongly recommended) CORS lockdown**. Everything else is a fast-follow.

---

## 3. Track 1 — Friday Pilot Architecture (Minimum Viable Production)

### 3.1 Target topology

```
Indian shopper's browser (on client's Shopify store)
   │  loads <script> → widget.js  ─────────────┐
   │  widget calls /search,/product-details ───┤ (HTTPS, api.teampop.<tld>)
   ▼                                            ▼
ElevenLabs (voice; routes to Singapore edge) ──► [ api.teampop.<tld> ]  (Caddy :443, auto-TLS)
   server-tool webhook → /search                     │
                                                      ├─ /search, /product-details      → search-service :8006
                                                      ├─ /onboard, /admin, /client, /*  → onboarding-service :8005
                                                      ├─ /widget/*                       → onboarding-service :8005
                                                      └─ /images/*                       → image_server :8000
                                              (all on ONE always-warm host in AWS ap-south-1 / Mumbai)
                                                      │
                                                      ▼
                                            Supabase (verify region = Mumbai/Singapore)
```

- **One host, three containers (or three processes), one Caddy reverse proxy, one subdomain.** Caddy terminates TLS and routes by path — this replaces the ngrok single-tunnel with a stable, real-HTTPS equivalent. (Caddyfile skeleton is in `enterprise-blueprint-2026-06-19.md` §3b — reuse it.)
- **Region: AWS Mumbai (`ap-south-1`).** Indian shoppers reach it in ~30–70ms; the ElevenLabs→search webhook comes in from ElevenLabs' Singapore edge (~62ms to Mumbai). Keeps the search leg fast so it doesn't blow the conversational latency budget.

### 3.2 Concrete host choice for Friday

Two acceptable forms, both AWS-native, both always-warm (no scale-to-zero — cold starts + model load would hurt the voice path):

- **Option T1-a (simplest): AWS Lightsail Container service, "Small" (2 GB, ~\$20/mo).** Push a container image, get managed HTTPS + a URL in minutes. Point our subdomain at it. Good if we containerize quickly.
- **Option T1-b (most control, closest to current mental model): a single Lightsail VM (2 GB) running `docker compose` + Caddy.** One box, all three services + Caddy, one Elastic-IP-equivalent static IP, DNS A-record. ~\$12–20/mo. This is the least-surprising path since our services aren't containerized yet and one box mirrors the current "everything together" setup.

> **Pick T1-b if containerization slips**; it's the fastest way to a stable HTTPS URL with the code exactly as-is (just `pip install` + run under a process manager + Caddy). Pick T1-a if we get clean Dockerfiles done in time (they're needed for Track 2 anyway — see §9).

### 3.3 What we consciously defer past Friday

Local-disk images (1 host, fine), Redis (1 node, fine), async onboarding (we run it once), CDN, multi-region, JWT admin auth, rate limiting. All tracked in §9 as fast-follows.

### 3.4 Friday runbook (ordered)

1. **Confirm Supabase region** (§4.4). If US, decide: accept for pilot, or spin a Mumbai/Singapore project and re-onboard. *(Do this first — it may change plans.)*
2. **Apply migrations** to the pilot Supabase: `2026-06-25_search_text_and_fts.sql`, then `2026-06-26_fuzzy_trigram_search.sql`.
3. **Provision host** in `ap-south-1` (T1-a or T1-b) + **DNS A-record** `api.teampop.<tld>` → host, and **Caddy** for auto-TLS.
4. **Set env vars** so all baked URLs are the public HTTPS subdomain (matrix in Appendix A): `SEARCH_API_URL`, `PUBLIC_SEARCH_API_URL`, `WIDGET_SCRIPT_URL`, `IMAGE_SERVER_URL`, `SEARCH_SERVICE_INTERNAL` (localhost), `ALLOWED_ORIGINS` (= client store domain), plus Supabase/ElevenLabs keys.
5. **Build the widget** (`npm run build`) so `dist/widget.js` is current; confirm it's served at `/widget/widget.js`.
6. **Smoke test** end-to-end on our test page against the live domain (search returns products, images load over HTTPS, voice turn works).
7. **Onboard the client** (`POST /onboard`) — this bakes the *stable* URL into their agent. Verify agent webhook points at `api.teampop.<tld>/search`.
8. **Install on the client store** (§6) — raw `<script>` in `theme.liquid`, ideally via collaborator access we hold.
9. **Verify on their live store** + set a simple uptime check (e.g. cron `curl /health` → alert). Keep the host running (don't restart casually — restarts must preserve the same public URL, which the domain guarantees).

---

## 4. Track 2 — AWS Production Architecture (multi-client target)

This is the existing `enterprise-blueprint-2026-06-19.md` re-pointed from Fly.io to AWS. Same phasing and invariants; different cloud primitives.

### 4.1 Target AWS topology

```
Route 53 (teampop.<tld>)
   ├── api.teampop.<tld>  ─► ALB (ACM TLS) ─► ECS Fargate (ap-south-1)
   │                                            ├─ search-service   (≥2 tasks, always-warm)
   │                                            └─ onboarding-service (1 task)  + worker task (async)
   ├── cdn.teampop.<tld>   ─► CloudFront ─► S3 (product images)      [or Cloudflare R2]
   ├── widget.teampop.<tld>─► CloudFront ─► S3 (widget.{sha}.js)     [or Cloudflare R2]
   └── (Supabase managed Postgres/pgvector in ap-south-1 or ap-southeast-1)
             ElastiCache Serverless (Valkey) — shared search cache + async queue backend
```

### 4.2 Service-by-service AWS mapping

| Piece | AWS choice | Rationale | Tradeoff |
|---|---|---|---|
| search-service | **ECS Fargate**, ≥2 tasks, `min desired=2` | Horizontal scale for the latency-sensitive path; always-warm avoids cold model load (30–90s). | Fargate task start is slow → never scale to zero. ALB adds ~\$16–20/mo. |
| onboarding-service | ECS Fargate, 1 task | CPU/IO heavy but infrequent; scales vertically. | Needs image volume until R2/S3 migration (or write straight to S3). |
| async worker | ECS Fargate task (Celery) or **SQS + worker** | Decouple 30–120s onboard from HTTP. | Adds Redis/SQS; only needed at multi-client volume. |
| images | **S3 + CloudFront** *or* **Cloudflare R2** | See §7 — cost vs single-vendor. Code change is env-var only. | R2 = 2nd vendor; CloudFront = India egress premium. |
| widget JS | S3 + CloudFront, versioned `widget.{sha}.js` | Immutable cache; new deploy = new URL, old sessions keep working. | Requires deploy-pipeline change. |
| cache / queue | **Upstash** (early) → **ElastiCache Serverless (Valkey)** (AWS-native) | Upstash \$0→~\$10/mo, no VPC; ElastiCache when we want everything in-VPC. | MemoryDB is overkill (~\$315+/mo) — skip. |
| DNS/TLS | Route 53 + ACM | AWS-native, integrates with ALB/CloudFront. | Cloudflare DNS also fine (and free) — see §8. |
| CI/CD | GitHub Actions → ECR → ECS | Reproducible deploys; none exists today. | Setup cost (~1 day). |

### 4.3 Scaling path (unchanged from blueprint, AWS terms)

1 warm search task → 2+ tasks behind ALB + shared Redis cache → Supabase read replica if onboarding writes degrade search p95 → dedicated embedding microservice (ONNX/GPU) only past ~5 concurrent onboards or sustained >200 QPS. The blueprint's capacity math (single well-cached node ≈ 100 req/s; ~500 concurrent voice sessions) still holds.

### 4.4 ⚠️ Supabase region — verify this now

Every search utterance = one `hybrid_search_products` RPC, and it stacks on top of the ElevenLabs voice round-trip. If the Supabase project is in **US-East**, that's **~180–260ms per query** from a Mumbai service (blueprint assumed ~500–1000ms India→US including query time). If it's in **Mumbai (`ap-south-1`) or Singapore**, it's tens of ms. **Confirm the pilot project's region before Friday**; if it's US and latency feels bad in the smoke test, the fix is a new regional project + re-embed/re-onboard (the enriched `search_text` re-onboard is already required anyway, so doing it against a regional project is nearly free).

---

## 5. Deployment Options Compared (core decision to review)

All assume: services in **ap-south-1**, one stable subdomain, always-warm (no scale-to-zero for the voice path).

| # | Option | Time to Friday | Ops burden | Scale path | AWS-aligned | Est. \$/mo (pilot) | Cold start |
|---|---|---|---|---|---|---|---|
| **A** | **Single Lightsail VM + Docker Compose + Caddy** | **Lowest** (code as-is) | Low–med (you patch the box) | Vertical only; migrate to C to scale | ✅ (in AWS) | **\$12–20** | none |
| **B** | **AWS Lightsail Containers** | Low (needs Dockerfiles) | Low (managed TLS/host) | Limited; migrate to C | ✅ | **~\$20** | none |
| **C** | **AWS ECS Fargate + ALB** | Med–high (Dockerfiles + task defs + ALB + IAM) | Med (managed runtime) | ✅ Best (horizontal, multi-AZ) | ✅✅ | ~\$40–70 | task start slow → keep warm |
| **D** | **Fly.io (blueprint's original)** | Low | Low | ✅ Good (Singapore region, replicas) | ❌ (not AWS) | ~\$10–25 | configurable warm |
| — | AWS App Runner | — | — | — | ✅ | — | **Closed to new customers (May 2026) — not available** |

### Recommendation

- **For Friday: Option A (Lightsail VM + Docker Compose + Caddy) in `ap-south-1`.** It gets us a stable HTTPS URL with the *least* new moving parts, runs the code essentially unchanged, is inside AWS (so it aligns with the company direction and the eventual bill), has no cold-start risk, and costs ~\$15/mo. Option B is equally fine if Dockerfiles are ready — and those Dockerfiles are needed for Track 2 regardless, so doing them now (→ B) is not wasted effort.
- **For production: Option C (ECS Fargate + ALB), same region.** It's the AWS standards-track path App Runner customers are being migrated to, gives real horizontal scale and multi-AZ, and matches the blueprint's phased plan. Migrating A/B → C is a re-host, not a re-architecture (same containers, same env vars, same baked URL if we keep the domain).
- **Fly.io (D)** is genuinely the lowest-latency-per-effort option (native Singapore region, trivial warm replicas) and is what the blueprint assumed — **but it contradicts the AWS standardization goal.** Worth flagging to you explicitly: if AWS-alignment is a hard company constraint, we forgo Fly.io's ergonomics; if it's a soft preference, Fly.io for the search-service is defensible. **This is a decision for you (§11).**

**Key gotcha for the reviewer:** the blueprint (2026-06-19) recommends Fly.io and implicitly assumes a managed-container PaaS. On AWS, the natural equivalent — **App Runner — is now closed to new customers**, so the AWS path is Lightsail (simple) or Fargate (scale), not App Runner. Don't let an older doc send us down the App Runner road.

---

## 6. Client Onboarding — What We Do vs What the Client Does

### 6.1 The flow (current, scrape + snippet)

1. **We** run `POST /onboard` with the client's storefront URL → system scrapes ≤200 products, embeds them, stores in Supabase, **creates the ElevenLabs agent (baking our stable search URL)**, and returns a widget snippet + test page.
2. **We** verify on the generated test page.
3. **The widget snippet** goes onto the client's Shopify store.

### 6.2 Installing on the client's store — three options (fastest first)

- **Option 1 — We install via collaborator access (recommended for Friday).** Client grants us **collaborator access with the "Themes" permission** (Partner Dashboard → request access → client approves with a 4-digit code). We add the `<script>` to `layout/theme.liquid` (before `</body>`), Save. Client does almost nothing; we control correctness. Collaborator accounts don't count against staff limits.
- **Option 2 — Client pastes the snippet themselves.** We email them the snippet + steps: *Shopify Admin → Online Store → Themes → ⋯ → Edit code → `layout/theme.liquid` → paste before `</body>` → Save.* Works on all Online Store 2.0 themes. Zero access needed, but relies on a non-technical merchant.
- **Option 3 — Theme App Extension / app embed block (later, productized).** A merchant-toggle in the theme customizer that **survives theme edits** and is the Shopify-preferred model. This is the durable answer and the path to the Shopify App Store. Build it **after** the first client (as you noted).

> **⚠️ Snippet-wipe risk (must tell the client):** A manual `theme.liquid` edit lives in **one theme version**. If the merchant **switches themes** or a theme update replaces the file, the widget silently disappears. Mitigations: (a) hold collaborator access so we can re-apply, (b) tell the merchant to ping us before changing themes, (c) prioritize the theme app extension (Option 3) so this stops being a risk. **Do not** build on Shopify's legacy **ScriptTag API** — it is being sunset (non-Plus final cutoff **Aug 26 2026**).

### 6.3 What we need from the client (collect before Friday)

- Storefront URL (and confirmation the store is **not password-protected** and has products).
- Preferred install method (§6.2) — and if Option 1, a scheduled 10-min window to grant collaborator access.
- The exact storefront domain(s) → we set `ALLOWED_ORIGINS` to lock CORS to their store.
- Confirmation of catalog size (we cap at 200 products by default; note if larger).
- A point of contact to notify before any theme change.

---

## 7. Cloudflare — What It Is and Why (you asked)

Cloudflare is a CDN/edge platform. Three pieces are relevant to us; **all can coexist with an AWS backend** (they're not either/or with AWS for compute):

- **R2 (object storage, S3-compatible):** stores product images + widget JS. **Its headline benefit is \$0 egress** — you pay storage (\$0.015/GB-mo) + cheap read ops, but *nothing* for bandwidth to users. For an image-heavy widget served to many shoppers, egress is the dominant cost, so R2 can be dramatically cheaper than S3+CloudFront (where India egress is ~\$0.109/GB). R2 speaks the S3 API, so our `boto3` upload code and read-time URL composition need only an endpoint/URL change.
- **CDN + PoPs in India:** Cloudflare has edge PoPs in Mumbai, Chennai, Delhi, Hyderabad, Bengaluru, Kolkata — so images/widget load fast for Indian shoppers. (CloudFront has comparable India coverage; **latency is not a differentiator** between them — cost and vendor-integration are.)
- **DNS (free, fast) and Workers (edge functions):** Cloudflare can host our DNS zone for free with a good UI (§8). Workers could later inject the `WEBHOOK_SECRET` at the edge, but that's optional.

**Bottom line for us:** Cloudflare is worth using **specifically for R2 (images/widget) to save egress**, even if compute stays on AWS. The counter-argument — and the reason a pure-AWS shop might skip it — is **single-vendor simplicity**: S3+CloudFront gives one bill, native IAM, Origin Access Control, CloudWatch/WAF/Shield, one CloudTrail for compliance, and free S3→CloudFront origin transfer. **Recommendation:** for the **pilot, ignore Cloudflare entirely** (images stay on the host). For **production**, choose R2 if egress cost dominates and a second vendor is acceptable; choose S3+CloudFront if AWS-native integration/compliance outweighs egress cost. It's a clean, reversible env-var-level decision.

---

## 8. Domain & DNS Recommendation

### Why it's a Friday blocker

The agent's search webhook URL and the widget's script/API URLs are **baked at onboarding**. If we onboard against an ngrok/`*.lightsail`/`*.fly.dev` URL and later move, we must re-onboard. A **domain we own decouples the public URL from the host** — we can re-point DNS to a new host in Track 2 without touching the client's agent or store. So: **secure a real subdomain before we create the client's agent.**

### What to do

- **Use a subdomain of a domain you already control** (you mentioned `teampop` — confirm the exact registered domain and who holds the registrar login).
- Create these records:
  - `api.teampop.<tld>` → A-record to the pilot host's static IP (this is the one baked into the agent/widget — **must be stable**).
  - Later: `cdn.` and `widget.` → CloudFront/R2 (Track 2 only).
- **TLS:** Caddy fetches/renews Let's Encrypt certs automatically once DNS resolves — no manual cert work.
- **Who runs DNS:** Either **Route 53** (AWS-native, integrates with ALB/CloudFront/ACM later) or **Cloudflare DNS** (free, fast, nice UI). Both are fine. **Recommendation:** if the domain's registrar/DNS is easy to access, point one subdomain now wherever it lives; if you want to standardize, move the zone to **Route 53** to match the AWS direction. The *critical* action is simply: **get edit access to DNS for the `teampop` domain this week** — that's the dependency, not the choice of provider.

> **If DNS access can't be secured in time:** fallback is a **reserved/static ngrok domain** or a Lightsail static IP with a stable provider hostname — anything that **won't change**. This is strictly a stopgap; a real subdomain is better and cheap. The absolute rule remains: onboard only against a URL that will not change.

---

## 9. Production Work Checklist (prioritized)

Mapped to existing `docs/agents/roadmap.md` and `enterprise-blueprint-2026-06-19.md` items where they exist.

### P0 — before/at Friday (pilot blockers)
- [ ] Confirm Supabase region; decide accept-or-migrate (§4.4).
- [ ] Apply `2026-06-25_search_text_and_fts.sql` + `2026-06-26_fuzzy_trigram_search.sql`; re-onboard.
- [ ] Provision `ap-south-1` host (Option A/B) + static IP.
- [ ] Get DNS edit access; create `api.teampop.<tld>` A-record.
- [ ] Caddy reverse proxy + auto-TLS (Caddyfile from blueprint §3b).
- [ ] Set all baked URLs to the HTTPS subdomain (Appendix A).
- [ ] Lock CORS: `ALLOWED_ORIGINS` = client store domain (roadmap: "CORS restriction", Refactor A).
- [ ] Basic uptime check + `/health` monitoring.
- [ ] End-to-end smoke test on live domain, then onboard + install + verify.

### P1 — fast-follow (first weeks, before 2nd client)
- [ ] **Refactor A** (search-service): TTLCache, `/metrics`, structured logs, `WEBHOOK_SECRET`, request-ID (roadmap: Ready, ~1hr).
- [ ] **Refactor B** (onboarding): parallel image downloads + batch embed + ElevenLabs retry (roadmap: Ready, ~1–2hr).
- [ ] Clean **Dockerfiles** for both Python services (needed for ECS).
- [ ] `send_delivery_email` fire-and-forget (H3); admin list `LIMIT` (H5); `agent_requests.agent_id` index (H4).
- [ ] Rate limiting on `/onboard` and `/submit-request`.

### P2 — production scale (Track 2)
- [ ] ECS Fargate + ALB + ECR + GitHub Actions CI/CD.
- [ ] Images → R2 or S3+CloudFront (§7); widget → versioned CDN.
- [ ] Redis (Upstash → ElastiCache Serverless) once >1 search instance.
- [ ] Async onboarding (202 + queue), Flower/monitoring.
- [ ] JWT admin auth; RLS review; OpenTelemetry + Grafana/CloudWatch dashboards.
- [ ] Theme App Extension for durable, App-Store-ready install (§6.2 Option 3).

---

## 10. Cost Estimates (indicative; verify ap-south-1 in AWS Pricing Calculator)

| | Pilot (Track 1) | Early production (Track 2, 1–5 clients) |
|---|---|---|
| Compute | Lightsail VM/Container ~\$15–20/mo | ECS Fargate 2–3 tasks + ALB ~\$60–90/mo |
| Supabase | existing (Free/Pro) | Pro ~\$25/mo + usage |
| Images/widget | on host (\$0 extra) | R2 ~\$1–5/mo *or* S3+CloudFront (egress-dependent) |
| Redis | none | Upstash \$0–10/mo |
| ElevenLabs | plan/usage (voice minutes) | scales with usage |
| DNS/TLS | ~free (Caddy) + domain | Route 53 ~\$0.50/zone + queries |
| **Rough total (excl. ElevenLabs/Supabase usage)** | **~\$15–25/mo** | **~\$90–140/mo** |

ElevenLabs conversation minutes will likely be the largest variable cost at scale — track it separately.

---

## 11. Open Decisions for the Senior

1. **AWS-only, or is Fly.io acceptable for the search-service?** Fly.io is the lowest-effort low-latency path (native Singapore, easy warm replicas) but not AWS. If AWS is a hard constraint, we go Lightsail→Fargate; the recommendation above assumes AWS.
2. **Friday host form: Lightsail VM+Compose (A) or Lightsail Containers (B)?** A is fastest with code as-is; B needs Dockerfiles (which we need anyway). Preference?
3. **Supabase region** — accept current region for the pilot, or migrate to `ap-south-1`/Singapore now (cheap to do alongside the required re-onboard)?
4. **Production CDN/storage: Cloudflare R2 (cheapest egress) vs S3+CloudFront (single-vendor AWS)?** Reversible, env-var-level — but pick a default.
5. **DNS provider: Route 53 vs Cloudflare** — and, more urgently, **who can grant DNS edit access to the `teampop` domain this week?**
6. **Client install method for Friday: collaborator access (we install) vs send-snippet (they install)?** Affects what we ask the client to do before Friday.

---

## Appendix A — Env Var Matrix (pilot, HTTPS subdomain)

| Var | Service | Pilot value |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_KEY` | all | from Supabase project (verify region) |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | onboarding | prod keys |
| `ELEVENLABS_LLM_MODEL` | onboarding | `claude-haiku-4-5` (default) |
| `ELEVENLABS_TTS_MODEL` | onboarding | Flash model (`eleven_flash_v2_5` recommended) |
| `SEARCH_API_URL` | onboarding | `https://api.teampop.<tld>` ← **baked into agent** |
| `PUBLIC_SEARCH_API_URL` | onboarding | `https://api.teampop.<tld>` ← baked into widget |
| `WIDGET_SCRIPT_URL` | onboarding | `https://api.teampop.<tld>/widget/widget.js` |
| `SEARCH_SERVICE_INTERNAL` | onboarding | `http://localhost:8006` (behind Caddy) |
| `IMAGE_SERVER_URL` | search | `https://api.teampop.<tld>` (composed at read time — movable later) |
| `ALLOWED_ORIGINS` | both | client's Shopify store domain(s) |
| `STORE_IMAGES_PATH` | onboarding/image | host volume path |
| `RELOAD` | search | `false` (prod), with `UVICORN_WORKERS` |

## Appendix B — Migrations to apply on the pilot Supabase
1. `migrations/2026-06-25_search_text_and_fts.sql` (enriched `search_text` + RRF `hybrid_search_products` + GIN index; **source of truth** for the RPC).
2. `migrations/2026-06-26_fuzzy_trigram_search.sql` (fuzzy/trigram).
3. Ensure `agent_requests` table exists (per roadmap manual step #1).
4. **Re-onboard** stores after migration to populate enriched `search_text` + embeddings.

## Appendix C — Primary sources (verified 2026-07-02)
- ElevenLabs tool timeout (default 30s / max 300s since 2026-05-04) & Claude support: elevenlabs.io/docs (API reference, changelog, webhook-tools, LLM list).
- ElevenLabs latency (India→Singapore edge, S. Asia TTFB 150–200ms, WebSocket + Flash): elevenlabs.io/docs latency-optimization; cloudping.co.
- AWS App Runner closed to new customers: docs.aws.amazon.com/apprunner apprunner-availability-change.
- AWS pricing (Fargate/EC2/Lightsail; Mumbai ≈ us-east-1 +10–15%, verify in calculator): aws.amazon.com pricing pages.
- Cloudflare R2 \$0 egress vs CloudFront India ~\$0.109/GB: developers.cloudflare.com/r2/pricing, aws.amazon.com/cloudfront/pricing.
- Redis: upstash.com/pricing/redis, aws.amazon.com/elasticache/pricing, memorydb/pricing.
- Shopify theme `<script>` install, collaborator access, ScriptTag sunset (non-Plus 2026-08-26): help.shopify.com edit-theme-code, shopify.dev collaborator-accounts & blocking-script-tags.
- India network latency (broadband ~40ms, mobile ~69ms, Q1 2026): SpeedGeo/Opensignal.
