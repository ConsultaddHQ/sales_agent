# Observability Runbook — Latency, Errors & RCA

> Phase 0 of the 2026-09-29 pilot plan (see `docs/agents/roadmap.md`).
> Goal: for any shopper complaint, paste one `conversation_id` and see the whole call.

## Live setup (deployed 2026-09-30)

- Box runs branch `perf/phase0-observability`. **Rollback:** `git checkout release/xfused-pilot` (was `3f411ce`), restore `~/backups/pre-phase0-*/{onboarding,search}.env` + `widget.js`, `sudo systemctl restart tp-search tp-onboard`.
- **Post-call webhook:** workspace webhook "TeamPop Wrina (Xfused) post-call" (`1e82aa83da704fd7a058f000bacc40b6`), attached **only to the Wrina agent** via `platform_settings.workspace_overrides.webhooks`. The ElevenLabs workspace is **shared with other products (Loro)**. Never change the workspace-level post-call webhook.
- **Traces:** the box's `ELEVENLABS_API_KEY` can't read conversations (401), so `ELEVENLABS_OTEL_API_KEY` holds a key that can.
- **Loki:** the push URL must end in `/loki/api/v1/push`. The token needs `logs:write`. The originally supplied Loki token lacked that scope, so Alloy currently uses the OTLP token, which has it. Alloy uses about 200 MB of RAM.
- **Grafana Postgres:** user `grafana_ro.jchigqerypjwmszslzke`, host `aws-1-ap-south-1.pooler.supabase.com:5432`, db `postgres`, SSL `require`. The password is `GRAFANA_PG_RO_PASSWORD` in the local `onboarding-service/.env`.
- **Demo page** `api.teampop.com/demo/test_9cec7cd0.html` loads the old agent `agent_8601…`, not Wrina v2 (`agent_4901…`). Test Wrina on the real storefront or theme preview.

## How it fits together

| Signal | Source | Lands in |
|---|---|---|
| Per-turn LLM TTFB, tool latency, tool errors, interruptions, eval + data-collection results | ElevenLabs post-call webhook → `POST /webhooks/elevenlabs` | Supabase `conversations`, `conversation_turns` |
| Full call trace (spans per turn/tool) | ElevenLabs `GET /conversations/{id}?format=opentelemetry` | Grafana Cloud **Tempo** |
| Search timing by stage (queue / embedding / RPC / rerank), cache hit | search-service | Supabase `search_latency` + JSON logs → **Loki** |
| What the shopper felt: user→first AI, →products, click→greeting, image paint, network RTT, context tokens | widget | Supabase `turn_latency` |
| Errors: widget crashes, ElevenLabs errors, tool errors, cart failures; backend exceptions | Sentry SDKs | **Sentry** |
| CPU / RAM / swap of the Lightsail box | `system.stats` log line every 60s | **Loki** |

