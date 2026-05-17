# Pop Sales Agent — Live Test Runbook (Team Pop website)

Goal: talk to the sales agent on the Team Pop website end-to-end. No
retarget needed — the program already targets Team Pop.

> You run every step here (it needs your keys/Supabase/ngrok/browser). The
> tooling makes it turnkey; ping me with any failing step's output.

## 0. Prereqs (one-time)

- Supabase project (URL + **service-role** key)
- ElevenLabs API key
- OpenRouter API key (or OpenAI) for the sales brain
- ngrok installed and authed

## 1. Apply the database migrations

Supabase → SQL editor → run, in order:
1. `migrations/0001_sales_agent.sql`
2. `migrations/0002_sales_proof_seed.sql`

(Idempotent — safe to re-run. Then tick them in `migrations/README.md`.)

## 2. Configure env

`onboarding-service/.env` (from `.env.example`): `SUPABASE_URL`,
`SUPABASE_KEY`, `ELEVENLABS_API_KEY`, `OPENROUTER_API_KEY`. Leave
`SEARCH_API_URL` for now (set in step 5).

`www.teampop/website/.env` (from `.env.example`): `VITE_API_URL`,
`VITE_CALENDLY_URL`. Leave `VITE_SALES_AGENT_ID` for step 7.

## 3. Build the widget IIFE

```bash
cd www.teampop/frontend && npm install && npm run build   # → dist/widget.js
```
(onboarding-service serves it at `/widget/widget.js`. Never the Vite dev
build — project invariant.)

## 4. Start services

```bash
./start_services.sh        # onboarding-service :8005, search-service, images
```

## 5. Tunnel + point the brain URL at it

```bash
ngrok http 8005
```
Copy the `https://….ngrok-free.app` URL. Set it in `onboarding-service/.env`:
```
SEARCH_API_URL=https://….ngrok-free.app
```
> ⚠️ **Order matters.** The brain URL is baked into the ElevenLabs agent at
> creation time (same as store onboarding). If ngrok restarts → new URL →
> re-run step 6. Restart onboarding-service so it picks up the new env.

## 6. Preflight, then provision

```bash
cd onboarding-service && source .venv/bin/activate
python preflight_sales.py          # must print READY (exit 0)
python provision_sales_agent.py    # creates the agent, prints the env line
```
`preflight_sales.py` blocks (exit 1) on any ❌. Fix those first
(troubleshooting below). `provision_sales_agent.py` prints:
```
VITE_SALES_AGENT_ID=agent_xxx
```

## 7. Wire the agent id into the site + run it

Put that line in `www.teampop/website/.env`, then:
```bash
cd www.teampop/website && npm run build && npm run preview   # or: npm run dev
```
Open the site, click the orb, allow the mic, and talk to it.

## 8. Verify the one load-bearing assumption

On your **first turn**, watch the onboarding-service logs for:
```
➡️  /sales/brain site=teampop conv=…  msg='…'
```
- `conv=` shows a real id → ✅ cross-turn memory + lead↔transcript work.
- `conv=` is empty / `{{system__conversation_id}}` / you see
  `conversation_id unresolved — session not persisted` → the ElevenLabs
  system-variable substitution didn't happen (DESIGN §8 Q2). The agent
  still works per-turn, but flag it — we'll switch to a widget-generated
  session id passed through the host bridge.

## CORS / production note

Services use `allow_origins=["*"]` — fine for this test. Before real
external traffic, restrict CORS (constraint #10, already on the roadmap).

## Troubleshooting

| Symptom | Cause → Fix |
|---|---|
| preflight ❌ `table sales_sessions missing` | migration 0001 not applied → step 1 |
| preflight ⚠️ `proof content empty` | 0002 not applied → step 1 (or add proof in `/admin`) |
| preflight ❌ `brain_url … is local` | `SEARCH_API_URL` still localhost → set the ngrok https URL (step 5) |
| preflight ⚠️ `widget build missing` | `npm run build` in `www.teampop/frontend` (step 3) |
| provision: `Provisioning failed: … 400` | bad/truncated brain URL or ELEVENLABS key → check step 5 / key |
| Agent talks but forgets context | `conversation_id` unresolved → step 8 |
| Widget doesn't appear | `VITE_SALES_AGENT_ID` unset, or site loaded the Vite dev widget not `/widget/widget.js` |
| Agent talks but no products/proof | onboarding-service not reachable at the ngrok URL, or search-service down |
| ngrok restarted, agent broke | new tunnel URL → redo steps 5–7 |