**The join key is `conversation_id`** (ElevenLabs'). The webhook tools send it
automatically (`system__conversation_id` dynamic variable), the widget tags
Sentry with it, and the Shopify cart carries it as the `TeamPop Conversation`
order attribute.

## Where to put credentials

Never paste secrets into chat or commit them. All `.env` files are gitignored.

| Credential | File (on the Lightsail box; also local if you run locally) | Variable |
|---|---|---|
| Sentry DSN — backend project | `search-service/.env` **and** `onboarding-service/.env` | `SENTRY_DSN` |
| Sentry DSN — widget project (can be the same project) | `www.teampop/frontend/.env` (where you run `npm run build`) | `VITE_SENTRY_DSN` |
| ElevenLabs post-call webhook secret | `onboarding-service/.env` | `ELEVENLABS_WEBHOOK_SECRET` |
| Grafana OTLP endpoint / instance ID / token (traces:write) | `onboarding-service/.env` | `GRAFANA_OTLP_ENDPOINT`, `GRAFANA_OTLP_INSTANCE_ID`, `GRAFANA_OTLP_TOKEN` |
| Grafana Loki push URL / user / token (logs:write) | `/etc/default/alloy` on the box | `GRAFANA_LOKI_URL`, `GRAFANA_LOKI_USER`, `GRAFANA_LOKI_TOKEN` |
| Supabase read-only DB password for Grafana | Grafana UI → Connections → PostgreSQL data source | — |

**Sentry's GitHub integration is not needed.** It only adds commit/suspect-PR
linking. Error capture works with just the DSN. Create a Sentry project of type
*Python/FastAPI* (backend) and optionally *Browser JavaScript* (widget), then copy
each DSN from Project → Settings → Client Keys.

## Setup, in order

1. **Database.** In the Supabase SQL editor run `create_latency_tracking_table.sql` if it hasn't been run yet, then
   `create_observability_tables.sql`. For the 30-day retention job, enable the `pg_cron`
   extension first (Database → Extensions), then re-run the file.
2. **Backend deploy.** On the box: `git pull`, then `pip install -r requirements.txt` in
   both service venvs (adds `sentry-sdk`, `psutil`). Fill the env vars from the table above
   and run `sudo systemctl restart tp-search tp-onboard`.
   - Check: `curl https://api.teampop.com/health` returns an `x-request-id` header.
   - Check: `curl localhost:8006/health?deep=1` shows `embedder_loaded`, `reranker_loaded` and `supabase` all `true`.
3. **ElevenLabs post-call webhook.** In ElevenLabs → ElevenAgents → Settings → Post-call webhook:
   - Add URL `https://api.teampop.com/webhooks/elevenlabs`, transcript format **JSON**, audio **off**.
   - Put the secret it shows into `ELEVENLABS_WEBHOOK_SECRET` and restart `tp-onboard`.
   - Set conversation retention to **30 days** (agreed 2026-09-29). This is in the agent's privacy/retention settings; I haven't confirmed which dashboard tab it's on.
4. **Live agent tools.** Add `conversation_id` to the existing agent's webhook tools. This touches nothing else on the agent:
   ```bash
   python3 testing/monitoring/add_conversation_id_to_tools.py --agent-id agent_4901kwna71tve5nbyy85c8v20yre
   python3 testing/monitoring/add_conversation_id_to_tools.py --agent-id agent_4901kwna71tve5nbyy85c8v20yre --apply
   ```
5. **Widget.**
   - Build: in `www.teampop/frontend` run `cp .env.example .env`, fill `VITE_SENTRY_DSN`, then `npm install && npm run build`.
   - Deploy: copy `dist/widget.js` to the box as usual.
   - This upgrades `@elevenlabs/react` to 1.16, which is needed for `onPing` and `onContextUsage`. Smoke-test a real voice session before you tell the client.
6. **Logs → Loki (Grafana Alloy).** Run on the box:
   ```bash
   sudo mkdir -p /etc/apt/keyrings && wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg >/dev/null
   echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
   sudo apt-get update && sudo apt-get install -y alloy
   sudo cp deploy/alloy/config.alloy /etc/alloy/config.alloy
   sudo usermod -aG systemd-journal alloy
   sudoedit /etc/default/alloy
   sudo systemctl enable --now alloy
   ```
   In `/etc/default/alloy`, add the three `GRAFANA_LOKI_*` lines. Alloy uses about 60–120 MB of RAM. Check the box's memory in the dashboard afterwards.
7. **Grafana data sources + dashboard.**
   - Loki and Tempo are pre-provisioned in Grafana Cloud.
   - Add PostgreSQL. Use the Supabase **session pooler** connection (Project Settings → Database), user `grafana_ro` (see below), SSL mode `require`.
   - Dashboards → Import → upload `deploy/grafana/teampop-dashboard.json`, then pick the Loki and Postgres data sources.

   Create the read-only Grafana role in Supabase:
   ```sql
   CREATE ROLE grafana_ro LOGIN PASSWORD '<generate one>';
   GRANT USAGE ON SCHEMA public TO grafana_ro;
   GRANT SELECT ON conversations, conversation_turns, search_latency, turn_latency,
                   session_feedback, v_conversation_timeline TO grafana_ro;
   ALTER ROLE grafana_ro SET statement_timeout = '15s';
   -- RLS is on for conversations/turns; allow this read-only role to read them:
   CREATE POLICY grafana_read ON conversations      FOR SELECT TO grafana_ro USING (true);
   CREATE POLICY grafana_read ON conversation_turns FOR SELECT TO grafana_ro USING (true);
   ```

## RCA playbook: "it was slow" or "it didn't work"

1. **Find the `conversation_id`:**
   - From an order: Shopify admin, order → Additional details → `TeamPop Conversation`.
   - From an error: the Sentry issue, under the `conversation_id` tag.
   - From a time and date: the dashboard's *Recent conversations* table, or ElevenLabs → Conversations.
2. **Paste it** into the dashboard's `conversation_id` variable. The *Timeline* and *Server logs* panels fill in.
3. **Read the timeline.** Find the turn that looks wrong and match it below:

| You see | Meaning | Next step |
|---|---|---|
| `llm_ttfb_ms` high (>1.5s) on turns, tool latency low | LLM is slow (model, prompt size, context) | Check *Context tokens*. Compare against another LLM on a branch. |
| Tool latency high, but `search` row `duration_ms` low | Time lost between ElevenLabs and our server (network/proxy) | Proxy log `proxy_total_ms` vs `search_ms`. Residency or region question. |
| `search` row slow; `extra.rerank_ms` dominates | Rerank on CPU | Check *CPU %* at that time. A high CPU reading is the evidence needed for a bigger box. |
| `extra.queue_wait_ms` high | Concurrent searches waiting for the embedding semaphore | Concurrency spike. Raise `SEARCH_EMBEDDING_CONCURRENCY` only if CPU allows. |
| `extra.rpc_ms` high | Supabase slow | Supabase dashboard → Query performance. |
| `widget` row: products fine but high `image_ms` | Images slow to download | Image size / CDN (Phase 1). |
| Cycle 0 `connect_ms` high | WebRTC/session setup | `network_rtt_ms`, shopper's network. ElevenLabs status page. |
| `is_error` true / `has_tool_error` | Tool failed or timed out | Sentry issue with the same `conversation_id`. The server log shows `search.timeout` or `proxy.error`. |
| Nothing looks slow, shopper still unhappy | Behaviour problem, not latency | Read `transcript_summary` and the evaluation results. Replay audio in the ElevenLabs dashboard. |

4. **Full trace:** Grafana → Explore → Tempo, search by `conversation_id`. This is the ElevenLabs-side span breakdown.

## Log events worth alerting on (Phase 4)

`search.timeout` · `proxy.error` · `conversation.store_failed` · `webhook.bad_signature` ·
`webhook.misconfigured` · `search.rerank_failed` · p95 of `search.completed.total_ms` > 1500 ·
`system.stats.swap_used_mb` rising · Sentry `Tool error:` issues.

## Ops: deploy, rollback, alerts

### Deploy (from the dev Mac)

```bash
deploy/deploy.sh --branch perf/phase0-observability --widget   # --widget builds + uploads widget.js
deploy/deploy.sh --dry-run                                     # print remote steps only
```

Needs a clean, pushed branch. `SSH_KEY` and `HOST` env vars override the defaults. The script
backs up the current commit, `widget.js` and both `.env` files to `~/backups/deploy-<ts>/` on the
box, fast-forwards the branch, runs `pip install` only if a requirements file changed, sets
`RELEASE=<sha>` in both `.env` files (Sentry release tag), restarts `tp-search` (waits up to 120s for
`/health?deep=1`), then `tp-onboard`, then checks the public `/health`. Any failure triggers an
automatic rollback and a non-zero exit.

### Rollback

```bash
deploy/rollback.sh              # latest backup: commit + widget.js + .env files
deploy/rollback.sh <commit>     # a specific commit (code only)
```

The box is left on a detached HEAD at that commit. The next deploy checks the branch out again.

### Alerts

Rules live in `deploy/grafana/alert-rules.yaml`, contact points and routing in
`deploy/grafana/contact-points.yaml`. Grafana Cloud has no file provisioning: create the rules in
the UI (Alerting, New alert rule, Loki data source, paste the `expr`) or POST each to
`/api/v1/provisioning/alert-rules`. Replace `${LOKI_UID}`, `${SLACK_WEBHOOK_URL}` and `${ALERT_EMAIL}`.

| Alert | Severity | Meaning | First step |
|---|---|---|---|
| Search timeout/failed/proxy error | critical | A shopper search failed in the last 5m | Loki for the event, then `system.stats` at that time |
| No search-service logs 10m | critical | Service down or Alloy not shipping | `systemctl status tp-search alloy`; roll back if just deployed |
| Search p95 > 1500ms | warning | Slow searches | Dashboard stage split: rerank means CPU, rpc means Supabase |
| Keep-warm slow / failed | warning | Models cold or search unreachable | CPU and recent restarts; curl deep health |
| Webhook misconfigured / bad signature | warning | Post-call webhook rejected | Check `ELEVENLABS_WEBHOOK_SECRET` |
| conversation.store_failed | warning | Call data not saved | Supabase status and key |
| Swap > 600MB / mem < 250MB | warning | OOM risk | `free -m`, top RSS processes |

### External uptime

`.github/workflows/uptime.yml` runs `testing/monitoring/uptime_check.py` every 5 minutes
(`/health` plus a fixed `POST /search`). Add the repo secret `SLACK_WEBHOOK_URL`. Run it locally with
`python testing/monitoring/uptime_check.py`.

## Business metrics (Phase 3)

Product/market intelligence derived from the same conversations. Dashboard: `deploy/grafana/teampop-business-dashboard.json` (uid `teampop-business`). Brand-facing delivery (reports/exports per merchant) is future work; today this is an internal view.

| Metric | Meaning | Source |
|---|---|---|
| Catalog coverage score | % of product-seeking conversations where `need_met` was true, per ISO week | `data_collection.need_met` |
| Top unmet needs | Normalised `unmet_need` values plus zero-result searches | `data_collection.unmet_need`, `search_latency` (`result_count = 0`) |
| Requested categories / products | Category mix; products most detailed or added | `product_category`, `conversation_turns.tool_calls` joined to `products` |
| Vocabulary gap | Shopper words (`shopper_terms`, search queries) found in no product name/description. Catalog is treated as one corpus across stores | `data_collection.shopper_terms`, `search_latency.query`, `products` |
| Conversion by category | Cart-add and `go_to_cart` rates per category (cart add counts only if the tool did not error) | `conversation_turns` |
| Drop-off turn / reason | Shopper turns before leaving without a cart add; `drop_off_reason` split | `user_turns`, `data_collection.drop_off_reason` |
| Price sensitivity | Budget-mentioned and price-objection rates, stated-budget buckets | `budget_mentioned`, `budget_amount_inr`, `price_objection` |
| Purchase lag / assisted revenue | Hours from conversation start to Shopify order (<1h, 1-24h, 1-7d, >7d); revenue of tagged orders | `assisted_orders` (Shopify webhook) |

Setup:
1. Run `create_business_metrics.sql` in the Supabase SQL editor (idempotent; needs role `grafana_ro`).
2. Configure the ElevenLabs agent data-collection ids exactly: `shopper_need`, `product_category`, `need_met`, `unmet_need`, `shopper_terms`, `budget_mentioned`, `budget_amount_inr`, `price_objection`, `drop_off_reason`. Missing ids just yield NULLs.
3. Set `SHOPIFY_WEBHOOK_SECRET` in `onboarding-service/.env` (the signing secret of the app that owns the webhook) and restart the service.
4. `SHOPIFY_SHOP=... SHOPIFY_ADMIN_TOKEN=... python testing/monitoring/register_shopify_order_webhook.py` (dry run), then add `--apply`. It skips if the subscription already exists.
5. Grafana: Dashboards, Import, upload the JSON, pick the Supabase datasource.

Orders are stored only when the cart carries a `TeamPop Conversation` (or `TeamPop Assisted = yes`) note attribute. Log events: `shopify.order_received`, `shopify.order_stored`, `shopify.bad_signature`.
